"""Tier-3 scraping adapters (python-jobspy).

All-in board scraping for max coverage: Naukri, Indeed, LinkedIn, Google,
Glassdoor — via the `python-jobspy` library. This tier is fragile and legally
risky (ToS / anti-bot), so it is:
  * master-gated behind settings.TIER3_ENABLED (default off),
  * per-source toggled (settings.SCRAPE_<SITE>),
  * fully isolated — each site runs in its own try/except and degrades to [],
    so a single source failure never breaks the discovery run.

jobspy.scrape_jobs is synchronous (blocking HTTP + optional browser), so each
call runs in a worker thread via asyncio.to_thread to keep the event loop free.
Returns normalized job dicts (contract #3); India filtering happens downstream.
"""

import asyncio
import logging
import math
import random
from datetime import datetime, timezone

from app.agents.job_discovery_agent import _detect_work_arrangement, _normalize, _strip_html
from app.agents.proxy_pool import circuit, proxy_pool

logger = logging.getLogger(__name__)

_QUERY_JITTER = (1.0, 3.0)   # seconds slept between queries to look less bot-like

# jobspy site name → settings toggle attr + sensible default.
_SITES = {
    "indeed": ("SCRAPE_INDEED", True),
    "google": ("SCRAPE_GOOGLE", True),
    "naukri": ("SCRAPE_NAUKRI", False),
    "linkedin": ("SCRAPE_LINKEDIN", False),
    "glassdoor": ("SCRAPE_GLASSDOOR", False),
}

_RESULTS_WANTED = 30
_COUNTRY = "India"


def _clean(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _to_dt(value) -> datetime | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        if hasattr(value, "isoformat"):
            dt = datetime.fromisoformat(value.isoformat())
        else:
            dt = datetime.fromisoformat(str(value))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _salary_raw(rec: dict) -> str | None:
    lo, hi = _clean(rec.get("min_amount")), _clean(rec.get("max_amount"))
    if not lo and not hi:
        return None
    cur = _clean(rec.get("currency")) or "INR"
    interval = _clean(rec.get("interval")) or ""
    if lo and hi:
        body = f"{cur} {lo:,.0f}–{hi:,.0f}"
    else:
        body = f"{cur} {(lo or hi):,.0f}"
    return f"{body} {interval}".strip()


def _scrape_blocking(site: str, query: str, location: str, proxies: list[str] | None) -> tuple[list[dict], bool]:
    """Runs in a worker thread. Imports jobspy lazily so a missing package or a
    scraper crash for one site can't take down the module or the run.

    Returns ``(jobs, ok)``. ``ok`` is False only on a hard failure (missing
    package / scraper exception) so the circuit breaker can distinguish a block
    from a legitimately empty result set (an empty board is not a failure)."""
    try:
        from jobspy import scrape_jobs
    except Exception as exc:  # noqa: BLE001 — package may be absent / partially installed
        logger.warning("jobspy unavailable (%s) — Tier-3 returns []", exc)
        return [], False

    try:
        df = scrape_jobs(
            site_name=[site],
            search_term=query,
            google_search_term=f"{query} jobs in {location or 'India'}",
            location=location or "India",
            results_wanted=_RESULTS_WANTED,
            country_indeed=_COUNTRY,
            proxies=proxies or None,
            verbose=0,
        )
    except Exception as exc:  # noqa: BLE001 — any scraper failure → ([], not ok)
        logger.warning("jobspy %s/%r failed: %s", site, query, exc)
        return [], False

    if df is None or getattr(df, "empty", True):
        return [], True

    out: list[dict] = []
    for rec in df.to_dict("records"):
        url = _clean(rec.get("job_url")) or _clean(rec.get("job_url_direct"))
        if not url:
            continue
        title = _clean(rec.get("title")) or ""
        location_str = _clean(rec.get("location")) or ""
        description = _strip_html(_clean(rec.get("description")) or "")
        out.append(_normalize(
            job_url=url,
            title=title,
            company=_clean(rec.get("company")),
            location=location_str,
            job_description=description,
            source=site,
            work_arrangement=(
                "remote" if _clean(rec.get("is_remote"))
                else _detect_work_arrangement(title, location_str, description)
            ),
            posted_at=_to_dt(rec.get("date_posted")),
            salary_raw=_salary_raw(rec),
        ))
    return out, True


async def _scrape_site(site: str, queries: list[str], location: str, proxies: list[str] | None) -> list[dict]:
    if not circuit.allow(site):
        logger.info("Tier-3 %s skipped — circuit open", site)
        return []

    jobs: list[dict] = []
    seen: set[str] = set()
    ok_any = False
    selected = queries[:2]
    for i, query in enumerate(selected):
        try:
            recs, ok = await asyncio.to_thread(_scrape_blocking, site, query, location, proxies)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Tier-3 %s/%r thread failed: %s", site, query, exc)
            recs, ok = [], False
        if ok:
            ok_any = True
        for j in recs:
            if j["job_url"] not in seen:
                seen.add(j["job_url"])
                jobs.append(j)
        if i < len(selected) - 1:
            await asyncio.sleep(random.uniform(*_QUERY_JITTER))

    if ok_any:
        circuit.record_success(site)
    else:
        circuit.record_failure(site)
    logger.info("Tier-3 %s: %d jobs", site, len(jobs))
    return jobs


async def fetch_all_scraped(queries: list[str], locations: list[str]) -> list[dict]:
    """Fan out enabled Tier-3 scrapers. Returns [] entirely if TIER3_ENABLED is off."""
    from app.config import settings

    if not getattr(settings, "TIER3_ENABLED", False):
        logger.info("Tier-3 scraping disabled (TIER3_ENABLED=false)")
        return []

    proxies = proxy_pool.as_list()   # jobspy rotates the list itself; None = direct
    location = locations[0] if locations else "India"

    enabled = [
        site for site, (attr, default) in _SITES.items()
        if getattr(settings, attr, default)
    ]
    if not enabled:
        return []

    results = await asyncio.gather(
        *(_scrape_site(site, queries, location, proxies) for site in enabled),
        return_exceptions=True,
    )
    jobs: list[dict] = []
    for r in results:
        if isinstance(r, list):
            jobs.extend(r)
        elif isinstance(r, Exception):
            logger.warning("Tier-3 site failed: %s", r)
    logger.info("Tier-3 scraping total: %d jobs (sites: %s)", len(jobs), ", ".join(enabled))
    return jobs
