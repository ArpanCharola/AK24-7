from datetime import datetime, timezone
from sqlalchemy import String, Text, Integer, Float, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DiscoveredJob(Base):
    __tablename__ = "discovered_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    search_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_search_profiles.id"), nullable=True
    )
    job_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    work_arrangement: Mapped[str | None] = mapped_column(String(20), nullable=True)  # remote/hybrid/onsite/unknown
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    match_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Explainable why-fit (India/Jobright-style) — populated by the matching engine.
    match_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    missing_skills: Mapped[str | None] = mapped_column(Text, nullable=True)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # India-specific fields parsed at discovery time.
    salary_lpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notice_period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="discovered")
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # Contact enrichment — populated by services/contact_finder.py
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_linkedin: Mapped[str | None] = mapped_column(String(512), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Source: jd_regex | jd_llm | generic_verified | generic_unverified | apify
    contact_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    contact_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="discovered_jobs")
    search_profile: Mapped["JobSearchProfile"] = relationship(back_populates="discovered_jobs")
