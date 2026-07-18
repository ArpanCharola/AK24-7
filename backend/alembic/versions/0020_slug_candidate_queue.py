"""Turn company_source into a resumable slug-probe queue.

The registry seeded 34 rows and had no automated path to grow: discovery was a
manual CLI and the only scheduled job (revalidation) prunes. These columns let a
short, resumable tick lease a batch of unprobed candidates, probe them, and
record a terminal state — so the registry can grow to 1000+ slugs a few hundred
probes at a time without ever running long enough to be killed.

`status` stays authoritative for the runtime slug loader; `probe_state` drives
the queue. `_upsert` keeps them in sync.

Revision ID: 0020_slug_candidate_queue
Revises: 0019_production_reconcile
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0020_slug_candidate_queue"
down_revision: Union[str, None] = "0019_production_reconcile"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "company_source",
        sa.Column(
            "probe_state",
            sa.String(length=16),
            nullable=False,
            server_default="candidate",
        ),
    )
    op.add_column(
        "company_source",
        sa.Column("probe_priority", sa.Integer(), nullable=False, server_default="100"),
    )
    op.add_column(
        "company_source",
        sa.Column("next_probe_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_source",
        sa.Column("probe_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "company_source",
        sa.Column("probe_leased_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "company_source",
        sa.Column("country_hint", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "company_source",
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Seed the queue from whatever the registry already knows. Anything not yet
    # proven active becomes a candidate, so an existing deployment starts
    # probing its 34 unverified seeds on the first tick.
    op.execute(
        """
        UPDATE company_source
           SET probe_state = CASE status
                               WHEN 'active' THEN 'active'
                               WHEN 'dead'   THEN 'dead'
                               ELSE 'candidate'
                             END
        """
    )
    # Recover slugs the old logic discarded. `_next_status` collapsed "endpoint
    # is gone" and "endpoint answered but had no India roles that day" into a
    # single `dead`, so every board that happened to be between India reqs at
    # probe time was retired permanently. A row that returned *any* postings is
    # a working endpoint and belongs in the monthly re-probe lane instead.
    op.execute(
        """
        UPDATE company_source
           SET probe_state = 'no_india',
               next_probe_at = NOW(),
               probe_attempts = 0,
               consecutive_dead_checks = 0
         WHERE status = 'dead' AND total_roles_count > 0
        """
    )

    # Existing rows are hand-curated seeds; rank them above harvested candidates.
    op.execute("UPDATE company_source SET probe_priority = 300")

    op.create_index(
        "ix_company_source_probe_queue",
        "company_source",
        ["probe_state", sa.text("probe_priority DESC"), "next_probe_at"],
    )
    # The ingest sweep pages through active rows by id; keep that index tight.
    op.create_index(
        "ix_company_source_active",
        "company_source",
        ["id"],
        postgresql_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_index("ix_company_source_active", table_name="company_source")
    op.drop_index("ix_company_source_probe_queue", table_name="company_source")
    for col in (
        "last_ingested_at",
        "country_hint",
        "probe_leased_until",
        "probe_attempts",
        "next_probe_at",
        "probe_priority",
        "probe_state",
    ):
        op.drop_column("company_source", col)
