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
  - USA-only locations
  - No internships / part-time / staffing / gov
  - Work-arrangement detection
  - Role synonym expansion via _matches_criteria

Rate limit: in-memory per-IP, 10 req/min on the live search endpoint. The
browse endpoint is much cheaper (DB only) so it gets a looser 60 req/min.
For multi-worker scaling, swap in slowapi + Redis backend.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlsplit

import httpx
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.discovered_job import DiscoveredJob
from app.models.job_pool import JobPool
from app.models.job_search_profile import JobSearchProfile
from app.models.user import User
from app.services.serpapi_jobs import search_serpapi_jobs

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


class PublicSearchResponse(BaseModel):
    query: str
    location: str
    source_filter: Optional[str]
    fetched: int           # raw rows SerpAPI returned (before our filters)
    matched: int           # rows kept after USA / source / exclusion filters
    saved: int             # rows actually upserted into JobPool
    jobs: list[PublicJobResponse]


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/job-search", response_model=PublicSearchResponse)
async def public_search(
    request: Request,
    role: str = Query(..., min_length=2, max_length=120, description="e.g. 'Software Engineer'"),
    location: str = Query("United States", max_length=120),
    source: Optional[str] = Query(
        None,
        description="Restrict results to a single ATS — greenhouse | lever | ashby | workday | icims | smartrecruiters | bamboohr",
    ),
    posted_within_days: Optional[int] = Query(7, ge=1, le=60),
    pages: int = Query(
        5, ge=1, le=10,
        description="How many SerpAPI pages to fetch (1 page ≈ 10 jobs). Each page costs 1 SerpAPI search credit.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """Unauthenticated live job search. Calls SerpAPI, filters to known ATS
    hosts, upserts into the shared JobPool, returns the rows it just saved."""
    await _rate_limit(_client_ip(request), "search", max_calls=10, window_sec=60)

    profile_for_serpapi = {
        "target_roles": role,
        "locations": location,
        "posted_within_days": posted_within_days,
    }

    # Run SerpAPI (broad aggregator) and direct ATS API scrapes (Greenhouse +
    # Ashby) IN PARALLEL. The ATS scrapes return direct ATS URLs — the kind
    # SerpAPI almost never surfaces. quick_ats_search caps at ~3-5s.
    # Re-use the same USA / job-type filters the authed discovery uses so
    # the pool holds the same quality bar.
    from app.agents.job_discovery_agent import (
        quick_ats_search,
        _is_usa_location,
        _is_excluded_job,
    )

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        serpapi_task = search_serpapi_jobs(
            client, profile_for_serpapi, posted_within_days, max_pages=pages,
        )
        ats_task = quick_ats_search(role, posted_within_days)
        # return_exceptions so a failure in one source never discards the other's
        # results (e.g. a SerpAPI hiccup must not throw away the ATS scrape).
        results = await asyncio.gather(serpapi_task, ats_task, return_exceptions=True)
        raw_serpapi = results[0] if isinstance(results[0], list) else []
        ats_jobs = results[1] if isinstance(results[1], list) else []
        for label, r in zip(("serpapi", "ats"), results):
            if isinstance(r, Exception):
                logger.warning("Public search %s source failed: %s", label, r)

    matched: list[dict] = []

    # SerpAPI results need URL/source post-processing (Google Jobs sends
    # aggregator wrappers; pick the most-direct option from apply_options).
    for j in raw_serpapi:
        best = _best_apply_url(j.get("apply_options") or [])
        if best:
            j["job_url"], src = best
        else:
            src = _classify_source(j.get("job_url", ""))
        if not src:
            continue
        if source and src != source:
            continue
        j["source"] = src
        matched.append(j)

    # ATS scrapers already produce normalized direct URLs + tagged sources.
    # Just apply the optional source filter.
    for j in ats_jobs:
        if source and j.get("source") != source:
            continue
        matched.append(j)

    # ── Quality filters (same as the authed discovery flow) ────────────────
    # USA-only + drop internships / part-time / staffing / .gov before the
    # rows hit the pool. Saves on storage + every browse downstream.
    before_filters = len(matched)
    matched = [
        j for j in matched
        if _is_usa_location(j.get("location"))
        and not _is_excluded_job(j.get("title", ""), j.get("company", ""), j.get("job_url", ""))
    ]
    dropped_by_filters = before_filters - len(matched)

    raw_jobs = raw_serpapi + ats_jobs
    logger.info(
        "Public search role=%r location=%r source=%r: "
        "SerpAPI=%d, ATS direct=%d, post-source=%d, post-quality=%d (dropped %d)",
        role, location, source,
        len(raw_serpapi), len(ats_jobs), before_filters, len(matched), dropped_by_filters,
    )

    # ── Dedupe within the batch by job_url ────────────────────────────────────
    # The same posting can arrive from BOTH SerpAPI (apply_options) and the
    # direct ATS scrape — most commonly a Greenhouse job. Two new rows with the
    # same job_url violate the UNIQUE(job_url) constraint and abort the entire
    # commit, so the whole search would persist nothing. Collapse duplicates
    # first, preferring the direct ATS row (clean URL + full description).
    deduped: dict[str, dict] = {}
    for j in matched:
        url = j.get("job_url")
        if not url:
            continue
        prev = deduped.get(url)
        if prev is None or (not prev.get("job_description") and j.get("job_description")):
            deduped[url] = j
    matched = list(deduped.values())

    # ── Upsert into pool ────────────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    urls = [j["job_url"] for j in matched if j.get("job_url")]
    existing: dict[str, JobPool] = {}
    if urls:
        rows = await db.execute(select(JobPool).where(JobPool.job_url.in_(urls)))
        existing = {r.job_url: r for r in rows.scalars().all()}

    saved_objs: list[JobPool] = []
    for j in matched:
        url = j.get("job_url")
        if not url:
            continue
        if url in existing:
            row = existing[url]
            row.last_seen_at = now
            # Refresh metadata in case the posting was edited
            row.title = j.get("title") or row.title
            row.company = j.get("company") or row.company
            row.location = j.get("location") or row.location
            row.work_arrangement = j.get("work_arrangement") or row.work_arrangement
            if j.get("posted_at"):
                row.posted_at = j["posted_at"]
            saved_objs.append(row)
        else:
            row = JobPool(
                job_url=url,
                title=j.get("title"),
                company=j.get("company"),
                location=j.get("location"),
                job_description=j.get("job_description"),
                source=j["source"],
                work_arrangement=j.get("work_arrangement"),
                posted_at=j.get("posted_at"),
                search_query=role,
            )
            db.add(row)
            saved_objs.append(row)
    await db.commit()
    for row in saved_objs:
        await db.refresh(row)

    return PublicSearchResponse(
        query=role,
        location=location,
        source_filter=source,
        fetched=len(raw_jobs),
        matched=len(matched),
        saved=len(saved_objs),
        jobs=[PublicJobResponse.model_validate(r) for r in saved_objs],
    )


@router.get("/jobs", response_model=list[PublicJobResponse])
async def browse_pool(
    request: Request,
    role: Optional[str] = Query(None, max_length=120, description="Substring match on title"),
    source: Optional[str] = Query(None),
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

    from datetime import timedelta
    fresh_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    q = select(JobPool).where(JobPool.last_seen_at >= fresh_cutoff)
    if role:
        q = q.where(func.lower(JobPool.title).contains(role.lower()))
    if source:
        q = q.where(JobPool.source == source)
    q = q.order_by(JobPool.last_seen_at.desc()).limit(limit).offset(offset)
    rows = await db.execute(q)
    return [PublicJobResponse.model_validate(r) for r in rows.scalars().all()]


# ── Import to a user's profile ───────────────────────────────────────────────

class ImportRequest(BaseModel):
    pool_job_ids: list[int]


class ImportResponse(BaseModel):
    profile_id: int
    requested: int
    imported: int        # new DiscoveredJob rows created
    already_present: int # job_url already in this user's DiscoveredJobs
    skipped_filters: int # failed USA / role-match / exclusion filter


@router.post("/import-to-profile/{profile_id}", response_model=ImportResponse)
async def import_to_profile(
    profile_id: int,
    body: ImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import selected pool jobs into the user's DiscoveredJobs feed, filtered
    against the named JobSearchProfile (role match, USA, no internships, etc).

    Scoring is NOT done here — the regular scoring pass on next discovery run
    will pick these up. This keeps import cheap and deterministic.
    """
    # Lazy import to avoid pulling discovery dependencies into module load.
    from app.agents.job_discovery_agent import (
        _matches_criteria,
        _is_usa_location,
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
        if not _is_usa_location(p.location):
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
