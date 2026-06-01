"""Find recruiter / HR contact details for a discovered job — free sources only.

Layered enrichment, cheapest first (no paid APIs, no Apify):

  Tier 1  Regex over the job description
          → emails, LinkedIn profile URLs (free, always run)

  Tier 2  LLM scan of the description for a named recruiter / hiring manager
          → recruiter name (~$0.0005/job via gpt-4o-mini, always run)

  Tier 3  Public-page fetch of the company's careers / about / team / contact
          pages → real published emails + LinkedIn profiles (free httpx, best
          effort, opt-in via ``deep=True`` since it makes live HTTP requests)

  Tier 4  Generic-pattern guess from the company domain
          → careers@<domain> (free, last resort, marked unverified)

Each tier populates the DiscoveredJob.contact_* columns and tags
``contact_source`` so callers know provenance. ``draft_outreach`` turns a found
contact into a short, grounded outreach email via the shared ``_generate``.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urlsplit

import httpx

logger = logging.getLogger(__name__)

# ── Regexes ──────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
)

_LINKEDIN_RE = re.compile(
    r"https?://(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-._~%/]+",
    re.IGNORECASE,
)

# Emails we never want — bug reports / abuse / press / unsubscribe / loops.
_EMAIL_BLOCKLIST_LOCAL = {
    "no-reply", "noreply", "donotreply", "do-not-reply",
    "unsubscribe", "abuse", "postmaster", "mailer-daemon",
    "press", "media", "support", "help", "info",
    "privacy", "security", "legal", "dpo",
}

# Generic addresses worth trying when nothing specific is found.
_GENERIC_LOCAL_PARTS = ("careers", "jobs", "recruiting", "talent", "hr", "people")

# Domains that are NOT corporate (job boards, ATS).
_NON_CORPORATE_DOMAINS = {
    "greenhouse.io", "lever.co", "ashbyhq.com", "myworkdayjobs.com",
    "icims.com", "smartrecruiters.com", "bamboohr.com", "jobvite.com",
    "workable.com", "recruitee.com", "breezy.hr", "comeet.com",
    "amazon.jobs", "metacareers.com", "jobs.apple.com",
    "careers.google.com", "careers.microsoft.com",
    "jobs.netflix.com", "explore.jobs.netflix.net",
    "linkedin.com", "indeed.com", "glassdoor.com", "monster.com",
    "ziprecruiter.com",
    # India boards / aggregators
    "naukri.com", "foundit.in", "monsterindia.com", "timesjobs.com",
    "shine.com", "instahyre.com", "hirist.com", "cutshort.io",
    "internshala.com", "apna.co", "iimjobs.com",
}


# ── Tier 1: regex extraction from JD ─────────────────────────────────────────

def extract_from_jd(job_description: str | None) -> dict:
    """Pull any emails and LinkedIn URLs out of a job description string.

    Returns a dict with `email`, `linkedin`, `name` keys (any may be None).
    Filters out obvious non-recruiter emails (no-reply, abuse, etc.)."""
    if not job_description:
        return {}

    out: dict = {}

    # Emails — first one that isn't obviously a non-recruiter address.
    for raw in _EMAIL_RE.findall(job_description):
        addr = raw.lower().strip(".,;:()[]<>")
        if "@" not in addr:
            continue
        local = addr.split("@", 1)[0]
        if local in _EMAIL_BLOCKLIST_LOCAL:
            continue
        out["email"] = addr
        break

    m = _LINKEDIN_RE.search(job_description)
    if m:
        out["linkedin"] = m.group(0).rstrip(".,;:()[]<>")

    return out


# ── Tier 2: LLM scan for named recruiter ─────────────────────────────────────

async def extract_recruiter_via_llm(
    job_description: str | None,
    company: str | None,
) -> dict:
    """Ask gpt-4o-mini whether a recruiter or hiring manager is named in the
    description (and return contact-shaped fields). Returns {} on failure or
    if the model finds nothing concrete."""
    if not job_description or len(job_description) < 60:
        return {}

    # Keep the prompt small — ~$0.0005/call on gpt-4o-mini.
    snippet = job_description[:4000]
    from app.services.resume_tailor import _generate, _parse_json

    system = (
        "You scan job descriptions for recruiter or hiring-manager contact info. "
        "Return JSON only: {\"name\": str|null, \"email\": str|null, \"linkedin\": str|null}. "
        "Only include values that appear LITERALLY in the text. "
        "Do not invent. If nothing is present, return all nulls."
    )
    user = f"Company: {company or 'unknown'}\n\nJob description:\n{snippet}"
    try:
        raw = await _generate(system, user, max_tokens=160, model="gpt-4o-mini")
    except Exception as exc:
        logger.debug("LLM recruiter extraction failed: %s", exc)
        return {}

    try:
        parsed = _parse_json(raw) or {}
    except Exception:
        return {}

    out: dict = {}
    name = (parsed.get("name") or "").strip()
    email = (parsed.get("email") or "").strip().lower()
    linkedin = (parsed.get("linkedin") or "").strip()

    if name and len(name) <= 80:
        out["name"] = name
    if email and "@" in email and email.split("@", 1)[0] not in _EMAIL_BLOCKLIST_LOCAL:
        out["email"] = email
    if linkedin and "linkedin.com/in/" in linkedin.lower():
        out["linkedin"] = linkedin
    return out


# ── Tier 3: public careers / about / team / contact pages (free scrape) ───────

_PUBLIC_PAGE_PATHS = ("", "careers", "about", "about-us", "team", "contact", "jobs")
_PUBLIC_FETCH_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AK247JobsBot/1.0; +https://ak247jobs.example)"
}


def _pick_email(text: str, domain: str) -> tuple[str | None, str | None]:
    """Return (on_domain_email, any_email) from a blob of HTML/text. Prefers an
    address on the company's own domain; falls back to any non-blocklisted one."""
    on_domain: str | None = None
    fallback: str | None = None
    for raw in _EMAIL_RE.findall(text or ""):
        addr = raw.lower().strip(".,;:()[]<>")
        if "@" not in addr:
            continue
        local, _, edom = addr.partition("@")
        if local in _EMAIL_BLOCKLIST_LOCAL:
            continue
        if edom == domain or edom.endswith("." + domain):
            return addr, addr  # on-domain wins immediately
        fallback = fallback or addr
    return on_domain, fallback


