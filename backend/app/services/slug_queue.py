"""Resumable driver for the company_source slug-probe queue.

`app.scripts.slug_discovery` holds the harvest + probe *library*; it was built
to run as a long CLI pass (1200 validations, minutes of wall time). Render's
free tier kills long work and sleeps through in-process cron, so this module
re-shapes the same primitives into short, crash-safe ticks that an external
scheduler can call every few minutes:

    enqueue_candidates()  -> park (ats, slug) pairs as `candidate` rows
    probe_tick()          -> lease a batch, probe it, record terminal state
    reap_stale_leases()   -> return crashed-mid-probe rows to the queue

Each tick is bounded by wall clock rather than a fixed count, so a slow batch
degrades into fewer probes instead of a timeout.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agents import ats_sources
from app.core.database import AsyncSessionLocal
from app.models.company_source import CompanySource
from app.scripts.slug_discovery import _upsert, validate_candidate

logger = logging.getLogger(__name__)

# Provenance -> queue priority. Curated names are hand-picked India employers and
# convert far better than a Common Crawl URL, so they drain first.
PROVENANCE_PRIORITY = {
    "curated": 300,
    "seed_json": 300,
    "yc": 250,
    "serpapi": 200,
    "commoncrawl": 100,
}

_LEASE_MINUTES = 5
_MAX_PROBE_ATTEMPTS = 3


async def enqueue_candidates(pairs: dict[tuple[str, str], str]) -> int:
    """Park harvested (ats, slug) pairs as unprobed candidates.

    Idempotent on the (ats, slug) natural key: re-harvesting the same slug is a
    no-op rather than a duplicate or a status reset, so a harvester can be run
    as often as we like.
    """
    if not pairs:
        return 0
    now = datetime.now(timezone.utc)
    rows = [
        {
            "ats": ats,
            "slug": slug,
            "status": "unverified",
            "probe_state": "candidate",
            "probe_priority": PROVENANCE_PRIORITY.get(prov, 100),
            "source_of_discovery": prov,
            "first_added_at": now,
            "india_roles_count": 0,
            "total_roles_count": 0,
            "consecutive_dead_checks": 0,
            "probe_attempts": 0,
        }
        for (ats, slug), prov in pairs.items()
    ]

    inserted = 0
    async with AsyncSessionLocal() as session:
        # Chunked so one harvest page can't build a multi-MB statement.
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            stmt = pg_insert(CompanySource).values(chunk).on_conflict_do_nothing(
                index_elements=["ats", "slug"]
            )
            result = await session.execute(stmt)
            inserted += result.rowcount or 0
        await session.commit()
    logger.info("enqueue_candidates: %d new of %d offered", inserted, len(rows))
    return inserted


async def reap_stale_leases() -> int:
    """Return rows whose probe lease expired (process died mid-probe) to the queue.

    A row that keeps failing this way is almost certainly a hanging endpoint, so
    it burns an attempt each time and is retired after _MAX_PROBE_ATTEMPTS.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            update(CompanySource)
            .where(
                CompanySource.probe_state == "probing",
                CompanySource.probe_leased_until < now,
            )
            .values(
                probe_state=case(
                    (CompanySource.probe_attempts + 1 >= _MAX_PROBE_ATTEMPTS, "dead"),
                    else_="candidate",
                ),
                probe_attempts=CompanySource.probe_attempts + 1,
                probe_leased_until=None,
            )
        )
        await session.commit()
    reaped = result.rowcount or 0
    if reaped:
        logger.info("reap_stale_leases: returned %d rows", reaped)
    return reaped


async def _lease_batch(session, size: int) -> list[tuple[int, str, str]]:
    """Atomically claim up to `size` eligible candidates.

    SKIP LOCKED means two concurrent ticks take disjoint batches instead of
    blocking, and the lease timestamp means a crash releases the batch rather
    than stranding it in `probing` forever.
    """
    now = datetime.now(timezone.utc)
    picked = (await session.execute(
        select(CompanySource.id, CompanySource.ats, CompanySource.slug)
        .where(
            CompanySource.probe_state.in_(("candidate", "no_india")),
            or_(CompanySource.next_probe_at.is_(None), CompanySource.next_probe_at <= now),
            CompanySource.probe_attempts < _MAX_PROBE_ATTEMPTS,
        )
        .order_by(CompanySource.probe_priority.desc(), CompanySource.id)
        .limit(size)
        .with_for_update(skip_locked=True)
    )).all()

    if picked:
        await session.execute(
            update(CompanySource)
            .where(CompanySource.id.in_([p[0] for p in picked]))
            .values(
                probe_state="probing",
                probe_leased_until=now + timedelta(minutes=_LEASE_MINUTES),
            )
        )
    await session.commit()
    return [(pid, ats, slug) for pid, ats, slug in picked]


