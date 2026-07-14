"""user desired roles for recommendation-first jobs

Revision ID: 0018_user_desired_roles
Revises: e5a7c9d1f3b6
Create Date: 2026-07-13 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = "0018_user_desired_roles"
down_revision: Union[str, None] = "e5a7c9d1f3b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = inspect(bind)
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if _has_column("users", "desired_roles"):
        return
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("desired_roles", sa.Text(), nullable=True))


def downgrade() -> None:
    if not _has_column("users", "desired_roles"):
        return
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("desired_roles")
