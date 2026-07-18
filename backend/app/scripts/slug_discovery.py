"""Slug-discovery pipeline — grows the company_source registry toward 500-1000.

How the scale platforms (Jobright/Tsenta) work: they don't have one magic feed,
they aggregate hundreds of thousands of employer career pages by discovering ATS
"board tokens" (slugs) at scale. We do the same for India:

  harvest candidate slugs  ->  probe each ATS's public API  ->  keep the ones
  that return >=1 India role  ->  de-fish  ->  upsert into company_source

Candidate sources (each best-effort, a failure is non-fatal):
  - Common Crawl CDX index  (broad ATS URL patterns — the scalable lever)
  - curated India list      (india_curated_slugs.json — highest precision)
  - the seed JSON           (re-validated, not blindly trusted)

Validation reuses the live adapters in app.agents.ats_sources as single-slug
probes (no new HTTP fetch code) and the exact India + staffing filters used by
the discovery postprocess. Idempotent upsert keyed on (ats, slug); dead slugs
are marked, never deleted. The same machinery powers the daily revalidation job.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
import re

import httpx
from sqlalchemy import select, func

from app.agents import ats_sources
from app.agents.job_discovery_agent import (
    _is_excluded_job,
    _INDIA_TOKENS,
    _GLOBAL_REMOTE,
    log_discovery_run,
)
from app.core.database import AsyncSessionLocal
from app.models.company_source import CompanySource

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data"
_SEED_PATH = _DATA_DIR / "india_company_slugs.json"
_CURATED_PATH = _DATA_DIR / "india_curated_slugs.json"
_TOP_PATH = _DATA_DIR / "top_india_companies.json"

# ATSes whose public board is keyed by a single bare slug — these are the ones
# we can both harvest and fan-out-probe. workday/zoho need per-employer config
# (tenant/site/feed_url) so they stay curated-only and are not probed here.
SLUG_ATSES = ("greenhouse", "lever", "ashby", "workable")
PROBE_ATSES = ("greenhouse", "lever", "ashby", "workable", "smartrecruiters", "recruitee", "breezy", "personio")

_ATS_FN = {
    "greenhouse": ats_sources.greenhouse,
    "lever": ats_sources.lever,
    "ashby": ats_sources.ashby,
    "workable": ats_sources.workable,
    "smartrecruiters": ats_sources.smartrecruiters,
    "recruitee": ats_sources.recruitee,
    "breezy": ats_sources.breezy,
    "personio": ats_sources.personio,
}

_DEAD_THRESHOLD = 3  # hysteresis: keep an active slug until N consecutive misses
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,60}$")
_SR_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,60}$")  # SmartRecruiters is case-sensitive

_PATH_RESERVED = {"", "embed", "jobs", "job", "api", "j", "o", "careers", "search", "login", "apply", "p", "k"}
_SUB_RESERVED = {"www", "api", "app", "jobs", "careers", "my", "static", "cdn", "assets", "blog", "help", "support", "go", "info", "mail", "docs", "status"}


# ── Candidate harvest ─────────────────────────────────────────────────────────

# (ats, cdx domain query, allowed_hosts, extract). matchType=domain captures the
# whole registered domain; allowed_hosts (path0) restricts to the board host so
# marketing pages don't pollute. sub = leftmost host label.
_CC_PATTERNS = [
    ("greenhouse", "greenhouse.io", {"boards.greenhouse.io", "job-boards.greenhouse.io"}, "path0"),
    ("lever", "lever.co", {"jobs.lever.co"}, "path0"),
    ("ashby", "ashbyhq.com", {"jobs.ashbyhq.com"}, "path0"),
    ("workable", "workable.com", {"apply.workable.com"}, "path0"),
    ("smartrecruiters", "smartrecruiters.com", {"jobs.smartrecruiters.com", "careers.smartrecruiters.com"}, "path0"),
    ("recruitee", "recruitee.com", None, "sub"),
    ("breezy", "breezy.hr", None, "sub"),
    ("personio", "jobs.personio.de", None, "sub"),
]


def _slug_from_url(url: str, ats: str, mode: str, allowed_hosts: set[str] | None = None) -> str | None:
    try:
        parts = urlsplit(url if "://" in url else f"https://{url}")
    except ValueError:
        return None
    host = (parts.netloc or "").lower().split(":")[0]
    if mode == "path0":
        if allowed_hosts and host not in allowed_hosts:
            return None
        segs = [s for s in (parts.path or "").split("/") if s]
        if not segs:
            return None
        cand = segs[0]
        if cand.lower() in _PATH_RESERVED:
            return None
    else:  # sub
        labels = host.split(".")
        if len(labels) < 3:
            return None
        cand = labels[0]
        if cand in _SUB_RESERVED:
            return None
    if ats == "smartrecruiters":
        return cand if _SR_SLUG_RE.match(cand) else None
    cand = cand.lower()
    return cand if _SLUG_RE.match(cand) else None


async def harvest_common_crawl(client: httpx.AsyncClient, limit_per_pattern: int = 800) -> dict[str, set[str]]:
    """Scan the latest Common Crawl CDX index for ATS URL patterns -> slugs."""
    out: dict[str, set[str]] = {a: set() for a in PROBE_ATSES}
    try:
        info = await client.get("https://index.commoncrawl.org/collinfo.json", timeout=30)
        indexes = info.json()
        cdx_api = indexes[0]["cdx-api"]  # most recent crawl
    except Exception as exc:  # noqa: BLE001
        logger.warning("Common Crawl index unavailable, skipping CC harvest: %s", repr(exc)[:160])
        return out

    for ats, domain, allowed_hosts, mode in _CC_PATTERNS:
        try:
            resp = await client.get(
                cdx_api,
                params={"url": domain, "output": "json", "fl": "url",
                        "matchType": "domain", "collapse": "urlkey", "limit": limit_per_pattern},
                timeout=90,
            )
            if resp.status_code != 200:
                continue
            for line in resp.text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                slug = _slug_from_url(rec.get("url", ""), ats, mode, allowed_hosts)
                if slug:
                    out[ats].add(slug)
        except Exception as exc:  # noqa: BLE001
            logger.warning("CC harvest %s/%s failed: %s", ats, domain, repr(exc)[:120])
        await asyncio.sleep(0.5)
    logger.info("Common Crawl harvest: %s", {k: len(v) for k, v in out.items() if v})
    return out


def _load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("could not read %s: %s", path.name, exc)
        return {}


# Corporate suffixes that never appear in an ATS slug. "Acme Technologies Pvt
# Ltd" registers its board as `acme`, not `acmetechnologiespvtltd`.
_CORP_SUFFIX_RE = re.compile(
    r"\b(pvt|private|ltd|limited|llp|inc|incorporated|corp|corporation|co|"
    r"technologies|technology|labs|solutions|services|systems|software|"
    r"global|india|consulting|ventures|group|holdings)\b",
    re.I,
)


def _name_to_slugs(name: str) -> list[str]:
    """A company name → candidate slug forms: concatenated + hyphenated, both
    with and without corporate suffixes (the boards use the bare brand)."""
    low = name.strip().lower()
    stripped = _CORP_SUFFIX_RE.sub(" ", low).strip()
    out: list[str] = []
    for base in (low, stripped):
        if not base:
            continue
        concat = re.sub(r"[^a-z0-9]", "", base)
        hyph = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        for c in (concat, hyph):
            if c and len(c) >= 2 and c not in out:
                out.append(c)
    return out


def harvest_curated() -> tuple[dict[str, set[str]], set[str]]:
    """Return (typed slugs by ats, bare company-name slugs to fan-out across ATSes).
    Merges india_curated_slugs.json + top_india_companies.json (the curated TOP
    500-1000 India employers)."""
    typed: dict[str, set[str]] = {a: set() for a in PROBE_ATSES}
    names: set[str] = set()
    for path in (_CURATED_PATH, _TOP_PATH):
        data = _load_json(path)
        for ats in PROBE_ATSES:
            for s in data.get(ats, []) or []:
                if isinstance(s, str):
                    typed[ats].add(s if ats == "smartrecruiters" else s.lower())
        for n in (data.get("names") or []):
            if isinstance(n, str) and n.strip():
                names.update(_name_to_slugs(n))
    return typed, names


def harvest_seed() -> dict[str, set[str]]:
    data = _load_json(_SEED_PATH)
    typed: dict[str, set[str]] = {a: set() for a in PROBE_ATSES}
    for ats in PROBE_ATSES:
        for s in data.get(ats, []) or []:
            if isinstance(s, str):
                typed[ats].add(s if ats == "smartrecruiters" else s.lower())
    return typed


# ── Validation ────────────────────────────────────────────────────────────────

def _explicit_india(location: str | None) -> bool:
    """Stricter than _is_india_location: a discovery candidate must have at least
    one role with an *explicit* India (or global-remote) location — the lenient
    'empty location -> India' default is not enough to claim a slug for India."""
    if not location:
        return False
    low = f" {location.strip().lower()} "
    return any(t in low for t in _INDIA_TOKENS) or any(t in low for t in _GLOBAL_REMOTE)


async def validate_candidate(client, ats: str, slug: str) -> tuple[int, int, str | None]:
    """Probe one (ats, slug). Returns (total_roles, india_roles, company_name)."""
    fn = _ATS_FN.get(ats)
    if fn is None:
        return 0, 0, None
    try:
        jobs = await fn(client, [slug], None, None)
    except Exception as exc:  # noqa: BLE001 — adapters shouldn't raise, but be safe
        logger.debug("probe %s/%s raised: %s", ats, slug, exc)
        return 0, 0, None
    india = [
        j for j in jobs
        if _explicit_india(j.get("location"))
        and not _is_excluded_job(j.get("title") or "", j.get("company") or "",
                                 j.get("job_url", ""), j.get("job_description") or "")
    ]
    company = jobs[0].get("company") if jobs else None
    return len(jobs), len(india), company


def _next_status(existing_status: str, india: int, dead_checks: int) -> tuple[str, int]:
    if india >= 1:
        return "active", 0
    new_checks = dead_checks + 1
    if existing_status == "active" and new_checks < _DEAD_THRESHOLD:
        return "active", new_checks  # hysteresis — survive transient misses
    return "dead", new_checks


# A board that answers but lists no India roles is future supply, not a broken
# endpoint. Re-probe it monthly instead of discarding it the way `dead` does.
_NO_INDIA_RECHECK_DAYS = 30


def _next_probe_state(status: str, total: int, india: int) -> tuple[str, datetime | None]:
    """Map a probe result onto (probe_state, next_probe_at).

    `status` is the legacy verdict from _next_status, which collapses "endpoint
    is gone" and "endpoint works but has no India roles" into `dead`. The queue
    keeps them apart so a hiring freeze doesn't permanently burn a good slug.
    """
    if status == "active":
        return "active", None
    if total > 0:
        return "no_india", datetime.now(timezone.utc) + timedelta(days=_NO_INDIA_RECHECK_DAYS)
    return "dead", None


def _country_hint(total: int, india: int) -> str | None:
    """Mark boards that are demonstrably India-centric.

    Threshold is deliberate: at >=40% India-explicit roles, an *unlabelled*
    posting on the same board is far more likely India than not, which is what
    lets the admission policy admit blank locations without guessing wildly.
    """
    if total <= 0:
        return None
    return "IN" if (india / total) >= 0.4 else None


async def _upsert(session, ats: str, slug: str, total: int, india: int,
                  company: str | None, source: str, config: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    row = (await session.execute(
        select(CompanySource).where(CompanySource.ats == ats, CompanySource.slug == slug)
    )).scalar_one_or_none()

    if row is None:
        status, checks = _next_status("unverified", india, 0)
        probe_state, next_probe = _next_probe_state(status, total, india)
        session.add(CompanySource(
            ats=ats, slug=slug, company_name=company, status=status,
            india_roles_count=india, total_roles_count=total,
            last_validated_at=now, last_seen_active_at=now if status == "active" else None,
            source_of_discovery=source, consecutive_dead_checks=checks, config_json=config,
            probe_state=probe_state, next_probe_at=next_probe,
            country_hint=_country_hint(total, india), probe_leased_until=None,
        ))
        return status

    status, checks = _next_status(row.status, india, row.consecutive_dead_checks)
    probe_state, next_probe = _next_probe_state(status, total, india)
    row.total_roles_count = total
    row.india_roles_count = india
    if company:
        row.company_name = company
    row.last_validated_at = now
    row.status = status
    row.consecutive_dead_checks = checks
    row.probe_state = probe_state
    row.next_probe_at = next_probe
    row.probe_leased_until = None
    hint = _country_hint(total, india)
    if hint:
        row.country_hint = hint
    if status == "active":
        row.last_seen_active_at = now
    if config and not row.config_json:
        row.config_json = config
    return status


# ── Orchestration ─────────────────────────────────────────────────────────────

def _build_probe_set(harvests: list[dict[str, set[str]]], names: set[str]) -> dict[tuple[str, str], str]:
    """Merge harvests + name fan-out into a deduped {(ats, slug): provenance}."""
    probes: dict[tuple[str, str], str] = {}
    prov_order = {"curated": 3, "seed_json": 2, "commoncrawl": 1}

    def add(ats, slug, prov):
        key = (ats, slug)
        if key not in probes or prov_order.get(prov, 0) > prov_order.get(probes[key], 0):
            probes[key] = prov

    sources = list(zip(harvests, ("seed_json", "curated", "commoncrawl")))
    for harvest, prov in sources:
        for ats, slugs in harvest.items():
            for slug in slugs:
                add(ats, slug, prov)
    # Bare names: try across the four common slug ATSes; validation finds the hit.
    for name in names:
        for ats in SLUG_ATSES:
            add(ats, name, "curated")
    return probes


async def run_discovery(
    *,
    use_common_crawl: bool = True,
    cc_limit_per_pattern: int = 800,
    max_validations: int = 1200,
    skip_recent_probed: bool = True,
    skip_within_hours: int = 48,
) -> dict:
    """Harvest -> probe -> upsert. Returns a stats dict."""
    typed_curated, names = harvest_curated()
    seed = harvest_seed()
    harvests = [seed, typed_curated]

    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": ats_sources._UA}) as client:
        if use_common_crawl:
            harvests.append(await harvest_common_crawl(client, cc_limit_per_pattern))

        probes = _build_probe_set(harvests, names)

        if skip_recent_probed:
            already = await _recently_probed_keys(skip_within_hours)
            probes = {k: v for k, v in probes.items() if k not in already}

        items = list(probes.items())[:max_validations]
        logger.info("Probing %d candidate (ats, slug) pairs", len(items))

        sem = asyncio.Semaphore(10)
        results: list[tuple[str, str, str, int, int, str | None]] = []

        async def probe(ats, slug, prov):
            async with sem:
                total, india, company = await validate_candidate(client, ats, slug)
                return ats, slug, prov, total, india, company

        gathered = await asyncio.gather(
            *(probe(ats, slug, prov) for (ats, slug), prov in items),
            return_exceptions=True,
        )
        for g in gathered:
            if isinstance(g, tuple):
                results.append(g)

    stats = {"probed": len(results), "active": 0, "live_no_india": 0, "dead": 0}
    async with AsyncSessionLocal() as session:
        for ats, slug, prov, total, india, company in results:
            status = await _upsert(session, ats, slug, total, india, company, prov)
            if status == "active":
                stats["active"] += 1
            elif total > 0:
                stats["live_no_india"] += 1
            else:
                stats["dead"] += 1
        await session.commit()
        stats["registry_active_total"] = (await session.execute(
            select(func.count()).select_from(CompanySource).where(CompanySource.status == "active")
        )).scalar()
    logger.info("Discovery wave done: %s", stats)
    await log_discovery_run("slug_discovery", jobs_found=stats.get("active", 0), stats=stats)
    return stats


async def _recently_probed_keys(within_hours: int) -> set[tuple[str, str]]:
    """(ats, slug) pairs validated within the window — skip to avoid re-probing
    known-dead/active slugs so a fresh wave spends its budget on new harvest."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(CompanySource.ats, CompanySource.slug)
            .where(CompanySource.last_validated_at.isnot(None))
            .where(CompanySource.last_validated_at >= cutoff)
        )).all()
    return {(r[0], r[1]) for r in rows}


