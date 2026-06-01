from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class JobSearchProfile(Base):
    __tablename__ = "job_search_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    target_roles: Mapped[str | None] = mapped_column(Text, nullable=True)
    locations: Mapped[str | None] = mapped_column(Text, nullable=True)
    keywords: Mapped[str | None] = mapped_column(Text, nullable=True)
    excluded_companies: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    work_arrangements: Mapped[str | None] = mapped_column(String(100), nullable=True)  # e.g. "remote,hybrid"
    posted_within_days: Mapped[int | None] = mapped_column(Integer, nullable=True)  # e.g. 14
    # India preferences
    min_salary_lpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Cached resume-driven search queries (JSON list) — regenerated when resume/roles change.
    generated_queries: Mapped[str | None] = mapped_column(Text, nullable=True)
    # NOTE: auto_apply_* below are deprecated for the India product (no autonomous apply in v1).
    auto_apply_threshold: Mapped[int] = mapped_column(Integer, default=75)
    auto_apply_mode: Mapped[str] = mapped_column(String(20), default="review", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="job_search_profiles")
    discovered_jobs: Mapped[list["DiscoveredJob"]] = relationship(back_populates="search_profile")
