import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.job_application import JobApplication, ApplicationStatus
from app.models.cover_letter import CoverLetter
from app.workers.tasks import run_application_task, _detect_portal

router = APIRouter()


class ApplyRequest(BaseModel):
    job_url: str
    job_title: str | None = None
    company: str | None = None
    job_description: str | None = None


class ApplicationResponse(BaseModel):
    id: int
    job_url: str
    job_title: str | None
    company: str | None
    status: ApplicationStatus
    queued_by: str
    celery_task_id: str | None
    error_message: str | None = None
    stage: str | None = None
    stage_updated_at: datetime | None = None
    created_at: datetime | None

    class Config:
        from_attributes = True


class CoverLetterResponse(BaseModel):
    id: int
    application_id: int
    content: str
    generated_at: datetime

    class Config:
        from_attributes = True


@router.post("/apply", response_model=ApplicationResponse, status_code=201)
async def apply(
    body: ApplyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Dedupe: don't create a second application for the same URL
    existing = await db.execute(
        select(JobApplication).where(
            JobApplication.user_id == current_user.id,
            JobApplication.job_url == body.job_url,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Application already exists for this URL")

    application = JobApplication(
        user_id=current_user.id,
        job_url=body.job_url,
        job_title=body.job_title,
        company=body.company,
        job_description=body.job_description,
        portal_type=_detect_portal(body.job_url),
        queued_by="manual",
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)

    # Persist celery_task_id BEFORE dispatch (pre-generated id) so a fast worker
    # can never pick up the row before its task id is committed.
    task_id = uuid.uuid4().hex
    application.celery_task_id = task_id
    await db.commit()
    await db.refresh(application)
    run_application_task.apply_async(args=[application.id, current_user.id], task_id=task_id)
    return application


@router.get("/status/{job_id}", response_model=ApplicationResponse)
async def get_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.id == job_id,
            JobApplication.user_id == current_user.id,
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.post("/applications/{application_id}/retry", response_model=ApplicationResponse)
async def retry_application(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run a failed application. Only FAILED apps can be retried — re-running a
    completed one risks a duplicate submission."""
    application = await _load_owned_application(db, application_id, current_user.id)
    if application.status != ApplicationStatus.FAILED:
        raise HTTPException(
            status_code=409,
            detail=f"Only failed applications can be retried (current status: {application.status.value})",
        )

    application.status = ApplicationStatus.PENDING
    application.error_message = None
    await db.commit()

    task = run_application_task.delay(application.id, current_user.id)
    application.celery_task_id = task.id
    await db.commit()
    await db.refresh(application)
    return application


@router.get("/applications", response_model=list[ApplicationResponse])
async def list_applications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(JobApplication)
        .where(JobApplication.user_id == current_user.id)
        .order_by(JobApplication.created_at.desc())
    )
    return result.scalars().all()


async def _load_owned_application(db: AsyncSession, application_id: int, user_id: int) -> JobApplication:
    result = await db.execute(
        select(JobApplication).where(
            JobApplication.id == application_id,
            JobApplication.user_id == user_id,
        )
    )
    application = result.scalar_one_or_none()
    if not application:
        raise HTTPException(status_code=404, detail="Application not found")
    return application


@router.get("/applications/{application_id}/cover-letter", response_model=CoverLetterResponse)
async def get_cover_letter(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _load_owned_application(db, application_id, current_user.id)
    result = await db.execute(
        select(CoverLetter).where(CoverLetter.application_id == application_id)
    )
    cover_letter = result.scalar_one_or_none()
    if not cover_letter:
        raise HTTPException(status_code=404, detail="No cover letter generated for this application")
    return cover_letter


@router.post("/applications/{application_id}/cover-letter/regenerate", response_model=CoverLetterResponse)
async def regenerate_cover_letter(
    application_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    application = await _load_owned_application(db, application_id, current_user.id)
    if not application.job_description:
        raise HTTPException(status_code=422, detail="Application has no job description to draft from")
    # Ground the letter in career_history if present, else fall back to resume_text.
    grounding = current_user.career_history or current_user.resume_text
    if not grounding:
        raise HTTPException(status_code=422, detail="Profile has no career history or résumé text — cannot draft cover letter")

    from app.services.resume_tailor import ResumeTailor
    try:
        content = await ResumeTailor().draft_cover_letter(
            application.job_description,
            application.company or "",
            application.job_title or "",
            grounding,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI service error: {exc}") from exc

    existing = await db.execute(
        select(CoverLetter).where(CoverLetter.application_id == application_id)
    )
    cover_letter = existing.scalar_one_or_none()
    if cover_letter:
        cover_letter.content = content
        cover_letter.generated_at = datetime.now(timezone.utc)
    else:
        cover_letter = CoverLetter(
            user_id=current_user.id,
            application_id=application_id,
            content=content,
        )
        db.add(cover_letter)
    await db.commit()
    await db.refresh(cover_letter)
    return cover_letter
