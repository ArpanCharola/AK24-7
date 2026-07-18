"""Persisted admission + search columns on job_pool.

Moves India/quality/employment classification and search out of per-request
Python loops (which capped at ~1500 rows and broke deep pagination) into indexed
SQL columns:

  india_confidence  graded India applicability (job_admission.india_confidence)
  employment_type   fulltime | internship | contract | parttime
  quality_score     ranking input, computed at ingest
  content_key       md5(company|title) for SQL-side dedupe (generated)
  search_tsv        weighted tsvector over title/company/location (generated)

Plus pg_trgm + GIN indexes so role/location filtering is index-backed. The
classification columns are populated by the ingest path going forward and by a
one-off backfill for existing rows.

Revision ID: 0023_job_pool_quality_search
Revises: 0022_api_credit_ledger
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision: str = "0023_job_pool_quality_search"
down_revision: Union[str, None] = "0022_api_credit_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("job_pool", sa.Column("india_confidence", sa.Float(), nullable=True))
    op.add_column("job_pool", sa.Column("employment_type", sa.String(length=16), nullable=True))
    op.add_column("job_pool", sa.Column("quality_score", sa.Float(), nullable=True))
    op.add_column("job_pool", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "job_pool",
        sa.Column(
            "content_key",
            sa.String(length=128),
            sa.Computed("md5(lower(coalesce(company,'')) || '|' || lower(coalesce(title,'')))", persisted=True),
            nullable=True,
        ),
    )
    # 'simple' config, not 'english': role tokens (SDE, QA, MLOps) must not be
    # stemmed. Weighted so a title hit outranks a location hit.
    op.add_column(
        "job_pool",
        sa.Column(
            "search_tsv",
            TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('simple', coalesce(title,'')), 'A') || "
                "setweight(to_tsvector('simple', coalesce(company,'')), 'B') || "
                "setweight(to_tsvector('simple', coalesce(location,'')), 'C')",
                persisted=True,
            ),
            nullable=True,
        ),
    )

    # Backfill so existing rows stay searchable the instant this deploys. The
    # old ingest path already applied the strict India filter before writing to
    # job_pool, so every existing row is an India role — 1.0 is correct, and the
    # next ingest sweep re-grades any that are actually global-remote. Without
    # this, the serving filter `india_confidence >= 0.5` would hide the entire
    # existing catalogue until re-ingested — a silent production outage.
    op.execute("UPDATE job_pool SET india_confidence = 1.0 WHERE india_confidence IS NULL")
    op.execute("UPDATE job_pool SET employment_type = 'fulltime' WHERE employment_type IS NULL")

    # tsvector GIN needs no extension — always safe.
    op.create_index("ix_job_pool_search_tsv", "job_pool", ["search_tsv"], postgresql_using="gin")
    op.create_index(
        "ix_job_pool_live", "job_pool", [sa.text("last_seen_at DESC")],
        postgresql_where=sa.text("india_confidence >= 0.5"),
    )

    # pg_trgm is optional: the trgm indexes only speed up city substring matches,
    # which work (seq scan) without them. On a locked-down Postgres role
    # CREATE EXTENSION can fail — so attempt it and the trgm indexes inside a
    # guarded PL/pgSQL block that degrades gracefully instead of aborting the
    # whole migration (and the deploy).
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS pg_trgm;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'pg_trgm unavailable (%); skipping trigram indexes', SQLERRM;
        END $$;
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
                CREATE INDEX IF NOT EXISTS ix_job_pool_title_trgm
                    ON job_pool USING gin (lower(title) gin_trgm_ops);
                CREATE INDEX IF NOT EXISTS ix_job_pool_location_trgm
                    ON job_pool USING gin (lower(location) gin_trgm_ops);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # IF EXISTS — the trgm indexes may have been skipped when pg_trgm was absent.
    for ix in ("ix_job_pool_live", "ix_job_pool_location_trgm",
               "ix_job_pool_title_trgm", "ix_job_pool_search_tsv"):
        op.execute(f"DROP INDEX IF EXISTS {ix}")
    for col in ("search_tsv", "content_key", "expires_at", "quality_score",
                "employment_type", "india_confidence"):
        op.drop_column("job_pool", col)
