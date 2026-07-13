"""Entry-level India tech supply backfill.

This is the durable version of the manual "bring jobs into the system" run:
fan out the heavier discovery sources by role family, keep only India/Remote
India fresher-valid tech jobs, and upsert them into the shared JobPool.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Iterable

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.agents.job_discovery_agent import (
    JobDiscoveryAgent,
    _is_excluded_job,
    _is_india_strict,
    _matches_criteria,
)
from app.config import settings
from app.core.database import AsyncSessionLocal
from app.models.job_pool import JobPool
from app.services.experience_filters import fresher_search_roles, is_experience_match
from app.services.serpapi_jobs import search_serpapi_jobs

logger = logging.getLogger(__name__)

ENTRY_LEVEL_TECH_ROLES: tuple[str, ...] = (
    "Software Developer",
    "Software Engineer",
    "Frontend Developer",
    "Backend Developer",
    "Fullstack Developer",
    "Web Developer",
    "Java Developer",
    "Python Developer",
    "React Developer",
    "AI/ML Engineer",
    "Data Analyst",
    "Data Engineer",
    "QA Engineer",
    "SDET",
    "DevOps Engineer",
)

DEFAULT_LOCATIONS: tuple[str, ...] = ("India", "Remote India")


def _trunc(value: str | None, n: int) -> str | None:
    return value[:n] if isinstance(value, str) else value


def _queries_for_role(role: str) -> list[str]:
    queries = fresher_search_roles(role, "fresher") or [role]
    return queries[:8]


def _is_supply_match(role: str, job: dict) -> bool:
    title = job.get("title") or ""
    company = job.get("company") or ""
    url = job.get("job_url") or ""
    description = job.get("job_description") or ""
    return (
        bool(url)
        and _matches_criteria(title, {"target_roles": role})
        and _is_india_strict(job.get("location"))
        and not _is_excluded_job(title, company, url, description)
        and is_experience_match(title, description, "fresher")
    )


async def _upsert_pool(role: str, jobs: Iterable[dict]) -> int:
    now = datetime.now(timezone.utc)
    by_url: dict[str, dict] = {}
    for job in jobs:
        if not _is_supply_match(role, job):
            continue
        url = job.get("job_url")
        if not url or len(url) > 2048:
            continue
        by_url[url] = {
            "job_url": url,
            "title": _trunc(job.get("title"), 255),
            "company": _trunc(job.get("company"), 255),
            "location": _trunc(job.get("location"), 255),
            "job_description": job.get("job_description"),
            "source": _trunc(job.get("source") or "discovery", 50),
            "work_arrangement": _trunc(job.get("work_arrangement"), 20),
            "posted_at": job.get("posted_at"),
            "salary_lpa": job.get("salary_lpa"),
            "salary_raw": _trunc(job.get("salary_raw"), 120),
            "notice_period": _trunc(job.get("notice_period"), 20),
            "search_query": _trunc(role, 255),
            "first_seen_at": now,
            "last_seen_at": now,
        }
    rows = list(by_url.values())
    if not rows:
        return 0

    saved = 0
    async with AsyncSessionLocal() as db:
        for i in range(0, len(rows), 250):
            chunk = rows[i:i + 250]
            stmt = pg_insert(JobPool).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["job_url"],
                set_={
                    "title": func.coalesce(stmt.excluded.title, JobPool.title),
                    "company": func.coalesce(stmt.excluded.company, JobPool.company),
                    "location": func.coalesce(stmt.excluded.location, JobPool.location),
                    "job_description": func.coalesce(stmt.excluded.job_description, JobPool.job_description),
                    "source": stmt.excluded.source,
                    "work_arrangement": func.coalesce(stmt.excluded.work_arrangement, JobPool.work_arrangement),
                    "posted_at": func.coalesce(stmt.excluded.posted_at, JobPool.posted_at),
                    "salary_lpa": func.coalesce(stmt.excluded.salary_lpa, JobPool.salary_lpa),
                    "salary_raw": func.coalesce(stmt.excluded.salary_raw, JobPool.salary_raw),
                    "notice_period": func.coalesce(stmt.excluded.notice_period, JobPool.notice_period),
                    "search_query": stmt.excluded.search_query,
                    "last_seen_at": stmt.excluded.last_seen_at,
                },
            )
            await db.execute(stmt)
            await db.commit()
            saved += len(chunk)
    return saved


async def backfill_entry_level_supply(
    *,
    roles: Iterable[str] | None = None,
    locations: Iterable[str] | None = None,
    posted_within_days: int = 7,
    max_roles: int | None = None,
    use_stealth: bool = False,
) -> dict:
    selected_roles = list(dict.fromkeys(r.strip() for r in (roles or ENTRY_LEVEL_TECH_ROLES) if r and r.strip()))
    if max_roles is not None:
        selected_roles = selected_roles[:max_roles]
    selected_locations = list(dict.fromkeys(loc.strip() for loc in (locations or DEFAULT_LOCATIONS) if loc and loc.strip()))
    previous_stealth = settings.STEALTH_ENABLED
    settings.STEALTH_ENABLED = bool(use_stealth)
    agent = JobDiscoveryAgent()
    role_reports: list[dict] = []
    try:
        for role in selected_roles:
            queries = _queries_for_role(role)
            profile = {
                "target_roles": role,
                "locations": ", ".join(selected_locations),
                "posted_within_days": posted_within_days,
                "work_arrangements": "",
                "excluded_companies": "",
            }
            jobs = await agent.discover(profile, queries)
            serpapi_jobs = await _serpapi_supply_jobs(
                role=role,
                queries=queries,
                posted_within_days=posted_within_days,
            )
            all_jobs = [*jobs, *serpapi_jobs]
            accepted = [job for job in all_jobs if _is_supply_match(role, job)]
            saved = await _upsert_pool(role, accepted)
            role_reports.append({
                "role": role,
                "queries": queries,
                "discovered_clean": len(all_jobs),
                "discovered_by_supply_agent": len(jobs),
                "discovered_by_serpapi": len(serpapi_jobs),
                "accepted": len(accepted),
                "saved_or_updated": saved,
                "sources": dict(Counter(job.get("source") or "unknown" for job in accepted)),
                "sample_titles": [job.get("title") for job in accepted[:8]],
            })
            logger.info("entry-level supply role=%s accepted=%d saved=%d", role, len(accepted), saved)
    finally:
        settings.STEALTH_ENABLED = previous_stealth

    counts = await count_entry_level_supply(roles=selected_roles, posted_within_days=posted_within_days)
    return {
        "roles_requested": len(selected_roles),
        "locations": selected_locations,
        "posted_within_days": posted_within_days,
        "use_stealth": use_stealth,
        "roles": role_reports,
        "counts": counts,
    }


async def _serpapi_supply_jobs(
    *,
    role: str,
    queries: list[str],
    posted_within_days: int,
) -> list[dict]:
    if not (getattr(settings, "SERPAPI_KEY", "") or ""):
        return []
    jobs: list[dict] = []
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        results = await asyncio_gather_safe([
            search_serpapi_jobs(
                client,
                {
                    "target_roles": role,
                    "search_query": query,
                    "locations": "India",
                    "posted_within_days": posted_within_days,
                },
                posted_within_days,
                max_pages=2,
            )
            for query in queries[:4]
        ])
    seen: set[str] = set()
    for batch in results:
        for job in batch:
            url = job.get("job_url")
            if not url or url in seen:
                continue
            seen.add(url)
            jobs.append(job)
    return jobs


async def asyncio_gather_safe(tasks):
    import asyncio

    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = []
    for result in results:
        if isinstance(result, list):
            out.append(result)
        elif isinstance(result, Exception):
            logger.warning("entry-level SerpAPI supply failed: %s", result)
    return out


async def count_entry_level_supply(
    *,
    roles: Iterable[str] | None = None,
    posted_within_days: int = 7,
) -> dict:
    selected_roles = list(dict.fromkeys(r.strip() for r in (roles or ENTRY_LEVEL_TECH_ROLES) if r and r.strip()))
    cutoff = datetime.now(timezone.utc) - timedelta(days=posted_within_days)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(select(JobPool).where(JobPool.last_seen_at >= cutoff))).scalars().all()

    result: dict[str, dict] = {}
    for role in selected_roles:
        accepted: list[JobPool] = []
        seen: set[str] = set()
        for row in rows:
            key = row.job_url or f"{row.company}-{row.title}-{row.location}"
            if key in seen:
                continue
            if (
                _matches_criteria(row.title or "", {"target_roles": role})
                and _is_india_strict(row.location)
                and not _is_excluded_job(row.title or "", row.company or "", row.job_url, row.job_description or "")
                and is_experience_match(row.title, row.job_description, "fresher")
            ):
                seen.add(key)
                accepted.append(row)
        known_posted = [
            row for row in accepted
            if row.posted_at and (
                row.posted_at if row.posted_at.tzinfo else row.posted_at.replace(tzinfo=timezone.utc)
            ) >= cutoff
        ]
        result[role] = {
            "seen": len(accepted),
            "known_posted": len(known_posted),
            "sources": dict(Counter(row.source or "unknown" for row in accepted)),
            "sample_titles": [row.title for row in accepted[:8]],
        }
    return result
