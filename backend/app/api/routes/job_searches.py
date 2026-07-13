import logging
from datetime import datetime, timezone
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.job_search_profile import JobSearchProfile

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_ACTIVE_JOB_TARGETS = 3

def _profile_dict(profile: JobSearchProfile) -> dict:
    return {
        "target_roles": profile.target_roles,
        "locations": profile.locations,
        "keywords": profile.keywords,
        "work_arrangements": profile.work_arrangements,
        "posted_within_days": profile.posted_within_days,
        "excluded_companies": profile.excluded_companies,
        "experience_level": profile.experience_level,
    }


async def _seed_from_pool(profile: JobSearchProfile, user_id: int) -> int:
    """Instant feed: import matching jobs from the shared pool. Best-effort."""
    try:
        from app.agents.job_discovery_agent import seed_user_feed_from_pool
        return await seed_user_feed_from_pool(user_id, _profile_dict(profile), search_profile_id=profile.id)
    except Exception:  # noqa: BLE001
        logger.exception("pool seed failed for profile %s", profile.id)
        return 0


async def _assert_active_target_capacity(
    db: AsyncSession,
    user_id: int,
    *,
    excluding_profile_id: int | None = None,
) -> None:
    """Protect the three-active-target product limit at the API boundary.

    Locking the owning user serializes two concurrent create/activate requests
    without introducing a database-specific partial unique constraint.
    """
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    statement = select(func.count(JobSearchProfile.id)).where(
        JobSearchProfile.user_id == user_id,
        JobSearchProfile.is_active.is_(True),
    )
    if excluding_profile_id is not None:
        statement = statement.where(JobSearchProfile.id != excluding_profile_id)
    active_count = int((await db.execute(statement)).scalar_one())
    if active_count >= MAX_ACTIVE_JOB_TARGETS:
        raise HTTPException(
            status_code=409,
            detail=f"A maximum of {MAX_ACTIVE_JOB_TARGETS} active job targets is allowed.",
        )


async def _queue_shared_aggregation(
    profile: JobSearchProfile, db: AsyncSession, user: User
) -> tuple[int, str]:
    """Attach a target to shared demand and mark its cluster ready for the worker.

    A user action must never create an individual live scrape. The scheduled
    warehouse worker owns source requests; this only makes the shared demand
    cluster eligible for its next run.
    """
    from app.services.aggregation import ensure_profile_demand

    cluster = await ensure_profile_demand(profile, db, user=user)
    if profile.is_active:
        cluster.status = "queued"
        cluster.priority = max(cluster.priority, 150)
        profile.last_run_at = datetime.now(timezone.utc)
    await db.commit()
    return cluster.id, cluster.status


class JobSearchProfileCreate(BaseModel):
    name: str
    target_roles: Optional[str] = None
    locations: Optional[str] = None
    keywords: Optional[str] = None
    excluded_companies: Optional[str] = None
    experience_level: Optional[str] = None
    auto_apply_threshold: int = 75
    auto_apply_mode: Literal["auto", "review"] = "review"
    is_active: bool = True
    work_arrangements: Optional[str] = None  # e.g. "remote,hybrid"
    posted_within_days: Optional[int] = None  # e.g. 14


class JobSearchProfileResponse(BaseModel):
    id: int
    name: str
    target_roles: Optional[str]
    locations: Optional[str]
    keywords: Optional[str]
    excluded_companies: Optional[str]
    experience_level: Optional[str]
    auto_apply_threshold: int
    auto_apply_mode: str
    is_active: bool
    last_run_at: Optional[datetime]
    created_at: datetime
    work_arrangements: Optional[str]
    posted_within_days: Optional[int]

    model_config = ConfigDict(from_attributes=True)


@router.get("/job-targets", response_model=list[JobSearchProfileResponse], tags=["job-targets"])
@router.get("/job-searches", response_model=list[JobSearchProfileResponse])
async def list_searches(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(JobSearchProfile)
        .where(JobSearchProfile.user_id == current_user.id)
        .order_by(JobSearchProfile.created_at.desc())
    )
    return result.scalars().all()


@router.post("/job-targets", response_model=JobSearchProfileResponse, status_code=201, tags=["job-targets"])
@router.post("/job-searches", response_model=JobSearchProfileResponse, status_code=201)
async def create_search(
    body: JobSearchProfileCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.is_active:
        await _assert_active_target_capacity(db, current_user.id)
    profile = JobSearchProfile(user_id=current_user.id, **body.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    # A profile adds reusable warehouse demand immediately. It does not launch
    # a separate full scrape: the shared 12-hour aggregator owns source work.
    cluster_id, _ = await _queue_shared_aggregation(profile, db, current_user)
    from app.services.aggregation import refresh_cluster_matches
    await refresh_cluster_matches(cluster_id, db)
    if profile.is_active:
        await _seed_from_pool(profile, current_user.id)  # legacy instant pool seed
    return profile


@router.put("/job-targets/{profile_id}", response_model=JobSearchProfileResponse, tags=["job-targets"])
@router.put("/job-searches/{profile_id}", response_model=JobSearchProfileResponse)
async def update_search(
    profile_id: int,
    body: JobSearchProfileCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(JobSearchProfile).where(
            JobSearchProfile.id == profile_id,
            JobSearchProfile.user_id == current_user.id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Search profile not found")
    if body.is_active and not profile.is_active:
        await _assert_active_target_capacity(
            db, current_user.id, excluding_profile_id=profile.id
        )
    for key, value in body.model_dump().items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    cluster_id, _ = await _queue_shared_aggregation(profile, db, current_user)
    from app.services.aggregation import refresh_cluster_matches
    await refresh_cluster_matches(cluster_id, db)
    return profile


@router.delete("/job-targets/{profile_id}", status_code=204, tags=["job-targets"])
@router.delete("/job-searches/{profile_id}", status_code=204)
async def delete_search(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(JobSearchProfile).where(
            JobSearchProfile.id == profile_id,
            JobSearchProfile.user_id == current_user.id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Search profile not found")
    await db.delete(profile)
    await db.commit()


@router.post("/job-targets/{profile_id}/run", status_code=202, tags=["job-targets"])
@router.post("/job-searches/{profile_id}/run", status_code=202)
async def run_search(
    profile_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(JobSearchProfile).where(
            JobSearchProfile.id == profile_id,
            JobSearchProfile.user_id == current_user.id,
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Search profile not found")
    if not profile.is_active:
        raise HTTPException(status_code=409, detail="Activate this job target before running it.")
    # Preserve the legacy instant pool-feed response while routing source work
    # exclusively through the shared warehouse aggregation queue.
    seeded = await _seed_from_pool(profile, current_user.id)
    cluster_id, queue_status = await _queue_shared_aggregation(profile, db, current_user)
    # Read warehouse matches first; this is local DB work and intentionally
    # never triggers individual source discovery for a user.
    from app.services.aggregation import refresh_cluster_matches
    warehouse_jobs_considered = await refresh_cluster_matches(cluster_id, db)
    return {
        "status": "queued",
        "message": "Job target queued for shared aggregation.",
        "seeded_from_pool": seeded,
        "demand_cluster_id": cluster_id,
        "queue_status": queue_status,
        "warehouse_jobs_considered": warehouse_jobs_considered,
    }
