from datetime import datetime
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.job_search_profile import JobSearchProfile

router = APIRouter()


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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile = JobSearchProfile(user_id=current_user.id, **body.model_dump())
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
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
    from app.workers.tasks import discover_jobs_task
    discover_jobs_task.delay(profile_id, current_user.id)
    return {"status": "discovery started"}
