from __future__ import annotations
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class SentEmail(Base):
    """Audit log of every email AI Apply sent on the user's behalf — both
    review-first composes and autonomous follow-ups. Also used to enforce the
    per-application 'one follow-up' rule and the per-user daily send cap."""
    __tablename__ = "sent_emails"
    __table_args__ = (Index("ix_sent_emails_app_kind", "application_id", "kind"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_applications.id"), nullable=True
    )
    to_addr: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # compose|follow_up|thank_you|reply
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="sent_emails")
