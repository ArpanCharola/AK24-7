"""Tier-1 public ATS adapters for India job discovery.

Each adapter hits a free, no-auth, direct-employer endpoint and returns a list
of normalized job dicts (the shape frozen in WORKSTREAMS contract #3). Adapters
never raise: a dead slug or transient error degrades to an empty list so one bad
source can never break a discovery run. India/staffing filtering and LPA/notice
parsing happen downstream in job_discovery_agent — adapters only fetch + shape.

Endpoints verified live 2026-05-31 (see Others/status/A1-discovery.md):
Greenhouse, Lever, SmartRecruiters, Ashby, Workable, Breezy, remote feeds.
Recruitee/Personio/Workday-CXS/Zoho adapters are shape-correct but their seed
lists are best-effort (no India roles confirmed at probe time).
"""

import asyncio
import logging
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import httpx

from app.agents.job_discovery_agent import (
    _detect_work_arrangement,
    _is_within_days,
    _matches_criteria,
    _normalize,
    _parse_iso,
    _strip_html,
)

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 15
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _company_from_slug(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").title()


def _epoch_ms_to_dt(ms) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


# ── Greenhouse ──────────────────────────────────────────────────────────────

async def greenhouse(client, slugs, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for slug in slugs:
        try:
            resp = await client.get(
                f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true",
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            company = data.get("name") or _company_from_slug(slug)
            for job in data.get("jobs", []):
                title = job.get("title", "")
                if profile and not _matches_criteria(title, profile):
                    continue
                location = (job.get("location") or {}).get("name", "")
                description = _strip_html(job.get("content", ""))
                posted_at = _parse_iso(job.get("updated_at"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                jobs.append(_normalize(
                    job_url=job.get("absolute_url", ""),
                    title=title, company=company, location=location,
                    job_description=description, source="greenhouse",
                    work_arrangement=_detect_work_arrangement(title, location, description),
                    posted_at=posted_at,
                ))
        except Exception as exc:
            logger.debug("Greenhouse %s: %s", slug, exc)
    logger.info("Greenhouse: %d jobs from %d slugs", len(jobs), len(slugs))
    return jobs


# ── Lever ───────────────────────────────────────────────────────────────────

async def lever(client, slugs, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for slug in slugs:
        try:
            resp = await client.get(
                f"https://api.lever.co/v0/postings/{slug}?mode=json", timeout=_HTTP_TIMEOUT
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not isinstance(data, list):
                continue
            for posting in data:
                title = posting.get("text", "")
                if profile and not _matches_criteria(title, profile):
                    continue
                cats = posting.get("categories", {}) or {}
                commitment = (cats.get("commitment") or "").lower()
                if commitment and any(x in commitment for x in ("part", "intern", "temp", "volunteer")):
                    continue
                location = cats.get("location", "")
                description = _strip_html(
                    posting.get("descriptionPlain") or posting.get("description", "")
                )
                created = posting.get("createdAt")
                posted_at = _epoch_ms_to_dt(created) if created else None
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                jobs.append(_normalize(
                    job_url=posting.get("hostedUrl", ""),
                    title=title, company=_company_from_slug(slug), location=location,
                    job_description=description, source="lever",
                    work_arrangement=(
                        "remote" if (posting.get("workplaceType") or "").lower() == "remote"
                        else _detect_work_arrangement(title, location, description)
                    ),
                    posted_at=posted_at,
                ))
        except Exception as exc:
            logger.debug("Lever %s: %s", slug, exc)
        await asyncio.sleep(0.3)  # Lever rate-limits bursts
    logger.info("Lever: %d jobs from %d slugs", len(jobs), len(slugs))
    return jobs


# ── SmartRecruiters ───────────────────────────────────────────────────────────
# The ?country=India filter proved unreliable (returns 0 even for employers with
# India offices), so we fetch all postings and let _is_india_location filter.

async def smartrecruiters(client, company_ids, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for company_id in company_ids:
        offset = 0
        try:
            while offset < 400:
                resp = await client.get(
                    f"https://api.smartrecruiters.com/v1/companies/{company_id}/postings",
                    params={"limit": 100, "offset": offset},
                    headers={"Accept": "application/json"},
                    timeout=_HTTP_TIMEOUT,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                postings = data.get("content", [])
                if not postings:
                    break
                company = postings[0].get("company", {}).get("name") or _company_from_slug(company_id)
                for p in postings:
                    title = p.get("name", "")
                    if profile and not _matches_criteria(title, profile):
                        continue
                    loc = p.get("location", {}) or {}
                    location = ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")]))
                    posted_at = _parse_iso(p.get("releasedDate") or p.get("createdOn"))
                    if not _is_within_days(posted_at, posted_within_days):
                        continue
                    jobs.append(_normalize(
                        job_url=f"https://jobs.smartrecruiters.com/{company_id}/{p.get('id', '')}",
                        title=title, company=company, location=location,
                        job_description="", source="smartrecruiters",
                        work_arrangement=(
                            "remote" if p.get("remote") else _detect_work_arrangement(title, location, "")
                        ),
                        posted_at=posted_at,
                    ))
                offset += len(postings)
                if offset >= data.get("totalFound", 0):
                    break
        except Exception as exc:
            logger.debug("SmartRecruiters %s: %s", company_id, exc)
    logger.info("SmartRecruiters: %d jobs from %d companies", len(jobs), len(company_ids))
    return jobs


# ── Ashby ─────────────────────────────────────────────────────────────────────

def _ashby_salary(job: dict) -> str | None:
    comp = job.get("compensation") or {}
    summary = comp.get("compensationTierSummary") or comp.get("summary")
    if summary:
        return str(summary)
    tiers = comp.get("compensationTiers") or []
    if tiers and isinstance(tiers, list):
        return tiers[0].get("title") or tiers[0].get("summary")
    return None


async def ashby(client, slugs, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for slug in slugs:
        try:
            resp = await client.get(
                f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true",
                headers={"Accept": "application/json"},
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            company = (data.get("organization") or {}).get("name") or data.get("name") or _company_from_slug(slug)
            # Ashby's posting-api returns `jobs` (current) or `jobPostings` (older).
            for job in (data.get("jobPostings") or data.get("jobs") or []):
                title = job.get("title", "")
                if profile and not _matches_criteria(title, profile):
                    continue
                emp_type = (job.get("employmentType") or "").lower()
                if any(x in emp_type for x in ("part", "intern", "temp", "volunteer")):
                    continue
                location = job.get("location") or job.get("locationName") or ""
                if isinstance(location, dict):
                    location = location.get("name", "")
                description = _strip_html(job.get("descriptionHtml") or job.get("descriptionPlain") or "")
                posted_at = _parse_iso(job.get("publishedAt") or job.get("publishedDate"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                job_id = job.get("id", "")
                jobs.append(_normalize(
                    job_url=(job.get("jobUrl") or job.get("applyUrl")
                             or f"https://jobs.ashbyhq.com/{slug}/{job_id}"),
                    title=title, company=company, location=location,
                    job_description=description, source="ashby",
                    work_arrangement=(
                        "remote" if job.get("isRemote")
                        else _detect_work_arrangement(title, location, description)
                    ),
                    posted_at=posted_at,
                    salary_raw=_ashby_salary(job),
                ))
        except Exception as exc:
            logger.debug("Ashby %s: %s", slug, exc)
    logger.info("Ashby: %d jobs from %d slugs", len(jobs), len(slugs))
    return jobs


# ── Workable ──────────────────────────────────────────────────────────────────

async def workable(client, subdomains, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for sub in subdomains:
        try:
            resp = await client.get(
                f"https://apply.workable.com/api/v1/widget/accounts/{sub}?details=true",
                headers={"Accept": "application/json", "User-Agent": _UA},
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            company = data.get("name") or _company_from_slug(sub)
            for job in data.get("jobs", []):
                title = job.get("title", "")
                if profile and not _matches_criteria(title, profile):
                    continue
                emp_type = (job.get("employment_type") or "").lower()
                if any(x in emp_type for x in ("part", "intern", "temp")):
                    continue
                location = ", ".join(filter(None, [
                    job.get("city"), job.get("state"), job.get("country")
                ])) or job.get("location", "")
                description = _strip_html(job.get("description", ""))
                posted_at = _parse_iso(job.get("published_on") or job.get("created_at"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                shortcode = job.get("shortcode", "")
                jobs.append(_normalize(
                    job_url=(job.get("url") or job.get("application_url")
                             or f"https://apply.workable.com/{sub}/j/{shortcode}/"),
                    title=title, company=company, location=location,
                    job_description=description, source="workable",
                    work_arrangement=(
                        "remote" if job.get("remote") else _detect_work_arrangement(title, location, description)
                    ),
                    posted_at=posted_at,
                ))
        except Exception as exc:
            logger.debug("Workable %s: %s", sub, exc)
    logger.info("Workable: %d jobs from %d subdomains", len(jobs), len(subdomains))
    return jobs


# ── Recruitee ───────────────────────────────────────────────────────────────

async def recruitee(client, subdomains, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for sub in subdomains:
        try:
            resp = await client.get(
                f"https://{sub}.recruitee.com/api/offers/",
                headers={"Accept": "application/json", "User-Agent": _UA},
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            company = _company_from_slug(sub)
            for offer in resp.json().get("offers", []):
                title = offer.get("title", "")
                if profile and not _matches_criteria(title, profile):
                    continue
                emp_type = (offer.get("employment_type") or "").lower()
                if any(x in emp_type for x in ("intern", "part", "temp")):
                    continue
                location = ", ".join(filter(None, [
                    offer.get("city"), offer.get("country")
                ])) or offer.get("location", "")
                description = _strip_html(offer.get("description", ""))
                posted_at = _parse_iso(offer.get("published_at") or offer.get("created_at"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                jobs.append(_normalize(
                    job_url=offer.get("careers_url") or offer.get("careers_apply_url", ""),
                    title=title, company=company, location=location,
                    job_description=description, source="recruitee",
                    work_arrangement=_detect_work_arrangement(title, location, description),
                    posted_at=posted_at,
                ))
        except Exception as exc:
            logger.debug("Recruitee %s: %s", sub, exc)
    logger.info("Recruitee: %d jobs from %d subdomains", len(jobs), len(subdomains))
    return jobs


# ── Breezy ──────────────────────────────────────────────────────────────────

async def breezy(client, subdomains, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for sub in subdomains:
        try:
            resp = await client.get(
                f"https://{sub}.breezy.hr/json",
                headers={"Accept": "application/json", "User-Agent": _UA},
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            data = resp.json()
            if not isinstance(data, list):
                continue
            company = _company_from_slug(sub)
            for job in data:
                if not isinstance(job, dict):
                    continue
                title = job.get("name", "")
                if profile and not _matches_criteria(title, profile):
                    continue
                emp_type = (job.get("type", {}) or {}).get("name", "").lower()
                if any(x in emp_type for x in ("intern", "part", "temp")):
                    continue
                loc = job.get("location", {}) or {}
                location = (loc.get("name")
                            or ", ".join(filter(None, [(loc.get("city") or {}).get("name") if isinstance(loc.get("city"), dict) else loc.get("city"),
                                                       (loc.get("country") or {}).get("name") if isinstance(loc.get("country"), dict) else loc.get("country")])))
                description = _strip_html(job.get("description", ""))
                posted_at = _parse_iso(job.get("published_date") or job.get("creation_date"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                jobs.append(_normalize(
                    job_url=job.get("url") or f"https://{sub}.breezy.hr/p/{job.get('id', '')}",
                    title=title, company=company, location=location,
                    job_description=description, source="breezy",
                    work_arrangement=(
                        "remote" if (loc.get("is_remote") or job.get("remote"))
                        else _detect_work_arrangement(title, location, description)
                    ),
                    posted_at=posted_at,
                ))
        except Exception as exc:
            logger.debug("Breezy %s: %s", sub, exc)
    logger.info("Breezy: %d jobs from %d subdomains", len(jobs), len(subdomains))
    return jobs


# ── Personio (XML) ────────────────────────────────────────────────────────────

def _xml_text(el, tag: str) -> str:
    child = el.find(tag)
    return (child.text or "").strip() if child is not None and child.text else ""


async def personio(client, subdomains, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for sub in subdomains:
        try:
            resp = await client.get(
                f"https://{sub}.jobs.personio.de/xml",
                headers={"Accept": "application/xml", "User-Agent": _UA},
                timeout=_HTTP_TIMEOUT,
            )
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            company = _company_from_slug(sub)
            for pos in root.iter("position"):
                title = _xml_text(pos, "name")
                if profile and not _matches_criteria(title, profile):
                    continue
                emp_type = _xml_text(pos, "employmentType").lower()
                if any(x in emp_type for x in ("intern", "part", "temp", "working_student")):
                    continue
                location = _xml_text(pos, "office")
                desc_parts = [(d.text or "") for d in pos.iter("value")]
                description = _strip_html(" ".join(desc_parts))
                posted_at = _parse_iso(_xml_text(pos, "createdAt"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                job_id = _xml_text(pos, "id")
                jobs.append(_normalize(
                    job_url=f"https://{sub}.jobs.personio.de/job/{job_id}",
                    title=title, company=company, location=location,
                    job_description=description, source="personio",
                    work_arrangement=_detect_work_arrangement(title, location, description),
                    posted_at=posted_at,
                ))
        except Exception as exc:
            logger.debug("Personio %s: %s", sub, exc)
    logger.info("Personio: %d jobs from %d subdomains", len(jobs), len(subdomains))
    return jobs


# ── Workday CXS ───────────────────────────────────────────────────────────────

async def workday(client, entries, profile=None, posted_within_days=None) -> list[dict]:
    roles = [r.strip() for r in ((profile or {}).get("target_roles") or "").split(",") if r.strip()]
    search_terms = roles[:2] or [""]
    jobs: list[dict] = []
    for entry in entries:
        sub = entry.get("subdomain", "")
        tenant = entry.get("tenant", "1")
        site = entry.get("site") or entry.get("careers_page", "External")
        company = entry.get("company", sub)
        base = f"https://{sub}.wd{tenant}.myworkdayjobs.com"
        api = f"{base}/wday/cxs/{sub}/{site}/jobs"
        for term in search_terms:
            offset = 0
            try:
                while offset < 100:
                    resp = await client.post(
                        api,
                        json={"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": term},
                        headers={"Content-Type": "application/json", "Accept": "application/json"},
                        timeout=_HTTP_TIMEOUT,
                    )
                    if resp.status_code != 200:
                        break
                    data = resp.json()
                    postings = data.get("jobPostings", [])
                    if not postings:
                        break
                    for p in postings:
                        title = (p.get("title") or "").strip()
                        if not title or (profile and not _matches_criteria(title, profile)):
                            continue
                        location = (p.get("locationsText") or "").strip()
                        ext = p.get("externalPath", "")
                        jobs.append(_normalize(
                            job_url=f"{base}/en-US/{site}{ext}",
                            title=title, company=company, location=location,
                            job_description="", source="workday",
                            work_arrangement=_detect_work_arrangement(title, location, ""),
                            posted_at=None,
                        ))
                    offset += len(postings)
                    if offset >= data.get("total", 0):
                        break
                    await asyncio.sleep(0.3)
            except Exception as exc:
                logger.debug("Workday %s/%s: %s", company, term, exc)
    logger.info("Workday: %d jobs from %d tenants", len(jobs), len(entries))
    return jobs


# ── Zoho Recruit (XML feed) ─────────────────────────────────────────────────
# Zoho exposes no single canonical pattern — each employer publishes a per-account
# RSS/XML feed. Seed entries carry an explicit "feed_url" so this stays declarative.

async def zoho(client, entries, profile=None, posted_within_days=None) -> list[dict]:
    jobs: list[dict] = []
    for entry in entries:
        feed_url = entry.get("feed_url")
        company = entry.get("company", "")
        if not feed_url:
            continue
        try:
            resp = await client.get(
                feed_url, headers={"Accept": "application/xml", "User-Agent": _UA}, timeout=_HTTP_TIMEOUT
            )
            if resp.status_code != 200:
                continue
            root = ET.fromstring(resp.content)
            for item in root.iter("item"):
                title = _xml_text(item, "title")
                if profile and not _matches_criteria(title, profile):
                    continue
                link = _xml_text(item, "link")
                description = _strip_html(_xml_text(item, "description"))
                posted_at = _parse_iso(_xml_text(item, "pubDate"))
                if not _is_within_days(posted_at, posted_within_days):
                    continue
                jobs.append(_normalize(
                    job_url=link, title=title, company=company, location="",
                    job_description=description, source="zoho",
                    work_arrangement=_detect_work_arrangement(title, "", description),
                    posted_at=posted_at,
                ))
        except Exception as exc:
            logger.debug("Zoho %s: %s", company, exc)
    logger.info("Zoho: %d jobs from %d feeds", len(jobs), len(entries))
    return jobs


# ── Orchestrator ──────────────────────────────────────────────────────────────

async def fetch_all_ats(client, slugs: dict, profile=None, posted_within_days=None) -> list[dict]:
    """Fan out every Tier-1 ATS adapter concurrently. Returns combined dicts."""
    tasks = [
        greenhouse(client, slugs.get("greenhouse", []), profile, posted_within_days),
        lever(client, slugs.get("lever", []), profile, posted_within_days),
        smartrecruiters(client, slugs.get("smartrecruiters", []), profile, posted_within_days),
        ashby(client, slugs.get("ashby", []), profile, posted_within_days),
        workable(client, slugs.get("workable", []), profile, posted_within_days),
        recruitee(client, slugs.get("recruitee", []), profile, posted_within_days),
        breezy(client, slugs.get("breezy", []), profile, posted_within_days),
        personio(client, slugs.get("personio", []), profile, posted_within_days),
        workday(client, slugs.get("workday", []), profile, posted_within_days),
        zoho(client, slugs.get("zoho", []), profile, posted_within_days),
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    jobs: list[dict] = []
    for r in results:
        if isinstance(r, list):
            jobs.extend(r)
        elif isinstance(r, Exception):
            logger.warning("ATS adapter failed: %s", r)
    logger.info("Tier-1 ATS total: %d jobs", len(jobs))
    return jobs
