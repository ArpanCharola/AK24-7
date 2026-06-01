"""LLM-backed search-query generation for India job discovery.

Turns a user's search profile + resume into 3-6 concise, India-targeted search
queries used to drive the query-based sources (TimesJobs, Jooble, JobSpy). Uses
the shared `_generate` helper (contract #1) — no second OpenAI client.
"""

import logging

from app.services.resume_tailor import _generate, _parse_json

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You generate job-board search queries for an India-only job platform. "
    "Given a candidate's target roles, seniority, skills and resume, output 3-6 "
    "short search queries (2-4 words each) that an Indian tech professional would "
    "type into Naukri/Indeed India. Favour role + key tech (e.g. 'Backend Engineer "
    "Python', 'Senior Data Scientist'). Do NOT include city names or salary. "
    'Output only JSON: {"queries": ["...", "..."]} — no explanation.'
)

_MAX_QUERIES = 6


def _fallback(profile: dict) -> list[str]:
    roles = [r.strip() for r in (profile.get("target_roles") or "").split(",") if r.strip()]
    return (roles or ["Software Engineer"])[:_MAX_QUERIES]


async def build_search_queries(profile: dict, resume_text: str) -> list[str]:
    roles = profile.get("target_roles") or ""
    seniority = profile.get("seniority") or profile.get("experience_level") or ""
    skills = profile.get("skills") or profile.get("keywords") or ""

    user = (
        f"Target roles: {roles}\n"
        f"Seniority: {seniority}\n"
        f"Skills/keywords: {skills}\n"
        f"Resume excerpt:\n{(resume_text or '')[:3000]}"
    )

    try:
        raw = await _generate(_SYSTEM, user, max_tokens=300)
        parsed = _parse_json(raw)
        queries = parsed.get("queries") if isinstance(parsed, dict) else None
        cleaned = [
            " ".join(str(q).split())
            for q in (queries or [])
            if isinstance(q, str) and q.strip()
        ]
        # de-dupe, preserve order
        seen: set[str] = set()
        unique = [q for q in cleaned if not (q.lower() in seen or seen.add(q.lower()))]
        if unique:
            return unique[:_MAX_QUERIES]
        logger.warning("Query builder returned no usable queries; using fallback")
    except Exception as exc:
        logger.warning("Query builder failed (%s); using fallback", exc)

    return _fallback(profile)
