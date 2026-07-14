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


def _subject_for(purpose: str, company: str, role: str) -> str:
    if purpose == "follow_up":
        return f"Following up on {role} at {company}"
    if purpose == "thank_you":
        return f"Thank you — {role} conversation"
    if purpose == "reply":
        return f"Re: {role} at {company}"
    return f"Interest in {role} at {company}"


def _fallback_draft(purpose: str, context: dict) -> dict:
    company = context.get("company") or "your team"
    role = context.get("role") or "the role"
    candidate_name = (context.get("candidate_name") or "").strip()
    recipient_name = (context.get("recipient_name") or "").strip()
    greeting_name = recipient_name or "there"
    signoff_name = candidate_name or "Best regards"
    background = " ".join((context.get("career_history") or "").split())
    highlight = background[:220].rstrip(" .,;") if background else "my background and recent work"
    last_message = (context.get("last_message") or "").strip()

    if purpose == "follow_up":
        body = (
            f"Hi {greeting_name},\n\n"
            f"I wanted to follow up on the {role} opportunity at {company}. "
            f"I'm still very interested and would be glad to share any additional information that may be helpful.\n\n"
            f"Best regards,\n{signoff_name}"
        )
    elif purpose == "thank_you":
        body = (
            f"Hi {greeting_name},\n\n"
            f"Thank you for your time and for the conversation about the {role} opportunity. "
            f"I enjoyed learning more about {company} and remain excited about the role.\n\n"
            f"Best regards,\n{signoff_name}"
        )
    elif purpose == "reply":
        body = (
            f"Hi {greeting_name},\n\n"
            f"Thank you for your message about {role} at {company}. "
            f"{last_message or 'I appreciate the update and would be happy to continue the conversation.'}\n\n"
            f"Best regards,\n{signoff_name}"
        )
    else:
        body = (
            f"Hi {greeting_name},\n\n"
            f"I'm reaching out regarding the {role} opportunity at {company}. "
            f"Based on {highlight}, I believe my experience could be a strong fit for the role. "
            f"I'd be glad to share more details or speak briefly if helpful.\n\n"
            f"Best regards,\n{signoff_name}"
        )

    return {"subject": _subject_for(purpose, company, role), "body": body}


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

    try:
        raw = await _generate(system, user, max_tokens=600)
        parsed = _parse_json(raw)
        subject = (parsed.get("subject") or "").strip() if isinstance(parsed, dict) else ""
        body = (parsed.get("body") or "").strip() if isinstance(parsed, dict) else ""
        if not body:  # parse fell back to {"raw": ...} or empty — use raw text as the body
            body = raw.strip()
        if not subject:
            subject = _subject_for(purpose, company, role)
        return {"subject": subject, "body": body}
    except Exception as exc:
        logger.warning("Email compose AI fallback triggered for purpose=%s: %s", purpose, exc)
        return _fallback_draft(purpose, context)
