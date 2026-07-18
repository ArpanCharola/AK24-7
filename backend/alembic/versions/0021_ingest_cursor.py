"""Checkpoint table for resumable supply ticks.

Revision ID: 0021_ingest_cursor
Revises: 0020_slug_candidate_queue
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021_ingest_cursor"
down_revision: Union[str, None] = "0020_slug_candidate_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_cursor",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("cursor_value", sa.String(length=255), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_stats", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("ingest_cursor")
