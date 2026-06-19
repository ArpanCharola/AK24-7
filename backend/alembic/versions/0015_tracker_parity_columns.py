"""saved_applications tracker-parity columns (job link, portal, location, salary, type, contact)

Revision ID: c3e5a7b9d1f2
Revises: b8d2f4a6c1e3
Create Date: 2026-06-19 11:30:00.000000

Brings the hand-curated Job Tracker to parity with the user's spreadsheet:
Company, Role, Job Portal, Location, Salary, Job Type, Resume, Job Link,
Status, Notes, Contacts. All new columns nullable — no backfill.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3e5a7b9d1f2"
down_revision: Union[str, None] = "b8d2f4a6c1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("saved_applications") as batch_op:
        batch_op.add_column(sa.Column("job_link", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("job_portal", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("location", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("salary", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("job_type", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("work_arrangement", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("resume_label", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("contact", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("saved_applications") as batch_op:
        batch_op.drop_column("contact")
        batch_op.drop_column("resume_label")
        batch_op.drop_column("work_arrangement")
        batch_op.drop_column("job_type")
        batch_op.drop_column("salary")
        batch_op.drop_column("location")
        batch_op.drop_column("job_portal")
        batch_op.drop_column("job_link")
