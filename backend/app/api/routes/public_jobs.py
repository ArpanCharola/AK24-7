"""Public (unauthenticated) job search + shared JobPool.

Flow:
  1. Anyone (no login) GETs /api/public/job-search?role=...&location=...&source=...
     → runs SerpAPI Google Jobs, filters to "applyable" ATS hosts only,
       upserts into JobPool, returns results.
  2. Anyone GETs /api/public/jobs?role=...&source=...
     → paginated browse of the existing pool, no SerpAPI call.
  3. Logged-in user POSTs /api/job-pool/import-to-profile/{profile_id}
     → scores pool jobs against the profile and inserts matches into
       the user's DiscoveredJobs.

Constraints honored (re-using existing helpers from job_discovery_agent):
  - India-only locations
  - No internships / part-time / staffing / gov
  - Work-arrangement detection
  - Role synonym expansion via _matches_criteria

Rate limit: in-memory per-IP, 10 req/min on the live search endpoint. The
browse endpoint is much cheaper (DB only) so it gets a looser 60 req/min.
For multi-worker scaling, swap in slowapi + Redis backend.
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.discovered_job import DiscoveredJob
from app.models.job_pool import JobPool
from app.models.job_search_profile import JobSearchProfile
from app.models.user import User
from app.services.experience_filters import (
    FRESHER_TERMS,
    ROLE_QUERY_ALIASES,
    is_experience_match,
    normalize_experience,
)
from app.services.warehouse_views import public_job_quality_score

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Rate limiter (Redis-backed, falls back to in-memory if Redis is down) ────
#
# Multi-worker safe: a single shared counter per (bucket, ip) lives in Redis,
# implemented with a fixed-window INCR + EXPIRE. Approximate (window boundary
# burst possible) but cheap and correct enough for an abuse gate.
#
# Falls back to a per-process in-memory deque if Redis isn't reachable so
# this endpoint never goes from "rate-limited" → "completely unavailable".

_RATE_WINDOWS: dict[str, dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis | None:
    global _redis_client
    if _redis_client is None:
        try:
            _redis_client = aioredis.from_url(
                settings.REDIS_URL, encoding="utf-8", decode_responses=True
            )
        except Exception as exc:
            logger.warning("Rate limiter: cannot init Redis (%s) — falling back to in-memory", exc)
            _redis_client = None  # leave as None so we hit the fallback path
    return _redis_client


def _inmem_rate_limit(client_ip: str, bucket: str, max_calls: int, window_sec: int) -> None:
    now = time.monotonic()
    q = _RATE_WINDOWS[bucket][client_ip]
    while q and q[0] < now - window_sec:
        q.popleft()
    if len(q) >= max_calls:
        retry_after = int(window_sec - (now - q[0])) + 1
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded — try again in {retry_after}s",
            headers={"Retry-After": str(retry_after)},
        )
    q.append(now)


async def _rate_limit(client_ip: str, bucket: str, max_calls: int, window_sec: int) -> None:
    """Atomic fixed-window counter in Redis, fallback to in-memory on Redis errors."""
    r = _get_redis()
    if r is None:
        _inmem_rate_limit(client_ip, bucket, max_calls, window_sec)
        return
    try:
        # Fixed-window key changes every `window_sec` seconds.
        window_id = int(time.time()) // window_sec
        key = f"rl:{bucket}:{client_ip}:{window_id}"
        # Pipeline so INCR + EXPIRE are one round-trip
        async with r.pipeline(transaction=True) as pipe:
            pipe.incr(key, 1)
            pipe.expire(key, window_sec + 5)  # small grace so we don't EXPIRE-during-check
            count, _ = await pipe.execute()
    except Exception as exc:
        logger.debug("Rate limiter: Redis op failed (%s) — falling back to in-memory", exc)
        _inmem_rate_limit(client_ip, bucket, max_calls, window_sec)
        return
    if int(count) > max_calls:
        # Approximate retry-after: time until current window ends
        retry_after = window_sec - (int(time.time()) % window_sec)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded — try again in {retry_after}s",
            headers={"Retry-After": str(max(retry_after, 1))},
        )


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Source classification ────────────────────────────────────────────────────
# Google Jobs aggregates from many sources. We classify each URL into one of:
#   - ATS native (greenhouse, lever, ashby, workday, icims, ...)
#       → directly applyable by our SmartApplyAgent
#   - Tier-2 portal (amazon, netflix, microsoft, google, apple)
#       → applyable via per-company adapters
#   - Aggregator (linkedin, indeed, glassdoor, ziprecruiter, monster, dice)
#       → not directly applyable, but listable; user can click through
#   - Company-direct (any non-aggregator URL on the company's own domain)
#       → tagged "company_site"; usually applyable manually
#
# This is permissive on purpose — SerpAPI Google Jobs rarely returns direct
# ATS URLs. Filtering hard would yield 0 results. The UI exposes source as a
# filter, so users who only want ATS rows can opt in via the dropdown.

_HOST_PATTERNS: tuple[tuple[str, str], ...] = (
    # ATS-native (most preferred)
    ("greenhouse.io",         "greenhouse"),
    ("lever.co",              "lever"),
    ("ashbyhq.com",           "ashby"),
    ("myworkdayjobs.com",     "workday"),
    ("icims.com",             "icims"),
    ("smartrecruiters.com",   "smartrecruiters"),
    ("bamboohr.com",          "bamboohr"),
    # Tier-2 proprietary portals
    ("amazon.jobs",           "amazon"),
    ("jobs.netflix.com",      "netflix"),
    ("explore.jobs.netflix.net", "netflix"),
    ("jobs.microsoft.com",    "microsoft"),
    ("careers.microsoft.com", "microsoft"),
    ("jobs.apple.com",        "apple"),
    ("careers.google.com",    "google"),
    ("metacareers.com",       "meta"),
    # Aggregators / job boards (clickable, not directly applyable by agent)
    ("linkedin.com",          "linkedin"),
    ("indeed.com",            "indeed"),
    ("glassdoor.com",         "glassdoor"),
    ("ziprecruiter.com",      "ziprecruiter"),
    ("monster.com",           "monster"),
    ("dice.com",              "dice"),
    ("themuse.com",           "themuse"),
)

# Sources we never want — pure spam/scrape aggregators with no value-add.
_SPAM_HOSTS: tuple[str, ...] = (
    "bebee.com", "trabajo.org", "lensa.com", "sonicjobs.com",
    "jobilize.com", "hirethebetter.com", "vacancies.cu-fc.com",
    "talent.com",
)

# Sources we consider "directly applyable" — preferred when multiple
# apply_options exist on a single Google Jobs result.
_PREFERRED_SOURCES = frozenset({
    "greenhouse", "lever", "ashby", "workday", "icims", "smartrecruiters",
    "bamboohr", "amazon", "netflix", "microsoft", "apple", "google", "meta",
})


def _classify_source(job_url: str) -> str | None:
    """Return canonical source name, or 'company_site' for non-aggregator
    company URLs, or None for known spam hosts / invalid URLs."""
    try:
        host = urlsplit(job_url).netloc.lower()
    except Exception:
        return None
    if not host:
        return None
    if any(spam in host for spam in _SPAM_HOSTS):
        return None
    for needle, source in _HOST_PATTERNS:
        if needle in host:
            return source
    # Unrecognized host but not spam → assume it's the company's own careers
    # page (e.g. careers.cisco.com, jobsus.deloitte.com, spectraforce.com).
    return "company_site"


def _best_apply_url(apply_options: list[dict]) -> tuple[str, str] | None:
    """Walk all apply_options and return (url, source) for the most-direct
    one. Preference order: ATS/portal > company_site > aggregator. Returns
    None if no usable option exists."""
    if not apply_options:
        return None
    candidates: list[tuple[int, str, str]] = []  # (rank, url, source)
    for opt in apply_options:
        link = (opt.get("link") or "").strip()
        if not link or "google.com" in link:
            continue
        src = _classify_source(link)
        if src is None:
            continue
        if src in _PREFERRED_SOURCES:
            rank = 0
        elif src == "company_site":
            rank = 1
        else:
            rank = 2
        candidates.append((rank, link, src))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[0][1], candidates[0][2]


# ── Schemas ──────────────────────────────────────────────────────────────────

class PublicJobResponse(BaseModel):
    id: int
    job_url: str
    title: Optional[str]
    company: Optional[str]
    location: Optional[str]
    source: str
    work_arrangement: Optional[str]
    posted_at: Optional[datetime]
    first_seen_at: datetime
    last_seen_at: datetime
    search_query: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("title", "company", "location", mode="before")
    @classmethod
    def _repair_mojibake(cls, value):
        if not isinstance(value, str):
            return value
        if not any(marker in value for marker in ("â", "Ã", "Â")):
            return value
        try:
            return value.encode("latin1").decode("utf-8")
        except UnicodeError:
            return value


class PublicSearchResponse(BaseModel):
    query: str
    location: str
    source_filter: Optional[str]
    experience_filter: Optional[str] = None
    work_arrangement_filter: Optional[str] = None
    fetched: int           # raw rows SerpAPI returned (before our filters)
    matched: int           # rows kept after USA / source / exclusion filters
    saved: int             # rows actually upserted into JobPool
    jobs: list[PublicJobResponse]


async def _matching_pool_rows(
    db: AsyncSession,
    *,
    role: str | None,
    location: str | None,
    experience_filter: str | None,
    work_filter: str | None,
    source: str | None = None,
    posted_within_days: int | None = 7,
    limit: int = 100,
    offset: int = 0,
) -> list[JobPool]:
    """Fast DB-backed matches with synonym-aware role filtering."""
    from app.agents.job_discovery_agent import (
        _is_excluded_job,
        _is_india_strict,
        _matches_criteria,
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=posted_within_days or 7)
    q = select(JobPool).where(JobPool.last_seen_at >= cutoff)
    if source:
        q = q.where(JobPool.source == source)
    if work_filter:
        q = q.where(func.lower(JobPool.work_arrangement) == work_filter)
    if location and location.strip().lower() not in {"india", "all india", "pan india"}:
        loc = location.strip().lower()
        q = q.where(or_(
            func.lower(JobPool.location).contains(loc),
            func.lower(JobPool.location).contains("remote india"),
            func.lower(JobPool.location).contains("pan india"),
            func.lower(JobPool.location).contains("pan-india"),
            func.lower(JobPool.location).contains("anywhere in india"),
        ))

    fetch_limit = min(1500, max(limit * 8, limit + offset + 200))
    rows = (await db.execute(
        q.order_by(JobPool.last_seen_at.desc()).limit(fetch_limit)
    )).scalars().all()

    profile_dict = {"target_roles": role or ""}
    out: list[JobPool] = []
    seen: set[str] = set()
    seen_content: set[tuple[str, str]] = set()
    for row in rows:
        key = row.job_url or f"{row.company}-{row.title}-{row.location}"
        if key in seen:
            continue
        seen.add(key)
        content_key = _content_key(row.company, row.title)
        if content_key and content_key in seen_content:
            continue
        if content_key:
            seen_content.add(content_key)
        if role and not _matches_criteria(row.title or "", profile_dict):
            continue
        if not _is_india_strict(row.location):
            continue
        if _is_excluded_job(row.title or "", row.company or "", row.job_url, row.job_description or ""):
            continue
        if not is_experience_match(row.title, row.job_description, experience_filter):
            continue
        out.append(row)
    ranked = _rank_pool_rows(out, role=role, experience_filter=experience_filter)
    return ranked[offset:offset + limit]


def _content_key(company: str | None, title: str | None) -> tuple[str, str] | None:
    c = re.sub(r"[^a-z0-9]", "", (company or "").lower())
    t = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", (title or "").lower())).strip()
    return (c, t) if c and t else None


def _row_quality_score(row: JobPool, *, role: str | None, experience_filter: str | None) -> float:
    title = (row.title or "").lower()
    company = (row.company or "").lower()
    url = (row.job_url or "").lower()
    score = public_job_quality_score(
        title=row.title,
        source=row.source,
        posted_at=row.posted_at,
        now=datetime.now(timezone.utc),
        role=role,
        experience_filter=experience_filter,
    )
    if re.search(r"\b(seo|digital marketing|wordpress designer|data analyst)\b", title):
        score -= 14
    if "javabykiran" in url or "placements/latest-job-opening" in url or "training" in company:
        score -= 18
    if title.count("/") + title.count(",") >= 2:
        score -= 5

    return score


def _rank_pool_rows(rows: list[JobPool], *, role: str | None, experience_filter: str | None) -> list[JobPool]:
    ranked = sorted(
        rows,
        key=lambda row: (
            _row_quality_score(row, role=role, experience_filter=experience_filter),
            row.posted_at or row.last_seen_at,
            row.last_seen_at,
        ),
        reverse=True,
    )
    unique_company: list[JobPool] = []
    overflow: list[JobPool] = []
    companies: set[str] = set()
    for row in ranked:
        company_key = re.sub(r"[^a-z0-9]", "", (row.company or "").lower())
        if company_key and company_key in companies:
            overflow.append(row)
            continue
        if company_key:
            companies.add(company_key)
        unique_company.append(row)
    return unique_company + overflow


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/job-search", response_model=PublicSearchResponse)
async def public_search(
    request: Request,
    role: str = Query(..., min_length=2, max_length=120, description="e.g. 'Software Engineer'"),
    location: str = Query("India", max_length=120),
    source: Optional[str] = Query(
        None,
        description="Restrict results to a single ATS — greenhouse | lever | ashby | workday | icims | smartrecruiters | bamboohr",
    ),
    experience: Optional[str] = Query(None, description="fresher | junior | mid | senior"),
    work_arrangement: Optional[str] = Query(None, description="remote | hybrid | onsite"),
    posted_within_days: Optional[int] = Query(7, ge=1, le=60),
    pages: int = Query(
        5, ge=1, le=10,
        description="How many SerpAPI pages to fetch (1 page ≈ 10 jobs). Each page costs 1 SerpAPI search credit.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Unauthenticated cached job search.

    Reads the shared pool immediately so user search never blocks on a live
    scrape. The background warehouse and scheduled supply runs own fetching.
    """
    await _rate_limit(_client_ip(request), "search", max_calls=10, window_sec=60)

    experience_filter = normalize_experience(experience)
    work_filter = (work_arrangement or "").strip().lower() or None
    if work_filter not in {"remote", "hybrid", "onsite", None}:
        work_filter = None
    cached_rows = await _matching_pool_rows(
        db,
        role=role,
        location=location,
        experience_filter=experience_filter,
        work_filter=work_filter,
        source=source,
        posted_within_days=posted_within_days,
        limit=100,
    )
    return PublicSearchResponse(
        query=role,
        location=location,
        source_filter=source,
        experience_filter=experience_filter,
        work_arrangement_filter=work_filter,
        fetched=0,
        matched=len(cached_rows),
        saved=0,
        jobs=[PublicJobResponse.model_validate(r) for r in cached_rows],
    )


