"""reconcile production profile and warehouse schema

Revision ID: 0019_production_reconcile
Revises: 0018_user_desired_roles
Create Date: 2026-07-15 19:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "0019_production_reconcile"
down_revision: Union[str, None] = "0018_user_desired_roles"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WAREHOUSE_TABLES = (
    "employers",
    "demand_clusters",
    "aggregation_runs",
    "canonical_jobs",
    "profile_demand_memberships",
    "job_source_sightings",
    "profile_job_matches",
    "source_run_metrics",
    "job_rejections",
)


def _has_column(bind, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspect(bind).get_columns(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("users") and not _has_column(bind, "users", "desired_roles"):
        with op.batch_alter_table("users") as batch_op:
            batch_op.add_column(sa.Column("desired_roles", sa.Text(), nullable=True))

    # Repair databases that were incorrectly stamped after create_all. The
    # operation is check-first and only creates missing warehouse tables.
    from app.core.database import Base
    import app.models  # noqa: F401

    missing = [name for name in _WAREHOUSE_TABLES if not inspect(bind).has_table(name)]
    if missing:
        tables = [Base.metadata.tables[name] for name in _WAREHOUSE_TABLES]
        Base.metadata.create_all(bind=bind, tables=tables, checkfirst=True)


def downgrade() -> None:
    # Reconciliation is deliberately non-destructive: older application code
    # can safely ignore these nullable/additive structures.
    pass
