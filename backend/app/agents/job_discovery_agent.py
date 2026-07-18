"""India job-discovery engine (AK24/7Jobs).

Owns the shared normalization helpers (imported by ats_sources / jobs_aggregators
/ scrape_sources) plus the India location/salary/notice parsing and the
anti-staffing filter. `discover_for_profile` is the entrypoint the scheduler
calls: it loads the profile, builds resume-driven queries, fans out every
enabled Tier-1/2/3 source, dedupes by canonical URL, drops non-India and
staffing rows, and returns normalized job dicts (WORKSTREAMS contract #3).
"""

import asyncio
import json
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from app.services.india_locations import (
    is_india_or_remote_location,
    is_remote_india,
    location_matches_preference,
    normalize_india_location,
)

logger = logging.getLogger(__name__)

_SLUGS_PATH = Path(__file__).parent.parent / "data" / "india_company_slugs.json"


# ── India location ────────────────────────────────────────────────────────────

_INDIA_CITIES = {
    "bengaluru", "bangalore", "mumbai", "bombay", "delhi", "new delhi", "ncr",
    "gurgaon", "gurugram", "noida", "hyderabad", "secunderabad", "chennai",
    "madras", "pune", "kolkata", "calcutta", "ahmedabad", "jaipur", "kochi",
    "cochin", "thiruvananthapuram", "trivandrum", "coimbatore", "indore",
    "chandigarh", "nagpur", "lucknow", "bhubaneswar", "vadodara", "surat",
    "mohali", "mysuru", "mysore", "visakhapatnam", "vizag", "mangaluru",
    "mangalore", "vijayawada", "nashik", "faridabad", "ghaziabad",
}
_INDIA_STATES = {
    "karnataka", "maharashtra", "tamil nadu", "telangana", "kerala", "gujarat",
    "rajasthan", "west bengal", "uttar pradesh", "haryana", "punjab", "odisha",
    "andhra pradesh", "madhya pradesh", "bihar", "goa", "assam", "uttarakhand",
}
_INDIA_KEYWORDS = {"india", "bharat", "pan india", "pan-india", "in remote", "remote india"}
_INDIA_TOKENS = _INDIA_CITIES | _INDIA_STATES | _INDIA_KEYWORDS

# Remote markers that imply "open to India" rather than a foreign-only role.
_GLOBAL_REMOTE = {"worldwide", "anywhere", "global", "remote", "fully remote", "work from anywhere"}

# Explicit non-India locations — drop these (unless an India token is also present).
_FOREIGN_TOKENS = {
    "united states", "usa", "u.s.", "u.s.a", "us only", "u.s. only", " us ", " us,",
    " eu ", "eu only", "canada", "united kingdom", "u.k.",
    " uk ", "europe", "emea", "singapore", "australia", "germany", "france",
    "netherlands", "ireland", "poland", "spain", "portugal", "brazil", "mexico",
    "argentina", "philippines", "vietnam", "indonesia", "malaysia", "thailand",
    "japan", "china", "korea", "dubai", "uae", "abu dhabi", "saudi", "qatar",
    "nigeria", "kenya", "south africa", "new zealand", "latam", "north america",
}

_CITY_CANON = {
    "bangalore": "Bengaluru", "bombay": "Mumbai", "madras": "Chennai",
    "calcutta": "Kolkata", "gurgaon": "Gurugram", "cochin": "Kochi",
    "trivandrum": "Thiruvananthapuram", "mysore": "Mysuru", "vizag": "Visakhapatnam",
    "mangalore": "Mangaluru", "new delhi": "Delhi",
}


def _is_india_location(location: str | None) -> bool:
    """True if a job is India-based or a remote role open to India.

    Empty/unknown → True (Tier-1 ATS sources are Indian employers that often omit
    location; query-driven sources already target India). Explicit foreign-only
    locations are rejected; global-remote markers are accepted as India-eligible.
    """
    if not location or not location.strip():
        return True
    low = f" {location.strip().lower()} "
    if any(tok in low for tok in _INDIA_TOKENS):
        return True
    if any(tok in low for tok in _FOREIGN_TOKENS):
        return False
    if any(tok in low for tok in _GLOBAL_REMOTE):
        return True
    return True


def _is_india_strict(location: str | None) -> bool:
    """Strict India gate for the feed: keep only an explicit India location OR a
    remote/worldwide role (remote is fine even for another country). Foreign-
    onsite AND empty/unknown locations are DROPPED — high preference to India.
    Use this for the user-facing feed/pool; _is_india_location stays lenient for
    slug discovery where empty often means an India employer omitted the field."""
    return is_india_or_remote_location(location, allow_named_city=True)


