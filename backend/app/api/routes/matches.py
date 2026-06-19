"""Resume-scored job feed for the Dashboard.

GET /api/matches/feed reads the per-user discovered_jobs that already carry a
match_score (written by discovery + scoring) — it never re-scores on read. It
adds freshness filtering (24h / 7d) and an `is_early_applicant` flag so the UI
can surface "apply first" jobs. POST /api/matches/refresh kicks the scoring
pipeline and is defensive: it never 500s the page even if the ranking backend
(pgvector) isn't migrated yet.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.discovered_job import DiscoveredJob
from app.models.discovery_run import DiscoveryRun

logger = logging.getLogger(__name__)

router = APIRouter()

# Substrings that mean "scoring backend not ready" rather than a real failure.
_RANKING_PENDING_MARKERS = (
    "column", "undefinedcolumn", "pgvector", "embedding", "vector", "does not exist",
)


class MatchResponse(BaseModel):
    id: int
    job_url: str
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    source: str
    match_score: Optional[int] = None
    match_reason: Optional[str] = None
    match_explanation: Optional[str] = None
    missing_skills: list[str] = []
    salary_lpa: Optional[float] = None
    salary_raw: Optional[str] = None
    notice_period: Optional[str] = None
    work_arrangement: Optional[str] = None
    posted_at: Optional[datetime] = None
    discovered_at: datetime
    status: str
    contact_email: Optional[str] = None
    contact_linkedin: Optional[str] = None
    contact_name: Optional[str] = None
    is_early_applicant: bool = False

    model_config = ConfigDict(from_attributes=True)

    @field_validator("missing_skills", mode="before")
    @classmethod
    def _coerce_missing_skills(cls, value) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return []
            if s.startswith("["):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(v) for v in parsed if v]
                except (ValueError, TypeError):
                    pass
            return [part.strip() for part in s.split(",") if part.strip()]
        return []


def _is_early_applicant(posted_at: Optional[datetime], now: datetime) -> bool:
    return posted_at is not None and posted_at >= now - timedelta(days=1)


@router.get("/feed", response_model=list[MatchResponse])
async def get_feed(
    location: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    freshness: Optional[str] = Query("all", description="24h | 7d | all"),
    posted_within_days: Optional[int] = Query(None, description="alt freshness filter sent by the frontend"),
    sort: str = Query("score", description="score | recent"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    q = select(DiscoveredJob).where(
        DiscoveredJob.user_id == current_user.id,
        DiscoveredJob.match_score.is_not(None),
    )

    if location:
        q = q.where(func.lower(DiscoveredJob.location).contains(location.lower()))
    if min_score is not None:
        q = q.where(DiscoveredJob.match_score >= min_score)

    # Freshness: explicit posted_within_days wins; else the bucket.
    days = posted_within_days
    if days is None and freshness in ("24h", "7d"):
        days = 1 if freshness == "24h" else 7
    if days is not None:
        cutoff = now - timedelta(days=days)
        q = q.where(or_(DiscoveredJob.posted_at >= cutoff, DiscoveredJob.posted_at.is_(None)))

    if sort == "recent":
        q = q.order_by(DiscoveredJob.posted_at.desc().nulls_last(), DiscoveredJob.discovered_at.desc())
    else:
        q = q.order_by(DiscoveredJob.match_score.desc().nulls_last(), DiscoveredJob.discovered_at.desc())

    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()

    out: list[MatchResponse] = []
    for row in rows:
        model = MatchResponse.model_validate(row)
        model.is_early_applicant = _is_early_applicant(row.posted_at, now)
        out.append(model)
    return out


class DiscoveryRunResponse(BaseModel):
    id: int
    run_type: str
    queries: Optional[str] = None
    locations: Optional[str] = None
    jobs_found: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


@router.get("/history", response_model=list[DiscoveryRunResponse])
async def search_history(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(DiscoveryRun)
        .where(DiscoveryRun.user_id == current_user.id)
        .order_by(DiscoveryRun.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return rows


@router.post("/refresh")
async def refresh_feed(current_user: User = Depends(get_current_user)):
    from app.services.matching import refresh_user_feed

    try:
        count = await refresh_user_feed(current_user.id)
    except Exception as exc:  # noqa: BLE001 — feed must never 500 the page
        message = str(exc).lower()
        if any(marker in message for marker in _RANKING_PENDING_MARKERS):
            logger.warning("refresh_feed: ranking backend not ready for user %s: %s", current_user.id, repr(exc)[:160])
        else:
            logger.exception("refresh_feed failed for user %s", current_user.id)
        return {"refreshed": 0, "detail": "ranking backend pending"}

    return {"refreshed": count or 0}
