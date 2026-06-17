"""Tier-3 custom adapters for Indian-native boards that python-jobspy does not
cover: **Instahyre** and **Cutshort**.

Both are reached through the site's own public, no-auth JSON — not HTML scraping:

* **Instahyre** exposes an internal search API at
  ``GET /api/v1/job_search/?limit=&offset=`` returning ``{meta, objects[]}``.
  It ignores free-text query params, so we paginate the feed and filter for the
  user's roles client-side (see ``_matches_query``). Each object carries title,
  employer, locations, public_url, keywords — but no JD/salary inline (those live
  on the detail page and are fetched lazily elsewhere).
* **Cutshort** server-side-renders a rich ``featuredJobListData`` block inside
  ``__NEXT_DATA__`` on ``/jobs``: headline, companyDetails, locationsText,
  salaryRangeText (₹), allSkills, remoteType, and a ``hiringForClient`` staffing
  flag. Category pages (``/jobs/<slug>``) are client-rendered (no SSR data), so
  this adapter reads the SSR feed — best-effort, low volume, degrades to [].

Contract: every fetcher returns ``_normalize(...)`` dicts and self-isolates
(``try/except → []``). Gated by ``TIER3_ENABLED`` + per-source ``SCRAPE_*``.
Downstream ``_postprocess`` handles dedupe / India filter / anti-staffing /
LPA + notice parsing, so adapters stay thin.
"""

import asyncio
import json
import logging
import re

from app.agents.job_discovery_agent import _detect_work_arrangement, _normalize, _strip_html
from app.agents.proxy_pool import circuit
from app.config import settings

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html;q=0.9",
    "Accept-Language": "en-IN,en;q=0.9",
}

_INSTAHYRE_API = "https://www.instahyre.com/api/v1/job_search/"
_INSTAHYRE_PAGE_SIZE = 35
_INSTAHYRE_MAX_PAGES = 3       # ~105 jobs/run before client-side relevance filtering

_CUTSHORT_BASE = "https://cutshort.io/jobs"
_CUTSHORT_REMOTE = {"remote_only": "remote", "remote_okay": "remote", "remote_not_okay": "onsite"}
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
_STOPWORDS = {"the", "and", "for", "with", "job", "jobs", "role", "engineer", "developer"}


# ── Query relevance filter (TUNABLE POLICY) ───────────────────────────────────
def _matches_query(haystack: str, queries: list[str]) -> bool:
    """Should a job whose searchable text is ``haystack`` be kept for these roles?

    Instahyre's feed is unfiltered and Cutshort's SSR feed is a fixed featured
    set, so this client-side filter is what makes those sources role-relevant.
    Default policy: keep a job if any query phrase appears verbatim, OR if ≥60%
    of a query's significant tokens are present. This is the one knob that most
    shapes precision-vs-recall for the custom Indian boards — tune it freely.
    """
    if not queries:
        return True
    hay = haystack.lower()
    for q in queries:
        ql = q.lower().strip()
        if not ql:
            continue
        if ql in hay:
            return True
        tokens = [t for t in re.findall(r"[a-z0-9+#.]+", ql) if len(t) >= 3]
        if not tokens:
            continue
        hits = sum(1 for t in tokens if t in hay)
        if hits / len(tokens) >= 0.6:
            return True
    return False


# ── Instahyre ─────────────────────────────────────────────────────────────────
def _instahyre_job(obj: dict) -> dict | None:
    url = obj.get("public_url")
    title = obj.get("title")
    if not url or not title:
        return None
    employer = obj.get("employer") or {}
    company = employer.get("company_name")
    locations = obj.get("locations") or ""
    keywords = obj.get("keywords")
    if isinstance(keywords, list):
        keywords = " ".join(str(k) for k in keywords)
    desc_bits = [employer.get("company_tagline"), keywords]
    description = _strip_html(" — ".join(b for b in desc_bits if b)) or None
    work = "remote" if re.search(r"work from home|remote", locations, re.I) else \
        _detect_work_arrangement(title, locations, description or "")
    return _normalize(
        job_url=url,
        title=title,
        company=company,
        location=locations,
        job_description=description,
        source="instahyre",
        work_arrangement=work,
    )


