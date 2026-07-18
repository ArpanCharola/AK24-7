"""Read/write helpers for ingest_cursor + a Postgres advisory lock.

Kept separate from the route module so both the tick endpoints and the local
APScheduler jobs record their progress the same way.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import AsyncSessionLocal
from app.models.ingest_cursor import IngestCursor


async def load_cursor(key: str) -> IngestCursor | None:
    async with AsyncSessionLocal() as session:
        return (await session.execute(
            select(IngestCursor).where(IngestCursor.key == key)
        )).scalar_one_or_none()


async def save_cursor(
    key: str,
    *,
    cursor_value: str | None = None,
    payload: dict | None = None,
    stats: dict | None = None,
    ok: bool = True,
) -> None:
    """Upsert a stream's checkpoint. Only non-None fields are written, so a
    caller that just wants to bump the run counter can omit cursor_value."""
    now = datetime.now(timezone.utc)
    values = {
        "key": key,
        "cursor_value": cursor_value,
        "payload": payload,
        "last_stats": stats,
        "runs": 1,
        "last_run_at": now,
        "last_ok_at": now if ok else None,
    }
    set_ = {
        "last_run_at": now,
        "runs": IngestCursor.runs + 1,
        "last_stats": stats,
    }
    if cursor_value is not None:
        set_["cursor_value"] = cursor_value
    if payload is not None:
        set_["payload"] = payload
    if ok:
        set_["last_ok_at"] = now

    async with AsyncSessionLocal() as session:
        stmt = pg_insert(IngestCursor).values(**values).on_conflict_do_update(
            index_elements=["key"], set_=set_
        )
        await session.execute(stmt)
        await session.commit()


class advisory_lock:
    """`async with advisory_lock("ingest") as got:` — session-scoped Postgres
    advisory lock so two overlapping ticks of the same task don't run at once.
    The lock auto-releases if the connection dies, so a crashed tick never
    strands it (unlike a DB row lease). `got` is False when another holder has
    it; the caller should no-op in that case rather than error.
    """

    def __init__(self, task: str):
        self._task = task
        self._session = None
        self._got = False

    async def __aenter__(self) -> bool:
        self._session = AsyncSessionLocal()
        await self._session.__aenter__()
        self._got = bool((await self._session.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:t))"), {"t": self._task}
        )).scalar())
        return self._got

    async def __aexit__(self, *exc) -> None:
        try:
            if self._got:
                await self._session.execute(
                    text("SELECT pg_advisory_unlock(hashtext(:t))"), {"t": self._task}
                )
                await self._session.commit()
        finally:
            await self._session.__aexit__(*exc)