def _normalize_india_location(location: str | None) -> str | None:
    return normalize_india_location(location)


# ── Salary (LPA) parsing ──────────────────────────────────────────────────────

_LPA_RANGE_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*([\d.]+)\s*(?:-|–|to)\s*([\d.]+)\s*(lpa|lakhs?|l\b|cr|crores?)",
    re.IGNORECASE,
)
_LPA_SINGLE_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*([\d.]+)\s*(lpa|lakhs?|l\b|cr|crores?)",
    re.IGNORECASE,
)
_INR_ABS_RE = re.compile(r"(?:₹|rs\.?|inr)\s*([\d,]{6,})", re.IGNORECASE)

# Only trust a salary parsed out of free-text description when an explicit
# compensation cue is present — otherwise loan/recovery/revenue figures in a JD
# (e.g. "recover ₹60 Cr") get misread as the candidate's pay.
_SALARY_CONTEXT_RE = re.compile(
    r"\b(ctc|salary|compensation|remuneration|package|per\s+annum|p\.?a\.?|"
    r"in[\s-]hand|take[\s-]home|lpa)\b",
    re.IGNORECASE,
)
_LPA_MIN, _LPA_MAX = 1.0, 200.0  # sane band (₹1L – ₹2Cr p.a.)


def _unit_to_lpa(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit.startswith("cr"):
        return value * 100.0
    return value  # lpa / lakh / l


def _parse_lpa(text: str | None) -> float | None:
    """Best-effort parse of an Indian salary string to lakhs-per-annum (float)."""
    if not text:
        return None
    try:
        m = _LPA_RANGE_RE.search(text)
        if m:
            hi = max(float(m.group(1)), float(m.group(2)))
            return round(_unit_to_lpa(hi, m.group(3)), 2)
        m = _LPA_SINGLE_RE.search(text)
        if m:
            return round(_unit_to_lpa(float(m.group(1)), m.group(2)), 2)
        m = _INR_ABS_RE.search(text)
        if m:
            amount = float(m.group(1).replace(",", ""))
            if amount >= 100000:
                return round(amount / 100000.0, 2)
    except (ValueError, TypeError):
        return None
    return None


# ── Notice period parsing ─────────────────────────────────────────────────────

_NOTICE_IMMEDIATE_RE = re.compile(
    r"\b(immediate(?:ly)?\s*joiner?s?|immediate\s*joining|0\s*days?\s*notice)\b", re.IGNORECASE
)
_NOTICE_RE = re.compile(
    r"notice\s*period[^\d]{0,15}(\d{1,3})\s*(day|month)|(\d{1,3})\s*(day|month)s?\s*notice",
    re.IGNORECASE,
)


def _parse_notice_period(text: str | None) -> str | None:
    """Extract a short notice-period label (≤20 chars) from text, or None."""
    if not text:
        return None
    if _NOTICE_IMMEDIATE_RE.search(text):
        return "immediate"
    m = _NOTICE_RE.search(text)
    if m:
        num = m.group(1) or m.group(3)
        unit = (m.group(2) or m.group(4) or "").lower()
        if num and unit:
            label = f"{num} {unit}{'s' if num != '1' else ''}"
            return label[:20]
    return None


# ── Job-type / staffing exclusion ─────────────────────────────────────────────

_EXCLUDED_TITLE_RE = re.compile(
    r"\b(intern(ship)?|co[\s-]?op|fellowship|apprentice|"
    r"part[\s-]?time|freelance|volunteer)\b",
    re.IGNORECASE,
)
_LOW_QUALITY_TITLE_RE = re.compile(
    r"\b(training|course|courses|bootcamp|classes|certification|certifications)\b|"
    r"real[\s-]?time projects?|placement guarantee|online training",
    re.IGNORECASE,
)

# Indian + global staffing / RPO / consultancy firms and generic markers.
_STAFFING_RE = re.compile(
    r"\b(staffing|recruit(ing|ment)?|manpower|rpo|talent\s+solutions|"
    r"hr\s+services|placement[s]?|consultanc(y|ies)|consultants?|"
    r"teamlease|quess|quesscorp|randstad|adecco|manpowergroup|abc\s+consultants|"
    r"ikya|kelly\s+services?|gi\s+group|ciel\s+hr|ma\s+foi|careernet|xpheno|"
    r"aptech|vsplash|magna\s+infotech|spectraforce|collabera|"
    r"jobs?\s+opportunit(y|ies)|robert\s+half|kforce|insight\s+global|apex\s+systems)\b",
    re.IGNORECASE,
)
# Description heuristics: third-party hiring on behalf of an undisclosed client.
_STAFFING_DESC_RE = re.compile(
    r"\b(hiring\s+for\s+(our|a)\s+client|on\s+behalf\s+of\s+(our|a)\s+client|"
    r"our\s+client\s+is|client\s+of\s+ours|for\s+our\s+(esteemed\s+)?client|"
    r"leading\s+mnc\s+client)\b",
    re.IGNORECASE,
)


def _is_excluded_job(title: str, company: str, job_url: str = "", description: str = "") -> bool:
    if _EXCLUDED_TITLE_RE.search(title or ""):
        return True
    if _LOW_QUALITY_TITLE_RE.search(title or ""):
        return True
    if _STAFFING_RE.search(company or ""):
        return True
    if description and _STAFFING_DESC_RE.search(description):
        return True
    return False


# ── Work arrangement ──────────────────────────────────────────────────────────

_HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
_REMOTE_RE = re.compile(r"\b(remote|work from home|wfh|distributed|anywhere)\b", re.IGNORECASE)
_ONSITE_RE = re.compile(r"\b(onsite|on[\s-]site|in[\s-]office|in[\s-]person|work from office|wfo)\b", re.IGNORECASE)


def _detect_work_arrangement(title: str, location: str, description: str) -> str:
    combined = f"{title} {location} {description}"
    if _HYBRID_RE.search(combined):
        return "hybrid"
    if _REMOTE_RE.search(combined):
        return "remote"
    if _ONSITE_RE.search(combined):
        return "onsite"
    return "unknown"


def _matches_work_arrangement(job_arrangement: str, wanted: set[str]) -> bool:
    if not wanted:
        return True
    if job_arrangement == "unknown":
        return True
    return job_arrangement in wanted


# ── Date helpers ──────────────────────────────────────────────────────────────

def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _is_within_days(dt: datetime | None, max_days: int | None) -> bool:
    if max_days is None or dt is None:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=max_days)


