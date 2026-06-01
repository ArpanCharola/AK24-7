"""Orion — the AK24/7Jobs AI career copilot.

A thin chat layer over the shared OpenAI helper (``resume_tailor._generate``).
Each turn is stateless: the caller passes the running message history, which we
fold into a single prompt (the frozen ``_generate`` signature is system + user
only). Context is the signed-in user's profile plus an OPTIONAL focused job, so
Orion can explain why a role fits, run interview prep, and give skill-gap advice
for the Indian market.

No facts are invented — the model is told to use only the provided context and
to ask for anything missing.
"""
from __future__ import annotations

import logging

from app.services.resume_tailor import _generate

logger = logging.getLogger(__name__)

# Keep the prompt bounded regardless of how long a conversation or resume grows.
_MAX_TURNS = 12
_MAX_MESSAGE_CHARS = 4000
_MAX_RESUME_CHARS = 6000
_MAX_JD_CHARS = 4000

_SYSTEM_PROMPT = (
    "You are Orion, the AI career copilot for AK24/7Jobs, a job-search platform for the "
    "Indian market. You help one job seeker at a time.\n\n"
    "Use ONLY the profile and job context provided below. Never invent experience, employers, "
    "salaries, titles, or facts about the user. If something needed isn't in the context, say so "
    "and ask the user for it.\n\n"
    "You can:\n"
    "1. Explain fit — why a specific job does or doesn't match the user's background, and what to "
    "highlight when applying.\n"
    "2. Interview prep — likely questions for the role, strong answers grounded in the user's real "
    "experience, and what to revise.\n"
    "3. Skill-gap advice — concrete, prioritised steps to close the distance to a target role.\n\n"
    "India context: salaries are in LPA (lakhs per annum) and CTC; respect notice-period "
    "constraints; tailor advice to Indian hiring (Naukri/LinkedIn, referrals, service vs product "
    "companies, fresher vs experienced tracks).\n\n"
    "Be concise, specific, and encouraging. Reply in plain text — short paragraphs or tight bullet "
    "lists. No JSON, no preamble."
)

_ROLES = {"user", "assistant"}


def _clip(text: str | None, limit: int) -> str:
    text = (text or "").strip()
    return text[:limit]


def _profile_block(user) -> str:
    lines: list[str] = ["## Candidate profile"]
    if getattr(user, "full_name", None):
        lines.append(f"Name: {user.full_name}")
    if getattr(user, "location", None):
        lines.append(f"Location: {user.location}")
    for label, attr in (("LinkedIn", "linkedin_url"), ("GitHub", "github_url"), ("Website", "website_url")):
        val = getattr(user, attr, None)
        if val:
            lines.append(f"{label}: {val}")

    resume = _clip(getattr(user, "resume_text", None) or getattr(user, "career_history", None), _MAX_RESUME_CHARS)
    if resume:
        lines.append("\nResume / career history:\n" + resume)
    else:
        lines.append("\n(No resume or career history on file yet — ask the user to share details if needed.)")
    return "\n".join(lines)


def _job_block(job) -> str | None:
    """Render the optional focused DiscoveredJob. New scoring/India columns are
    read defensively (getattr) so this works whether or not they've landed."""
    if job is None:
        return None
    lines: list[str] = ["## Focused job"]
    if getattr(job, "title", None):
        lines.append(f"Title: {job.title}")
    if getattr(job, "company", None):
        lines.append(f"Company: {job.company}")
    if getattr(job, "location", None):
        lines.append(f"Location: {job.location}")
    if getattr(job, "work_arrangement", None):
        lines.append(f"Work arrangement: {job.work_arrangement}")

    salary_lpa = getattr(job, "salary_lpa", None)
    salary_raw = getattr(job, "salary_raw", None)
    if salary_lpa:
        lines.append(f"Salary: {salary_lpa} LPA")
    elif salary_raw:
        lines.append(f"Salary: {salary_raw}")
    if getattr(job, "notice_period", None):
        lines.append(f"Notice period: {job.notice_period}")

    if getattr(job, "match_score", None) is not None:
        lines.append(f"Match score: {job.match_score}/100")
    explanation = getattr(job, "match_explanation", None) or getattr(job, "match_reason", None)
    if explanation:
        lines.append(f"Why-fit so far: {explanation}")
    if getattr(job, "missing_skills", None):
        lines.append(f"Missing skills flagged: {job.missing_skills}")

    jd = _clip(getattr(job, "job_description", None), _MAX_JD_CHARS)
    if jd:
        lines.append("\nJob description:\n" + jd)
    return "\n".join(lines)


def _normalise(messages: list[dict]) -> list[dict]:
    """Keep only valid user/assistant turns with content, trimmed to the last N."""
    cleaned: list[dict] = []
    for m in messages or []:
        role = (m.get("role") or "").strip().lower()
        content = _clip(m.get("content"), _MAX_MESSAGE_CHARS)
        if role in _ROLES and content:
            cleaned.append({"role": role, "content": content})
    return cleaned[-_MAX_TURNS:]


def _transcript(messages: list[dict]) -> str:
    label = {"user": "User", "assistant": "Orion"}
    return "\n\n".join(f"{label[m['role']]}: {m['content']}" for m in messages)


async def chat(user, messages: list[dict], job=None) -> str:
    """Generate Orion's next reply.

    ``messages`` is the running history as ``[{"role": "user"|"assistant",
    "content": str}, ...]`` ending with the latest user turn. ``job`` is an
    optional focused ``DiscoveredJob`` to ground the conversation. Raises only if
    the underlying OpenAI call exhausts its retries.
    """
    convo = _normalise(messages)
    if not convo:
        raise ValueError("No user message to respond to")

    sections = [_profile_block(user)]
    job_block = _job_block(job)
    if job_block:
        sections.append(job_block)
    sections.append("## Conversation\n" + _transcript(convo))
    sections.append("Respond as Orion to the user's latest message.")

    user_prompt = "\n\n".join(sections)
    return await _generate(_SYSTEM_PROMPT, user_prompt, max_tokens=900)
