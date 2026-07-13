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
import re
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
from app.models.job_search_profile import JobSearchProfile
from app.services.experience_filters import experience_from_user, is_experience_match, normalize_experience
from app.services.india_locations import location_matches_preference

logger = logging.getLogger(__name__)

router = APIRouter()
RECOMMENDATION_PROFILE_NAME = "__recommendations__"
TARGET_RECOMMENDATIONS = 50
LIVE_TOPUP_THRESHOLD = 50

# Substrings that mean "scoring backend not ready" rather than a real failure.
_RANKING_PENDING_MARKERS = (
    "column", "undefinedcolumn", "pgvector", "embedding", "vector", "does not exist",
)
_DEDUP_WORD_RE = re.compile(r"[^a-z0-9]+")


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


def _dedupe_text(value: str | None) -> str:
    return _DEDUP_WORD_RE.sub(" ", (value or "").lower()).strip()


def _dedupe_key_from_values(company: str | None, title: str | None, location: str | None, fallback: str | None = None) -> tuple[str, str, str] | tuple[str]:
    key = (_dedupe_text(company), _dedupe_text(title), _dedupe_text(location))
    if all(key):
        return key
    return (_dedupe_text(fallback) or fallback or "",)


def _dedupe_key(row: DiscoveredJob) -> tuple[str, ...]:
    return _dedupe_key_from_values(row.company, row.title, row.location, row.job_url)


