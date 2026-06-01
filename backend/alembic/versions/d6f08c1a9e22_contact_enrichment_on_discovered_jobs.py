"""Contact enrichment columns on discovered_jobs

Revision ID: d6f08c1a9e22
Revises: c5cb960c646c
Create Date: 2026-05-29 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6f08c1a9e22"
down_revision: Union[str, None] = "c5cb960c646c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("discovered_jobs") as batch_op:
        batch_op.add_column(sa.Column("contact_email", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("contact_linkedin", sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column("contact_name", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("contact_source", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("contact_enriched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("discovered_jobs") as batch_op:
        batch_op.drop_column("contact_enriched_at")
        batch_op.drop_column("contact_source")
        batch_op.drop_column("contact_name")
        batch_op.drop_column("contact_linkedin")
        batch_op.drop_column("contact_email")
