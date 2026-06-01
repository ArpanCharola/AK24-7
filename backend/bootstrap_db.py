"""One-shot bootstrap: create all tables from SQLAlchemy models, then stamp
alembic to head. Use only on a fresh DB when the migration chain is broken
(the "initial" migration is actually an ALTER, not a CREATE).
"""
import asyncio
from alembic import command
from alembic.config import Config

from app.core.database import Base, engine
import app.models  # noqa: F401  -- registers ORM models on Base.metadata


async def create_all():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def stamp_head():
    cfg = Config("alembic.ini")
    command.stamp(cfg, "head")


if __name__ == "__main__":
    asyncio.run(create_all())
    stamp_head()
    print("Bootstrap complete: tables created and alembic stamped to head.")
