"""Scan a connected user's Gmail and advance their JobApplications' lifecycle.

Pipeline: get a valid token → narrow Gmail search → classify each message
(confirmed/assessment/interview) → match it to one of the user's applications
by company/domain within a time window → set the application's `stage`
(monotonic: never downgrade). PII discipline: log counts/categories only.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime

from sqlalchemy import select

from app.services.email_classifiers import build_scan_query, decide_email_kind, is_repliable_human
from app.services.gmail_service import fetch_messages_by_query
from app.services.gmail_client import get_valid_access_token

logger = logging.getLogger(__name__)

SCAN_DAYS = 30
# Only attribute mail to applications created in this look-back (bounds matching).
APP_LOOKBACK_DAYS = 120
# Non-terminal stages are monotonic (a later stage wins, never downgrades).
# Terminal outcomes (offer/rejected) override any non-terminal stage and are final.
_NONTERMINAL_RANK = {None: 0, "confirmed": 1, "assessment": 2, "interview": 3}
_TERMINAL = {"offer", "rejected"}


def _should_update_stage(current: str | None, new: str) -> bool:
    if current in _TERMINAL:
        return False  # a final outcome is never overwritten
    if new in _TERMINAL:
        return True   # a terminal outcome overrides any non-terminal stage
    return _NONTERMINAL_RANK.get(new, 0) > _NONTERMINAL_RANK.get(current, 0)

_SUFFIXES = re.compile(r"\b(inc|llc|ltd|limited|corp|corporation|co|gmbh|technologies|technology|labs|software|solutions)\b")


def _norm(text: str) -> str:
    """Lowercase alphanumeric-only key for fuzzy company/domain comparison."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _company_tokens(company: str) -> list[str]:
    """Significant tokens of a company name (suffixes stripped), for matching."""
    cleaned = _SUFFIXES.sub(" ", (company or "").lower())
    toks = [t for t in re.split(r"[^a-z0-9]+", cleaned) if len(t) >= 4]
    full = _norm(company)
    if full and full not in toks:
        toks.append(full)
    return toks


