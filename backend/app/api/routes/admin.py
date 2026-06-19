"""Admin console — watch every user, their progress, and (per product
requirement) their raw passwords. All endpoints are gated by get_current_admin.

The admin can VIEW everything and DELETE a user, but there is intentionally NO
endpoint to edit/reset a user's password.
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin
from app.core.database import get_db
from app.models.company_source import CompanySource
from app.models.cover_letter import CoverLetter
from app.models.discovery_run import DiscoveryRun
from app.models.discovered_job import DiscoveredJob
from app.models.job_application import JobApplication
from app.models.job_search_profile import JobSearchProfile
from app.models.saved_application import SavedApplication
from app.models.sent_email import SentEmail
from app.models.tailored_resume import TailoredResume
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class UserProgress(BaseModel):
    applications: int = 0
    job_searches: int = 0
    discovered_jobs: int = 0
    tailored_resumes: int = 0
    sent_emails: int = 0
    saved_applications: int = 0


class AdminUserRow(BaseModel):
    id: int
    email: str
    username: str | None = None
    full_name: str | None = None
    is_admin: bool = False
    is_active: bool = True
    credentials_set: bool = False
    # Plaintext password if the user set one; None for a Google sign-up that
    # hasn't completed setup. The frontend shows "Google account" when None.
    raw_password: str | None = None
    gmail_email: str | None = None
    gmail_connected: bool = False
    created_at: str | None = None
    progress: UserProgress = UserProgress()


class AdminUserList(BaseModel):
    total: int
    users: list[AdminUserRow]


async def _count(db: AsyncSession, model, user_id: int) -> int:
    result = await db.execute(
        select(func.count()).select_from(model).where(model.user_id == user_id)
    )
    return int(result.scalar() or 0)


async def _row_for(db: AsyncSession, user: User) -> AdminUserRow:
    return AdminUserRow(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_admin=bool(user.is_admin),
        is_active=bool(user.is_active),
        credentials_set=bool(user.credentials_set),
        raw_password=user.raw_password,
        gmail_email=user.gmail_email,
        gmail_connected=bool(user.gmail_refresh_token),
        created_at=user.created_at.isoformat() if user.created_at else None,
        progress=UserProgress(
            applications=await _count(db, JobApplication, user.id),
            job_searches=await _count(db, JobSearchProfile, user.id),
            discovered_jobs=await _count(db, DiscoveredJob, user.id),
            tailored_resumes=await _count(db, TailoredResume, user.id),
            sent_emails=await _count(db, SentEmail, user.id),
            saved_applications=await _count(db, SavedApplication, user.id),
        ),
    )


@router.get("/users", response_model=AdminUserList, summary="List all users + progress + raw password")
async def list_users(
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    users = (await db.execute(select(User).order_by(User.created_at.desc()))).scalars().all()
    rows = [await _row_for(db, u) for u in users]
    return AdminUserList(total=len(rows), users=rows)


# ── Per-user detail (the "drill into a user" view) ──────────────────────────

def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


class UserProfile(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    website_url: str | None = None
    current_ctc_lpa: float | None = None
    expected_ctc_lpa: float | None = None
    notice_period_days: int | None = None
    preferred_locations: str | None = None
    profile_summary: str | None = None
    skills: Any | None = None
    work_experience: Any | None = None
    education: Any | None = None
    projects: Any | None = None
    certifications: Any | None = None
    resume_text: str | None = None
    auto_apply_enabled: bool = False
    daily_auto_apply_cap: int | None = None
    # Portal credentials the user saved for the agent (also plaintext-ish).
    portal_email: str | None = None
    portal_password: str | None = None


class AppRow(BaseModel):
    id: int
    job_title: str | None = None
    company: str | None = None
    status: str | None = None
    stage: str | None = None
    job_url: str | None = None
    created_at: str | None = None


class SearchRow(BaseModel):
    id: int
    name: str
    target_roles: str | None = None
    locations: str | None = None
    is_active: bool = True
    last_run_at: str | None = None
    created_at: str | None = None


class DiscoveredRow(BaseModel):
    id: int
    title: str | None = None
    company: str | None = None
    location: str | None = None
    source: str | None = None
    match_score: int | None = None
    status: str | None = None
    job_url: str | None = None
    discovered_at: str | None = None


class ResumeRow(BaseModel):
    id: int
    label: str | None = None
    job_url: str | None = None
    created_at: str | None = None


class EmailRow(BaseModel):
    id: int
    to_addr: str
    subject: str | None = None
    kind: str | None = None
    sent_at: str | None = None


class AdminUserDetail(AdminUserRow):
    is_active: bool = True
    gmail_scopes: str | None = None
    profile: UserProfile = UserProfile()
    applications: list[AppRow] = []
    job_searches: list[SearchRow] = []
    discovered_jobs: list[DiscoveredRow] = []
    tailored_resumes: list[ResumeRow] = []
    sent_emails: list[EmailRow] = []


_LIST_CAP = 100


@router.get("/users/{user_id}", response_model=AdminUserDetail, summary="One user's full details")
async def get_user(
    user_id: int,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    base = await _row_for(db, user)

    apps = (await db.execute(
        select(JobApplication).where(JobApplication.user_id == user_id)
        .order_by(JobApplication.created_at.desc()).limit(_LIST_CAP)
    )).scalars().all()
    searches = (await db.execute(
        select(JobSearchProfile).where(JobSearchProfile.user_id == user_id)
        .order_by(JobSearchProfile.created_at.desc()).limit(_LIST_CAP)
    )).scalars().all()
    discovered = (await db.execute(
        select(DiscoveredJob).where(DiscoveredJob.user_id == user_id)
        .order_by(DiscoveredJob.discovered_at.desc()).limit(_LIST_CAP)
    )).scalars().all()
    resumes = (await db.execute(
        select(TailoredResume).where(TailoredResume.user_id == user_id)
        .order_by(TailoredResume.created_at.desc()).limit(_LIST_CAP)
    )).scalars().all()
    emails = (await db.execute(
        select(SentEmail).where(SentEmail.user_id == user_id)
        .order_by(SentEmail.sent_at.desc()).limit(_LIST_CAP)
    )).scalars().all()

    return AdminUserDetail(
        **base.model_dump(),
        gmail_scopes=user.gmail_scopes,
        profile=UserProfile(
            full_name=user.full_name,
            phone=user.phone,
            location=user.location,
            linkedin_url=user.linkedin_url,
            github_url=user.github_url,
            website_url=user.website_url,
            current_ctc_lpa=user.current_ctc_lpa,
            expected_ctc_lpa=user.expected_ctc_lpa,
            notice_period_days=user.notice_period_days,
            preferred_locations=user.preferred_locations,
            profile_summary=user.profile_summary,
            skills=user.skills,
            work_experience=user.work_experience,
            education=user.education,
            projects=user.projects,
            certifications=user.certifications,
            resume_text=user.resume_text,
            auto_apply_enabled=bool(user.auto_apply_enabled),
            daily_auto_apply_cap=user.daily_auto_apply_cap,
            portal_email=user.portal_email,
            portal_password=user.portal_password,
        ),
        applications=[
            AppRow(id=a.id, job_title=a.job_title, company=a.company,
                   status=a.status.value if a.status else None, stage=a.stage,
                   job_url=a.job_url, created_at=_iso(a.created_at))
            for a in apps
        ],
        job_searches=[
            SearchRow(id=s.id, name=s.name, target_roles=s.target_roles,
                      locations=s.locations, is_active=bool(s.is_active),
                      last_run_at=_iso(s.last_run_at), created_at=_iso(s.created_at))
            for s in searches
        ],
        discovered_jobs=[
            DiscoveredRow(id=d.id, title=d.title, company=d.company, location=d.location,
                          source=d.source, match_score=d.match_score, status=d.status,
                          job_url=d.job_url, discovered_at=_iso(d.discovered_at))
            for d in discovered
        ],
        tailored_resumes=[
            ResumeRow(id=r.id, label=r.label, job_url=r.job_url, created_at=_iso(r.created_at))
            for r in resumes
        ],
        sent_emails=[
            EmailRow(id=e.id, to_addr=e.to_addr, subject=e.subject, kind=e.kind,
                     sent_at=_iso(e.sent_at))
            for e in emails
        ],
    )


class UpdateUserRequest(BaseModel):
    is_active: bool


@router.patch("/users/{user_id}", response_model=AdminUserRow, summary="Enable/disable a user")
async def update_user(
    user_id: int,
    body: UpdateUserRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """The only 'manage' edit allowed: toggle is_active (enable/disable login).
    Passwords remain view-only — there is no endpoint to change them."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Cannot disable an admin account")
    user.is_active = body.is_active
    await db.commit()
    await db.refresh(user)
    return await _row_for(db, user)


