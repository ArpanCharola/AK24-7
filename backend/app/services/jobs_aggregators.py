"""Tier-2 aggregator adapters: official free feeds/APIs.

TimesJobs RSS (pan-India, always-on), Jooble direct API (key-gated), and remote
job feeds (Remotive / RemoteOK / Himalayas). Like Tier-1, every adapter is
best-effort: any failure degrades to []. Returns normalized job dicts (contract
#3). India filtering happens downstream in job_discovery_agent.

Verified live 2026-05-31: Remotive, RemoteOK, Himalayas (200 + shapes confirmed).
TimesJobs was unreachable from the build sandbox (ConnectError — geo/network, not
a bad URL); the documented feed URL is used and the adapter is defensive.
Jooble needs JOOBLE_API_KEY and could not be exercised without a key.
"""

import logging
from datetime import datetime, timezone
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

import httpx

from app.agents.job_discovery_agent import (
    _detect_work_arrangement,
    _normalize,
    _parse_iso,
    _strip_html,
)

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 20
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_MAX_PER_QUERY = 50


def _query_match(text: str, queries: list[str]) -> bool:
    """Loose relevance gate for feeds that have no server-side search."""
    if not queries:
        return True
    low = (text or "").lower()
    return any(any(tok in low for tok in q.lower().split() if len(tok) > 2) for q in queries)


def _rss_pubdate(raw: str) -> datetime | None:
    if not raw:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%a, %d %b %Y %H:%M:%S"):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return _parse_iso(raw)


# ── TimesJobs RSS ─────────────────────────────────────────────────────────────

async def timesjobs_rss(client, queries: list[str], locations: list[str]) -> list[dict]:
    locs = locations or [""]
    jobs: list[dict] = []
    seen: set[str] = set()
    for query in queries[:4]:
        for loc in locs[:3]:
            url = (
                "https://www.timesjobs.com/candidate/rssfeed.html"
                f"?keyword={quote_plus(query)}&location={quote_plus(loc)}"
            )
            try:
                resp = await client.get(
                    url, headers={"Accept": "application/xml", "User-Agent": _UA}, timeout=_HTTP_TIMEOUT
                )
                if resp.status_code != 200:
                    continue
                root = ET.fromstring(resp.content)
                for item in root.iter("item"):
                    link = (item.findtext("link") or "").strip()
                    if not link or link in seen:
                        continue
                    seen.add(link)
                    title = (item.findtext("title") or "").strip()
                    description = _strip_html(item.findtext("description") or "")
                    posted_at = _rss_pubdate(item.findtext("pubDate") or "")
                    jobs.append(_normalize(
                        job_url=link, title=title, company=None, location=loc or "India",
                        job_description=description, source="timesjobs",
                        work_arrangement=_detect_work_arrangement(title, loc, description),
                        posted_at=posted_at,
                    ))
            except Exception as exc:
                logger.debug("TimesJobs %r/%r: %s", query, loc, exc)
    logger.info("TimesJobs RSS: %d jobs", len(jobs))
    return jobs


# ── Jooble direct API ─────────────────────────────────────────────────────────

