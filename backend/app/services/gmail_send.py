"""Send mail via the Gmail REST API (requires gmail.send). Builds a MIME message
with the stdlib and POSTs the base64url raw form to users.messages.send.

`From` is omitted — Gmail stamps it as the authenticated account automatically.
When replying in-thread, pass `thread_id` (+ `in_reply_to` Message-ID) so Gmail
and the recipient's client thread it correctly.
"""
from __future__ import annotations

import base64
import logging
from email.message import EmailMessage

import httpx

from app.config import settings
from app.services.gmail_client import GmailScopeError

logger = logging.getLogger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _build_raw(to: str, subject: str, body: str, in_reply_to: str | None) -> str:
    msg = EmailMessage()
    msg["To"] = to
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(body)
    return base64.urlsafe_b64encode(msg.as_bytes()).decode()


async def send_email(
    token: str,
    to: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
    in_reply_to: str | None = None,
) -> dict:
    """Send (or, under EMAIL_SEND_DRYRUN, just log) an email. Returns
    {"id", "thread_id", "dry_run"}."""
    if settings.EMAIL_SEND_DRYRUN:
        logger.info("[DRYRUN] would send to=%s subject=%r thread=%s", to, subject[:80], thread_id)
        return {"id": None, "thread_id": thread_id, "dry_run": True}

    payload: dict = {"raw": _build_raw(to, subject, body, in_reply_to)}
    if thread_id:
        payload["threadId"] = thread_id

    async with httpx.AsyncClient(timeout=20.0, headers={"Authorization": f"Bearer {token}"}) as client:
        resp = await client.post(f"{GMAIL_BASE}/messages/send", json=payload)
        if resp.status_code == 401:
            raise PermissionError("Gmail access token expired or invalid")
        if resp.status_code == 403:
            raise GmailScopeError("send", "Reconnect Gmail to grant send permission")
        if not resp.is_success:
            detail = resp.text[:200]
            try:
                detail = resp.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(f"Gmail API {resp.status_code}: {detail}")
        data = resp.json()
        return {"id": data.get("id"), "thread_id": data.get("threadId"), "dry_run": False}
