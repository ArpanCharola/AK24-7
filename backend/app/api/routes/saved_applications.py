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

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.saved_application import SavedApplication
from app.models.user import User
from app.schemas.saved_application import (
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