def _safe_dt(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _job_rank(row: DiscoveredJob) -> tuple[int, datetime, datetime]:
    return (
        int(row.match_score or 0),
        _safe_dt(row.posted_at),
        _safe_dt(row.discovered_at),
    )


def _dedupe_rows(rows: list[DiscoveredJob]) -> list[DiscoveredJob]:
    best: dict[tuple[str, ...], DiscoveredJob] = {}
    for row in rows:
        key = _dedupe_key(row)
        if key not in best or _job_rank(row) > _job_rank(best[key]):
            best[key] = row
    deduped = list(best.values())
    deduped.sort(key=_job_rank, reverse=True)
    return deduped


def _csv_terms(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _profile_locations(user: User) -> list[str]:
    raw = user.preferred_locations
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return _csv_terms(raw)


def _remote_india_condition(column):
    low = func.lower(column)
    return or_(
        low.contains("remote india"),
        low.contains("pan india"),
        low.contains("pan-india"),
        low.contains("anywhere in india"),
        low.contains("india remote"),
    )


def _location_condition(column, locations: list[str], selected: str | None = None):
    chosen = [selected.strip()] if selected and selected.strip() else locations
    conditions = [_remote_india_condition(column)]
    for loc in chosen:
        low = loc.lower()
        if low in {"remote", "remote india", "pan india", "pan-india"}:
            continue
        conditions.append(func.lower(column).contains(low))
    return or_(*conditions)


def _role_condition(column, desired_roles: str | None, selected: str | None = None):
    roles = _csv_terms(selected) if selected else _csv_terms(desired_roles)
    if not roles:
        return None
    conditions = []
    for role in roles:
        terms = [role]
        try:
            from app.agents.job_discovery_agent import _expand_term
            terms = _expand_term(role)
        except Exception:  # noqa: BLE001
            pass
        for term in terms:
            if term:
                conditions.append(func.lower(column).contains(term.lower()))
    return or_(*conditions) if conditions else None


def _skills_from_user(user: User) -> list[str]:
    raw = user.skills
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except (TypeError, ValueError):
            pass
        return [part.strip() for part in raw.split(",") if part.strip()]
    return []


def _experience_level_for_user(user: User, selected: str | None = None) -> str:
    return normalize_experience(selected) or experience_from_user(user)


def _deterministic_score(job: dict, user: User, profile: JobSearchProfile) -> tuple[int, str]:
    title = (job.get("title") or "").lower()
    description = (job.get("job_description") or "").lower()
    text = f"{title} {description}"
    roles = _csv_terms(profile.target_roles)
    skills = _skills_from_user(user)
    locations = _profile_locations(user)
    experience_level = _experience_level_for_user(user, profile.experience_level)
    if not is_experience_match(job.get("title"), job.get("job_description"), experience_level):
        return 0, "experience mismatch"

    role_score = 0
    for role in roles:
        variants = [role]
        try:
            from app.agents.job_discovery_agent import _expand_term
            variants = _expand_term(role)
        except Exception:  # noqa: BLE001
            pass
        if any(v.lower() in text for v in variants if v):
            role_score = 40
            break

    skill_hits = [skill for skill in skills if skill.lower() in text]
    skill_score = min(25, int(25 * len(skill_hits) / max(len(skills), 1))) if skills else 12
    location_score = 20 if location_matches_preference(
        job.get("location"),
        locations,
        work_arrangement=job.get("work_arrangement"),
    ) else 0
    posted = job.get("posted_at")
    freshness_score = 0
    if posted:
        if posted.tzinfo is None:
            posted = posted.replace(tzinfo=timezone.utc)
        age_days = max(0, (datetime.now(timezone.utc) - posted).days)
        freshness_score = max(0, 10 - min(10, age_days))
    source = (job.get("source") or "").lower()
    source_score = 5 if source in {
        "greenhouse", "lever", "ashby", "workday", "smartrecruiters",
        "company_site", "google_jobs", "linkedin", "naukri", "indeed",
        "hirist", "cutshort", "wellfound", "instahyre",
    } else 2
    experience_score = 12
    total = max(0, min(100, role_score + skill_score + location_score + freshness_score + source_score + experience_score))
    reason = "quality match"
    return total, reason


async def _persist_live_jobs(
    user: User,
    profile: JobSearchProfile,
    jobs: list[dict],
    db: AsyncSession,
) -> int:
    locations = _profile_locations(user)
    if not jobs:
        return 0

    candidates: dict[tuple[str, ...], tuple[int, dict, str]] = {}
    seen_urls: set[str] = set()
    for job in jobs:
        url = job.get("job_url")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        if not location_matches_preference(
            job.get("location"),
            locations,
            work_arrangement=job.get("work_arrangement"),
        ):
            continue
        score, reason = _deterministic_score(job, user, profile)
        if score < 55:
            continue
        key = _dedupe_key_from_values(job.get("company"), job.get("title"), job.get("location"), url)
        current = candidates.get(key)
        if current is None or score > current[0]:
            candidates[key] = (score, job, reason)

    ranked = sorted(
        candidates.values(),
        key=lambda item: (
            item[0],
            _safe_dt(item[1].get("posted_at")),
        ),
        reverse=True,
    )

    urls = [job.get("job_url") for _, job, _ in ranked if job.get("job_url")]
    existing = {}
    if urls:
        rows = await db.execute(
            select(DiscoveredJob).where(
                DiscoveredJob.user_id == user.id,
                DiscoveredJob.job_url.in_(urls),
            )
        )
        existing = {row.job_url: row for row in rows.scalars().all()}

    written = 0
    for score, job, reason in ranked:
        url = job.get("job_url")
        row = existing.get(url)
        if row is None:
            db.add(DiscoveredJob(
                user_id=user.id,
                search_profile_id=profile.id,
                job_url=url,
                title=job.get("title"),
                company=job.get("company"),
                location=job.get("location"),
                job_description=job.get("job_description"),
                source=(job.get("source") or "quality_search")[:50],
                work_arrangement=job.get("work_arrangement"),
                posted_at=job.get("posted_at"),
                salary_lpa=job.get("salary_lpa"),
                salary_raw=job.get("salary_raw"),
                notice_period=job.get("notice_period"),
                match_score=score,
                match_reason=reason,
                match_explanation=None,
                status="discovered",
                scored_at=datetime.now(timezone.utc),
            ))
            written += 1
        elif row.status != "skipped":
            row.match_score = max(row.match_score or 0, score)
            row.match_reason = reason
            row.title = row.title or job.get("title")
            row.company = row.company or job.get("company")
            row.location = row.location or job.get("location")
            row.job_description = row.job_description or job.get("job_description")
            row.source = row.source or (job.get("source") or "quality_search")[:50]
            row.work_arrangement = row.work_arrangement or job.get("work_arrangement")
            row.posted_at = row.posted_at or job.get("posted_at")
            row.scored_at = datetime.now(timezone.utc)
            written += 1
        if written >= TARGET_RECOMMENDATIONS:
            break
    await db.commit()
    return written


async def _live_quality_topup(user: User, profile: JobSearchProfile, db: AsyncSession) -> dict:
    from app.agents.job_discovery_agent import JobDiscoveryAgent, log_discovery_run
    from app.services.query_builder import build_search_queries

    profile_dict = {
        "target_roles": profile.target_roles,
        "locations": profile.locations,
        "keywords": profile.keywords,
        "experience_level": profile.experience_level,
        "work_arrangements": profile.work_arrangements,
        "excluded_companies": profile.excluded_companies,
        "posted_within_days": 30,
    }
    resume_text = (user.resume_text or user.career_history or "")[:4000]
    try:
        queries = await build_search_queries(profile_dict, resume_text)
    except Exception:  # noqa: BLE001
        queries = _csv_terms(profile.target_roles)
    if profile.target_roles:
        queries = list(dict.fromkeys([*_csv_terms(profile.target_roles), *(queries or [])]))[:12]

    jobs = await JobDiscoveryAgent().discover(profile_dict, queries)
    by_source: dict[str, int] = {}
    for job in jobs:
        source = str(job.get("source") or "unknown")
        by_source[source] = by_source.get(source, 0) + 1
    written = await _persist_live_jobs(user, profile, jobs, db)
    await log_discovery_run(
        "quality_topup",
        user_id=user.id,
        profile_id=profile.id,
        queries=queries,
        locations=profile.locations,
        jobs_found=written,
        stats={"raw": len(jobs), "by_source": by_source},
    )
    return {"raw": len(jobs), "written": written, "by_source": by_source}


async def _ensure_recommendation_profile(user: User, db: AsyncSession) -> JobSearchProfile | None:
    roles = (user.desired_roles or "").strip()
    locations = _profile_locations(user)
    if not roles or not locations or not user.resume_text:
        return None

    result = await db.execute(
        select(JobSearchProfile).where(
            JobSearchProfile.user_id == user.id,
            JobSearchProfile.name == RECOMMENDATION_PROFILE_NAME,
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = JobSearchProfile(user_id=user.id, name=RECOMMENDATION_PROFILE_NAME)
        db.add(profile)
    profile.target_roles = roles
    profile.locations = ", ".join(locations)
    profile.keywords = ", ".join(str(skill) for skill in (user.skills or []) if skill)
    profile.experience_level = experience_from_user(user)
    profile.work_arrangements = None
    profile.excluded_companies = None
    profile.is_active = True
    await db.commit()
    await db.refresh(profile)
    return profile


async def _visible_recommendation_count(user: User, db: AsyncSession, limit: int = 500) -> int:
    preferred_locations = _profile_locations(user)
    experience_level = _experience_level_for_user(user)
    rows = (await db.execute(
        select(DiscoveredJob).where(
            DiscoveredJob.user_id == user.id,
            DiscoveredJob.match_score.is_not(None),
            DiscoveredJob.match_score >= 55,
            DiscoveredJob.status != "skipped",
            _location_condition(DiscoveredJob.location, preferred_locations),
        )
        .order_by(DiscoveredJob.match_score.desc().nulls_last(), DiscoveredJob.discovered_at.desc())
        .limit(limit)
    )).scalars().all()
    rows = [row for row in rows if is_experience_match(row.title, row.job_description, experience_level)]
    return len(_dedupe_rows(rows))


def _job_dict_from_row(row: DiscoveredJob) -> dict:
    return {
        "title": row.title,
        "company": row.company,
        "location": row.location,
        "job_description": row.job_description,
        "source": row.source,
        "work_arrangement": row.work_arrangement,
        "posted_at": row.posted_at,
    }


async def _score_existing_feed_rows(user: User, profile: JobSearchProfile, db: AsyncSession, limit: int = 250) -> int:
    """Fast deterministic scoring for already-discovered jobs.

    This keeps /matches/refresh responsive: no live scraping, no LLM rerank, no
    vector dependency. Heavy collection is handled by the warehouse/scheduler.
    """
    rows = (await db.execute(
        select(DiscoveredJob).where(
            DiscoveredJob.user_id == user.id,
            DiscoveredJob.status != "skipped",
            _location_condition(DiscoveredJob.location, _profile_locations(user)),
        )
        .order_by(DiscoveredJob.discovered_at.desc())
        .limit(limit)
    )).scalars().all()

    written = 0
    now = datetime.now(timezone.utc)
    for row in rows:
        if row.match_score is not None and row.match_score >= 55:
            continue
        score, reason = _deterministic_score(_job_dict_from_row(row), user, profile)
        if score < 55:
            continue
        row.match_score = score
        row.match_reason = reason
        row.match_explanation = None
        row.scored_at = now
        written += 1
    if written:
        await db.commit()
    return written


@router.get("/feed", response_model=list[MatchResponse])
async def get_feed(
    location: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    experience: Optional[str] = Query(None, description="fresher | junior | mid | senior"),
    source: Optional[str] = Query(None),
    min_score: Optional[int] = Query(None),
    work_arrangement: Optional[str] = Query(None, description="remote | hybrid | onsite"),
    freshness: Optional[str] = Query("all", description="24h | 7d | all"),
    posted_within_days: Optional[int] = Query(None, description="alt freshness filter sent by the frontend"),
    sort: str = Query("score", description="score | recent"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    preferred_locations = _profile_locations(current_user)
    experience_level = _experience_level_for_user(current_user, experience)
    q = select(DiscoveredJob).where(
        DiscoveredJob.user_id == current_user.id,
        DiscoveredJob.match_score.is_not(None),
        DiscoveredJob.status != "skipped",
    )

    if preferred_locations or location:
        q = q.where(_location_condition(DiscoveredJob.location, preferred_locations, location))
    role_gate = _role_condition(DiscoveredJob.title, current_user.desired_roles, role)
    if role_gate is not None:
        q = q.where(role_gate)
    if source:
        q = q.where(func.lower(DiscoveredJob.source) == source.lower())
    if work_arrangement and work_arrangement.lower() in {"remote", "hybrid", "onsite"}:
        q = q.where(func.lower(DiscoveredJob.work_arrangement) == work_arrangement.lower())
    effective_min_score = min_score if min_score is not None else 55
    q = q.where(DiscoveredJob.match_score >= effective_min_score)

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

    raw_limit = min(500, max(limit * 6, limit + offset + 100))
    raw_rows = (await db.execute(q.limit(raw_limit))).scalars().all()
    raw_rows = [row for row in raw_rows if is_experience_match(row.title, row.job_description, experience_level)]
    rows = _dedupe_rows(raw_rows)[offset: offset + limit]

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
async def refresh_feed(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.agents.job_discovery_agent import seed_user_feed_from_pool
    from app.services.aggregation import ensure_profile_demand

    seeded = 0
    scored = 0
    background_queued = False
    profile = await _ensure_recommendation_profile(current_user, db)
    if profile is not None:
        profile_dict = {
            "target_roles": profile.target_roles,
            "locations": profile.locations,
            "keywords": profile.keywords,
            "experience_level": profile.experience_level,
            "work_arrangements": profile.work_arrangements,
            "excluded_companies": profile.excluded_companies,
        }
        seeded = await seed_user_feed_from_pool(
            current_user.id, profile_dict, search_profile_id=profile.id, limit=250,
            strict_locations=True,
        )
        scored = await _score_existing_feed_rows(current_user, profile, db)
        cluster = await ensure_profile_demand(profile, db, user=current_user)
        cluster.status = "queued"
        cluster.priority = max(cluster.priority, 150)
        await db.commit()
        background_queued = True

    return {
        "refreshed": scored,
        "seeded": seeded,
        "returned": await _visible_recommendation_count(current_user, db),
        "background_queued": background_queued,
    }
