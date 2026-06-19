"""hirist.tech adapter — India's niche IT job board (Next.js SSR).

robots.txt checked 2026-06-19: job-listing paths (e.g. /software-developer-jobs-in-bangalore,
/it-jobs-in-*) are ALLOWED for "User-agent: *", with "Crawl-delay: 10". This adapter
honors that crawl-delay and only reads public listing pages. hirist is a Next.js
app and ships its listing data inside the SSR ``__NEXT_DATA__`` JSON blob — no
public JSON API and no JSON-LD JobPosting was found — so we parse that blob with a
defensive recursive walk (resilient to field renames). If the shape changes and no
jobs are found, the adapter returns [] and the run is unaffected.

Gated by ``SCRAPE_HIRIST`` + ``TIER3_ENABLED`` (opt-in, OFF by default) and the
shared circuit breaker. PII GUARDRAIL: collect job postings only (title, company,
location, JD, link, salary) — never persist recruiter names/phones/emails.
"""
import asyncio
import json
import logging
import re

from app.agents.job_discovery_agent import (
    _detect_work_arrangement,
    _normalize,
    _parse_iso,
    _parse_notice_period,
    _strip_html,
)
from app.agents.proxy_pool import circuit
from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://www.hirist.tech"
_CRAWL_DELAY = 10  # robots.txt Crawl-delay
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-IN,en;q=0.9",
}
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.DOTALL
)

_TITLE_KEYS = ("title", "designation", "jobTitle", "position", "name")
_COMPANY_KEYS = ("company", "companyName", "company_name", "organisation", "recruiterCompany")
_LOC_KEYS = ("location", "city", "jobLocation", "locations", "cityName")
_URL_KEYS = ("url", "jobUrl", "seoUrl", "link", "applyUrl")
_ID_KEYS = ("id", "jobId", "_id", "jobIdEncrypted")
_DESC_KEYS = ("description", "jobDescription", "jd", "aboutJob")
_SAL_KEYS = ("salary", "salaryRange", "ctc", "compensation")


def _first(d: dict, keys) -> str | None:
    for k in keys:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, list) and v and isinstance(v[0], str):
            return ", ".join(x for x in v if isinstance(x, str))
    return None


def _looks_like_job(d: dict) -> bool:
    return _first(d, _TITLE_KEYS) is not None and (
        _first(d, _COMPANY_KEYS) is not None or _first(d, _ID_KEYS) is not None
    )


def _to_job(d: dict) -> dict | None:
    title = _first(d, _TITLE_KEYS)
    if not title:
        return None
    url = _first(d, _URL_KEYS)
    if url and not url.startswith("http"):
        url = f"{_BASE}/{url.lstrip('/')}"
    if not url:
        jid = _first(d, _ID_KEYS)
        if not jid:
            return None
        url = f"{_BASE}/j/{jid}"
    company = _first(d, _COMPANY_KEYS)
    location = _first(d, _LOC_KEYS)
    desc = _strip_html(_first(d, _DESC_KEYS) or "") or None
    salary = _first(d, _SAL_KEYS)
    posted = _parse_iso(d.get("postedDate") or d.get("createdAt") or d.get("postedOn"))
    return _normalize(
        job_url=url, title=title, company=company, location=location,
        job_description=desc, source="hirist",
        work_arrangement=_detect_work_arrangement(title, location or "", desc or ""),
        posted_at=posted, salary_raw=salary,
        notice_period=_parse_notice_period(desc or ""),
    )


def _walk_for_jobs(node, out: list[dict], seen_ids: set[int]) -> None:
    if isinstance(node, dict):
        if _looks_like_job(node):
            out.append(node)
            return
        for v in node.values():
            _walk_for_jobs(v, out, seen_ids)
    elif isinstance(node, list):
        for v in node:
            _walk_for_jobs(v, out, seen_ids)


def _parse_next_data(html: str) -> list[dict]:
    m = _NEXT_DATA_RE.search(html or "")
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []
    raw: list[dict] = []
    _walk_for_jobs(data.get("props", data), raw, set())
    jobs: list[dict] = []
    seen: set[str] = set()
    for d in raw:
        job = _to_job(d)
        if job and job["job_url"] not in seen:
            seen.add(job["job_url"])
            jobs.append(job)
    return jobs


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _listing_urls(queries: list[str], locations: list[str]) -> list[str]:
    city = _slugify(locations[0]) if locations else ""
    urls: list[str] = []
    for q in queries[:2]:
        kw = _slugify(q)
        if not kw:
            continue
        urls.append(f"{_BASE}/{kw}-jobs-in-{city}" if city else f"{_BASE}/{kw}-jobs")
    return urls


async def fetch_hirist_tech(client, queries: list[str], locations: list[str]) -> list[dict]:
    jobs: list[dict] = []
    seen: set[str] = set()
    for i, url in enumerate(_listing_urls(queries, locations)):
        if i:
            await asyncio.sleep(_CRAWL_DELAY)  # respect robots Crawl-delay
        resp = await client.get(url, headers=_HEADERS, timeout=20)
        if resp.status_code != 200:
            continue
        for job in _parse_next_data(resp.text):
            if job["job_url"] not in seen:
                seen.add(job["job_url"])
                jobs.append(job)
    logger.info("Hirist: %d jobs", len(jobs))
    return jobs


async def fetch_all_hirist_tech(client, queries: list[str], locations: list[str]) -> list[dict]:
    """Entry point with master gate + circuit breaker. Returns [] when off."""
    if not getattr(settings, "TIER3_ENABLED", False) or not getattr(settings, "SCRAPE_HIRIST", False):
        return []
    if not circuit.allow("hirist"):
        return []
    try:
        jobs = await fetch_hirist_tech(client, queries, locations)
        circuit.record_success("hirist")
        return jobs
    except Exception as exc:  # noqa: BLE001 — any failure isolates to []
        logger.warning("Hirist failed: %s", exc)
        circuit.record_failure("hirist")
        return []
