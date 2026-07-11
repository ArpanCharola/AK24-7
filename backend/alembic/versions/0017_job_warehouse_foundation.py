"""shared canonical job warehouse and aggregation foundation

Revision ID: e5a7c9d1f3b6
Revises: d4f6b8a0c2e5
Create Date: 2026-07-11 13:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5a7c9d1f3b6"
down_revision: Union[str, None] = "d4f6b8a0c2e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("normalized_domain", sa.String(255), nullable=True),
        sa.Column("classification", sa.String(30), nullable=False, server_default="direct_employer"),
        sa.Column("is_excluded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("exclusion_reason", sa.String(100), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        sa.Column("manually_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("normalized_name", "normalized_domain", name="uq_employer_identity"),
    )
    op.create_index("ix_employers_normalized_name", "employers", ["normalized_name"])
    op.create_index("ix_employers_normalized_domain", "employers", ["normalized_domain"])
    op.create_index("ix_employers_classification", "employers", ["classification", "is_excluded"])

    op.create_table(
        "demand_clusters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("signature", sa.String(64), nullable=False, unique=True),
        sa.Column("role_family", sa.String(100), nullable=False),
        sa.Column("query_terms", sa.JSON(), nullable=False),
        sa.Column("skill_cluster", sa.JSON(), nullable=True),
        sa.Column("experience_band", sa.String(30), nullable=True),
        sa.Column("locations", sa.JSON(), nullable=True),
        sa.Column("work_arrangements", sa.JSON(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('queued','active','paused','failed')", name="ck_demand_cluster_status"),
    )
    op.create_index("ix_demand_clusters_role_family", "demand_clusters", ["role_family"])
    op.create_index("ix_demand_clusters_queue", "demand_clusters", ["status", "priority", "next_run_at"])

    op.create_table(
        "aggregation_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trigger", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("lease_key", sa.String(100), nullable=True, unique=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_unique", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_sightings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('queued','running','succeeded','partial','failed','cancelled')", name="ck_aggregation_run_status"),
    )
    op.create_index("ix_aggregation_runs_history", "aggregation_runs", ["started_at", "status"])

    op.create_table(
        "canonical_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("employer_id", sa.Integer(), sa.ForeignKey("employers.id"), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("normalized_title", sa.String(500), nullable=False),
        sa.Column("role_family", sa.String(100), nullable=True),
        sa.Column("seniority", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("location_normalized", sa.String(255), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("work_arrangement", sa.String(20), nullable=True),
        sa.Column("employment_type", sa.String(30), nullable=True),
        sa.Column("experience_min_years", sa.Float(), nullable=True),
        sa.Column("experience_max_years", sa.Float(), nullable=True),
        sa.Column("skills", sa.JSON(), nullable=True),
        sa.Column("salary_min", sa.Float(), nullable=True),
        sa.Column("salary_max", sa.Float(), nullable=True),
        sa.Column("salary_currency", sa.String(3), nullable=True),
        sa.Column("salary_period", sa.String(20), nullable=True),
        sa.Column("requisition_id", sa.String(255), nullable=True),
        sa.Column("canonical_url", sa.Text(), nullable=True),
        sa.Column("canonical_url_hash", sa.String(64), nullable=True),
        sa.Column("preferred_source", sa.String(50), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("duplicate_confidence", sa.Float(), nullable=True),
        sa.Column("possible_duplicate_of_id", sa.BigInteger(), sa.ForeignKey("canonical_jobs.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="live"),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('live','expired','quarantined','closed')", name="ck_canonical_job_status"),
        sa.UniqueConstraint("canonical_url_hash", name="uq_canonical_jobs_url_hash"),
    )
    op.create_index("ix_canonical_jobs_feed", "canonical_jobs", ["status", "posted_at", "role_family"])
    op.create_index("ix_canonical_jobs_location", "canonical_jobs", ["status", "location_normalized", "work_arrangement"])
    op.create_index("ix_canonical_jobs_employer_requisition", "canonical_jobs", ["employer_id", "requisition_id"])
    op.create_index("ix_canonical_jobs_fingerprint", "canonical_jobs", ["fingerprint"])

    op.create_table(
        "profile_demand_memberships",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("job_search_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demand_cluster_id", sa.Integer(), sa.ForeignKey("demand_clusters.id", ondelete="CASCADE"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("profile_id", "demand_cluster_id", name="uq_profile_demand_membership"),
    )
    op.create_index("ix_profile_demand_memberships_profile_id", "profile_demand_memberships", ["profile_id"])
    op.create_index("ix_profile_demand_active", "profile_demand_memberships", ["demand_cluster_id", "is_active"])

    op.create_table(
        "job_source_sightings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("canonical_job_id", sa.BigInteger(), sa.ForeignKey("canonical_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aggregation_run_id", sa.BigInteger(), sa.ForeignKey("aggregation_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_native_id", sa.String(500), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("source_url_hash", sa.String(64), nullable=False),
        sa.Column("source_confidence", sa.Float(), nullable=True),
        sa.Column("observed_metadata", sa.JSON(), nullable=True),
        sa.Column("source_posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("source", "source_native_id", name="uq_job_sighting_native_id"),
        sa.UniqueConstraint("source", "source_url_hash", name="uq_job_sighting_url_hash"),
    )
    op.create_index("ix_job_sightings_source_observed", "job_source_sightings", ["source", "observed_at"])
    op.create_index("ix_job_sightings_job_seen", "job_source_sightings", ["canonical_job_id", "last_seen_at"])

    op.create_table(
        "profile_job_matches",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("job_search_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("canonical_job_id", sa.BigInteger(), sa.ForeignKey("canonical_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("role_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("skill_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("experience_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("location_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("freshness_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("explanation_codes", sa.JSON(), nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="new"),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_profile_job_match_score"),
        sa.UniqueConstraint("profile_id", "canonical_job_id", name="uq_profile_canonical_job_match"),
    )
    op.create_index("ix_profile_job_matches_feed", "profile_job_matches", ["profile_id", "state", "score"])
    op.create_index("ix_profile_job_matches_job", "profile_job_matches", ["canonical_job_id", "state"])

    op.create_table(
        "source_run_metrics",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("aggregation_run_id", sa.BigInteger(), sa.ForeignKey("aggregation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("demand_cluster_id", sa.Integer(), sa.ForeignKey("demand_clusters.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("raw_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_unique", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_sightings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("watermark_before", sa.JSON(), nullable=True),
        sa.Column("watermark_after", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("aggregation_run_id", "source", "demand_cluster_id", name="uq_source_run_cluster_metric"),
    )
    op.create_index("ix_source_metrics_analytics", "source_run_metrics", ["source", "started_at"])

    op.create_table(
        "job_rejections",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("aggregation_run_id", sa.BigInteger(), sa.ForeignKey("aggregation_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("source_native_id", sa.String(500), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("employer_name", sa.String(255), nullable=True),
        sa.Column("reason_code", sa.String(50), nullable=False),
        sa.Column("reason_detail", sa.Text(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_rejections_analytics", "job_rejections", ["rejected_at", "source", "reason_code"])
    op.create_index("ix_job_rejections_expiry", "job_rejections", ["retain_until"])


def downgrade() -> None:
    for table in (
        "job_rejections",
        "source_run_metrics",
        "profile_job_matches",
        "job_source_sightings",
        "profile_demand_memberships",
        "canonical_jobs",
        "aggregation_runs",
        "demand_clusters",
        "employers",
    ):
        op.drop_table(table)
