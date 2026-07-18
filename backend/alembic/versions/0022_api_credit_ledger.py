"""Monthly spend ledger for metered external APIs (SerpAPI).

Revision ID: 0022_api_credit_ledger
Revises: 0021_ingest_cursor
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0022_api_credit_ledger"
down_revision: Union[str, None] = "0021_ingest_cursor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_credit_ledger",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("period_ym", sa.String(length=7), nullable=False),
        sa.Column("used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "period_ym", name="uq_api_credit_provider_period"),
    )


def downgrade() -> None:
    op.drop_table("api_credit_ledger")
