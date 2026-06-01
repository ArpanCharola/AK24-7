"""Tier-2 enterprise career-portal adapters.

Each adapter targets a single company's *proprietary* careers API (these
companies are not on Greenhouse / Lever / Ashby / Workday). The function
contract matches what `JobDiscoveryAgent._discover_*` produces: a list of
dicts with the standard keys (job_url, title, company, location,
job_description, source, work_arrangement, posted_at).

Each adapter is best-effort and wrapped in try/except — a broken adapter
(stale endpoint, schema change) returns [] instead of poisoning the run.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable
from urllib.parse import quote_plus

import httpx

from .job_discovery_agent import (
    _matches_criteria,
    _strip_html,
    _parse_iso,
    _is_within_days,
    _detect_work_arrangement,
)

logger = logging.getLogger(__name__)

# Cap roles per company to keep cost bounded — same as Workday/SmartRecruiters.
_ROLES_PER_COMPANY = 2

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Some portals (e.g. amazon.jobs) respond with zstd compression, which the
# pinned httpx/zstandard combo cannot decode reliably. Exclude zstd explicitly
# so the server falls back to gzip/deflate.
_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.9",
    "User-Agent": _UA,
}


def _profile_roles(profile: dict) -> list[str]:
    return [r.strip() for r in (profile.get("target_roles") or "").split(",") if r.strip()]


# ── Amazon ──────────────────────────────────────────────────────────────────
# Public JSON endpoint backing the amazon.jobs search UI.
# Returns ~10–100 results per page; sort=recent to bias toward fresh postings.

async def fetch_amazon(
    client: httpx.AsyncClient,
    profile: dict,
    posted_within_days: int | None,
) -> list[dict]:
    roles = _profile_roles(profile)
    if not roles:
        return []
    jobs: list[dict] = []
    for role in roles[:_ROLES_PER_COMPANY]:
        try:
            resp = await client.get(
                "https://amazon.jobs/en/search.json",
                params=[
                    ("base_query", role),
                    ("normalized_country_code[]", "USA"),
                    ("result_limit", 100),
                    ("offset", 0),
                    ("sort", "recent"),
                ],
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for j in data.get("jobs", []):
                title = j.get("title", "")
                if not _matches_criteria(title, profile):
                    continue
                location = j.get("location", "") or ""
                description = _strip_html(
                    j.get("description") or j.get("description_short") or ""
                )
                # posted_date is a human string like "May 15, 2025"
                posted_at = None
                pd = j.get("posted_date")
                if pd and isinstance(pd, str):
                    for fmt in ("%B %d, %Y", "%b %d, %Y"):
                        try:
                            posted_at = datetime.strptime(pd, fmt).replace(tzinfo=timezone.utc)
                            break
                        except ValueError:
                            continue
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                path = j.get("url_next_step") or ""
                job_url = (
                    f"https://amazon.jobs{path}" if path.startswith("/")
                    else (path or f"https://amazon.jobs/en/jobs/{j.get('id_icims', '')}")
                )
                jobs.append({
                    "job_url": job_url,
                    "title": title,
                    "company": j.get("company_name") or "Amazon",
                    "location": location,
                    "job_description": description,
                    "source": "amazon",
                    "work_arrangement": _detect_work_arrangement(title, location, description),
                    "posted_at": posted_at,
                })
        except Exception as exc:
            logger.debug("Amazon / %s: %s", role, exc)
    logger.info("Amazon: %d jobs", len(jobs))
    return jobs


# ── Microsoft ───────────────────────────────────────────────────────────────
# Public JSON endpoint backing jobs.careers.microsoft.com.

async def fetch_microsoft(
    client: httpx.AsyncClient,
    profile: dict,
    posted_within_days: int | None,
) -> list[dict]:
    roles = _profile_roles(profile)
    if not roles:
        return []
    jobs: list[dict] = []
    for role in roles[:_ROLES_PER_COMPANY]:
        try:
            resp = await client.get(
                "https://gcsservices.careers.microsoft.com/search/api/v1/search",
                params={
                    "q": role,
                    "lc": "United States",
                    "l": "en_us",
                    "pg": 1,
                    "pgSz": 50,
                    "o": "Recent",
                    "flt": "true",
                },
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                continue
            payload = resp.json()
            result = (payload.get("operationResult") or {}).get("result") or {}
            for j in result.get("jobs", []):
                title = j.get("title", "")
                if not _matches_criteria(title, profile):
                    continue
                props = j.get("properties") or {}
                location = (
                    props.get("primaryLocation")
                    or (props.get("locations") or [""])[0]
                    or ""
                )
                description = _strip_html(props.get("description") or "")
                posted_at = _parse_iso(j.get("postingDate"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                flex = (props.get("workSiteFlexibility") or "").lower()
                if "remote" in flex:
                    arrangement = "remote"
                elif "hybrid" in flex:
                    arrangement = "hybrid"
                elif "on" in flex or "site" in flex:
                    arrangement = "onsite"
                else:
                    arrangement = _detect_work_arrangement(title, location, description)
                job_id = j.get("jobId", "")
                jobs.append({
                    "job_url": f"https://jobs.careers.microsoft.com/global/en/job/{job_id}",
                    "title": title,
                    "company": "Microsoft",
                    "location": location,
                    "job_description": description,
                    "source": "microsoft",
                    "work_arrangement": arrangement,
                    "posted_at": posted_at,
                })
        except Exception as exc:
            logger.debug("Microsoft / %s: %s", role, exc)
    logger.info("Microsoft: %d jobs", len(jobs))
    return jobs


# ── Google ──────────────────────────────────────────────────────────────────
# careers.google.com public JSON API.

async def fetch_google(
    client: httpx.AsyncClient,
    profile: dict,
    posted_within_days: int | None,
) -> list[dict]:
    roles = _profile_roles(profile)
    if not roles:
        return []
    jobs: list[dict] = []
    for role in roles[:_ROLES_PER_COMPANY]:
        try:
            resp = await client.get(
                "https://www.google.com/about/careers/applications/api/v3/search/",
                params={
                    "company": "Google",
                    "q": role,
                    "location": "United States",
                    "page": 1,
                },
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for j in data.get("jobs", []):
                title = j.get("title", "")
                if not _matches_criteria(title, profile):
                    continue
                locs = j.get("locations") or []
                location = ""
                if locs and isinstance(locs[0], dict):
                    location = ", ".join(
                        filter(None, [locs[0].get("city"), locs[0].get("state"), locs[0].get("countryCode")])
                    )
                description = _strip_html(
                    (j.get("description") or "") + " " + (j.get("qualifications") or "")
                )
                posted_at = _parse_iso(j.get("publish_date") or j.get("created"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                jid = j.get("id") or j.get("job_id") or ""
                # The id is a long path like "jobs/123456789012345678..." — extract the digits.
                jid_clean = jid.rsplit("/", 1)[-1] if "/" in jid else jid
                jobs.append({
                    "job_url": f"https://www.google.com/about/careers/applications/jobs/results/{jid_clean}",
                    "title": title,
                    "company": j.get("company_name") or "Google",
                    "location": location,
                    "job_description": description,
                    "source": "google",
                    "work_arrangement": _detect_work_arrangement(title, location, description),
                    "posted_at": posted_at,
                })
        except Exception as exc:
            logger.debug("Google / %s: %s", role, exc)
    logger.info("Google: %d jobs", len(jobs))
    return jobs


# ── Apple ───────────────────────────────────────────────────────────────────
# jobs.apple.com role search API (POST with JSON body).

async def fetch_apple(
    client: httpx.AsyncClient,
    profile: dict,
    posted_within_days: int | None,
) -> list[dict]:
    roles = _profile_roles(profile)
    if not roles:
        return []
    jobs: list[dict] = []
    for role in roles[:_ROLES_PER_COMPANY]:
        try:
            resp = await client.post(
                "https://jobs.apple.com/api/role/search",
                json={
                    "page": 1,
                    "locale": "en-us",
                    "search": role,
                    "sort": "newest",
                    "filters": {"postingpostedDate": [], "locations": ["postLocation-USA"]},
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "User-Agent": _UA,
                    "Referer": "https://jobs.apple.com/en-us/search",
                },
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            for j in data.get("searchResults", []):
                title = j.get("postingTitle", "")
                if not _matches_criteria(title, profile):
                    continue
                locs = j.get("locations") or []
                location = ""
                if locs and isinstance(locs[0], dict):
                    location = locs[0].get("name") or locs[0].get("city") or ""
                description = _strip_html(j.get("jobSummary") or "")
                posted_at = _parse_iso(j.get("postingPostedDate"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                pid = j.get("positionId", "")
                jobs.append({
                    "job_url": f"https://jobs.apple.com/en-us/details/{pid}",
                    "title": title,
                    "company": "Apple",
                    "location": location,
                    "job_description": description,
                    "source": "apple",
                    "work_arrangement": _detect_work_arrangement(title, location, description),
                    "posted_at": posted_at,
                })
        except Exception as exc:
            logger.debug("Apple / %s: %s", role, exc)
    logger.info("Apple: %d jobs", len(jobs))
    return jobs


# ── Meta ────────────────────────────────────────────────────────────────────
# metacareers.com public GraphQL endpoint. Schema is the most volatile of
# the bunch — best-effort.

async def fetch_meta(
    client: httpx.AsyncClient,
    profile: dict,
    posted_within_days: int | None,
) -> list[dict]:
    roles = _profile_roles(profile)
    if not roles:
        return []
    jobs: list[dict] = []
    for role in roles[:_ROLES_PER_COMPANY]:
        try:
            resp = await client.get(
                "https://www.metacareers.com/graphql",
                params={
                    "doc_id": "9114524511922157",  # CareersJobSearchResultsQuery
                    "variables": (
                        '{"search_input":{"q":"' + role +
                        '","offices":["United States"],"page":1}}'
                    ),
                },
                headers={
                    "Accept": "application/json",
                    "User-Agent": _UA,
                    "X-FB-Friendly-Name": "CareersJobSearchResultsQuery",
                },
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            # Schema: data.data.job_search.job_search_results[]
            results = (
                ((data.get("data") or {}).get("job_search") or {})
                .get("job_search_results") or []
            )
            for j in results:
                title = j.get("title") or j.get("name") or ""
                if not _matches_criteria(title, profile):
                    continue
                locs = j.get("locations") or j.get("office_names") or []
                location = ", ".join(locs) if isinstance(locs, list) else str(locs)
                description = _strip_html(j.get("description") or "")
                posted_at = _parse_iso(j.get("published_at") or j.get("created_time"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                jid = j.get("id") or j.get("job_id") or ""
                jobs.append({
                    "job_url": f"https://www.metacareers.com/jobs/{jid}",
                    "title": title,
                    "company": "Meta",
                    "location": location,
                    "job_description": description,
                    "source": "meta",
                    "work_arrangement": _detect_work_arrangement(title, location, description),
                    "posted_at": posted_at,
                })
        except Exception as exc:
            logger.debug("Meta / %s: %s", role, exc)
    logger.info("Meta: %d jobs", len(jobs))
    return jobs


# ── Netflix ─────────────────────────────────────────────────────────────────
# jobs.netflix.com proprietary search API.

async def fetch_netflix(
    client: httpx.AsyncClient,
    profile: dict,
    posted_within_days: int | None,
) -> list[dict]:
    roles = _profile_roles(profile)
    if not roles:
        return []
    jobs: list[dict] = []
    for role in roles[:_ROLES_PER_COMPANY]:
        try:
            resp = await client.get(
                "https://explore.jobs.netflix.net/api/apply/v2/jobs",
                params={
                    "domain": "netflix.com",
                    "query": role,
                    "location": "United States",
                    "start": 0,
                    "num": 50,
                },
                headers=_HEADERS,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            postings = data.get("positions") or data.get("jobs") or []
            for j in postings:
                title = j.get("name") or j.get("title") or ""
                if not _matches_criteria(title, profile):
                    continue
                location = (
                    j.get("location")
                    or ", ".join(j.get("locations") or [])
                    or ""
                )
                description = _strip_html(j.get("job_description") or j.get("description") or "")
                # Netflix returns t_create as a Unix timestamp (int), not ISO.
                posted_at = None
                t = j.get("t_create")
                if isinstance(t, (int, float)):
                    try:
                        posted_at = datetime.fromtimestamp(t, tz=timezone.utc)
                    except (ValueError, OSError):
                        posted_at = None
                elif isinstance(t, str):
                    posted_at = _parse_iso(t)
                if posted_at is None:
                    posted_at = _parse_iso(j.get("publish_date"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                jid = j.get("id") or j.get("display_job_id") or ""
                job_url = (
                    j.get("canonicalPositionUrl")
                    or j.get("url")
                    or f"https://explore.jobs.netflix.net/careers/job/{jid}"
                )
                jobs.append({
                    "job_url": job_url,
                    "title": title,
                    "company": "Netflix",
                    "location": location,
                    "job_description": description,
                    "source": "netflix",
                    "work_arrangement": _detect_work_arrangement(title, location, description),
                    "posted_at": posted_at,
                })
        except Exception as exc:
            logger.debug("Netflix / %s: %s", role, exc)
    logger.info("Netflix: %d jobs", len(jobs))
    return jobs


# ── Registry ────────────────────────────────────────────────────────────────

PortalAdapter = Callable[
    [httpx.AsyncClient, dict, int | None],
    Awaitable[list[dict]],
]

PORTAL_ADAPTERS: list[PortalAdapter] = [
    fetch_amazon,
    fetch_microsoft,
    fetch_google,
    fetch_apple,
    fetch_meta,
    fetch_netflix,
]
