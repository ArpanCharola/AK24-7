"""merge contact_enrichment + automail heads

Revision ID: 0696a7f5c1e6
Revises: d6e7f8a9b0c1, d6f08c1a9e22
Create Date: 2026-05-29 02:56:38.798396

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0696a7f5c1e6'
down_revision: Union[str, None] = ('d6e7f8a9b0c1', 'd6f08c1a9e22')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
