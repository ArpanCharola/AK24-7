"""AI double-check for the application tracker.

Only the ambiguous band — a confirmation phrase present, but the sender is not a
trusted ATS — is sent to OpenAI for a yes/no verdict. Cached by Gmail message id
so each mail is judged at most once. This caching is what makes the daily
tracker count deterministic across refreshes.

Privacy mirrors ``label_ai`` exactly: subject + snippet + sender go to OpenAI for
classification only, never logged. Any failure returns ``None`` so the caller
falls back to the rules verdict. Never raises.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from app.config import settings
from app.services import cache

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You classify a single email from a job seeker's inbox. Decide whether it is "
    "a genuine confirmation that THIS person submitted a JOB application to an "
    "employer and the employer (or its applicant-tracking system) received it.\n\n"
    "Answer true ONLY for a real acknowledgement of a submitted job application — "
    "e.g. 'thank you for applying', 'we've received your application for the "
    "<role> position', 'your application has been submitted'.\n\n"
    "Answer false for everything else, even when it contains the word "
    "'application', including: job-board digests and job alerts ('jobs near "
    "you'), 'finish/complete/continue your application' nudges, application "
    "status-change or rejection updates, interview or assessment invitations "
    "(those are later stages, not the submission confirmation), marketing, "
    "newsletters, webinars, courses, surveys, sales/demo emails, and NON-JOB "
    "applications (loan, credit card, rental, mortgage, visa, passport, "
    "membership, insurance, college/admission, leave).\n\n"
    'Respond with ONLY a JSON object: {"application": <true|false>}.'
)

_client = None
_client_failed = False


def _get_client():
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
        logger.warning("[app-ai] client init failed: %s", type(e).__name__)
        _client_failed = True
        return None


def _ask_sync(subject: str, snippet: str, sender: str) -> Optional[bool]:
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
        return bool(data.get("application"))
    except Exception as e:
        logger.warning("[app-ai] verify failed: %s", type(e).__name__)
        return None


async def verify(msg_id: str, subject: str, snippet: str, sender: str) -> Optional[bool]:
    """Return True/False for an ambiguous candidate, or ``None`` when the AI is
    unavailable (caller falls back to the rules verdict)."""
    if msg_id:
        cached = await cache.get_application_ai_cache(msg_id)
        if cached is not None:
            return bool(cached.get("application"))
    verdict = await asyncio.to_thread(_ask_sync, subject, snippet, sender)
    if verdict is not None and msg_id:
        await cache.set_application_ai_cache(msg_id, {"application": verdict})
    return verdict
