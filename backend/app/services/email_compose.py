"""AI-drafted outbound emails (follow-up / thank-you / reply to a recruiter).

Reuses the shared OpenAI helper so it inherits the semaphore + retry + gpt-4o
config. Grounded strictly in the candidate's real background — never fabricate.
"""
from __future__ import annotations

import logging

from app.services.resume_tailor import _generate, _parse_json

logger = logging.getLogger(__name__)

_PURPOSE_GUIDANCE = {
    "follow_up": "Write a brief, polite follow-up nudging gently for a status update on the application.",
    "thank_you": "Write a short, warm thank-you note after an interview or conversation.",
    "reply": "Write a concise, professional reply to the recruiter's message below.",
    "outreach": (
        "Write a short, warm cold-outreach email to a recruiter / hiring manager "
        "expressing interest in a specific open role. Briefly explain why the "
        "candidate's background fits (cite 1-2 concrete points from their "
        "background). Be respectful of the recipient's time. Do NOT ask for "
        "a referral; ask for a quick conversation or next steps for applying."
    ),
}


async def draft_email(purpose: str, context: dict) -> dict:
    """Return {"subject", "body"} for the given purpose. `context` may include
    candidate_name, career_history, company, role, recipient_name, last_message."""
    guidance = _PURPOSE_GUIDANCE.get(purpose, _PURPOSE_GUIDANCE["follow_up"])
    company = context.get("company") or "the company"
    role = context.get("role") or "the role"

    system = (
        "You write short, professional job-search emails on behalf of a candidate. "
        f"{guidance} "
        "Ground every statement in the candidate's actual background below — never invent "
        "employers, skills, dates, or achievements. Keep it 3-6 sentences, friendly and concise. "
        "No letterhead, no '[Your Name]' placeholders (sign off with the candidate's real name if given). "
        'Return ONLY a JSON object: {"subject": "...", "body": "..."}.'
    )
    user = (
        f"Purpose: {purpose}\n"
        f"Company: {company}\nRole: {role}\n"
        f"Candidate name: {context.get('candidate_name') or ''}\n"
        f"Recipient: {context.get('recipient_name') or '(unknown)'}\n"
        f"Candidate background:\n{context.get('career_history') or ''}\n"
    )
    if context.get("last_message"):
        user += f"\nRecruiter's message to reply to:\n{context['last_message'][:1500]}\n"

    raw = await _generate(system, user, max_tokens=600)
    parsed = _parse_json(raw)
    subject = (parsed.get("subject") or "").strip() if isinstance(parsed, dict) else ""
    body = (parsed.get("body") or "").strip() if isinstance(parsed, dict) else ""
    if not body:  # parse fell back to {"raw": ...} or empty — use raw text as the body
        body = raw.strip()
    if not subject:
        subject = f"Following up — {role} at {company}" if purpose == "follow_up" else f"{role} at {company}"
    return {"subject": subject, "body": body}