async def probe_tick(
    *,
    budget_seconds: float = 50.0,
    concurrency: int = 8,
    batch: int = 60,
) -> dict:
    """Probe as many queued candidates as fit in the time budget.

    Concurrency is 8 rather than the CLI's 10: a Greenhouse board with
    ?content=true can return multiple MB, and 512MB of RAM is the binding
    constraint on the free tier.
    """
    started = time.monotonic()
    await reap_stale_leases()

    stats = {"probed": 0, "active": 0, "no_india": 0, "dead": 0, "batches": 0}
    sem = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        follow_redirects=True, headers={"User-Agent": ats_sources._UA}
    ) as client:
        while time.monotonic() - started < budget_seconds:
            async with AsyncSessionLocal() as session:
                leased = await _lease_batch(session, batch)
            if not leased:
                break
            stats["batches"] += 1

            async def probe(ats: str, slug: str):
                async with sem:
                    return ats, slug, await validate_candidate(client, ats, slug)

            gathered = await asyncio.gather(
                *(probe(ats, slug) for _, ats, slug in leased),
                return_exceptions=True,
            )

            async with AsyncSessionLocal() as session:
                for g in gathered:
                    if not isinstance(g, tuple):
                        continue
                    ats, slug, (total, india, company) = g
                    row = (await session.execute(
                        select(CompanySource).where(
                            CompanySource.ats == ats, CompanySource.slug == slug
                        )
                    )).scalar_one_or_none()
                    prov = row.source_of_discovery if row else "manual"
                    await _upsert(session, ats, slug, total, india, company, prov)
                    stats["probed"] += 1
                await session.commit()

    async with AsyncSessionLocal() as session:
        counts = dict((await session.execute(
            select(CompanySource.probe_state, func.count())
            .group_by(CompanySource.probe_state)
        )).all())
    stats.update({k: counts.get(k, 0) for k in ("active", "no_india", "dead")})
    stats["candidates_remaining"] = counts.get("candidate", 0)
    stats["elapsed_ms"] = int((time.monotonic() - started) * 1000)
    logger.info("probe_tick: %s", stats)
    return stats


async def harvest_tick(source: str) -> dict:
    """Run one harvester and park its finds as candidates.

    `names` fans the ~597 curated India company names across the four bare-slug
    ATSes — no network, high precision, drains fast. `commoncrawl` scans the CDX
    index for ATS URL patterns — the scalable but noisier lever. Both are
    idempotent, so a repeat run only adds genuinely new (ats, slug) pairs.
    """
    from app.scripts.slug_discovery import (
        harvest_common_crawl,
        harvest_curated,
        harvest_seed,
        _build_probe_set,
    )

    if source == "names":
        typed, names = harvest_curated()
        pairs = _build_probe_set([harvest_seed(), typed], names)
        offered = len(pairs)
        inserted = await enqueue_candidates(pairs)
    elif source == "commoncrawl":
        async with httpx.AsyncClient(
            follow_redirects=True, headers={"User-Agent": ats_sources._UA}
        ) as client:
            harvest = await harvest_common_crawl(client)
        # CC yields typed (ats -> slugs) directly; no name fan-out.
        pairs = {
            (ats, slug): "commoncrawl"
            for ats, slugs in harvest.items()
            for slug in slugs
        }
        offered = len(pairs)
        inserted = await enqueue_candidates(pairs)
    else:
        raise ValueError(f"unknown harvest source: {source!r}")

    return {"source": source, "offered": offered, "enqueued": inserted}


async def queue_counts() -> dict[str, int]:
    """Queue depth by probe_state — the headline metric for registry growth."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(CompanySource.probe_state, func.count()).group_by(CompanySource.probe_state)
        )).all()
    return {state: count for state, count in rows}
