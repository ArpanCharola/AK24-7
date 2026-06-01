"""Application tracker — counts of GENUINE job-application confirmation mail
bucketed per IST day.

Two-signal classifier (mirrors the rigor of the label classifier):

  1. Gmail full-text search (``_build_query``) returns candidate mail. Gmail
     matches the quoted phrases against the full message BODY, so a hit means a
     strong confirmation phrase ("thank you for applying", …) is genuinely
     present — this is the PRIMARY signal. We TRUST the body search; we do NOT
     re-check the phrase against Gmail's truncated ``snippet`` (doing so once
     dropped genuine confirmations and made the count flicker).

  2. ``classify()`` requires a SECOND, corroborating signal that the mail is
     about a JOB, and rejects noise that slipped through the phrase search:
       - hard reject: personal-domain senders, job-board aggregators
       - reject: scam/fee asks; NON-JOB "applications" (loan/credit/rental/visa/
         membership/college/…); marketing/newsletter/webinar/course/survey/digest
         phrasing (the shared veto list from email_classifiers).
       - corroborate: a trusted ATS sender domain (Greenhouse/Lever/Workday/…) →
         counted outright (``count``); otherwise the confirmation is present but
         the sender is untrusted → AI double-check decides (``review``).

  3. The ``review`` band is sent to ``application_ai`` (OpenAI), whose verdict is
     CACHED per Gmail message id. That cache is what makes the count
     deterministic across refreshes: each ambiguous mail is judged once and the
     answer is remembered. If the AI is unavailable (or per-request budget is
     spent) we fall back to a deterministic rule: keep it only if job-context
     wording is present.

Days are bucketed in IST (Asia/Kolkata, UTC+05:30, no DST).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr, parsedate_to_datetime

from app.services import application_ai, cache
from app.services.gmail_service import fetch_messages_by_query
# Reuse the label classifier's sender-domain intelligence and veto list so the
# two features can't drift apart.
from app.services.email_classifiers import classify_domain, _VETO_PATTERNS, _AGGREGATOR_DOMAINS

logger = logging.getLogger(__name__)

# Asia/Kolkata is fixed UTC+05:30 with no DST — a constant timezone avoids
# needing zoneinfo / tzdata on Windows.
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

DEFAULT_DAYS = 30

# Walk the WHOLE match set (not a drifting top-500). When matches exceed the cap
# Gmail returns a different "top N" each call, which made the count bounce; a
# high cap + full pagination removes that truncation churn.
_FETCH_CAP = 2000

# Per-request budget of LIVE (uncached) AI calls. Cached verdicts are free and
# don't count. Bounds latency on a pathological inbox.
_AI_REVIEW_BUDGET = 50

# Confirmation anchors — Gmail searches these against full body text.
_APPLICATION_PHRASES = [
    "thank you for applying",
    "thanks for applying",
    "thank you for your application",
    "thank you for submitting",
    "we received your application",
    "we have received your application",
    "we've received your application",
    "received your application",
    "application received",
    "application has been received",
    "your application has been received",
    "your application was received",
    "your application has been submitted",
    "your application is under review",
    "received your resume",
    "received your cv",
    "application has been successfully submitted",
    # India-English acknowledgements (classify() still requires the second
    # job-context signal, so broadening the anchor set stays precision-safe).
    "your candidature",
    "received your candidature",
    "your profile has been received",
]


def _day_start_epoch(d: date) -> int:
    """Unix timestamp of 00:00 IST on calendar date ``d``."""
    return int(datetime(d.year, d.month, d.day, tzinfo=IST).timestamp())


def _build_query(since: date, today: date) -> str:
    """Gmail query for the IST window [since 00:00, tomorrow 00:00).

    Uses ABSOLUTE ``after:``/``before:`` epoch bounds rather than relative
    ``newer_than:Nd`` — the relative form moves between back-to-back calls, which
    was one source of the count drifting on refresh. Absolute bounds are stable.
    """
    after_epoch = _day_start_epoch(since)
    before_epoch = _day_start_epoch(today + timedelta(days=1))
    or_clause = " OR ".join(f'"{p}"' for p in _APPLICATION_PHRASES)
    return f"in:inbox after:{after_epoch} before:{before_epoch} ({or_clause})"


# ── Genuine-application filter ──────────────────────────────────────────────

_PERSONAL_DOMAINS = frozenset({
    "gmail.com", "googlemail.com",
    "yahoo.com", "yahoo.co.in", "yahoo.co.uk", "yahoo.ca", "ymail.com",
    "hotmail.com", "hotmail.co.uk", "outlook.com", "live.com", "msn.com",
    "aol.com", "icloud.com", "me.com", "mac.com",
    "protonmail.com", "proton.me", "tutanota.com", "tuta.io",
    "rediffmail.com", "zoho.com", "fastmail.com", "gmx.com", "mail.com",
})

# _AGGREGATOR_DOMAINS is imported from email_classifiers (single source of truth)
# so the two sender-domain lists can't drift apart.

_DISQUALIFY_PHRASES = (
    "jobs near you", "jobs for you", "new jobs", "matching jobs",
    "trending jobs", "popular jobs", "daily digest", "weekly digest",
    "job alert", "job recommendations", "job suggestions",
    "saved search", "opportunities for you",
    "complete your profile", "complete your application", "finish your application",
    "continue your application", "continue to apply", "resume your application",
    "draft application", "draft job application",
    "application update", "application status update", "status update",
    "% match",
)

_SCAM_PHRASES = (
    "bank account", "bank details", "wire transfer", "money transfer",
    "western union", "moneygram",
    "processing fee", "registration fee", "deposit required",
    "send money", "send us money",
    "social security number", "ssn number", "aadhaar number", "aadhar number",
    "click here to claim", "claim your reward",
)

_NON_JOB_APPLICATION = [
    re.compile(
        r"\b(?:loan|emi|upi|kyc|pan|aadhaar|aadhar|credit card|credit-card|mortgage|"
        r"rental|rent|lease|tenancy|"
        r"visa|passport|immigration|green card|membership|insurance|policy|"
        r"account opening|admission|college|university|school|scholarship|"
        r"grant|permit|license|licence|leave|reimbursement|warranty|refund)\b"
        r"[^\n]{0,40}\bapplication\b"
    ),
    re.compile(
        r"\bapplication\b[^\n]{0,40}"
        r"\b(?:loan|emi|upi|kyc|pan|aadhaar|aadhar|credit card|credit-card|mortgage|"
        r"rental|lease|tenancy|visa|"
        r"passport|immigration|green card|membership|insurance|policy|admission|"
        r"scholarship|grant|permit|license|licence)\b"
    ),
]

_JOB_CONTEXT = [
    re.compile(r"\b(?:position|role|vacancy|vacancies|requisition|opening|openings)\b"),
    re.compile(r"\b(?:job|career|careers|employment|hiring|recruit(?:ing|ment|er)?|talent acquisition)\b"),
    re.compile(r"\b(?:candidate|candidacy|candidature|applicant)\b"),
    re.compile(r"\bapplied (?:for|to)\b"),
    re.compile(r"\b(?:full[\s-]?time|part[\s-]?time|internship|\bintern\b|contract role)\b"),
    re.compile(r"\bthe (?:hiring|recruiting|talent) team\b"),
    # India compensation/offer wording that only appears in genuine job mail.
    re.compile(r"\b(?:ctc|lpa|notice period|in[\s-]?hand)\b"),
]


def _sender_domain(from_header: str) -> str:
    _, addr = parseaddr(from_header or "")
    addr = addr.lower()
    if "@" not in addr:
        return ""
    return addr.split("@", 1)[1].strip()


def _matches_aggregator(domain: str) -> bool:
    if not domain:
        return False
    for k in _AGGREGATOR_DOMAINS:
        if domain == k or domain.endswith("." + k):
            return True
    return False


def _any_re(patterns: list[re.Pattern], text: str) -> bool:
    return any(p.search(text) for p in patterns)


COUNT_ATS = "counted_ats"
COUNT_AI = "counted_ai"
COUNT_CONTEXT = "counted_context"
REJECT_PERSONAL_DOMAIN = "personal_domain"
REJECT_AGGREGATOR_DOMAIN = "aggregator_domain"
REJECT_VETO = "veto"
REJECT_NON_JOB = "non_job_application"
REJECT_SCAM = "scam_phrase"
REJECT_AI = "ai_rejected"
REJECT_NO_CONTEXT = "no_context"

REJECTION_CATEGORIES = (
    REJECT_PERSONAL_DOMAIN,
    REJECT_AGGREGATOR_DOMAIN,
    REJECT_VETO,
    REJECT_NON_JOB,
    REJECT_SCAM,
    REJECT_AI,
    REJECT_NO_CONTEXT,
)


def classify(subject: str, snippet: str, from_email: str) -> dict:
    """Rules-only verdict for one candidate (no AI). Returns:

        {"bucket": "reject" | "count" | "review",
         "category": <one of the *_ constants, or "review">,
         "has_job_context": bool,
         "is_ats": bool}

    Candidates reach here only after Gmail's body search, so a confirmation
    phrase is guaranteed present — this function's job is the SECOND signal:
    confirm the mail is about a job and isn't noise. Never raises.
    """
    haystack = f"{(subject or '').lower()}\n{(snippet or '').lower()}"
    domain = _sender_domain(from_email or "")

    if domain in _PERSONAL_DOMAINS:
        return {"bucket": "reject", "category": REJECT_PERSONAL_DOMAIN,
                "has_job_context": False, "is_ats": False}

    if _matches_aggregator(domain):
        return {"bucket": "reject", "category": REJECT_AGGREGATOR_DOMAIN,
                "has_job_context": False, "is_ats": False}

    if any(p in haystack for p in _SCAM_PHRASES):
        return {"bucket": "reject", "category": REJECT_SCAM,
                "has_job_context": False, "is_ats": False}

    if _any_re(_NON_JOB_APPLICATION, haystack):
        return {"bucket": "reject", "category": REJECT_NON_JOB,
                "has_job_context": False, "is_ats": False}

    if any(p in haystack for p in _DISQUALIFY_PHRASES) or _any_re(_VETO_PATTERNS, haystack):
        return {"bucket": "reject", "category": REJECT_VETO,
                "has_job_context": False, "is_ats": False}

    is_ats = classify_domain(domain) == "ats"
    has_ctx = _any_re(_JOB_CONTEXT, haystack)

    if is_ats:
        return {"bucket": "count", "category": COUNT_ATS,
                "has_job_context": has_ctx, "is_ats": True}

    return {"bucket": "review", "category": "review",
            "has_job_context": has_ctx, "is_ats": False}


async def _decide(msg: dict, budget: dict) -> tuple[bool, str, bool]:
    """Final per-message decision: rules + (for review band) AI double-check.

    Returns (counted, category, ai_used). ``budget`` is a mutable
    ``{"remaining": int}`` of live AI calls left for this request; cached
    verdicts don't consume it. Never raises.
    """
    subject = msg.get("subject") or ""
    snippet = msg.get("snippet") or ""
    sender = msg.get("from_email") or ""
    msg_id = msg.get("id") or ""

    c = classify(subject, snippet, sender)
    if c["bucket"] == "reject":
        return False, c["category"], False
    if c["bucket"] == "count":
        return True, c["category"], False

    # review band — let the AI decide, preferring a cached verdict (free).
    verdict: bool | None = None
    cached = await cache.get_application_ai_cache(msg_id) if msg_id else None
    if cached is not None:
        verdict = bool(cached.get("application"))
    elif budget["remaining"] > 0:
        verdict = await application_ai.verify(msg_id, subject, snippet, sender)
        if verdict is not None:
            budget["remaining"] -= 1

    if verdict is True:
        return True, COUNT_AI, True
    if verdict is False:
        return False, REJECT_AI, True

    # AI unavailable or over budget → deterministic fallback on job-context.
    if c["has_job_context"]:
        return True, COUNT_CONTEXT, False
    return False, REJECT_NO_CONTEXT, False


def _ist_date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST).date()


async def _genuine_deduped(
    access_token: str, days: int, since: date, today: date
) -> tuple[list[tuple[date, dict]], dict]:
    """Fetch candidate mail, classify (rules + AI), dedupe by Gmail thread.

    Shared by the count endpoint and the auto-tracker so both agree on exactly
    what counts. Returns ``(deduped, counters)`` where ``deduped`` is a list of
    ``(ist_date, message)`` (oldest message per thread wins — the moment the
    user actually applied). Never raises.
    """
    query = _build_query(since, today)
    raw_count = in_window_count = deduped_count = 0
    counted_confident = counted_ai = counted_context = ai_reviewed = 0
    rejection_breakdown: dict[str, int] = {cat: 0 for cat in REJECTION_CATEGORIES}
    budget = {"remaining": _AI_REVIEW_BUDGET}

    try:
        msgs = await fetch_messages_by_query(access_token, query, max_results=_FETCH_CAP)
        raw_count = len(msgs)
    except Exception as e:
        logger.warning("[apptracker] fetch failed: %s", e)
        msgs = []

    # Deterministic order so AI budget always falls on the same messages,
    # keeping the count stable while the cache warms.
    msgs.sort(key=lambda m: m.get("id") or "")

    genuine: list[tuple[date, dict]] = []
    for msg in msgs:
        d = _ist_date(msg.get("date", ""))
        if d is None or d < since or d > today:
            continue
        in_window_count += 1

        counted, category, ai_used = await _decide(msg, budget)
        if ai_used:
            ai_reviewed += 1
        if not counted:
            if category in rejection_breakdown:
                rejection_breakdown[category] += 1
            continue
        if category == COUNT_ATS:
            counted_confident += 1
        elif category == COUNT_AI:
            counted_ai += 1
        elif category == COUNT_CONTEXT:
            counted_context += 1
        genuine.append((d, msg))

    # Dedupe by thread_id (one conversation = one application). Sort ascending
    # so the oldest message per thread is the one we keep.
    genuine.sort(key=lambda dm: dm[1].get("date", ""))
    seen_threads: set[str] = set()
    deduped: list[tuple[date, dict]] = []
    for d, msg in genuine:
        tid = msg.get("thread_id") or ""
        key = tid or msg.get("id") or ""
        if key and key in seen_threads:
            deduped_count += 1
            continue
        if key:
            seen_threads.add(key)
        deduped.append((d, msg))

    counters = {
        "query": query,
        "raw_count": raw_count,
        "in_window_count": in_window_count,
        "deduped_count": deduped_count,
        "counted_confident": counted_confident,
        "counted_ai": counted_ai,
        "counted_context": counted_context,
        "ai_reviewed": ai_reviewed,
        "rejection_breakdown": rejection_breakdown,
    }
    return deduped, counters


async def genuine_deduped(access_token: str, days: int = DEFAULT_DAYS) -> list[dict]:
    """The deduped genuine application messages for the last `days` IST days.

    Each item is the raw Gmail message dict (id, thread_id, subject, snippet,
    from_email, date). Exposed for the auto-tracker. Never raises.
    """
    if days < 1:
        days = 1
    if days > 90:
        days = 90
    today = datetime.now(IST).date()
    since = today - timedelta(days=days - 1)
    deduped, _ = await _genuine_deduped(access_token, days, since, today)
    return [msg for _, msg in deduped]


async def get_application_tracker(access_token: str, days: int = DEFAULT_DAYS, debug: bool = False) -> dict:
    """Daily-bucketed application summary for the last `days` IST days.

    Standard output:
      {
        "today": { "date", "count", "messages": [...] },
        "previous_days": [ { "date", "weekday", "count", "messages" }, ... ],
        "since_date": "YYYY-MM-DD",
        "total": int,
      }

    With ``debug=True``, adds counters at each pipeline stage. Today is always
    present even when count is 0; previous days only listed when count > 0.
    Never raises — gracefully returns an empty tracker if Gmail fails.
    """
    if days < 1: days = 1
    if days > 90: days = 90

    today = datetime.now(IST).date()
    since = today - timedelta(days=days - 1)

    deduped, counters = await _genuine_deduped(access_token, days, since, today)

    buckets: dict[date, list[dict]] = {}
    for d, msg in deduped:
        buckets.setdefault(d, []).append(msg)

    kept_count = sum(len(v) for v in buckets.values())
    rejected_total = sum(counters["rejection_breakdown"].values())
    if rejected_total or kept_count:
        # Counts only — never log subjects/senders/snippets. PII discipline.
        logger.info(
            "[apptracker] kept %d (ats %d / ai %d / context %d) / rejected %d / ai_reviewed %d / deduped %d",
            kept_count,
            counters["counted_confident"],
            counters["counted_ai"],
            counters["counted_context"],
            rejected_total,
            counters["ai_reviewed"],
            counters["deduped_count"],
        )

    for d in buckets:
        buckets[d].sort(key=lambda m: m.get("date", ""), reverse=True)

    today_messages = buckets.get(today, [])
    previous_dates = sorted([d for d in buckets.keys() if d != today], reverse=True)

    previous_days = [
        {
            "date": d.isoformat(),
            "weekday": d.strftime("%a"),
            "count": len(buckets[d]),
            "messages": buckets[d],
        }
        for d in previous_dates
    ]

    result = {
        "today": {
            "date": today.isoformat(),
            "count": len(today_messages),
            "messages": today_messages,
        },
        "previous_days": previous_days,
        "since_date": since.isoformat(),
        "total": kept_count,
    }

    if debug:
        result["debug"] = {
            "query": counters["query"],
            "raw_count": counters["raw_count"],
            "in_window_count": counters["in_window_count"],
            "counted_confident": counters["counted_confident"],
            "counted_ai": counters["counted_ai"],
            "counted_context": counters["counted_context"],
            "ai_reviewed": counters["ai_reviewed"],
            "deduped_count": counters["deduped_count"],
            "kept_count": kept_count,
            "rejection_breakdown": counters["rejection_breakdown"],
            "window": {"since": since.isoformat(), "today": today.isoformat()},
        }

    return result
