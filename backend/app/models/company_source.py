"""Registry of India-employer ATS slugs that feed Tier-1 discovery.

Replaces the static india_company_slugs.json as the source of truth (the JSON
stays as a seed + offline fallback). Each row is one (ats, slug) endpoint we can
probe. The slug-discovery pipeline harvests candidates (Common Crawl + public
datasets + curated lists), probes each ATS's public API, and writes the result
here: `status="active"` once the endpoint returns >=1 India role, `dead` once it
stops (with hysteresis), `unverified` until first probed. The daily revalidation
job keeps india_roles_count / last_validated_at fresh and prunes dead slugs.

workday/zoho carry their full adapter config in `config_json` (the adapters take
dict entries, not bare slugs); for those rows `slug` is the subdomain/company key.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, Integer, DateTime, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanySource(Base):
    __tablename__ = "company_source"
    __table_args__ = (
        # Natural key — one row per endpoint; lets the pipeline upsert idempotently.
        UniqueConstraint("ats", "slug", name="uq_company_source_ats_slug"),
        # The exact filter the runtime loader + revalidation queries use.
        Index("ix_company_source_ats_status", "ats", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # greenhouse | lever | ashby | smartrecruiters | workable | recruitee |
    # breezy | personio | workday | zoho
    ats: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # Bare slug / company-id / subdomain. SmartRecruiters ids are case-sensitive.
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # unverified (default) | active | dead
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unverified", index=True
    )
    # Postings passing _is_india_location AND not _is_excluded_job at last probe.
    india_roles_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # All postings returned — distinguishes "dead endpoint" from "no India roles".
    total_roles_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    last_seen_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # seed_json | commoncrawl | dataset_leadita | dataset_jba | curated | manual
    source_of_discovery: Mapped[str] = mapped_column(
        String(50), nullable=False, default="manual"
    )
    # Hysteresis: only demote to "dead" after N consecutive failed probes.
    consecutive_dead_checks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    # Full adapter config for workday/zoho ({company, subdomain, tenant, site} /
    # {company, feed_url}). NULL for slug-only ATSes.
    config_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
