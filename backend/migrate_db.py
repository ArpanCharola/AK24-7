"""Safely prepare either a fresh or an existing AK24/7 database.

Fresh databases need ``create_all`` because the historical first migration is
not a complete schema creator. Existing databases must always advance through
Alembic so new columns are never skipped by an unconditional stamp.
"""
from __future__ import annotations

import asyncio

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from app.core.database import Base, engine
import app.models  # noqa: F401 -- register every model on Base.metadata


async def _database_state() -> tuple[bool, bool]:
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: (
                inspect(sync_connection).has_table("users"),
                inspect(sync_connection).has_table("alembic_version"),
            )
        )


async def _create_fresh_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _alembic_config() -> Config:
    return Config("alembic.ini")


def main() -> None:
    has_users, has_alembic_version = asyncio.run(_database_state())
    if not has_users and not has_alembic_version:
        asyncio.run(_create_fresh_schema())
        command.stamp(_alembic_config(), "head")
        print("Fresh database created and stamped at Alembic head.")
        return

    if has_users and not has_alembic_version:
        raise RuntimeError(
            "Existing users table has no Alembic revision. Refusing to stamp over "
            "a live database; establish its revision before deployment."
        )

    command.upgrade(_alembic_config(), "head")
    print("Existing database upgraded to Alembic head.")


if __name__ == "__main__":
    main()
