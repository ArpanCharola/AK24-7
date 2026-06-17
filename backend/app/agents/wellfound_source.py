"""Wellfound (formerly AngelList Talent) adapter — best-effort, stealth-browser only.

Wellfound sits behind DataDome + Cloudflare: a plain httpx GET returns 403 + a
captcha challenge. We render the search page with a stealth browser
(``stealth_fetch``) and extract jobs from whatever the render exposes:

  1. structured embedded state — ``__NEXT_DATA__`` or ``window.__APOLLO_STATE__``
     (walked generically, since the exact typenames shift between deploys), then
  2. a fallback that harvests ``/jobs/<id>-<slug>`` detail links straight from the
     rendered HTML and humanises the slug into a title.

Without residential proxies the render is frequently challenged, so this source
is genuinely best-effort and degrades to ``[]`` on any block. Gated by
``SCRAPE_WELLFOUND`` + ``STEALTH_ENABLED``; plug residential proxies into
``SCRAPE_PROXIES`` to make it reliable (no code change).
"""

import json
import logging
import re

from app.agents.job_discovery_agent import _detect_work_arrangement, _normalize, _strip_html
from app.agents.proxy_pool import circuit, proxy_pool
from app.agents.stealth_fetch import fetch_rendered
from app.config import settings

logger = logging.getLogger(__name__)

_BASE = "https://wellfound.com"
_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
_APOLLO_RE = re.compile(r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\})\s*;?\s*<", re.DOTALL)
_JOB_LINK_RE = re.compile(r'href="(/jobs/(\d+)-([a-z0-9-]+))"')
_BLOCK_MARKERS = ("datadome", "captcha-delivery", "verifying you are human", "px-captcha")


def _role_slug(query: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")


def _humanize(slug: str) -> str:
    return re.sub(r"-\d+$", "", slug).replace("-", " ").title()


def _looks_blocked(html: str) -> bool:
    low = html.lower()
    return any(m in low for m in _BLOCK_MARKERS)


def _job_from_link(path: str, slug: str) -> dict:
    title = _humanize(slug)
    return _normalize(
        job_url=f"{_BASE}{path}",
        title=title,
        source="wellfound",
        location="India",
        work_arrangement=_detect_work_arrangement(title, "", ""),
    )


def _extract_jobs(html: str) -> list[dict]:
    """Pull jobs from embedded state, else from rendered job links. Best-effort."""
    jobs: list[dict] = []
    seen: set[str] = set()

    # Strategy 2 (most robust across deploys): harvest job detail links.
    for path, _job_id, slug in _JOB_LINK_RE.findall(html):
        if path in seen:
            continue
        seen.add(path)
        jobs.append(_job_from_link(path, slug))

    if jobs:
        return jobs

    # Strategy 1 fallback: walk embedded Apollo/Next state for job-shaped dicts.
    blob = None
    m = _APOLLO_RE.search(html) or _NEXT_DATA_RE.search(html)
    if m:
        try:
            blob = json.loads(m.group(1))
        except (ValueError, TypeError):
            blob = None
    if blob is not None:
        _walk_state(blob, jobs, seen)
    return jobs


def _walk_state(node, jobs: list[dict], seen: set[str]) -> None:
    if isinstance(node, dict):
        tn = str(node.get("__typename", ""))
        title = node.get("title") or node.get("jobTitle")
        jid = node.get("id")
        if "Job" in tn and title and jid:
            path = f"/jobs/{jid}"
            if path not in seen:
                seen.add(path)
                jobs.append(_normalize(
                    job_url=f"{_BASE}{path}",
                    title=str(title),
                    company=(node.get("startup") or {}).get("name") if isinstance(node.get("startup"), dict) else None,
                    source="wellfound",
                    location="India",
                    job_description=_strip_html(str(node.get("description") or "")) or None,
                    work_arrangement="remote" if node.get("remote") else _detect_work_arrangement(str(title), "", ""),
                ))
        for v in node.values():
            _walk_state(v, jobs, seen)
    elif isinstance(node, list):
        for v in node:
            _walk_state(v, jobs, seen)


async def fetch_wellfound(queries: list[str], locations: list[str]) -> list[dict]:
    """Render Wellfound role searches in a stealth browser and extract jobs."""
    if not settings.STEALTH_ENABLED:
        logger.info("Wellfound skipped — STEALTH_ENABLED=false")
        return []

    jobs: list[dict] = []
    seen: set[str] = set()
    for query in queries[:2]:
        url = f"{_BASE}/role/r/{_role_slug(query)}"
        html = await fetch_rendered(
            url,
            proxy=proxy_pool.get(),
            wait_selector='a[href^="/jobs/"]',
            timeout_ms=35000,
        )
        if not html:
            continue
        if _looks_blocked(html):
            logger.info("Wellfound blocked (DataDome/captcha) for %r — needs residential proxy", query)
            raise RuntimeError("wellfound_blocked")   # trip the circuit breaker
        for job in _extract_jobs(html):
            if job["job_url"] not in seen:
                seen.add(job["job_url"])
                jobs.append(job)
    logger.info("Wellfound: %d jobs (best-effort)", len(jobs))
    return jobs


async def fetch_all_wellfound(queries: list[str], locations: list[str]) -> list[dict]:
    """Entry point with master gate + circuit breaker. Returns [] when off/blocked."""
    if not getattr(settings, "TIER3_ENABLED", False) or not getattr(settings, "SCRAPE_WELLFOUND", True):
        return []
    if not circuit.allow("wellfound"):
        logger.info("Wellfound skipped — circuit open")
        return []
    try:
        jobs = await fetch_wellfound(queries, locations)
        circuit.record_success("wellfound")
        return jobs
    except Exception as exc:  # noqa: BLE001 — block/render failure → []
        logger.warning("Wellfound failed: %s", exc)
        circuit.record_failure("wellfound")
        return []
