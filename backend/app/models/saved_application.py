"""Hand-curated job pipeline card — separate from aiapply's auto-apply
``JobApplication`` table and from the live Gmail application count.

Pure user-owned data; never touches Gmail. The auto-track bridge can populate
new cards from detected confirmation mail (idempotent on ``source_thread_id``),
but stage moves are always manual.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class SavedApplication(Base):
    __tablename__ = "saved_applications"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: uuid.uuid4().hex)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    company: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str] = mapped_column(String(200), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Tracker-board columns (parity with the user's spreadsheet): the job link
    # itself, which portal/source, location, salary, job type, work arrangement,
    # which resume was used, and a free-text contact (recruiter/HM).
    job_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_portal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salary: Mapped[str | None] = mapped_column(String(100), nullable=True)
    job_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    work_arrangement: Mapped[str | None] = mapped_column(String(50), nullable=True)
    resume_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    contact: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Gmail thread this card was auto-created from (null for hand-added cards).
    # The per-(user, thread) idempotency key the auto-tracker dedupes on.
    source_thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    # Pipeline stage — applied | assessment | interview.
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="applied")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="saved_applications")