@router.get("/jobs", response_model=list[PublicJobResponse])
async def browse_pool(
    request: Request,
    role: Optional[str] = Query(None, max_length=120, description="Synonym-aware role match on title"),
    location: Optional[str] = Query(None, max_length=120),
    experience: Optional[str] = Query(None, description="fresher | junior | mid | senior"),
    work_arrangement: Optional[str] = Query(None, description="remote | hybrid | onsite"),
    source: Optional[str] = Query(None),
    posted_within_days: Optional[int] = Query(7, ge=1, le=60),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Paginated browse of the shared pool. Cheap (DB only).

    Filters out rows older than 24h (last_seen_at) — same TTL as the
    cleanup_job_pool Celery task. Belt-and-braces: even if cleanup hasn't
    run yet, users only see fresh rows.
    """
    await _rate_limit(_client_ip(request), "browse", max_calls=60, window_sec=60)

    experience_filter = normalize_experience(experience)
    work_filter = (work_arrangement or "").strip().lower() or None
    if work_filter not in {"remote", "hybrid", "onsite", None}:
        work_filter = None
    rows = await _matching_pool_rows(
        db,
        role=role,
        location=location,
        experience_filter=experience_filter,
        work_filter=work_filter,
        source=source,
        posted_within_days=posted_within_days,
        limit=limit,
        offset=offset,
    )
    return [PublicJobResponse.model_validate(r) for r in rows]


# ── Import to a user's profile ───────────────────────────────────────────────

class ImportRequest(BaseModel):
    pool_job_ids: list[int]


class ImportResponse(BaseModel):
    profile_id: int
    requested: int
    imported: int        # new DiscoveredJob rows created
    already_present: int # job_url already in this user's DiscoveredJobs
    skipped_filters: int # failed India / role-match / exclusion filter


@router.post("/import-to-profile/{profile_id}", response_model=ImportResponse)
async def import_to_profile(
    profile_id: int,
    body: ImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import selected pool jobs into the user's DiscoveredJobs feed, filtered
    against the named JobSearchProfile (role match, India, no internships, etc).

    Scoring is NOT done here — the regular scoring pass on next discovery run
    will pick these up. This keeps import cheap and deterministic.
    """
    # Lazy import to avoid pulling discovery dependencies into module load.
    from app.agents.job_discovery_agent import (
        _matches_criteria,
        _is_india_strict,
        _is_excluded_job,
    )

    profile_row = await db.execute(
        select(JobSearchProfile).where(
            JobSearchProfile.id == profile_id,
            JobSearchProfile.user_id == current_user.id,
        )
    )
    profile = profile_row.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    if not body.pool_job_ids:
        return ImportResponse(profile_id=profile_id, requested=0, imported=0, already_present=0, skipped_filters=0)

    pool_rows = (await db.execute(
        select(JobPool).where(JobPool.id.in_(body.pool_job_ids))
    )).scalars().all()

    # Dedupe against user's existing DiscoveredJobs
    urls = [p.job_url for p in pool_rows]
    seen = set()
    if urls:
        seen_rows = await db.execute(
            select(DiscoveredJob.job_url).where(
                DiscoveredJob.user_id == current_user.id,
                DiscoveredJob.job_url.in_(urls),
            )
        )
        seen = {r[0] for r in seen_rows.all()}

    profile_dict = {
        "target_roles": profile.target_roles or "",
        "work_arrangements": profile.work_arrangements or "",
    }

    imported = 0
    already_present = 0
    skipped_filters = 0
    for p in pool_rows:
        if p.job_url in seen:
            already_present += 1
            continue
        if not _matches_criteria(p.title or "", profile_dict):
            skipped_filters += 1
            continue
        if not _is_india_strict(p.location):
            skipped_filters += 1
            continue
        if _is_excluded_job(p.title or "", p.company or "", p.job_url):
            skipped_filters += 1
            continue
        dj = DiscoveredJob(
            user_id=current_user.id,
            search_profile_id=profile.id,
            job_url=p.job_url,
            title=p.title,
            company=p.company,
            location=p.location,
            job_description=p.job_description,
            source=p.source,
            work_arrangement=p.work_arrangement,
            posted_at=p.posted_at,
            status="discovered",
        )
        db.add(dj)
        imported += 1
    await db.commit()

    return ImportResponse(
        profile_id=profile_id,
        requested=len(pool_rows),
        imported=imported,
        already_present=already_present,
        skipped_filters=skipped_filters,
    )