# ── Normalized job dict (contract #3) ─────────────────────────────────────────

def _normalize(
    *,
    job_url: str,
    source: str,
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    job_description: str | None = None,
    work_arrangement: str | None = None,
    posted_at: datetime | None = None,
    salary_lpa: float | None = None,
    salary_raw: str | None = None,
    notice_period: str | None = None,
) -> dict:
    return {
        "job_url": job_url,
        "title": title,
        "company": company,
        "location": location,
        "job_description": job_description,
        "source": source,
        "work_arrangement": work_arrangement or "unknown",
        "posted_at": posted_at,
        "salary_lpa": salary_lpa,
        "salary_raw": salary_raw,
        "notice_period": notice_period,
    }


def _canonical_url(url: str) -> str:
    """Scheme+host(lowercased)+path(no trailing slash); query/fragment dropped."""
    try:
        parts = urlsplit(url)
        host = (parts.netloc or "").lower()
        path = (parts.path or "").rstrip("/")
        scheme = (parts.scheme or "https").lower()
        return f"{scheme}://{host}{path}" if host else url.strip()
    except Exception:
        return (url or "").strip()


def _strip_html(html: str) -> str:
    return re.sub(r"<[^>]+>", " ", html or "").strip()


def _content_key(company: str | None, title: str | None) -> tuple[str, str] | None:
    """Dedup key for the same role posted to multiple sources: (company, title)
    both normalized. None when either is missing (can't safely dedup)."""
    c = re.sub(r"[^a-z0-9]", "", (company or "").lower())
    t = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]", " ", (title or "").lower())).strip()
    return (c, t) if c and t else None


# ── Role matching (synonym-aware) ─────────────────────────────────────────────

