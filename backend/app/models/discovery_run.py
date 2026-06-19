"""History of every job-search / discovery run.

One row per run so users (and the admin) get an auditable history of what was
searched, when, and how much came back. run_type distinguishes the engine:
  - profile_discovery : a user's per-profile discovery (role-targeted)
  - pool_warm         : the generalized, role-agnostic JobPool refresh
  - slug_discovery    : a slug-registry growth/validation wave
  - external_link     : a user pasted their own job link
user_id/profile_id are NULL for global (non-user) runs like pool_warm.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DiscoveryRun(Base):
    __tablename__ = "discovery_run"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    profile_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    queries: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    locations: Mapped[str | None] = mapped_column(String(255), nullable=True)
    jobs_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )