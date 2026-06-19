"""Hand-curated Job Tracker — full CRUD over the user's pipeline board.

Distinct from aiapply's existing ``/api/applications`` (the auto-apply pipeline)
and from the live ``/api/mail-applications/tracker`` count — this is editable,
user-owned data with three columns: applied | assessment | interview. The
auto-track bridge (POST /api/mail-applications/auto-track) creates `applied`
cards from detected confirmation mail; users move them through the columns
themselves.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.saved_application import SavedApplication
from app.models.user import User
from app.schemas.saved_application import (
    ALLOWED_STATUSES,
    SavedApplicationCreate,
    SavedApplicationOut,
    SavedApplicationUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _get_owned(db: AsyncSession, user: User, app_id: str) -> SavedApplication:
    row = (await db.execute(
        select(SavedApplication).where(
            SavedApplication.id == app_id,
            SavedApplication.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Saved application not found")
    return row


@router.get(
    "/",
    response_model=List[SavedApplicationOut],
    summary="List the jobs you've saved",
    description="Returns every job application you've added to your tracker, newest application first. This is your own hand-curated list — separate from the automatic Gmail tracker.",
)
async def list_saved_applications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(
        select(SavedApplication)
        .where(SavedApplication.user_id == current_user.id)
        .order_by(SavedApplication.applied_at.desc(), SavedApplication.created_at.desc())
    )).scalars().all()
    return list(rows)


@router.post(
    "/",
    response_model=SavedApplicationOut,
    status_code=201,
    summary="Save a job application",
    description="Adds a job to your tracker — the company, the role, when you applied, an optional link to the email, and which stage it's at.",
)
async def create_saved_application(
    payload: SavedApplicationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Idempotent on the source Gmail thread: if this thread is already tracked
    # (auto-tracker created it, or the user clicked save twice), return the
    # existing row instead of making a duplicate card.
    if payload.source_thread_id:
        existing = (await db.execute(
            select(SavedApplication).where(
                SavedApplication.user_id == current_user.id,
                SavedApplication.source_thread_id == payload.source_thread_id,
            )
        )).scalar_one_or_none()
        if existing:
            return existing

    row = SavedApplication(
        user_id=current_user.id,
        company=payload.company,
        role=payload.role,
        applied_at=payload.applied_at,
        mail_url=payload.mail_url,
        status=payload.status,
        notes=payload.notes,
        job_link=payload.job_link,
        job_portal=payload.job_portal,
        location=payload.location,
        salary=payload.salary,
        job_type=payload.job_type,
        work_arrangement=payload.work_arrangement,
        resume_label=payload.resume_label,
        contact=payload.contact,
        source_thread_id=payload.source_thread_id,
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except Exception as exc:
        await db.rollback()
        logger.exception("create saved_application failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return row


class FromLinkRequest(BaseModel):
    url: str = Field(..., min_length=4, max_length=2000)
    status: str = Field(default="to apply")


@router.post(
    "/from-link",
    response_model=SavedApplicationOut,
    status_code=201,
    summary="Add a job to your tracker from any link you paste",
    description="Paste a job URL from anywhere (LinkedIn, Wellfound, a company page, …). "
                "We fetch it, pull out the company/role/location, classify the portal, and "
                "create a tracker card you can edit.",
)
async def create_from_link(
    payload: FromLinkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    url = payload.url.strip()
    status = payload.status.strip().lower()
    if status not in ALLOWED_STATUSES:
        status = "to apply"

    company, role, location = None, None, None
    try:
        from app.services.jd_extractor import jd_from_url
        data = await jd_from_url(url)
        company = (data.get("company") or None)
        role = (data.get("job_title") or None)
        location = (data.get("location") or None)
    except Exception:  # noqa: BLE001 — extraction is best-effort; card still saves
        logger.info("from-link: could not extract JD for %s", url)

    try:
        from app.api.routes.public_jobs import _classify_source
        portal = _classify_source(url)
    except Exception:  # noqa: BLE001
        portal = None

    row = SavedApplication(
        user_id=current_user.id,
        company=(company or "Unknown company")[:200],
        role=(role or "Role not specified")[:200],
        applied_at=datetime.now(timezone.utc),
        status=status,
        job_link=url,
        mail_url=url,
        job_portal=(portal or None),
        location=(location[:200] if location else None),
    )
    db.add(row)
    try:
        await db.commit()
        await db.refresh(row)
    except Exception as exc:
        await db.rollback()
        logger.exception("create_from_link failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return row


@router.patch(
    "/{app_id}",
    response_model=SavedApplicationOut,
    summary="Update a saved application",
    description="Edits a saved job — moving stage, fixing the role, attaching a link. Only the fields you send are changed.",
)
async def update_saved_application(
    app_id: str,
    payload: SavedApplicationUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_owned(db, current_user, app_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(row, field, value)
    try:
        await db.commit()
        await db.refresh(row)
    except Exception as exc:
        await db.rollback()
        logger.exception("update saved_application failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return row


@router.delete(
    "/{app_id}",
    summary="Remove a saved application",
    description="Deletes one job from your tracker. Only removes your saved record — never touches the email in Gmail.",
)
async def delete_saved_application(
    app_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_owned(db, current_user, app_id)
    try:
        await db.delete(row)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("delete saved_application failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return {"deleted": app_id}
