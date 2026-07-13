"""SerpAPI Google Jobs adapter.

Queries Google's job aggregator via SerpAPI, returning postings in the
standard job dict shape that JobDiscoveryAgent expects. Google Jobs
indexes LinkedIn, Indeed, Glassdoor, ZipRecruiter, and the company career
pages, so this single source covers a large swath that our per-ATS
adapters can't reach.

Disabled (returns []) if SERPAPI_KEY is unset.

Cost notes:
 - Two roles × up to two pages per discovery run = 4 SerpAPI calls.
 - Discovery runs every 4h by default → ~24 calls/day per active profile.
 - SerpAPI free tier is 100 searches/month; paid is $50/mo for 5,000.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_API_URL = "https://serpapi.com/search.json"

# "2 days ago" / "10+ days ago" / "Just posted" patterns.
_POSTED_AGO_RE = re.compile(
    r"(\d+)\+?\s*(minute|hour|day|week|month)s?\s*ago",
    re.IGNORECASE,
)


def _parse_posted_ago(s: str | None) -> datetime | None:
    """Map Google Jobs' human-readable posted_at into a UTC datetime."""
    if not s:
        return None
    text = s.lower().strip()
    if "just posted" in text or "today" in text:
        return datetime.now(timezone.utc)
    if "yesterday" in text:
        return datetime.now(timezone.utc) - timedelta(days=1)
    m = _POSTED_AGO_RE.search(text)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2).lower()
    deltas = {
        "minute": timedelta(minutes=n),
        "hour": timedelta(hours=n),
        "day": timedelta(days=n),
        "week": timedelta(weeks=n),
        # 31 (not 30) days/month so a "1 month ago" posting reads as just-older
        # than a 30-day freshness window rather than sneaking in at the boundary.
        "month": timedelta(days=n * 31),
    }
    return datetime.now(timezone.utc) - deltas.get(unit, timedelta(0))


def _pick_apply_url(job: dict) -> str:
    """Find the canonical posting URL. Prefer apply_options links, fall back
    to share_link. Skip Google-hosted links so dedup works against our other
    sources (we want the real ATS URL where possible)."""
    for opt in (job.get("apply_options") or []):
        link = (opt.get("link") or "").strip()
        if link and "google.com" not in link:
            return link
    # Last resort — Google's job-detail URL. Better than nothing for dedup.
    return (job.get("share_link") or "").strip()


def _date_posted_chip(posted_within_days: int | None) -> str | None:
    """Map our 'posted within N days' filter to Google Jobs' date_posted chip."""
    if not posted_within_days:
        return None
    if posted_within_days <= 1:
        return "date_posted:today"
    if posted_within_days <= 3:
        return "date_posted:3days"
    if posted_within_days <= 7:
        return "date_posted:week"
    return "date_posted:month"


async def search_serpapi_jobs(
    client: httpx.AsyncClient,
    profile: dict,
    posted_within_days: int | None,
    max_pages: int = 2,
) -> list[dict]:
    """Run Google Jobs search via SerpAPI for each role in the profile.

    Returns jobs in the standard discovery dict shape. The caller (the
    discovery agent's master loop) handles dedup, USA filtering, etc., so
    this adapter just emits well-shaped rows.
    """
    api_key = getattr(settings, "SERPAPI_KEY", "") or ""
    if not api_key:
        logger.warning(
            "SerpAPI source skipped: SERPAPI_KEY is empty. "
            "Add SERPAPI_KEY=... to backend/.env and restart the worker."
        )
        return []

    # Lazy-import the helpers so this module can be imported without the
    # discovery agent (e.g. for unit tests).
    from app.agents.job_discovery_agent import (
        _matches_criteria,
        _detect_work_arrangement,
        _is_within_days,
    )

    query_text = profile.get("search_query") or profile.get("target_roles") or ""
    roles = [r.strip() for r in query_text.split(",") if r.strip()]
    if not roles:
        logger.warning(
            "SerpAPI source skipped: profile has no target_roles. "
            "Set target_roles on the JobSearchProfile (e.g. 'Software Engineer')."
        )
        return []

    # SerpAPI's Google Jobs `location` takes one place at a time; use the
    # first location in the profile, or fall back to a national query.
    locations = [
        loc.strip() for loc in (profile.get("locations") or "").split(",") if loc.strip()
    ]
    location = locations[0] if locations else "India"
    if location.strip().lower() in {"all india", "india", "pan india", "remote india"}:
        location = "India"

    chip = _date_posted_chip(posted_within_days)

    jobs: list[dict] = []
    for role in roles[:2]:
        next_page_token: str | None = None
        for _ in range(max_pages):
            params = {
                "engine": "google_jobs",
                "q": role,
                "location": location,
                "gl": "in",
                "hl": "en",
                "api_key": api_key,
            }
            if chip:
                params["chips"] = chip
            if next_page_token:
                params["next_page_token"] = next_page_token

            try:
                resp = await client.get(_API_URL, params=params, timeout=30)
            except Exception as exc:
                logger.warning("SerpAPI / %s: request failed: %s", role, exc)
                break

            if resp.status_code != 200:
                logger.warning(
                    "SerpAPI / %s: HTTP %d — %s",
                    role, resp.status_code, resp.text[:160],
                )
                break

            try:
                data = resp.json()
            except Exception as exc:
                logger.warning("SerpAPI / %s: JSON parse failed: %s", role, exc)
                break

            results = data.get("jobs_results") or []
            if not results:
                break

            for j in results:
                title = j.get("title", "")
                if not _matches_criteria(title, profile):
                    continue

                exts = j.get("detected_extensions") or {}
                posted_at = _parse_posted_ago(exts.get("posted_at"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue

                job_url = _pick_apply_url(j)
                if not job_url:
                    continue

                # Skip non-full-time
                sched = (exts.get("schedule_type") or "").lower()
                if sched and any(x in sched for x in ("intern", "part", "contract", "temp", "volunteer")):
                    continue

                loc = j.get("location") or ""
                description = j.get("description") or ""
                if exts.get("work_from_home"):
                    arrangement = "remote"
                else:
                    arrangement = _detect_work_arrangement(title, loc, description)

                jobs.append({
                    "job_url": job_url,
                    "title": title,
                    "company": j.get("company_name") or "Unknown",
                    "location": loc,
                    "job_description": description,
                    "source": "google_jobs",
                    "work_arrangement": arrangement,
                    "posted_at": posted_at,
                    # Pass through all apply_options so callers (e.g. public_jobs)
                    # can pick the most-direct URL instead of the first one.
                    "apply_options": j.get("apply_options") or [],
                })

            next_page_token = (
                (data.get("serpapi_pagination") or {}).get("next_page_token")
                or (data.get("pagination") or {}).get("next_page_token")
            )
            if not next_page_token:
                break
            await asyncio.sleep(0.4)  # be nice to SerpAPI

    logger.info("SerpAPI Google Jobs: %d jobs", len(jobs))
    return jobs