async def jooble(client, queries: list[str], location: str, api_key: str) -> list[dict]:
    if not api_key:
        return []
    jobs: list[dict] = []
    seen: set[str] = set()
    for query in queries[:4]:
        try:
            resp = await client.post(
                f"https://jooble.org/api/{api_key}",
                json={"keywords": query, "location": location or "India", "page": "1"},
                headers={"Content-Type": "application/json"},
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            for j in resp.json().get("jobs", [])[:_MAX_PER_QUERY]:
                link = (j.get("link") or "").strip()
                if not link or link in seen:
                    continue
                seen.add(link)
                title = j.get("title", "")
                location_str = j.get("location", "")
                description = _strip_html(j.get("snippet", ""))
                jobs.append(_normalize(
                    job_url=link, title=title, company=j.get("company"), location=location_str,
                    job_description=description, source="jooble",
                    work_arrangement=_detect_work_arrangement(title, location_str, description),
                    posted_at=_parse_iso(j.get("updated")),
                    salary_raw=(j.get("salary") or None),
                ))
        except Exception as exc:
            logger.debug("Jooble %r: %s", query, exc)
    logger.info("Jooble: %d jobs", len(jobs))
    return jobs


# ── Remote feeds ──────────────────────────────────────────────────────────────

async def remotive(client, queries: list[str]) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for query in queries[:4]:
        try:
            resp = await client.get(
                "https://remotive.com/api/remote-jobs",
                params={"search": query, "limit": _MAX_PER_QUERY},
                headers={"Accept": "application/json", "User-Agent": _UA},
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            for j in resp.json().get("jobs", []):
                link = (j.get("url") or "").strip()
                if not link or link in seen:
                    continue
                seen.add(link)
                title = j.get("title", "")
                location = j.get("candidate_required_location", "")
                description = _strip_html(j.get("description", ""))
                jobs.append(_normalize(
                    job_url=link, title=title, company=j.get("company_name"), location=location,
                    job_description=description, source="remotive", work_arrangement="remote",
                    posted_at=_parse_iso(j.get("publication_date")),
                    salary_raw=(j.get("salary") or None),
                ))
        except Exception as exc:
            logger.debug("Remotive %r: %s", query, exc)
    logger.info("Remotive: %d jobs", len(jobs))
    return jobs


async def remoteok(client, queries: list[str]) -> list[dict]:
    jobs: list[dict] = []
    try:
        resp = await client.get(
            "https://remoteok.com/api",
            headers={"Accept": "application/json", "User-Agent": _UA},
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        for j in data:
            if not isinstance(j, dict) or "position" not in j:
                continue  # first element is a legal notice
            title = j.get("position", "")
            description = _strip_html(j.get("description", ""))
            if not _query_match(f"{title} {' '.join(j.get('tags', []))}", queries):
                continue
            link = (j.get("url") or j.get("apply_url") or "").strip()
            if not link:
                continue
            lo, hi = j.get("salary_min"), j.get("salary_max")
            salary_raw = f"${lo:,}–${hi:,} USD" if lo and hi else None
            jobs.append(_normalize(
                job_url=link, title=title, company=j.get("company"),
                location=j.get("location") or "Remote",
                job_description=description, source="remoteok", work_arrangement="remote",
                posted_at=_parse_iso(j.get("date")),
                salary_raw=salary_raw,
            ))
    except Exception as exc:
        logger.debug("RemoteOK: %s", exc)
    logger.info("RemoteOK: %d jobs", len(jobs))
    return jobs


async def himalayas(client, queries: list[str]) -> list[dict]:
    jobs: list[dict] = []
    try:
        resp = await client.get(
            "https://himalayas.app/jobs/api",
            params={"limit": 100},
            headers={"Accept": "application/json", "User-Agent": _UA},
            timeout=_HTTP_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        for j in resp.json().get("jobs", []):
            title = j.get("title", "")
            description = _strip_html(j.get("description") or j.get("excerpt") or "")
            if not _query_match(f"{title} {' '.join(j.get('categories', []))}", queries):
                continue
            link = (j.get("applicationLink") or "").strip()
            if not link:
                continue
            restrictions = j.get("locationRestrictions") or []
            location = ", ".join(restrictions) if restrictions else "Remote"
            lo, hi = j.get("minSalary"), j.get("maxSalary")
            cur = j.get("currency") or "USD"
            salary_raw = f"{cur} {lo:,}–{hi:,}" if lo and hi else None
            posted_at = None
            pub = j.get("pubDate")
            if pub:
                try:
                    posted_at = datetime.fromtimestamp(int(pub), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    posted_at = None
            jobs.append(_normalize(
                job_url=link, title=title, company=j.get("companyName"), location=location,
                job_description=description, source="himalayas", work_arrangement="remote",
                posted_at=posted_at, salary_raw=salary_raw,
            ))
    except Exception as exc:
        logger.debug("Himalayas: %s", exc)
    logger.info("Himalayas: %d jobs", len(jobs))
    return jobs


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def fetch_all_aggregators(client, queries: list[str], locations: list[str]) -> list[dict]:
    import asyncio

    from app.config import settings

    jooble_key = getattr(settings, "JOOBLE_API_KEY", "") or ""
    location = (locations[0] if locations else "India")

    tasks = [
        timesjobs_rss(client, queries, locations),
        jooble(client, queries, location, jooble_key),
        remotive(client, queries),
        remoteok(client, queries),
        himalayas(client, queries),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    jobs: list[dict] = []
    for r in results:
        if isinstance(r, list):
            jobs.extend(r)
        elif isinstance(r, Exception):
            logger.warning("Aggregator adapter failed: %s", r)
    logger.info("Tier-2 aggregators total: %d jobs", len(jobs))
    return jobs