async def revalidate_registry(*, batch: int = 300) -> dict:
    """Re-probe the least-recently-validated active/unverified slugs. Round-robin
    via last_validated_at ASC NULLS FIRST so the whole set is covered over time.
    Hysteresis + a provider-wide-outage guard prevent mass false-deaths."""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(CompanySource)
            .where(CompanySource.status.in_(("active", "unverified")))
            .order_by(CompanySource.last_validated_at.asc().nullsfirst())
            .limit(batch)
        )).scalars().all()
        targets = [(r.ats, r.slug, r.config_json) for r in rows]

    if not targets:
        return {"revalidated": 0, "active": 0, "demoted": 0}

    by_ats_fail: dict[str, int] = {}
    by_ats_total: dict[str, int] = {}
    results = []
    async with httpx.AsyncClient(follow_redirects=True, headers={"User-Agent": ats_sources._UA}) as client:
        sem = asyncio.Semaphore(10)

        async def probe(ats, slug):
            async with sem:
                return (ats, slug, *await validate_candidate(client, ats, slug))

        gathered = await asyncio.gather(*(probe(a, s) for a, s, _ in targets), return_exceptions=True)
        for g in gathered:
            if isinstance(g, tuple):
                ats, slug, total, india, company = g
                by_ats_total[ats] = by_ats_total.get(ats, 0) + 1
                if total == 0:
                    by_ats_fail[ats] = by_ats_fail.get(ats, 0) + 1
                results.append(g)

    # Provider-wide outage guard: if every probe for an ATS failed this run, don't
    # demote any of its slugs (likely the provider, not the slug).
    outage = {ats for ats, n in by_ats_total.items() if n >= 3 and by_ats_fail.get(ats, 0) == n}
    if outage:
        logger.warning("revalidation: skipping demotion for suspected outage ATSes %s", outage)

    stats = {"revalidated": len(results), "active": 0, "demoted": 0}
    async with AsyncSessionLocal() as session:
        for ats, slug, total, india, company in results:
            if ats in outage and india == 0:
                continue
            status = await _upsert(session, ats, slug, total, india, company, "revalidation")
            if status == "active":
                stats["active"] += 1
            elif status == "dead":
                stats["demoted"] += 1
        await session.commit()
    logger.info("Revalidation done: %s", stats)
    return stats