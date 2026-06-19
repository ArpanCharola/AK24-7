"""Daily-bucketed application tracker — counts genuine application-confirmation
emails in IST day buckets. The companion ``/auto-track`` endpoint turns each
new detected confirmation into a Job Tracker card (idempotent on Gmail thread).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.saved_application import SavedApplication
from app.models.user import User
from app.services import application_extract, cache, gmail_client
from app.services.application_tracker import (
    DEFAULT_DAYS,
    genuine_deduped,
    get_application_tracker,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _applied_at(raw: str) -> datetime:
    try:
        dt = parsedate_to_datetime(raw)
        if dt is None:
            raise ValueError
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _thread_url(thread_id: str) -> str:
    return f"https://mail.google.com/mail/u/0/#inbox/{thread_id}"


async def _require_token(current_user: User, db: AsyncSession) -> str:
    if not current_user.gmail_refresh_token:
        raise HTTPException(status_code=409, detail="No Gmail account connected")
    token = await gmail_client.get_valid_access_token(db, current_user)
    if not token:
        raise HTTPException(status_code=502, detail="Gmail token invalid — please reconnect")
    return token


def _empty_tracker() -> dict:
    """Zeroed tracker payload — returned by the read-only view when Gmail isn't
    usable, so the page shows '0 applications' instead of nagging to connect."""
    from datetime import timedelta
    ist_today = (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).date().isoformat()
    return {
        "today": {"date": ist_today, "count": 0, "messages": []},
        "previous_days": [],
        "since_date": ist_today,
        "total": 0,
    }


@router.get(
    "/tracker",
    summary="Count how many jobs you applied to",
    description=(
        "Looks through your Gmail for confirmation emails from companies you've "
        "applied to and counts them by day (in Indian Standard Time). Returns "
        "today's count, previous days, and a total so you can see your "
        "application volume over time."
    ),
)
async def application_tracker(
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=90, description="How many days to look back (1–90)."),
    debug: bool = Query(default=False, description="Set true to include behind-the-scenes counters."),
    fresh: bool = Query(default=False, description="Set true to skip the 60-second cache and recompute from Gmail."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        token = await _require_token(current_user, db)
    except HTTPException as exc:
        # Read-only view: never nag to connect Gmail — just show zeros.
        if exc.status_code in (409, 502):
            return _empty_tracker()
        raise

    use_cache = not fresh and not debug
    if use_cache:
        cached = await cache.get_tracker_cache(current_user.id, days)
        if cached is not None:
            return cached

    result = await get_application_tracker(token, days=days, debug=debug)

    if use_cache:
        await cache.set_tracker_cache(current_user.id, days, result, ttl=60)

    return result


@router.post(
    "/auto-track",
    summary="Auto-add detected applications to your Job Tracker",
    description=(
        "Looks through the job applications detected in your Gmail and adds any "
        "new ones to your Job Tracker automatically — pulling out the company "
        "and role for you. Idempotent on Gmail thread id, so the same email is "
        "never added twice."
    ),
)
async def auto_track(
    days: int = Query(default=DEFAULT_DAYS, ge=1, le=90, description="How many days of mail to consider (1–90)."),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token = await _require_token(current_user, db)
    messages = await genuine_deduped(token, days=days)

    # One query for every thread this user already tracks — so we never create a
    # duplicate card for a re-detected application.
    tracked_rows = (await db.execute(
        select(SavedApplication.source_thread_id).where(
            SavedApplication.user_id == current_user.id,
            SavedApplication.source_thread_id.isnot(None),
        )
    )).all()
    tracked: set[str] = {tid for (tid,) in tracked_rows if tid}

    created = 0
    already = 0
    for msg in messages:
        thread_id = msg.get("thread_id") or msg.get("id") or ""
        if not thread_id or thread_id in tracked:
            already += 1
            continue
        tracked.add(thread_id)  # intra-batch dedup

        fields = await application_extract.extract(
            msg.get("id") or "",
            msg.get("subject") or "",
            msg.get("snippet") or "",
            msg.get("from_email") or "",
        )
        db.add(SavedApplication(
            user_id=current_user.id,
            company=fields["company"] or "Unknown company",
            role=fields["role"] or "Role not specified",
            applied_at=_applied_at(msg.get("date", "")),
            mail_url=_thread_url(thread_id),
            status="applied",
            source_thread_id=thread_id,
        ))
        created += 1

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("auto-track DB error")
        raise HTTPException(status_code=500, detail=str(exc))

    # Counts only — never log company/role/subjects. PII discipline.
    logger.info("[auto-track] created %d / already %d / detected %d", created, already, len(messages))
    return {"created": created, "already_tracked": already, "detected": len(messages)}
