"""Pull the hiring company + job role out of an application-confirmation email.

Used by the Job Tracker auto-track bridge to turn each detected confirmation
into a card with a real company and role. Falls back to a sender-derived
heuristic when the AI is unavailable. Cached per Gmail message id so the same
mail is read at most once. Never raises.
"""
from __future__ import annotations

import asyncio
import json
import logging
from email.utils import parseaddr
from typing import Optional

from app.config import settings
from app.services import cache

logger = logging.getLogger(__name__)

_MODEL = "gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You read ONE job-application confirmation email from a candidate's inbox and "
    "extract two facts:\n"
    "- company: the employer the person applied to. Prefer the actual hiring "
    "company over the applicant-tracking system or mail platform (e.g. prefer "
    "'Acme' over 'Greenhouse', 'Lever', or 'Workday').\n"
    "- role: the specific job title applied for, if the email states it.\n\n"
    "If a field is not clearly present, use an empty string — do not guess.\n"
    'Respond with ONLY a JSON object: {"company": "<string>", "role": "<string>"}.'
)

_GENERIC_SENDER_NAMES = (
    "no-reply", "noreply", "no reply", "do not reply", "donotreply",
    "notifications", "notification", "careers", "recruiting", "talent", "jobs",
    "hello", "team", "support",
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
        logger.warning("[app-extract] client init failed: %s", type(e).__name__)
        _client_failed = True
        return None


def company_from_sender(from_header: str) -> str:
    """Heuristic company name from a From header; the AI-unavailable fallback.
    Prefers a meaningful display name, otherwise the domain's main label
    (jobs@greenhouse.io -> 'Greenhouse')."""
    name, addr = parseaddr(from_header or "")
    name = (name or "").strip().strip('"').strip()
    lname = name.lower()
    if name and "@" not in name and not any(g in lname for g in _GENERIC_SENDER_NAMES):
        return name[:200]
    domain = addr.split("@", 1)[1].lower() if "@" in addr else ""
    if domain:
        parts = [p for p in domain.split(".") if p]
        label = parts[-2] if len(parts) >= 2 else (parts[0] if parts else "")
        if label:
            return label.replace("-", " ").title()[:200]
    return (name or "Unknown company")[:200]


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
            max_tokens=60,
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content)
        return {
            "company": str(data.get("company") or "").strip()[:200],
            "role": str(data.get("role") or "").strip()[:200],
        }
    except Exception as e:
        logger.warning("[app-extract] extract failed: %s", type(e).__name__)
        return None


async def extract(msg_id: str, subject: str, snippet: str, sender: str) -> dict:
    """Return {"company": str, "role": str} for one application email.

    ``company`` is always non-empty (heuristic fallback); ``role`` may be ""
    when it can't be determined. Cached by ``msg_id`` so each mail is read once.
    Never raises.
    """
    if msg_id:
        cached = await cache.get_app_extract_cache(msg_id)
        if cached is not None:
            return cached
    ai = await asyncio.to_thread(_ask_sync, subject, snippet, sender)
    company = (ai or {}).get("company", "").strip()
    role = (ai or {}).get("role", "").strip()
    if not company:
        company = company_from_sender(sender)
    result = {"company": company, "role": role}
    if msg_id:
        await cache.set_app_extract_cache(msg_id, result)
    return result
