from datetime import datetime, timezone
from sqlalchemy import String, Text, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TailoredResume(Base):
    __tablename__ = "tailored_resumes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    application_id: Mapped[int] = mapped_column(ForeignKey("job_applications.id"), nullable=True)
    original_resume_path: Mapped[str] = mapped_column(String(1024), nullable=True)
    original_resume_text: Mapped[str] = mapped_column(Text, nullable=True)
    tailored_resume_path: Mapped[str] = mapped_column(String(1024), nullable=True)
    keywords_extracted: Mapped[str] = mapped_column(Text, nullable=True)
    modifications_summary: Mapped[str] = mapped_column(Text, nullable=True)
    label: Mapped[str] = mapped_column(String(255), nullable=True)
    job_description: Mapped[str] = mapped_column(Text, nullable=True)
    # Source job link the JD was extracted from (paste-a-URL tailoring flow).
    job_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="resumes")
    application: Mapped["JobApplication"] = relationship(back_populates="tailored_resume")