_ROLE_EXPANSIONS: list[tuple[re.Pattern, list[str]]] = []
_RAW_SYNONYMS = [
    (r"\bML\b", ["Machine Learning"]),
    (r"\bAI\b", ["Artificial Intelligence"]),
    (r"\bAI/ML\b", ["AI ML", "Artificial Intelligence", "Machine Learning", "Machine Learning Engineer", "AI Engineer"]),
    (r"\bSWE\b", ["Software Engineer", "Software Developer", "Software Development Engineer"]),
    (r"\bSDE\b", ["Software Development Engineer", "Software Engineer"]),
    (r"\bSDET\b", ["Software Development Engineer in Test", "Software Engineer in Test"]),
    (r"\bMLE\b", ["Machine Learning Engineer"]),
    (r"\bSRE\b", ["Site Reliability Engineer", "Platform Engineer"]),
    (r"\bDE\b", ["Data Engineer"]),
    (r"\bDS\b", ["Data Scientist"]),
    (r"\bPM\b", ["Product Manager"]),
    (r"\bFE\b", ["Frontend Engineer", "Front-End Engineer"]),
    (r"\bBE\b", ["Backend Engineer", "Back-End Engineer"]),
    (r"\bFront[\s-]?End\b", ["Frontend", "Front End", "Frontend Engineer", "Frontend Developer"]),
    (r"\bBack[\s-]?End\b", ["Backend", "Back End", "Backend Engineer", "Backend Developer"]),
    (r"\bFull[\s-]?Stack\b", ["Fullstack", "Full Stack", "Fullstack Engineer", "Full Stack Engineer", "Fullstack Developer", "Full Stack Developer"]),
    (r"\bMachine Learning\b", ["ML"]),
    (r"\bArtificial Intelligence\b", ["AI"]),
    (r"\bSoftware Engineer\b", ["SWE", "Software Development Engineer"]),
    (r"\bSoftware Developer\b", ["SWE", "Software Development Engineer"]),
    (r"\bSoftware Development Engineer\b", ["SDE", "Software Engineer"]),
    (r"\bWeb Developer\b", ["Web Engineer", "Frontend Developer", "Frontend Engineer", "Software Developer"]),
    (r"\bSite Reliability\b", ["SRE"]),
    (r"\bData Engineer\b", ["DE"]),
    (r"\bData Scientist\b", ["DS"]),
]
for _pat, _expansions in _RAW_SYNONYMS:
    _ROLE_EXPANSIONS.append((re.compile(_pat, re.IGNORECASE), _expansions))

_AI_TERMS_RE = re.compile(
    r"\b(ai|a\.i\.|ml|m\.l\.|machine learning|artificial intelligence|llm|genai|generative ai|agentic)\b",
    re.IGNORECASE,
)
_TECH_ROLE_RE = re.compile(
    r"\b(engineer|engineering|developer|scientist|research|architect|platform|infrastructure|backend|frontend|software|data)\b",
    re.IGNORECASE,
)
_BUSINESS_ROLE_RE = re.compile(
    r"\b(account executive|sales|presales|marketing|campaign|growth|partnerships?|customer success|recruiter|talent|finance|accounting|legal|hr|human resources)\b",
    re.IGNORECASE,
)
_LEADERSHIP_ROLE_RE = re.compile(
    r"\b(manager|head|director|vp|vice president|chief)\b", re.IGNORECASE
)


def _expand_term(term: str) -> list[str]:
    variants = [term]
    for pattern, expansions in _ROLE_EXPANSIONS:
        if pattern.search(term):
            variants.extend(expansions)
    return variants


def _matches_criteria(title: str, profile: dict) -> bool:
    """Title must match at least one target role (with synonym expansion).

    Skill keywords are intentionally NOT checked against titles — they appear in
    descriptions, not titles, and would silently drop almost every valid match.
    """
    roles = [r.strip() for r in (profile.get("target_roles") or "").split(",") if r.strip()]
    if not roles:
        return True
    if len(roles) > 1:
        return any(_matches_criteria(title, {**profile, "target_roles": role}) for role in roles)

    roles_text = " ".join(roles).lower()
    ai_focused_search = bool(_AI_TERMS_RE.search(roles_text))
    title_has_ai = bool(_AI_TERMS_RE.search(title))
    title_has_tech = bool(_TECH_ROLE_RE.search(title))
    title_has_business = bool(_BUSINESS_ROLE_RE.search(title))
    title_has_leadership = bool(_LEADERSHIP_ROLE_RE.search(title))
    leadership_requested = bool(_LEADERSHIP_ROLE_RE.search(roles_text))

    if ai_focused_search and title_has_ai and title_has_business and not title_has_tech:
        return False
    if ai_focused_search and title_has_ai and title_has_leadership and not leadership_requested:
        return False

    low_title = title.lower()
    if ai_focused_search:
        return title_has_ai and title_has_tech
    if re.search(r"\bjava\b", roles_text):
        return bool(re.search(r"\bjava\b", low_title)) and title_has_tech
    if "front" in roles_text:
        frontend_terms = ("frontend", "front-end", "front end", "react", "angular", "vue", "javascript", "typescript")
        return any(term in low_title for term in frontend_terms) and title_has_tech
    if "fullstack" in roles_text or "full stack" in roles_text or "full-stack" in roles_text:
        return any(term in low_title for term in ("fullstack", "full stack", "full-stack")) and title_has_tech
    if "web developer" in roles_text:
        web_terms = ("web developer", "web engineer", "frontend", "front-end", "front end", "react", "javascript", "typescript")
        return any(term in low_title for term in web_terms) and title_has_tech
    if "software developer" in roles_text or "software engineer" in roles_text:
        software_terms = (
            "software developer", "software engineer", "software development engineer",
            "sde", "swe", "application developer", "applications developer",
        )
        return any(term in low_title for term in software_terms)

    all_variants: list[str] = []
    for role in roles:
        all_variants.extend(_expand_term(role))

    return any(
        re.search(r"\b" + re.escape(variant) + r"\b", title, re.IGNORECASE)
        for variant in all_variants
    )