def _msg_datetime(raw: str):
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _host_root(url_or_domain: str) -> str:
    """Registrable-ish root: last two dotted labels of a host (brex.com, greenhouse.io)."""
    m = re.search(r"https?://([^/]+)", url_or_domain or "")
    host = (m.group(1) if m else url_or_domain or "").lower()
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def _match_application(msg: dict, apps: list) -> object | None:
    """Attribute a message to one JobApplication by company/domain + time window.
    Conservative: requires a company-token or domain overlap, and the message
    must post-date the application. On ties, the most recently created match wins."""
    _, sender_addr = parseaddr(msg.get("from_email") or "")
    sender_domain = sender_addr.split("@", 1)[1].lower() if "@" in sender_addr else ""
    sender_root = _host_root(sender_domain)
    haystack = _norm(f"{sender_domain} {msg.get('from_email','')} {msg.get('subject','')}")

    msg_dt = _msg_datetime(msg.get("date", ""))
    candidates = []
    for app in apps:
        if not app.company:
            continue
        # time window: confirmation/assessment/interview arrive after applying
        if msg_dt and app.created_at:
            created = app.created_at if app.created_at.tzinfo else app.created_at.replace(tzinfo=timezone.utc)
            if msg_dt < created - timedelta(days=1):
                continue
        company_hit = any(tok in haystack for tok in _company_tokens(app.company))
        domain_hit = bool(sender_root) and _host_root(app.job_url) == sender_root
        if company_hit or domain_hit:
            candidates.append(app)

    if not candidates:
        return None
    # Prefer the most recently created matching application.
    candidates.sort(key=lambda a: a.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return candidates[0]


async def scan_user(db, user, *, force_label: bool = False) -> dict:
    """Scan one connected user's inbox and update matched applications' stages.
    Never raises — returns a counts-only summary.

    `force_label=True` (the Labels page "Sync now") applies AI Apply labels even
    when the background auto-label toggle is off and even when the user has no
    tracked applications — labeling mail is the whole point of that action. The
    background scan leaves it False so labeling still follows the user's toggle.
    """
    from app.models.job_application import JobApplication

    summary = {"connected": False, "scanned": 0, "classified": 0, "matched": 0, "updated": 0,
               "labeled": 0, "ai_reviewed": 0,
               "by_kind": {"confirmed": 0, "assessment": 0, "interview": 0, "offer": 0, "rejected": 0},
               "labeled_by_kind": {"confirmed": 0, "assessment": 0, "interview": 0, "offer": 0, "rejected": 0}}

    token = await get_valid_access_token(db, user)
    if not token:
        return summary
    summary["connected"] = True

    try:
        msgs = await fetch_messages_by_query(token, build_scan_query(SCAN_DAYS), max_results=200)
    except Exception as exc:
        logger.warning("Gmail scan fetch failed for user %s: %s", user.id, exc)
        return summary
    summary["scanned"] = len(msgs)

    cutoff = datetime.now(timezone.utc) - timedelta(days=APP_LOOKBACK_DAYS)
    apps = (await db.execute(
        select(JobApplication)
        .where(JobApplication.user_id == user.id)
        .where(JobApplication.created_at >= cutoff)
    )).scalars().all()

    # Whether to apply AI Apply labels this scan. The Labels page forces it; the
    # background scan follows the user's toggle. Either way it needs modify scope.
    from app.services import gmail_client
    do_label = (force_label or bool(getattr(user, "auto_label_enabled", False))) \
        and gmail_client.scopes_can_label(user.gmail_scopes)

    # Nothing to do: no applications to advance AND not labeling. Skip the (costly,
    # AI-touching) per-message loop, just stamp the sync time.
    if not apps and not do_label:
        user.gmail_last_synced_at = datetime.now(timezone.utc)
        await db.commit()
        return summary

    # Auto-label setup (best-effort; failure disables labeling for this scan only).
    label_ids: dict[str, str] = {}
    if do_label:
        try:
            from app.services.gmail_labels import ensure_labels
            label_ids = await ensure_labels(token)
        except Exception as exc:
            logger.warning("ensure_labels failed for user %s (labeling off this scan): %s", user.id, exc)
            do_label = False

    updated = 0
    human_best: dict[int, datetime] = {}  # app_id -> newest human-email dt seen this scan
    for msg in msgs:
        kind, ai_used = await decide_email_kind(msg)
        if ai_used:
            summary["ai_reviewed"] += 1
        if not kind:
            continue
        summary["classified"] += 1
        summary["by_kind"][kind] = summary["by_kind"].get(kind, 0) + 1

        # Label the inbox message (every classified kind, not only matched ones).
        # Skip mail that already carries this label so "labeled" counts only what
        # is genuinely new — a repeat sync of unchanged mail reports "Up to date".
        if do_label and label_ids.get(kind) and msg.get("id"):
            target = label_ids[kind]
            if target not in (msg.get("label_ids") or []):
                try:
                    from app.services.gmail_labels import apply_label
                    await apply_label(token, msg["id"], target)
                    summary["labeled"] += 1
                    summary["labeled_by_kind"][kind] = summary["labeled_by_kind"].get(kind, 0) + 1
                except Exception as exc:
                    logger.debug("apply_label failed for msg %s: %s", msg.get("id"), exc)

        app = _match_application(msg, apps)
        if not app:
            continue
        summary["matched"] += 1
        if _should_update_stage(app.stage, kind):
            app.stage = kind
            app.stage_updated_at = datetime.now(timezone.utc)
            updated += 1

        # Capture the latest repliable human thread for autonomous follow-ups.
        # No-reply confirmations fail is_repliable_human, so they never enable a send.
        if kind in ("assessment", "interview") and is_repliable_human(msg.get("from_email", "")):
            dt = _msg_datetime(msg.get("date", "")) or datetime.min.replace(tzinfo=timezone.utc)
            if dt >= human_best.get(app.id, datetime.min.replace(tzinfo=timezone.utc)):
                human_best[app.id] = dt
                _, addr = parseaddr(msg.get("from_email", ""))
                app.last_human_email_from = addr or msg.get("from_email", "")
                app.last_human_email_thread_id = msg.get("thread_id")
                app.last_human_email_msgid = msg.get("message_id")

    user.gmail_last_synced_at = datetime.now(timezone.utc)
    await db.commit()
    summary["updated"] = updated
    logger.info(
        "Gmail scan user %s: scanned=%d classified=%d matched=%d updated=%d labeled=%d ai_reviewed=%d",
        user.id, summary["scanned"], summary["classified"], summary["matched"], updated, summary["labeled"], summary["ai_reviewed"],
    )
    return summary
