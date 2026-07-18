"""Checkpoints for resumable supply ticks.

Render's free tier kills long work and sleeps through in-process cron, so the
supply pipeline runs as short externally-triggered ticks (see
app/api/routes/internal_tasks.py). Each tick must remember where the last one
stopped — which Common Crawl page, which registry id the ingest sweep reached —
so the next tick resumes instead of restarting. That state lives here, one row
per logical stream keyed by a stable string.

`payload` carries stream-specific counters (e.g. sweeps_completed) that don't
deserve their own column.
"""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IngestCursor(Base):
    __tablename__ = "ingest_cursor"

    # e.g. "slug_harvest:commoncrawl", "bulk_ingest:sweep", "revalidate:cursor".
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    # Opaque resume token, meaning defined by the stream. For CC that's
    # "crawl_id:pattern_idx:page"; for the ingest sweep it's the last
    # company_source.id processed.
    cursor_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Last run that finished without raising — lets a monitor spot a stream
    # that is being triggered but silently failing every time.
    last_ok_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    @staticmethod
    def utcnow() -> datetime:
        return datetime.now(timezone.utc)
