"""merge automail: saved_applications table + consent fields on users

Revision ID: d6e7f8a9b0c1
Revises: c5cb960c646c
Create Date: 2026-05-28 12:00:00.000000

Adds Automail's `saved_applications` table (hand-curated Job Tracker, distinct
from aiapply's auto-apply `job_applications`) plus two consent-tracking columns
on `users` for the disclaimer gate. The columns are nullable (no backfill
needed) — until consent is recorded, the frontend shows the modal.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d6e7f8a9b0c1"
down_revision: Union[str, None] = "c5cb960c646c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Saved Job Tracker board — user-curated CRUD over a 3-stage pipeline.
    op.create_table(
        "saved_applications",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("company", sa.String(length=200), nullable=False),
        sa.Column("role", sa.String(length=200), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mail_url", sa.Text(), nullable=True),
        sa.Column("source_thread_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="applied"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_saved_applications_user_id"),
        "saved_applications",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_saved_applications_source_thread_id"),
        "saved_applications",
        ["source_thread_id"],
        unique=False,
    )

    # Consent gate (Stage 4) — recorded once per user; nullable since existing
    # rows haven't gone through the flow yet, the gate prompts them on next sign-in.
    op.add_column("users", sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("consented_scopes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "consented_scopes")
    op.drop_column("users", "consent_given_at")
    op.drop_index(op.f("ix_saved_applications_source_thread_id"), table_name="saved_applications")
    op.drop_index(op.f("ix_saved_applications_user_id"), table_name="saved_applications")
    op.drop_table("saved_applications")