def _load_india_slugs() -> dict:
    with open(_SLUGS_PATH, encoding="utf-8") as f:
        return json.load(f)


_ATS_KEYS = (
    "greenhouse", "lever", "ashby", "smartrecruiters", "workable",
    "recruitee", "breezy", "personio", "workday", "zoho",
)


async def load_india_slugs_from_db(session) -> dict | None:
    """Build the fetch_all_ats slug dict from `active` company_source rows.

    Returns None (so callers fall back to the seed JSON) when the table is
    empty/missing or the query errors — supply must never drop to zero.
    workday/zoho rows contribute their config_json dict; the rest their slug.
    """
    from sqlalchemy import select
    from app.models.company_source import CompanySource

    try:
        rows = (await session.execute(
            select(CompanySource.ats, CompanySource.slug, CompanySource.config_json)
            .where(CompanySource.status == "active")
        )).all()
    except Exception as exc:  # noqa: BLE001 — table not migrated yet, etc.
        logger.warning("load_india_slugs_from_db failed, using file seed: %s", repr(exc)[:160])
        return None

    if not rows:
        return None

    out: dict = {k: [] for k in _ATS_KEYS}
    for ats, slug, config in rows:
        out.setdefault(ats, [])
        if ats in ("workday", "zoho"):
            if config:
                out[ats].append(config)
        else:
            out[ats].append(slug)
    total = sum(len(v) for v in out.values())
    logger.info("Loaded %d active India slugs from registry", total)
    return out


async def get_india_slugs(session=None) -> dict:
    """Active slugs from the DB registry, falling back to the seed JSON file."""
    if session is not None:
        db = await load_india_slugs_from_db(session)
        return db if db else _load_india_slugs()
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as s:
        db = await load_india_slugs_from_db(s)
    return db if db else _load_india_slugs()


# ── Quick India ATS search (used by /api/public/job-search) ───────────────────

_QUICK_CONCURRENCY = 20


async def quick_ats_search(role: str, posted_within_days: int | None = 14) -> list[dict]:
    """Parallel Greenhouse + Lever + Ashby scrape across the India slug list.

    Sub-10s direct-employer ATS results for the public search endpoint. Role +
    freshness filters are applied; India/staffing filtering is left to the caller.
    """
    from app.agents import ats_sources

    slugs = await get_india_slugs()
    profile = {"target_roles": role}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        results = await asyncio.gather(
            ats_sources.greenhouse(client, slugs.get("greenhouse", []), profile, posted_within_days),
            ats_sources.lever(client, slugs.get("lever", []), profile, posted_within_days),
            ats_sources.ashby(client, slugs.get("ashby", []), profile, posted_within_days),
            return_exceptions=True,
        )
    jobs: list[dict] = []
    for r in results:
        if isinstance(r, list):
            jobs.extend(r)
    logger.info("quick_ats_search(%r): %d jobs", role, len(jobs))
    return jobs


# ── Agent ─────────────────────────────────────────────────────────────────────

