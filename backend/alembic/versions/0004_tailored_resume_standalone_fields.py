"""tailored_resumes: add fields for standalone (non-application) entries

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-05-27 14:00:00.000000

Adds:
- tailored_resumes.original_resume_text — the source resume text the user pasted/uploaded
  (used as the "before" side of the diff for standalone Quick Tailor entries that aren't
  tied to a JobApplication and therefore can't fall back to User.resume_text)
- tailored_resumes.label — optional user-friendly label for standalone entries
- tailored_resumes.job_description — the JD the user tailored against (for standalone entries
  there's no JobApplication to read it from)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('tailored_resumes', sa.Column('original_resume_text', sa.Text(), nullable=True))
    op.add_column('tailored_resumes', sa.Column('label', sa.String(length=255), nullable=True))
    op.add_column('tailored_resumes', sa.Column('job_description', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('tailored_resumes', 'job_description')
    op.drop_column('tailored_resumes', 'label')
    op.drop_column('tailored_resumes', 'original_resume_text')
