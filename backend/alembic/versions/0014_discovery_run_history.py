"""discovery_run history table

Revision ID: b8d2f4a6c1e3
Revises: a7c9e1f3b5d2
Create Date: 2026-06-19 11:00:00.000000

Auditable history of every job-search / discovery / pool-warm run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8d2f4a6c1e3"
down_revision: Union[str, None] = "a7c9e1f3b5d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "discovery_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("run_type", sa.String(length=30), nullable=False),
        sa.Column("queries", sa.Text(), nullable=True),
        sa.Column("locations", sa.String(length=255), nullable=True),
        sa.Column("jobs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stats", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_discovery_run_id", "discovery_run", ["id"], unique=False)
    op.create_index("ix_discovery_run_user_id", "discovery_run", ["user_id"], unique=False)
    op.create_index("ix_discovery_run_run_type", "discovery_run", ["run_type"], unique=False)
    op.create_index("ix_discovery_run_created_at", "discovery_run", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_discovery_run_created_at", table_name="discovery_run")
    op.drop_index("ix_discovery_run_run_type", table_name="discovery_run")
    op.drop_index("ix_discovery_run_user_id", table_name="discovery_run")
    op.drop_index("ix_discovery_run_id", table_name="discovery_run")
    op.drop_table("discovery_run")