async def find_from_public_pages(company: str | None, job_url: str | None) -> dict:
    """Fetch a handful of the company's public pages and extract a likely
    contact email + LinkedIn profile. Best-effort and never raises — any network
    failure just yields {}. Bounded to a few small GETs."""
    domain = _company_domain_from_job_url(job_url, company)
    if not domain:
        return {}

    base = f"https://{domain}"
    out: dict = {}
    any_email: str | None = None
    try:
        async with httpx.AsyncClient(
            timeout=8.0, follow_redirects=True, headers=_PUBLIC_FETCH_HEADERS
        ) as client:
            for path in _PUBLIC_PAGE_PATHS:
                url = base if not path else f"{base}/{path}"
                try:
                    resp = await client.get(url)
                except Exception:
                    continue
                if not resp.is_success:
                    continue
                if "text/html" not in resp.headers.get("content-type", ""):
                    continue
                text = resp.text or ""

                on_domain, fallback = _pick_email(text, domain)
                if on_domain and "email" not in out:
                    out["email"] = on_domain
                if fallback and any_email is None:
                    any_email = fallback

                if "linkedin" not in out:
                    m = _LINKEDIN_RE.search(text)
                    if m:
                        out["linkedin"] = m.group(0).rstrip(".,;:()[]<>")

                if out.get("email") and out.get("linkedin"):
                    break
    except Exception as exc:
        logger.debug("Public-page contact fetch failed for %s: %s", domain, exc)
        return {}

    if "email" not in out and any_email:
        out["email"] = any_email
    return out


# ── Tier 4: generic guesses by company domain ────────────────────────────────

def _company_domain_from_job_url(job_url: str | None, company: str | None) -> Optional[str]:
    """Infer a corporate domain from the job URL, skipping ATS / board hosts."""
    if not job_url:
        return None
    try:
        host = urlsplit(job_url).netloc.lower()
    except Exception:
        return None
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    # Strip the leftmost subdomain repeatedly until we hit a domain that ISN'T
    # one of the known ATS/board hosts. For myworkdayjobs.com, we never reach a
    # corporate domain — caller falls back to None.
    parts = host.split(".")
    while len(parts) >= 2:
        candidate = ".".join(parts[-2:])
        if candidate in _NON_CORPORATE_DOMAINS:
            return None
        # Stop at the first non-www, non-ATS, eTLD+1 form.
        return candidate
    return None


