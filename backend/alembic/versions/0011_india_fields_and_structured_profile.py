"""India fields, why-fit, structured profile, tailored job_url + FTS index

Revision ID: e1f2a3b4c5d6
Revises: 9b6db8726e3f
Create Date: 2026-05-31 12:00:00.000000

AK24/7Jobs pivot (India). Adds:
- discovered_jobs: salary_lpa, salary_raw, notice_period, match_explanation, missing_skills
- job_search_profiles: min_salary_lpa, max_notice_period_days, generated_queries
- job_pool: salary_lpa, salary_raw, notice_period
- tailored_resumes: job_url
- users: structured profile (profile_summary, work_experience, education, skills,
  projects, certifications) + India context (current/expected CTC LPA, notice period,
  preferred locations)
- GIN full-text index on job_pool (title + company + job_description) for lexical retrieval.

All columns nullable — no backfill needed. (pgvector embedding columns are a separate
fast-follow migration, applied after swapping to a pgvector-enabled Postgres image.)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "9b6db8726e3f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("discovered_jobs") as batch_op:
        batch_op.add_column(sa.Column("match_explanation", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("missing_skills", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("salary_lpa", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("salary_raw", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("notice_period", sa.String(length=20), nullable=True))

    with op.batch_alter_table("job_search_profiles") as batch_op:
        batch_op.add_column(sa.Column("min_salary_lpa", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("max_notice_period_days", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("generated_queries", sa.Text(), nullable=True))

    with op.batch_alter_table("job_pool") as batch_op:
        batch_op.add_column(sa.Column("salary_lpa", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("salary_raw", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("notice_period", sa.String(length=20), nullable=True))

    with op.batch_alter_table("tailored_resumes") as batch_op:
        batch_op.add_column(sa.Column("job_url", sa.String(length=1024), nullable=True))

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("profile_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("work_experience", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("education", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("skills", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("projects", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("certifications", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("current_ctc_lpa", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("expected_ctc_lpa", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("notice_period_days", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("preferred_locations", sa.Text(), nullable=True))

    # Lexical retrieval over the shared job pool (Postgres FTS; pairs with pgvector later).
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_job_pool_fts ON job_pool "
        "USING GIN (to_tsvector('english', "
        "coalesce(title,'') || ' ' || coalesce(company,'') || ' ' || coalesce(job_description,'')))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_job_pool_fts")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("preferred_locations")
        batch_op.drop_column("notice_period_days")
        batch_op.drop_column("expected_ctc_lpa")
        batch_op.drop_column("current_ctc_lpa")
        batch_op.drop_column("certifications")
        batch_op.drop_column("projects")
        batch_op.drop_column("skills")
        batch_op.drop_column("education")
        batch_op.drop_column("work_experience")
        batch_op.drop_column("profile_summary")

    with op.batch_alter_table("tailored_resumes") as batch_op:
        batch_op.drop_column("job_url")

    with op.batch_alter_table("job_pool") as batch_op:
        batch_op.drop_column("notice_period")
        batch_op.drop_column("salary_raw")
        batch_op.drop_column("salary_lpa")

    with op.batch_alter_table("job_search_profiles") as batch_op:
        batch_op.drop_column("generated_queries")
        batch_op.drop_column("max_notice_period_days")
        batch_op.drop_column("min_salary_lpa")

    with op.batch_alter_table("discovered_jobs") as batch_op:
        batch_op.drop_column("notice_period")
        batch_op.drop_column("salary_raw")
        batch_op.drop_column("salary_lpa")
        batch_op.drop_column("missing_skills")
        batch_op.drop_column("match_explanation")
