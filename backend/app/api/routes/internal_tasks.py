"""Token-guarded supply ticks, driven by an external scheduler.

Free Render can't run reliable in-process cron (it sleeps) and kills long jobs,
so the supply pipeline is decomposed into short ticks that GitHub Actions curls
on a schedule. Each endpoint:

  * is invisible (404) until INTERNAL_TASK_TOKEN is configured, then requires it;
  * takes a Postgres advisory lock so an overlapping trigger no-ops instead of
    double-running;
  * is bounded by a wall-clock budget and returns partial progress rather than
    raising, so a slow tick degrades into less work, never a 500;
  * checkpoints into ingest_cursor so the next tick resumes.

Endpoints backed by functions that don't exist yet (slug-harvest, ingest) are
added in their own stages; this module wires the ones whose backing already
exists (probe, revalidate, cleanup) plus a health probe.
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.config import settings
from app.services.tick_state import advisory_lock, save_cursor

logger = logging.getLogger(__name__)


def require_internal_token(x_internal_token: str = Header(default="")) -> None:
    """404 while the token is unset (surface is invisible when unconfigured);
    403 on a wrong token. compare_digest avoids a timing side-channel."""
    expected = settings.INTERNAL_TASK_TOKEN
    if not expected:
        raise HTTPException(status_code=404, detail="Not Found")
    if not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(status_code=403, detail="Forbidden")


# Every route in this router is guarded — there is no unauthenticated surface.
router = APIRouter(dependencies=[Depends(require_internal_token)])


async def _run_locked(task: str, coro_factory, *, cursor_key: str | None = None) -> dict:
    """Shared tick wrapper: advisory lock → run → checkpoint, swallowing errors
    into a JSON body so the scheduler sees a 200 with an `ok` flag."""
    async with advisory_lock(task) as got:
        if not got:
            return {"ok": True, "skipped": "locked", "task": task}
        try:
            stats = await coro_factory()
            if cursor_key:
                await save_cursor(cursor_key, stats=stats, ok=True)
            return {"ok": True, "task": task, **stats}
        except Exception as e:  # noqa: BLE001 — a tick must never 500 the scheduler
            logger.error("tick %s failed: %s", task, repr(e)[:300])
            if cursor_key:
                await save_cursor(cursor_key, stats={"error": repr(e)[:200]}, ok=False)
            return {"ok": False, "task": task, "error": repr(e)[:200]}


@router.post("/tick/slug-probe")
async def tick_slug_probe(
    budget_seconds: float = Query(50.0, le=90),
    concurrency: int = Query(8, ge=1, le=16),
):
    from app.services.slug_queue import probe_tick
    return await _run_locked(
        "slug-probe",
        lambda: probe_tick(budget_seconds=budget_seconds, concurrency=concurrency),
        cursor_key="slug_probe:tick",
    )


@router.post("/tick/ingest")
async def tick_ingest(
    chunk: int = Query(25, ge=1, le=100),
    budget_seconds: float = Query(50.0, le=90),
):
    from app.agents.job_discovery_agent import sweep_ingest_tick
    # No cursor_key here: sweep_ingest_tick owns the bulk_ingest:sweep cursor
    # (it writes cursor_value + payload), so the wrapper must not double-write it.
    return await _run_locked(
        "ingest",
        lambda: sweep_ingest_tick(chunk=chunk, budget_seconds=budget_seconds),
    )


@router.post("/tick/promote")
async def tick_promote(limit: int = Query(1000, ge=1, le=5000)):
    """Promote pooled jobs into the CanonicalJob warehouse that Admin stats and
    the Recommended feed read. Without this the warehouse starves while JobPool
    fills."""
    from app.services.aggregation import promote_pool_to_warehouse
    return await _run_locked(
        "promote",
        lambda: promote_pool_to_warehouse(limit=limit),
        cursor_key="warehouse:promote",
    )


@router.post("/tick/slug-harvest")
async def tick_slug_harvest(source: str = Query("names", pattern="^(names|commoncrawl)$")):
    from app.services.slug_queue import harvest_tick
    return await _run_locked(
        f"slug-harvest-{source}",
        lambda: harvest_tick(source),
        cursor_key=f"slug_harvest:{source}",
    )


@router.post("/tick/revalidate")
async def tick_revalidate(batch: int = Query(150, ge=1, le=500)):
    from app.scripts.slug_discovery import revalidate_registry
    return await _run_locked(
        "revalidate",
        lambda: revalidate_registry(batch=batch),
        cursor_key="revalidate:tick",
    )


@router.post("/tick/cleanup")
async def tick_cleanup():
    from app.services.aggregation import cleanup_warehouse
    return await _run_locked(
        "cleanup",
        cleanup_warehouse,
        cursor_key="cleanup:tick",
    )


@router.get("/health/supply")
async def health_supply():
    """Counts only — cheap enough for a frequent external monitor, and the
    assertion target for the GitHub Actions smoke check."""
    from sqlalchemy import func, select
    from datetime import datetime, timedelta, timezone
    from app.core.database import AsyncSessionLocal
    from app.models.company_source import CompanySource
    from app.models.job_pool import JobPool

    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        queue = dict((await session.execute(
            select(CompanySource.probe_state, func.count()).group_by(CompanySource.probe_state)
        )).all())
        active_slugs = int((await session.execute(
            select(func.count()).select_from(CompanySource).where(CompanySource.status == "active")
        )).scalar() or 0)
        fresh_jobs = int((await session.execute(
            select(func.count()).select_from(JobPool).where(
                JobPool.last_seen_at >= now - timedelta(hours=24)
            )
        )).scalar() or 0)
    return {
        "ok": True,
        "active_slugs": active_slugs,
        "queue": queue,
        "fresh_pool_jobs_24h": fresh_jobs,
    }