class JobDiscoveryAgent:
    """Fans out India job sources across three tiers and returns normalized,
    deduped, India-only, staffing-filtered job dicts."""

    async def discover(
        self,
        profile: dict,
        queries: list[str] | None = None,
        *,
        include_tier3: bool = True,
    ) -> list[dict]:
        from app.agents.ats_sources import fetch_all_ats
        from app.agents.scrape_sources import fetch_all_scraped
        from app.agents.india_board_sources import fetch_all_india_boards
        from app.agents.wellfound_source import fetch_all_wellfound
        from app.agents.hirect_source import fetch_all_hirect
        from app.agents.hirist_source import fetch_all_hirist_tech
        from app.services.jobs_aggregators import fetch_all_aggregators
        from app.services.serpapi_jobs import search_serpapi_jobs

        slugs = await get_india_slugs()
        locations = [l.strip() for l in (profile.get("locations") or "").split(",") if l.strip()]
        posted_within = profile.get("posted_within_days")
        wanted_arrangements = {
            w.strip().lower() for w in (profile.get("work_arrangements") or "").split(",") if w.strip()
        }
        excluded = {
            c.strip().lower() for c in (profile.get("excluded_companies") or "").split(",") if c.strip()
        }

        if not queries:
            queries = [
                r.strip() for r in (profile.get("target_roles") or "").split(",") if r.strip()
            ] or ["Software Engineer"]

        serpapi_profile = {**profile, "search_query": ", ".join(queries[:2])}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            tasks = [
                fetch_all_ats(client, slugs, profile, posted_within),
                fetch_all_aggregators(client, queries, locations),
                search_serpapi_jobs(client, serpapi_profile, posted_within, max_pages=2),
            ]
            if include_tier3:
                tasks.extend([
                    fetch_all_scraped(queries, locations),
                    fetch_all_india_boards(client, queries, locations),
                    fetch_all_wellfound(queries, locations),
                    fetch_all_hirect(client, queries, locations),
                    fetch_all_hirist_tech(client, queries, locations),
                ])
            tiered = await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        raw: list[dict] = []
        for result in tiered:
            if isinstance(result, list):
                raw.extend(result)
            elif isinstance(result, Exception):
                logger.warning("Discovery tier failed: %s", result)

        return self._postprocess(
            raw, excluded, wanted_arrangements, posted_within
        )

    def _postprocess(
        self,
        raw: list[dict],
        excluded: set[str],
        wanted_arrangements: set[str],
        posted_within: int | None,
    ) -> list[dict]:
        # ── Dedupe by canonical URL ────────────────────────────────────────
        seen: set[str] = set()
        deduped: list[dict] = []
        for j in raw:
            url = j.get("job_url") or ""
            if not url:
                continue
            key = _canonical_url(url)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(j)
        before = len(deduped)

        out: list[dict] = []
        for j in deduped:
            location = j.get("location")
            if not _is_india_strict(location):
                continue
            title = j.get("title") or ""
            company = j.get("company") or ""
            description = j.get("job_description") or ""
            if _is_excluded_job(title, company, j.get("job_url", ""), description):
                continue
            if excluded and company.lower() in excluded:
                continue
            if not _matches_work_arrangement(j.get("work_arrangement", "unknown"), wanted_arrangements):
                continue
            if not _is_within_days(j.get("posted_at"), posted_within):
                continue

            j["location"] = _normalize_india_location(location)
            if j.get("salary_lpa") is None:
                lpa = _parse_lpa(j.get("salary_raw"))
                if lpa is None and description and _SALARY_CONTEXT_RE.search(description):
                    lpa = _parse_lpa(description)
                if lpa is not None and not (_LPA_MIN <= lpa <= _LPA_MAX):
                    lpa = None
                j["salary_lpa"] = lpa
            if j.get("notice_period") is None:
                j["notice_period"] = _parse_notice_period(description)
            out.append(j)

        # ── Content-level dedupe: same company+title from different sources ──
        content_seen: set[tuple[str, str]] = set()
        final: list[dict] = []
        for j in out:
            ck = _content_key(j.get("company"), j.get("title"))
            if ck and ck in content_seen:
                continue
            if ck:
                content_seen.add(ck)
            final.append(j)

        logger.info(
            "Discovery postprocess: %d raw → %d url-deduped → %d clean → %d content-deduped",
            len(raw), before, len(out), len(final),
        )
        return final


# ── Entrypoint (contract #4) ──────────────────────────────────────────────────

