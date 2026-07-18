"""Shared, user-agnostic pool of jobs discovered via the public
unauthenticated search endpoint.

JobPool is intentionally separate from DiscoveredJob (which is per-user).
A pool row is created the first time a job URL is seen, then refreshed
(last_seen_at, metadata) on subsequent appearances. Logged-in users pull
matching jobs from the pool into their own DiscoveredJobs via the
import-to-profile endpoint.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, Float, DateTime, Computed
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class JobPool(Base):
    __tablename__ = "job_pool"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Unique on URL so re-discovering the same posting updates rather than dupes.
    job_url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Which ATS host the URL points to (greenhouse | lever | ashby | workday |
    # icims | smartrecruiters | bamboohr | amazon | netflix | other).
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    work_arrangement: Mapped[str | None] = mapped_column(String(20), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # India-specific fields (parsed at discovery time).
    salary_lpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_raw: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notice_period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Search query (role) that surfaced this job — useful for "browse by topic".
    search_query: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    # ── Admission + ranking (populated at ingest; see services/job_admission) ──
    india_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # DB-generated; declared Computed so the ORM excludes them from INSERT/UPDATE
    # (Postgres rejects any explicit value into a GENERATED ALWAYS column).
    content_key: Mapped[str | None] = mapped_column(
        String(128),
        Computed("md5(lower(coalesce(company,'')) || '|' || lower(coalesce(title,'')))", persisted=True),
        nullable=True,
    )
    search_tsv: Mapped[str | None] = mapped_column(
        TSVECTOR,
        Computed(
            "setweight(to_tsvector('simple', coalesce(title,'')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(company,'')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(location,'')), 'C')",
            persisted=True,
        ),
        nullable=True,
    )
