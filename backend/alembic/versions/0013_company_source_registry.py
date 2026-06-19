"""company_source registry (DB-backed ATS slug registry, seeded from JSON)

Revision ID: a7c9e1f3b5d2
Revises: f0a1b2c3d4e5
Create Date: 2026-06-19 10:00:00.000000

Moves India ATS slugs out of the static india_company_slugs.json into a DB table
so the slug-discovery pipeline can grow it to 500-1000 and the daily revalidation
job can prune dead endpoints. Seeds the current ~34 slugs inline (status
'unverified' until the pipeline probes them) so a fresh DB is immediately usable.
The JSON file remains as the seed-of-record and runtime fallback.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c9e1f3b5d2"
down_revision: Union[str, None] = "f0a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirror of india_company_slugs.json at migration time. workday entries carry
# full adapter config in config_json; their slug is the subdomain.
_SEED: dict = {
    "greenhouse": ["phonepe", "tekion", "groww", "postman", "druva", "narvar", "slice"],
    "lever": ["meesho", "mindtickle", "fampay", "zeta", "cred", "epifi"],
    "ashby": ["atlan", "navi", "scaler", "sarvam", "composio", "spotdraft", "nirvana"],
    "smartrecruiters": ["Visa", "Bosch", "PublicisSapient"],
    "workable": ["instahyre", "whatfix", "medibuddy", "ultrahuman", "fitterfly", "springworks", "invideo"],
    "breezy": ["squadstack"],
    "workday": [
        {"company": "NVIDIA", "subdomain": "nvidia", "tenant": "5", "site": "NVIDIAExternalCareerSite"},
        {"company": "Intel", "subdomain": "intel", "tenant": "1", "site": "External"},
        {"company": "Salesforce", "subdomain": "salesforce", "tenant": "12", "site": "External_Career_Site"},
    ],
}


def upgrade() -> None:
    op.create_table(
        "company_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ats", sa.String(length=30), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="unverified"),
        sa.Column("india_roles_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_roles_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_of_discovery", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("consecutive_dead_checks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ats", "slug", name="uq_company_source_ats_slug"),
    )
    op.create_index("ix_company_source_id", "company_source", ["id"], unique=False)
    op.create_index("ix_company_source_ats", "company_source", ["ats"], unique=False)
    op.create_index("ix_company_source_status", "company_source", ["status"], unique=False)
    op.create_index("ix_company_source_ats_status", "company_source", ["ats", "status"], unique=False)

    # Seed the current JSON slugs (status 'unverified' — pipeline flips to active).
    seed_tbl = sa.table(
        "company_source",
        sa.column("ats", sa.String),
        sa.column("slug", sa.String),
        sa.column("company_name", sa.String),
        sa.column("status", sa.String),
        sa.column("source_of_discovery", sa.String),
        sa.column("config_json", sa.JSON),
    )
    rows = []
    for ats, entries in _SEED.items():
        for entry in entries:
            if isinstance(entry, dict):  # workday/zoho
                rows.append({
                    "ats": ats,
                    "slug": entry.get("subdomain") or entry.get("company") or "",
                    "company_name": entry.get("company"),
                    "status": "unverified",
                    "source_of_discovery": "seed_json",
                    "config_json": entry,
                })
            else:
                rows.append({
                    "ats": ats,
                    "slug": entry,
                    "company_name": None,
                    "status": "unverified",
                    "source_of_discovery": "seed_json",
                    "config_json": None,
                })
    if rows:
        op.bulk_insert(seed_tbl, rows)


def downgrade() -> None:
    op.drop_index("ix_company_source_ats_status", table_name="company_source")
    op.drop_index("ix_company_source_status", table_name="company_source")
    op.drop_index("ix_company_source_ats", table_name="company_source")
    op.drop_index("ix_company_source_id", table_name="company_source")
    op.drop_table("company_source")
