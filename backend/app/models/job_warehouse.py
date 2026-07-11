"""Canonical job warehouse and shared aggregation demand models.

These tables intentionally live alongside the legacy ``job_pool`` and
``discovered_jobs`` tables.  The aggregator can shadow-write here before API
reads are migrated, which makes the warehouse rollout reversible.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Employer(Base):
    __tablename__ = "employers"
    __table_args__ = (
        UniqueConstraint("normalized_name", "normalized_domain", name="uq_employer_identity"),
        Index("ix_employers_classification", "classification", "is_excluded"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    classification: Mapped[str] = mapped_column(String(30), default="direct_employer", nullable=False)
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    manually_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    jobs: Mapped[list["CanonicalJob"]] = relationship(back_populates="employer")


class CanonicalJob(Base):
    __tablename__ = "canonical_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('live','expired','quarantined','closed')", name="ck_canonical_job_status"),
        UniqueConstraint("canonical_url_hash", name="uq_canonical_jobs_url_hash"),
        Index("ix_canonical_jobs_feed", "status", "posted_at", "role_family"),
        Index("ix_canonical_jobs_location", "status", "location_normalized", "work_arrangement"),
        Index("ix_canonical_jobs_employer_requisition", "employer_id", "requisition_id"),
        Index("ix_canonical_jobs_fingerprint", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employer_id: Mapped[int] = mapped_column(ForeignKey("employers.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_title: Mapped[str] = mapped_column(String(500), nullable=False)
    role_family: Mapped[str | None] = mapped_column(String(100), nullable=True)
    seniority: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location_normalized: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    work_arrangement: Mapped[str | None] = mapped_column(String(20), nullable=True)
    employment_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    experience_min_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    experience_max_years: Mapped[float | None] = mapped_column(Float, nullable=True)
    skills: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String(20), nullable=True)
    requisition_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_url_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferred_source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    duplicate_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    possible_duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("canonical_jobs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="live", nullable=False)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    employer: Mapped[Employer] = relationship(back_populates="jobs")
    sightings: Mapped[list["JobSourceSighting"]] = relationship(back_populates="canonical_job", cascade="all, delete-orphan")
    profile_matches: Mapped[list["ProfileJobMatch"]] = relationship(back_populates="canonical_job", cascade="all, delete-orphan")


class DemandCluster(Base):
    __tablename__ = "demand_clusters"
    __table_args__ = (
        CheckConstraint("status IN ('queued','active','paused','failed')", name="ck_demand_cluster_status"),
        Index("ix_demand_clusters_queue", "status", "priority", "next_run_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    signature: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role_family: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    query_terms: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    skill_cluster: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    experience_band: Mapped[str | None] = mapped_column(String(30), nullable=True)
    locations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    work_arrangements: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    profile_memberships: Mapped[list["ProfileDemandMembership"]] = relationship(back_populates="demand_cluster", cascade="all, delete-orphan")


class ProfileDemandMembership(Base):
    __tablename__ = "profile_demand_memberships"
    __table_args__ = (
        UniqueConstraint("profile_id", "demand_cluster_id", name="uq_profile_demand_membership"),
        Index("ix_profile_demand_active", "demand_cluster_id", "is_active"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("job_search_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    demand_cluster_id: Mapped[int] = mapped_column(ForeignKey("demand_clusters.id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    demand_cluster: Mapped[DemandCluster] = relationship(back_populates="profile_memberships")


class AggregationRun(Base):
    __tablename__ = "aggregation_runs"
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','succeeded','partial','failed','cancelled')", name="ck_aggregation_run_status"),
        Index("ix_aggregation_runs_history", "started_at", "status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trigger: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    lease_key: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_unique: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_sightings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    source_metrics: Mapped[list["SourceRunMetric"]] = relationship(back_populates="aggregation_run", cascade="all, delete-orphan")
    sightings: Mapped[list["JobSourceSighting"]] = relationship(back_populates="aggregation_run")


class JobSourceSighting(Base):
    __tablename__ = "job_source_sightings"
    __table_args__ = (
        UniqueConstraint("source", "source_native_id", name="uq_job_sighting_native_id"),
        UniqueConstraint("source", "source_url_hash", name="uq_job_sighting_url_hash"),
        Index("ix_job_sightings_source_observed", "source", "observed_at"),
        Index("ix_job_sightings_job_seen", "canonical_job_id", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    canonical_job_id: Mapped[int] = mapped_column(ForeignKey("canonical_jobs.id", ondelete="CASCADE"), nullable=False)
    aggregation_run_id: Mapped[int | None] = mapped_column(ForeignKey("aggregation_runs.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_native_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    observed_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    source_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    canonical_job: Mapped[CanonicalJob] = relationship(back_populates="sightings")
    aggregation_run: Mapped[AggregationRun | None] = relationship(back_populates="sightings")


class ProfileJobMatch(Base):
    __tablename__ = "profile_job_matches"
    __table_args__ = (
        UniqueConstraint("profile_id", "canonical_job_id", name="uq_profile_canonical_job_match"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_profile_job_match_score"),
        Index("ix_profile_job_matches_feed", "profile_id", "state", "score"),
        Index("ix_profile_job_matches_job", "canonical_job_id", "state"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("job_search_profiles.id", ondelete="CASCADE"), nullable=False)
    canonical_job_id: Mapped[int] = mapped_column(ForeignKey("canonical_jobs.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    role_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    skill_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    experience_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    location_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    freshness_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    explanation_codes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    canonical_job: Mapped[CanonicalJob] = relationship(back_populates="profile_matches")


class SourceRunMetric(Base):
    __tablename__ = "source_run_metrics"
    __table_args__ = (
        UniqueConstraint("aggregation_run_id", "source", "demand_cluster_id", name="uq_source_run_cluster_metric"),
        Index("ix_source_metrics_analytics", "source", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregation_run_id: Mapped[int] = mapped_column(ForeignKey("aggregation_runs.id", ondelete="CASCADE"), nullable=False)
    demand_cluster_id: Mapped[int | None] = mapped_column(ForeignKey("demand_clusters.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accepted_unique: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_sightings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watermark_before: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    watermark_after: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    aggregation_run: Mapped[AggregationRun] = relationship(back_populates="source_metrics")


class JobRejection(Base):
    __tablename__ = "job_rejections"
    __table_args__ = (
        Index("ix_job_rejections_analytics", "rejected_at", "source", "reason_code"),
        Index("ix_job_rejections_expiry", "retain_until"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    aggregation_run_id: Mapped[int | None] = mapped_column(ForeignKey("aggregation_runs.id", ondelete="SET NULL"), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    source_native_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    employer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason_code: Mapped[str] = mapped_column(String(50), nullable=False)
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    retain_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