def generic_email_guesses(job_url: str | None, company: str | None) -> dict:
    """Return one generic-tier email guess (the most likely one). We pick
    `careers@<domain>` as the default — highest open rate by convention."""
    domain = _company_domain_from_job_url(job_url, company)
    if not domain:
        return {}
    return {"email": f"careers@{domain}", "name": None, "linkedin": None}


# ── Draft outreach ────────────────────────────────────────────────────────────

async def draft_outreach(job: dict, contact: dict | None = None) -> dict:
    """Draft a short, grounded outreach/referral email for a discovered job.

    Returns ``{"subject": str, "body": str}``. Honest by construction — the model
    is told not to invent experience. Never raises; returns a simple fallback if
    the LLM is unavailable."""
    company = job.get("company") or "the company"
    role = job.get("title") or job.get("role") or "the open role"
    name = (contact or {}).get("name")
    jd = (job.get("job_description") or "")[:2000]

    from app.services.resume_tailor import _generate, _parse_json

    system = (
        "You write concise, warm, professional outreach emails from a job seeker to a "
        "recruiter or potential referrer at a company in India. Ground every claim only in the "
        "details provided — never invent the sender's experience, skills, or results. "
        "Keep it under 130 words: a specific reason for interest, one line on fit, and a soft ask "
        "(a referral or a quick chat). Return JSON only: {\"subject\": str, \"body\": str}. "
        "The body must end with a '[Your name]' placeholder signature."
    )
    user = (
        f"Recipient: {name or 'Hiring team'}\n"
        f"Company: {company}\n"
        f"Role: {role}\n\n"
        f"Job description (for context):\n{jd or '(not provided)'}"
    )
    try:
        raw = await _generate(system, user, max_tokens=400)
        parsed = _parse_json(raw) or {}
    except Exception as exc:
        logger.debug("Outreach draft failed: %s", exc)
        parsed = {}

    subject = (parsed.get("subject") or "").strip() or f"Interest in the {role} role at {company}"
    body = (parsed.get("body") or "").strip()
    if not body:
        greeting = f"Hi {name}," if name else "Hello,"
        body = (
            f"{greeting}\n\nI came across the {role} opening at {company} and I'm very interested. "
            "I'd love to learn more and explore whether my background could be a fit — would you be "
            "open to a quick chat or pointing me to the right person?\n\nThank you for your time.\n\n[Your name]"
        )
    return {"subject": subject, "body": body}


# ── Orchestrator ─────────────────────────────────────────────────────────────

async def find_contact(
    job: dict,
    *,
    deep: bool = False,
    use_apify: bool = False,
    with_draft: bool = False,
) -> dict:
    """Run the free enrichment cascade. Returns a dict shaped:
        {email, linkedin, name, source[, draft]}
    or {} if nothing found.

    ``deep`` (alias: the legacy ``use_apify`` flag the job-detail route still
    passes) enables the live public-page fetch tier — a few real HTTP GETs to the
    company's careers/about pages. The cheap regex + LLM + domain-pattern tiers
    always run. ``with_draft=True`` also attaches a ready-to-edit outreach email.
    """
    deep = deep or use_apify
    jd = job.get("job_description") or ""
    company = job.get("company")
    job_url = job.get("job_url")

    found: dict = {}

    # Tier 1 — emails / LinkedIn already in the JD text.
    t1 = extract_from_jd(jd)
    if t1.get("email") or t1.get("linkedin"):
        found = {**t1, "source": "jd_regex"}

    # Tier 2 — LLM finds a named person or a contact buried in prose.
    if not found:
        t2 = await extract_recruiter_via_llm(jd, company)
        if t2.get("email") or t2.get("linkedin") or t2.get("name"):
            found = {**t2, "source": "jd_llm"}

    # Tier 3 — fetch public company pages (opt-in; real HTTP).
    if not found and deep:
        t3 = await find_from_public_pages(company, job_url)
        if t3.get("email") or t3.get("linkedin"):
            found = {**t3, "source": "public_pages"}

    # Tier 4 — generic last-resort guess.
    if not found:
        t4 = generic_email_guesses(job_url, company)
        if t4.get("email"):
            found = {**t4, "source": "generic_unverified"}

    if found and with_draft:
        found["draft"] = await draft_outreach(job, found)

    return found
