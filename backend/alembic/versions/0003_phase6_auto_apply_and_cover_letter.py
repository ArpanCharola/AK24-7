"""phase 6 auto-apply gate and cover letters

Revision ID: a1b2c3d4e5f6
Revises: de46f82dc80b
Create Date: 2026-05-27 12:00:00.000000

Adds:
- users.auto_apply_enabled, users.daily_auto_apply_cap (master gate)
- job_search_profiles.auto_apply_mode ("auto" | "review")
- discovered_jobs.scored_at (cache to skip re-scoring within 7d)
- job_applications.queued_by ("manual" | "auto")
- cover_letters table

DiscoveredJob.status is a free-form String(50) — no schema change needed
to accept the new "auto_queued" value.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'de46f82dc80b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('auto_apply_enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        'users',
        sa.Column('daily_auto_apply_cap', sa.Integer(), nullable=False, server_default='5'),
    )

    op.add_column(
        'job_search_profiles',
        sa.Column('auto_apply_mode', sa.String(length=20), nullable=False, server_default='review'),
    )

    op.add_column(
        'discovered_jobs',
        sa.Column('scored_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        'job_applications',
        sa.Column('queued_by', sa.String(length=10), nullable=False, server_default='manual'),
    )

    op.create_table(
        'cover_letters',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('job_applications.id'), nullable=False, unique=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('cover_letters')
    op.drop_column('job_applications', 'queued_by')
    op.drop_column('discovered_jobs', 'scored_at')
    op.drop_column('job_search_profiles', 'auto_apply_mode')
    op.drop_column('users', 'daily_auto_apply_cap')
    op.drop_column('users', 'auto_apply_enabled')