async def discover_for_profile(profile_id: int, user_id: int) -> list[dict]:
    """Scheduler entrypoint: load profile + resume, build queries, run discovery."""
    from sqlalchemy import select

    from app.core.database import AsyncSessionLocal
    from app.models.job_search_profile import JobSearchProfile
    from app.models.user import User
    from app.services.query_builder import build_search_queries

    async with AsyncSessionLocal() as session:
        prof = await session.get(JobSearchProfile, profile_id)
        if not prof or prof.user_id != user_id:
            logger.warning("discover_for_profile: profile %s not found for user %s", profile_id, user_id)
            return []

        user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

        skills = ""
        if user and isinstance(user.skills, list):
            skills = ", ".join(str(s) for s in user.skills)
        profile = {
            "target_roles": prof.target_roles,
            "locations": prof.locations or (user.preferred_locations if user else "") or "India",
            "keywords": prof.keywords,
            "skills": skills,
            "excluded_companies": prof.excluded_companies,
            "experience_level": prof.experience_level,
            "work_arrangements": prof.work_arrangements,
            "posted_within_days": prof.posted_within_days,
            "min_salary_lpa": prof.min_salary_lpa,
            "max_notice_period_days": prof.max_notice_period_days,
        }
        resume_text = ((user.resume_text or user.career_history) if user else "") or ""

        queries: list[str] | None = None
        if prof.generated_queries:
            try:
                cached = json.loads(prof.generated_queries)
                if isinstance(cached, list) and cached:
                    queries = [str(q) for q in cached]
            except (json.JSONDecodeError, TypeError):
                queries = None

        if not queries:
            queries = await build_search_queries(profile, resume_text)
            prof.generated_queries = json.dumps(queries)

        prof.last_run_at = datetime.now(timezone.utc)
        await session.commit()

    agent = JobDiscoveryAgent()
    jobs = await agent.discover(profile, queries)
    logger.info("discover_for_profile(%s, %s): %d jobs", profile_id, user_id, len(jobs))
    await log_discovery_run(
        "profile_discovery", user_id=user_id, profile_id=profile_id,
        queries=queries, locations=profile.get("locations"), jobs_found=len(jobs),
    )
    return jobs


# ── Generalized pool warming (role-agnostic) ──────────────────────────────────

def _trunc(value: str | None, n: int) -> str | None:
    return value[:n] if isinstance(value, str) else value


