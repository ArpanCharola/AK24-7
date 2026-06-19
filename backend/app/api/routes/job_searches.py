import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.job_search_profile import JobSearchProfile

logger = logging.getLogger(__name__)
router = APIRouter()

# Admin/back-end snapshot of every search profile's resolved config, so we can
# "find jobs for their role beforehand" and admin can inspect them offline.
_PROFILE_SNAPSHOT_DIR = Path(__file__).resolve().parent.parent.parent / "app" / "data" / "profiles"


def _write_profile_snapshot(user_id: int, profile: JobSearchProfile) -> None:
    try:
        _PROFILE_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        snap = {
            "user_id": user_id,
            "profile_id": profile.id,
            "name": profile.name,
            "target_roles": profile.target_roles,
            "locations": profile.locations,
            "keywords": profile.keywords,
            "work_arrangements": profile.work_arrangements,
            "posted_within_days": profile.posted_within_days,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        (_PROFILE_SNAPSHOT_DIR / f"{user_id}_{profile.id}.json").write_text(
            json.dumps(snap, indent=2), encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 — snapshot is best-effort
        logger.warning("profile snapshot failed for %s/%s: %s", user_id, profile.id, exc)


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


async def _prewarm_discovery(profile_id: int, user_id: int) -> None:
    """Full live discovery + scoring in-process (no Celery worker needed). Runs in
    the background after the instant pool-seed so the feed is fresh + complete."""
    try:
        from app.workers.tasks import _run_discovery
        await _run_discovery(profile_id, user_id)
    except Exception:  # noqa: BLE001
        logger.exception("pre-warm discovery failed for profile %s", profile_id)


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


@router.post("/job-searches", response_model=JobSearchProfileResponse, status_code=201)
async def create_search(
    body: JobSearchProfileCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = JobSearchProfile(user_id=current_user.id, **body.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    # Snapshot the resolved config for admin/back-end + pre-warm this role's feed
    # so jobs are ready before the user browses.
    _write_profile_snapshot(current_user.id, profile)
    if profile.is_active:
        await _seed_from_pool(profile, current_user.id)  # instant
        background_tasks.add_task(_prewarm_discovery, profile.id, current_user.id)  # full, in bg
    return profile


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
    for key, value in body.model_dump().items():
        setattr(profile, key, value)
    await db.commit()
    await db.refresh(profile)
    return profile


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


@router.post("/job-searches/{profile_id}/run", status_code=202)
async def run_search(
    profile_id: int,
    background_tasks: BackgroundTasks,
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
    # Instant feed from the shared pool, then full live discovery in the background.
    seeded = await _seed_from_pool(profile, current_user.id)
    background_tasks.add_task(_prewarm_discovery, profile_id, current_user.id)
    return {"status": "discovery started", "seeded_from_pool": seeded}
