"""DB engine + session factory.

Pool sizing matters in prod:
- Default asyncpg pool is small (5 connections). With 2 uvicorn workers + 4
  celery workers all reaching for the DB concurrently we'd queue or 504.
- pool_size=10 + max_overflow=10 → up to 20 connections per process.
  With 2 api workers + 4 celery workers = 6 processes × 20 = 120 max.
- pool_pre_ping=True catches stale connections after Postgres restarts /
  network blips without surfacing an error to the request.
- pool_recycle=1800 closes connections older than 30 min so we don't get
  killed by Postgres-side idle timeouts (default in many managed PGs is 1h).
"""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,
)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def init_db():
    # Schema is owned by Alembic. Do NOT call Base.metadata.create_all() here —
    # it bypasses migration tracking and creates orphan tables that block
    # subsequent alembic upgrades (and silently does NOT add new columns to
    # existing tables). Run `alembic upgrade head` from backend/ to migrate.
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
