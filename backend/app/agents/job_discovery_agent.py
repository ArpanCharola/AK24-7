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


def _normalize_india_location(location: str | None) -> str | None:
    if not location:
        return location
    cleaned = " ".join(location.split())
    low = cleaned.lower()
    for raw, canon in _CITY_CANON.items():
        if re.search(r"\b" + re.escape(raw) + r"\b", low):
            cleaned = re.sub(r"\b" + re.escape(raw) + r"\b", canon, cleaned, flags=re.IGNORECASE)
            low = cleaned.lower()
    return cleaned


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

# Indian + global staffing / RPO / consultancy firms and generic markers.
_STAFFING_RE = re.compile(
    r"\b(staffing|recruit(ing|ment)?|manpower|rpo|talent\s+solutions|"
    r"hr\s+services|placement[s]?|consultanc(y|ies)|consultants?|"
    r"teamlease|quess|quesscorp|randstad|adecco|manpowergroup|abc\s+consultants|"
    r"ikya|kelly\s+services?|gi\s+group|ciel\s+hr|ma\s+foi|careernet|xpheno|"
    r"aptech|vsplash|magna\s+infotech|spectraforce|collabera|"
    r"robert\s+half|kforce|insight\s+global|apex\s+systems)\b",
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


# ── Role matching (synonym-aware) ─────────────────────────────────────────────

_ROLE_EXPANSIONS: list[tuple[re.Pattern, list[str]]] = []
_RAW_SYNONYMS = [
    (r"\bML\b", ["Machine Learning"]),
    (r"\bAI\b", ["Artificial Intelligence"]),
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
    (r"\bFront[\s-]End\b", ["Frontend"]),
    (r"\bBack[\s-]End\b", ["Backend"]),
    (r"\bFull[\s-]Stack\b", ["Fullstack"]),
    (r"\bMachine Learning\b", ["ML"]),
    (r"\bArtificial Intelligence\b", ["AI"]),
    (r"\bSoftware Engineer\b", ["SWE", "Software Development Engineer"]),
    (r"\bSoftware Developer\b", ["SWE", "Software Development Engineer"]),
    (r"\bSoftware Development Engineer\b", ["SDE", "Software Engineer"]),
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


# ── Quick India ATS search (used by /api/public/job-search) ───────────────────

_QUICK_CONCURRENCY = 20


async def quick_ats_search(role: str, posted_within_days: int | None = 14) -> list[dict]:
    """Parallel Greenhouse + Lever + Ashby scrape across the India slug list.

    Sub-10s direct-employer ATS results for the public search endpoint. Role +
    freshness filters are applied; India/staffing filtering is left to the caller.
    """
    from app.agents import ats_sources

    slugs = _load_india_slugs()
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

    async def discover(self, profile: dict, queries: list[str] | None = None) -> list[dict]:
        from app.agents.ats_sources import fetch_all_ats
        from app.agents.scrape_sources import fetch_all_scraped
        from app.agents.india_board_sources import fetch_all_india_boards
        from app.agents.wellfound_source import fetch_all_wellfound
        from app.agents.hirect_source import fetch_all_hirect
        from app.services.jobs_aggregators import fetch_all_aggregators

        slugs = _load_india_slugs()
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

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            tiered = await asyncio.gather(
                fetch_all_ats(client, slugs, profile, posted_within),
                fetch_all_aggregators(client, queries, locations),
                fetch_all_scraped(queries, locations),
                fetch_all_india_boards(client, queries, locations),
                fetch_all_wellfound(queries, locations),
                fetch_all_hirect(client, queries, locations),
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
            if not _is_india_location(location):
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

        logger.info(
            "Discovery postprocess: %d raw → %d deduped → %d India/clean", len(raw), before, len(out)
        )
        return out


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
    return jobs