async def warm_job_pool(posted_within_days: int | None = 7) -> dict:
    """Fetch EVERY role from every active ATS slug into the shared JobPool.

    Generalized discovery: passing profile=None to fetch_all_ats skips the
    per-role title filter, so the pool fills with the full breadth of India
    roles (not just one user's target role). Per-user feeds then match/score
    from this pool. Runs on a schedule so freshness stays high. Returns stats.
    """
    from sqlalchemy import func
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.agents.ats_sources import fetch_all_ats
    from app.core.database import AsyncSessionLocal
    from app.models.job_pool import JobPool

    slugs = await get_india_slugs()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        raw = await fetch_all_ats(client, slugs, None, posted_within_days)

    agent = JobDiscoveryAgent()
    jobs = agent._postprocess(raw, excluded=set(), wanted_arrangements=set(), posted_within=posted_within_days)

    now = datetime.now(timezone.utc)
    # Dedup by exact job_url (keep last) + truncate to column limits → row dicts.
    by_url: dict[str, dict] = {}
    for j in jobs:
        url = j.get("job_url")
        if not url or len(url) > 2048:
            continue
        by_url[url] = {
            "job_url": url,
            "title": _trunc(j.get("title"), 255),
            "company": _trunc(j.get("company"), 255),
            "location": _trunc(j.get("location"), 255),
            "job_description": j.get("job_description"),
            "source": _trunc(j.get("source") or "pool", 50),
            "work_arrangement": _trunc(j.get("work_arrangement"), 20),
            "posted_at": j.get("posted_at"),
            "salary_lpa": j.get("salary_lpa"),
            "salary_raw": _trunc(j.get("salary_raw"), 120),
            "notice_period": _trunc(j.get("notice_period"), 20),
            "search_query": "__pool_warm__",
            "first_seen_at": now,
            "last_seen_at": now,
        }
    rows = list(by_url.values())

    # Atomic, dup-safe upsert in chunks; a bad chunk is skipped, never fatal.
    saved = 0
    async with AsyncSessionLocal() as db:
        for i in range(0, len(rows), 500):
            chunk = rows[i:i + 500]
            stmt = pg_insert(JobPool).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["job_url"],
                set_={
                    "title": func.coalesce(stmt.excluded.title, JobPool.title),
                    "company": func.coalesce(stmt.excluded.company, JobPool.company),
                    "location": func.coalesce(stmt.excluded.location, JobPool.location),
                    "job_description": func.coalesce(stmt.excluded.job_description, JobPool.job_description),
                    "source": stmt.excluded.source,
                    "work_arrangement": func.coalesce(stmt.excluded.work_arrangement, JobPool.work_arrangement),
                    "posted_at": func.coalesce(stmt.excluded.posted_at, JobPool.posted_at),
                    "salary_lpa": func.coalesce(stmt.excluded.salary_lpa, JobPool.salary_lpa),
                    "salary_raw": func.coalesce(stmt.excluded.salary_raw, JobPool.salary_raw),
                    "notice_period": func.coalesce(stmt.excluded.notice_period, JobPool.notice_period),
                    "last_seen_at": stmt.excluded.last_seen_at,
                },
            )
            try:
                await db.execute(stmt)
                await db.commit()
                saved += len(chunk)
            except Exception as exc:  # noqa: BLE001 — one bad chunk never aborts the run
                await db.rollback()
                logger.warning("pool chunk %d skipped: %s", i // 500, repr(exc)[:160])

    stats = {"fetched": len(raw), "kept": len(jobs), "pooled": saved}
    logger.info("warm_job_pool: %s", stats)
    await log_discovery_run("pool_warm", jobs_found=saved, stats=stats)
    return stats


async def seed_user_feed_from_pool(
    user_id: int, profile: dict, *, search_profile_id: int | None = None, limit: int = 150,
    strict_locations: bool = False,
) -> int:
    """Fast feed seed: pull matching jobs from the shared JobPool into the user's
    DiscoveredJob feed so results appear instantly — no live 895-slug crawl. Role
    titles are synonym-expanded; missing-location pool rows are included."""
    from sqlalchemy import select, or_, func
    from app.core.database import AsyncSessionLocal
    from app.models.job_pool import JobPool
    from app.models.discovered_job import DiscoveredJob

    roles = [r.strip() for r in (profile.get("target_roles") or "").split(",") if r.strip()]
    locations = [l.strip() for l in (profile.get("locations") or "").split(",") if l.strip()]

    async with AsyncSessionLocal() as db:
        q = select(JobPool)
        if roles:
            terms: list[str] = []
            for r in roles:
                terms.extend(_expand_term(r))
            q = q.where(or_(*[func.lower(JobPool.title).contains(t.lower()) for t in terms]))
        if locations:
            loc_conds = [func.lower(JobPool.location).contains(l.lower()) for l in locations]
            loc_conds.extend([
                func.lower(JobPool.location).contains("remote india"),
                func.lower(JobPool.location).contains("pan india"),
                func.lower(JobPool.location).contains("pan-india"),
                func.lower(JobPool.location).contains("anywhere in india"),
            ])
            if not strict_locations:
                loc_conds.append(JobPool.location.is_(None))
            q = q.where(or_(*loc_conds))
        pool_jobs = (await db.execute(
            q.order_by(JobPool.last_seen_at.desc()).limit(limit)
        )).scalars().all()
        if not pool_jobs:
            return 0

        urls = [p.job_url for p in pool_jobs]
        existing: set[str] = set()
        for i in range(0, len(urls), 500):
            rows = await db.execute(
                select(DiscoveredJob.job_url).where(
                    DiscoveredJob.user_id == user_id,
                    DiscoveredJob.job_url.in_(urls[i:i + 500]),
                )
            )
            existing.update(r[0] for r in rows.all())

        inserted = 0
        for p in pool_jobs:
            if p.job_url in existing:
                continue
            db.add(DiscoveredJob(
                user_id=user_id, search_profile_id=search_profile_id, job_url=p.job_url,
                title=p.title, company=p.company, location=p.location,
                job_description=p.job_description, source=p.source or "pool",
                work_arrangement=p.work_arrangement, posted_at=p.posted_at,
                salary_lpa=p.salary_lpa, salary_raw=p.salary_raw, notice_period=p.notice_period,
                status="discovered",
            ))
            inserted += 1
        await db.commit()
    logger.info("seed_user_feed_from_pool(%s): +%d from pool", user_id, inserted)
    return inserted


async def log_discovery_run(
    run_type: str, *, user_id: int | None = None, profile_id: int | None = None,
    queries: list[str] | None = None, locations: str | None = None,
    jobs_found: int = 0, stats: dict | None = None,
) -> None:
    """Append one row to the job-search history. Never raises (best-effort)."""
    from app.core.database import AsyncSessionLocal
    from app.models.discovery_run import DiscoveryRun
    try:
        async with AsyncSessionLocal() as session:
            session.add(DiscoveryRun(
                run_type=run_type, user_id=user_id, profile_id=profile_id,
                queries=json.dumps(queries) if queries else None,
                locations=locations[:255] if locations else None,
                jobs_found=jobs_found, stats=stats,
            ))
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("log_discovery_run(%s) failed: %s", run_type, repr(exc)[:160])
