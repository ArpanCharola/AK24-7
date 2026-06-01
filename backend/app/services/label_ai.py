"""AI double-check for the label classifier (assessment / interview).

Only the ambiguous band the rules surface — a rules match from an untrusted
sender (review_yes), or a topical mail without a confident verdict (review_no) —
is sent to OpenAI for a meaning-aware verdict. Verdicts are cached by Gmail
message id so each mail is judged at most once.

Privacy: this is one of the places where subject + snippet + sender leave the
server (sent to OpenAI for classification only, never logged). Any failure
returns ``None`` so the caller falls back to the rules verdict. Never raises.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from app.config import settings
from app.services import cache
from app.services.email_classifiers import LABEL_ASSESSMENT, LABEL_INTERVIEW

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You classify a single email from a job seeker's inbox. Decide whether it is "
    "a genuine, personalized step in THIS person's hiring process.\n\n"
    "Definitions:\n"
    "- assessment: an invitation, reminder, or link to take a coding test, online "
    "assessment, take-home assignment, skills/aptitude test, or one-way recorded "
    "video assessment as part of a job application.\n"
    "- interview: scheduling, inviting, confirming, or rescheduling a real job "
    "interview or recruiter/hiring-team screen (phone, video, or onsite).\n\n"
    "Be strict. Mark BOTH false for anything that is not a real hiring step, "
    "including: marketing or product emails, newsletters, blog posts, webinars, "
    "online courses or bootcamps, sales/demo bookings, job-board digests or job "
    "alerts, 'complete your profile/application' nudges, surveys, and general "
    "tips or advice articles — even when they use the words interview or "
    "assessment.\n\n"
    'Respond with ONLY a JSON object: {"assessment": <true|false>, '
    '"interview": <true|false>}.'
)

_client = None
_client_failed = False


def _get_client():
    """Lazily build the OpenAI client; cache failure so we don't retry every call."""
    global _client, _client_failed
    if _client is not None:
        return _client
    if _client_failed:
        return None
    try:
        from openai import OpenAI

        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return _client
    except Exception as e:
        logger.warning("[label-ai] client init failed: %s", type(e).__name__)
        _client_failed = True
        return None


def _ask_sync(subject: str, snippet: str, sender: str) -> Optional[dict]:
    client = _get_client()
    if client is None:
        return None
    user_content = (
        f"From: {sender or ''}\n"
        f"Subject: {subject or ''}\n"
        f"Preview: {snippet or ''}"
    )
    try:
        resp = client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=20,
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return {
            LABEL_ASSESSMENT: bool(data.get("assessment")),
            LABEL_INTERVIEW: bool(data.get("interview")),
        }
    except Exception as e:
        logger.warning("[label-ai] verify failed: %s", type(e).__name__)
        return None


async def verify(msg_id: str, subject: str, snippet: str, sender: str) -> Optional[dict]:
    """Return {assessment: bool, interview: bool} for an ambiguous email, or
    ``None`` when the AI is unavailable (caller then falls back to the rules)."""
    if msg_id:
        cached = await cache.get_label_ai_cache(msg_id)
        if cached is not None:
            return cached
    verdict = await asyncio.to_thread(_ask_sync, subject, snippet, sender)
    if verdict is not None and msg_id:
        await cache.set_label_ai_cache(msg_id, verdict)
    return verdict
