"""user experience years/months (drives entry/mid/senior job targeting)

Revision ID: d4f6b8a0c2e5
Revises: c3e5a7b9d1f2
Create Date: 2026-06-20 22:30:00.000000

Adds experience_years + experience_months to users. Both nullable — no backfill.
Replaces the old CTC/notice-period profile inputs with a single experience
figure the simplified profile collects.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f6b8a0c2e5"
down_revision: Union[str, None] = "c3e5a7b9d1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("experience_years", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("experience_months", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("experience_months")
        batch_op.drop_column("experience_years")
