from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import String, Text, ForeignKey, DateTime, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ApplicationStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_OTP = "awaiting_otp"
    AWAITING_CAPTCHA = "awaiting_captcha"
    COMPLETED = "completed"
    FAILED = "failed"


class JobApplication(Base):
    __tablename__ = "job_applications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    job_title: Mapped[str] = mapped_column(String(255), nullable=True)
    company: Mapped[str] = mapped_column(String(255), nullable=True)
    job_description: Mapped[str] = mapped_column(Text, nullable=True)
    portal_type: Mapped[str] = mapped_column(String(50), nullable=True)  # workday, icims, greenhouse
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.PENDING
    )
    queued_by: Mapped[str] = mapped_column(String(10), default="manual", nullable=False)
    celery_task_id: Mapped[str] = mapped_column(String(255), nullable=True)
    agent_log: Mapped[str] = mapped_column(Text, nullable=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    # Post-submission lifecycle derived from the user's Gmail (Phase 7). Separate
    # axis from `status` (which tracks the apply *run*): confirmed|assessment|interview.
    stage: Mapped[str | None] = mapped_column(String(20), nullable=True)
    stage_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Latest repliable *human* email in this application's thread (Phase 7 follow-ups).
    # Only set for non-no-reply senders, so no-reply confirmations never enable a send.
    last_human_email_from: Mapped[str | None] = mapped_column(String(320), nullable=True)
    last_human_email_thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_human_email_msgid: Mapped[str | None] = mapped_column(String(998), nullable=True)
    followup_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship(back_populates="applications")
    tailored_resume: Mapped["TailoredResume"] = relationship(back_populates="application", uselist=False)
    cover_letter: Mapped["CoverLetter"] = relationship(back_populates="application", uselist=False)