async def fetch_instahyre(client, queries: list[str], locations: list[str]) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for page in range(_INSTAHYRE_MAX_PAGES):
        params = {"limit": _INSTAHYRE_PAGE_SIZE, "offset": page * _INSTAHYRE_PAGE_SIZE}
        resp = await client.get(_INSTAHYRE_API, params=params, headers=_HEADERS)
        resp.raise_for_status()
        objects = (resp.json() or {}).get("objects") or []
        if not objects:
            break
        for obj in objects:
            job = _instahyre_job(obj)
            if not job or job["job_url"] in seen:
                continue
            haystack = f"{job['title']} {job.get('job_description') or ''}"
            if not _matches_query(haystack, queries):
                continue
            seen.add(job["job_url"])
            jobs.append(job)
        await asyncio.sleep(1.0)
    logger.info("Instahyre: %d relevant jobs", len(jobs))
    return jobs


# ── Cutshort ────────────────────────────────────────────────────────────────
def _cutshort_jobs_from_next_data(html: str) -> list[dict]:
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (ValueError, TypeError):
        return []
    queries = data.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
    for q in queries:
        key = q.get("queryKey")
        if isinstance(key, list) and key and key[0] == "featuredJobListData":
            return (((q.get("state") or {}).get("data") or {}).get("data") or {}) \
                .get("pageData", {}).get("jobs", []) or []
    return []


def _cutshort_job(raw: dict) -> dict | None:
    url = raw.get("publicUrl")
    title = raw.get("headline")
    if not url or not title:
        return None
    if raw.get("hiringForClient"):     # explicit staffing/agency flag — drop
        return None
    company = (raw.get("companyDetails") or {}).get("name")
    skills = raw.get("allSkills") or []
    jd = _strip_html(raw.get("sanitizedComment") or "")
    description = jd or (("Skills: " + ", ".join(skills)) if skills else None)
    work = _CUTSHORT_REMOTE.get(raw.get("remoteType")) or \
        _detect_work_arrangement(title, raw.get("locationsText") or "", description or "")
    return _normalize(
        job_url=url,
        title=title,
        company=company,
        location=raw.get("locationsText"),
        job_description=description,
        source="cutshort",
        work_arrangement=work,
        salary_raw=raw.get("salaryRangeText") or None,
    )


async def fetch_cutshort(client, queries: list[str], locations: list[str]) -> list[dict]:
    resp = await client.get(_CUTSHORT_BASE, headers=_HEADERS)
    resp.raise_for_status()
    jobs: list[dict] = []
    seen: set[str] = set()
    for raw in _cutshort_jobs_from_next_data(resp.text):
        job = _cutshort_job(raw)
        if not job or job["job_url"] in seen:
            continue
        haystack = f"{job['title']} {job.get('job_description') or ''}"
        if not _matches_query(haystack, queries):
            continue
        seen.add(job["job_url"])
        jobs.append(job)
    logger.info("Cutshort: %d relevant jobs (best-effort SSR feed)", len(jobs))
    return jobs


# ── Orchestration ─────────────────────────────────────────────────────────────
_SOURCES = [
    ("instahyre", "SCRAPE_INSTAHYRE", fetch_instahyre),
    ("cutshort", "SCRAPE_CUTSHORT", fetch_cutshort),
]


async def _run_source(name: str, fn, client, queries, locations) -> list[dict]:
    if not circuit.allow(name):
        logger.info("%s skipped — circuit open", name)
        return []
    try:
        jobs = await fn(client, queries, locations)
        circuit.record_success(name)
        return jobs
    except Exception as exc:  # noqa: BLE001 — any failure isolates to []
        logger.warning("%s failed: %s", name, exc)
        circuit.record_failure(name)
        return []


async def fetch_all_india_boards(client, queries: list[str], locations: list[str]) -> list[dict]:
    """Fan out the custom Indian-board adapters. Returns [] if Tier-3 is off."""
    if not getattr(settings, "TIER3_ENABLED", False):
        return []
    enabled = [(n, fn) for n, attr, fn in _SOURCES if getattr(settings, attr, True)]
    if not enabled:
        return []
    results = await asyncio.gather(
        *(_run_source(n, fn, client, queries, locations) for n, fn in enabled),
        return_exceptions=True,
    )
    jobs: list[dict] = []
    for r in results:
        if isinstance(r, list):
            jobs.extend(r)
        elif isinstance(r, Exception):
            logger.warning("India-board source failed: %s", r)
    logger.info("India-board custom adapters total: %d jobs", len(jobs))
    return jobs