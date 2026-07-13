"""user desired roles for recommendation-first jobs

Revision ID: 0018_user_desired_roles
Revises: 0017_job_warehouse_foundation
Create Date: 2026-07-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0018_user_desired_roles"
down_revision: Union[str, None] = "0017_job_warehouse_foundation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("desired_roles", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("desired_roles")
