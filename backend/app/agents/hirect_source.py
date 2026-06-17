"""Hirect adapter — config-driven replay of the (reverse-engineered) mobile API.

Hirect is an Android/iOS-first **direct-chat** hiring app: there is no public web
API, traffic is TLS-certificate-pinned, and seeing jobs requires a logged-in
account. As of this writing the Indian domain ``hirect.in`` does **not resolve**
(the India service appears wound down) — verify Hirect is still live in India
before investing capture effort. See ``Others/hirect_api_notes.md`` for the full
mobile-capture playbook (emulator + mitmproxy + Frida cert-unpinning).

This adapter ships **dormant**: it only fires when both ``HIRECT_API_BASE`` and
``HIRECT_TOKEN`` are set (filled in from a capture). Until then it returns ``[]``
so it never affects a discovery run. Gated by ``SCRAPE_HIRECT`` + ``TIER3_ENABLED``.

PII GUARDRAIL: collect job postings only — title, company, location, JD, link.
**Never** persist recruiter/candidate names, phone numbers, or chat content
(Hirect's core is direct messaging; that data is personal under the DPDP Act).
"""

import logging

from app.agents.job_discovery_agent import _detect_work_arrangement, _normalize, _strip_html
from app.agents.proxy_pool import circuit
from app.config import settings

logger = logging.getLogger(__name__)

# Endpoint path + payload shape are unknown until the capture spike. These are
# placeholders to adjust from your captured request (see the notes file).
_JOB_SEARCH_PATH = "/v1/job/search"      # TODO: replace with the captured path
_PAGE_SIZE = 30


def _parse_hirect(payload: dict) -> list[dict]:
    """Map a captured Hirect job-search response to normalized jobs.

    The real field names come from your capture — this reads a defensive set of
    common shapes (``data.list`` / ``data.jobs`` / ``results``). Adjust the keys
    once the capture confirms them. Deliberately ignores any recruiter/HR contact
    fields (PII).
    """
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    items = data.get("list") or data.get("jobs") or data.get("results") or []
    jobs: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        jid = it.get("jobId") or it.get("id")
        title = it.get("jobName") or it.get("title") or it.get("position")
        if not jid or not title:
            continue
        company = it.get("companyName") or it.get("company")
        location = it.get("cityName") or it.get("city") or it.get("location")
        desc = _strip_html(str(it.get("jobDescription") or it.get("description") or "")) or None
        jobs.append(_normalize(
            job_url=it.get("shareUrl") or f"https://www.hirect.in/job/{jid}",
            title=str(title),
            company=company,
            location=location,
            job_description=desc,
            source="hirect",
            work_arrangement=_detect_work_arrangement(str(title), str(location or ""), desc or ""),
            salary_raw=it.get("salaryDesc") or it.get("salary"),
        ))
    return jobs


async def fetch_hirect(client, queries: list[str], locations: list[str]) -> list[dict]:
    base = (settings.HIRECT_API_BASE or "").rstrip("/")
    token = settings.HIRECT_TOKEN or ""
    if not base or not token:
        logger.info("Hirect dormant — HIRECT_API_BASE / HIRECT_TOKEN unset (run the capture spike)")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Hirect/Android",
        "Accept": "application/json",
    }
    jobs: list[dict] = []
    seen: set[str] = set()
    for query in queries[:2]:
        params = {"keyword": query, "pageSize": _PAGE_SIZE, "city": (locations[0] if locations else "")}
        resp = await client.get(f"{base}{_JOB_SEARCH_PATH}", params=params, headers=headers)
        resp.raise_for_status()
        for job in _parse_hirect(resp.json() or {}):
            if job["job_url"] not in seen:
                seen.add(job["job_url"])
                jobs.append(job)
    logger.info("Hirect: %d jobs", len(jobs))
    return jobs


async def fetch_all_hirect(client, queries: list[str], locations: list[str]) -> list[dict]:
    """Entry point with master gate + circuit breaker. Returns [] when off/dormant."""
    if not getattr(settings, "TIER3_ENABLED", False) or not getattr(settings, "SCRAPE_HIRECT", False):
        return []
    if not circuit.allow("hirect"):
        return []
    try:
        jobs = await fetch_hirect(client, queries, locations)
        circuit.record_success("hirect")
        return jobs
    except Exception as exc:  # noqa: BLE001 — any failure isolates to []
        logger.warning("Hirect failed: %s", exc)
        circuit.record_failure("hirect")
        return []