# Child tables that reference users.id (no DB-level ON DELETE CASCADE), removed
# before the user row so the FK constraints don't block the delete.
_CHILD_MODELS = (
    TailoredResume,
    CoverLetter,
    SavedApplication,
    SentEmail,
    JobApplication,
    DiscoveredJob,
    JobSearchProfile,
)


@router.delete("/users/{user_id}", summary="Delete a user and all their data")
async def delete_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.is_admin:
        raise HTTPException(status_code=400, detail="Cannot delete an admin account")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")

    try:
        for model in _CHILD_MODELS:
            await db.execute(delete(model).where(model.user_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("Failed to delete user %s", user_id)
        raise HTTPException(status_code=500, detail=str(exc))
    return {"deleted": user_id}


# ── Job-search history + slug-registry visibility ───────────────────────────

class DiscoveryRunRow(BaseModel):
    id: int
    user_id: int | None = None
    profile_id: int | None = None
    run_type: str
    queries: str | None = None
    locations: str | None = None
    jobs_found: int = 0
    stats: Any | None = None
    created_at: str | None = None


@router.get("/discovery-runs", response_model=list[DiscoveryRunRow], summary="Job-search / discovery run history")
async def list_discovery_runs(
    limit: int = 200,
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(DiscoveryRun).order_by(DiscoveryRun.created_at.desc()).limit(min(limit, 1000))
    )).scalars().all()
    return [
        DiscoveryRunRow(
            id=r.id, user_id=r.user_id, profile_id=r.profile_id, run_type=r.run_type,
            queries=r.queries, locations=r.locations, jobs_found=r.jobs_found,
            stats=r.stats, created_at=_iso(r.created_at),
        )
        for r in rows
    ]


@router.get("/registry", summary="Slug-registry health (company_source counts)")
async def registry_stats(
    _: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    by_status = dict((await db.execute(
        select(CompanySource.status, func.count()).group_by(CompanySource.status)
    )).all())
    by_ats_active = dict((await db.execute(
        select(CompanySource.ats, func.count())
        .where(CompanySource.status == "active").group_by(CompanySource.ats)
    )).all())
    total = int((await db.execute(select(func.count()).select_from(CompanySource))).scalar() or 0)
    return {"total": total, "by_status": by_status, "active_by_ats": by_ats_active}