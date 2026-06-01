"""Minimal async Gmail REST client (read-only) for the application tracker.

Ported from skilluence/Gmail-Automation to httpx + asyncio to match AI Apply.
We only need to search the inbox and read message metadata (headers + snippet),
so this is deliberately small — no batch endpoint, no send. The tracker's search
query is narrow (confirmation/assessment/interview anchors), so result sets are
small enough to fetch metadata with a bounded-concurrency gather.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging

import httpx

logger = logging.getLogger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
_METADATA_HEADERS = ["From", "To", "Subject", "Date", "Message-ID"]
_FETCH_CONCURRENCY = 8


def _shape(detail: dict) -> dict:
    headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
    return {
        "id": detail.get("id", ""),
        "thread_id": detail.get("threadId", ""),
        "from_email": headers.get("From", ""),
        "to_email": headers.get("To", ""),
        "subject": headers.get("Subject", "(no subject)"),
        "date": headers.get("Date", ""),
        "message_id": headers.get("Message-ID", "") or headers.get("Message-Id", ""),
        "snippet": detail.get("snippet", ""),
        "label_ids": detail.get("labelIds", []),
    }


async def _list_ids(client: httpx.AsyncClient, q: str, max_results: int) -> list[str]:
    ids: list[str] = []
    page_token: str | None = None
    while len(ids) < max_results:
        params: dict = {"q": q, "maxResults": min(100, max_results - len(ids))}
        if page_token:
            params["pageToken"] = page_token
        resp = await client.get(f"{GMAIL_BASE}/messages", params=params)
        if resp.status_code == 401:
            raise PermissionError("Gmail access token expired or invalid")
        if not resp.is_success:
            # Surface Gmail's own message (e.g. "Gmail API has not been used in
            # project … or it is disabled", or insufficient-scope) for diagnosis.
            detail = resp.text[:300]
            try:
                detail = resp.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(f"Gmail API {resp.status_code}: {detail}")
        data = resp.json()
        for stub in data.get("messages") or []:
            if stub.get("id"):
                ids.append(stub["id"])
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return ids


async def _fetch_metadata(client: httpx.AsyncClient, mid: str, sem: asyncio.Semaphore) -> dict | None:
    async with sem:
        try:
            resp = await client.get(
                f"{GMAIL_BASE}/messages/{mid}",
                params=[("format", "metadata")] + [("metadataHeaders", h) for h in _METADATA_HEADERS],
            )
            if not resp.is_success:
                return None
            return _shape(resp.json())
        except Exception as exc:
            logger.debug("gmail metadata fetch failed for %s: %s", mid, exc)
            return None


async def fetch_inbox_page(
    access_token: str,
    q: str = "in:inbox",
    page_token: str | None = None,
    label_id: str | None = None,
    max_results: int = 25,
) -> dict:
    """One page of inbox messages + the next page token (for the browser UI)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    # Skip an empty q so callers can scope purely by labelIds (e.g. the label
    # browser, which wants archived mail too — not just in:inbox).
    params: list = [("maxResults", max_results)]
    if q:
        params.append(("q", q))
    if page_token:
        params.append(("pageToken", page_token))
    if label_id:
        params.append(("labelIds", label_id))
    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        resp = await client.get(f"{GMAIL_BASE}/messages", params=params)
        if resp.status_code == 401:
            raise PermissionError("Gmail access token expired or invalid")
        if not resp.is_success:
            detail = resp.text[:200]
            try:
                detail = resp.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(f"Gmail API {resp.status_code}: {detail}")
        data = resp.json()
        ids = [s["id"] for s in (data.get("messages") or []) if s.get("id")]
        next_token = data.get("nextPageToken")
        total_estimate = int(data.get("resultSizeEstimate") or 0)
        if not ids:
            return {"messages": [], "next_page_token": next_token, "result_size_estimate": total_estimate}
        sem = asyncio.Semaphore(_FETCH_CONCURRENCY)
        results = await asyncio.gather(*(_fetch_metadata(client, mid, sem) for mid in ids))
    return {
        "messages": [m for m in results if m is not None],
        "next_page_token": next_token,
        "result_size_estimate": total_estimate,
    }


def _decode_b64url(data: str) -> str:
    """Decode Gmail's base64url body data to a UTF-8 string (lossy on bad bytes)."""
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data.encode("ascii")).decode("utf-8", "replace")
    except (binascii.Error, ValueError):
        return ""


def _extract_bodies(payload: dict) -> tuple[str, str]:
    """Walk a message payload tree, returning (html, plain) — the first body found
    of each type. Gmail nests parts (multipart/alternative, multipart/mixed, …),
    so this recurses; attachments carry no inline `body.data` and are skipped."""
    html, plain = "", ""

    def walk(part: dict) -> None:
        nonlocal html, plain
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data:
            if mime == "text/html" and not html:
                html = _decode_b64url(data)
            elif mime == "text/plain" and not plain:
                plain = _decode_b64url(data)
        for sub in part.get("parts", []) or []:
            walk(sub)

    walk(payload or {})
    return html, plain


async def fetch_message_full(access_token: str, message_id: str) -> dict:
    """Fetch a single message with its full body (HTML + plain text) for reading.

    Returns the shaped metadata plus `body_html` / `body_text`. Raises
    PermissionError on a 401 so callers can refresh the token and retry.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        resp = await client.get(f"{GMAIL_BASE}/messages/{message_id}", params={"format": "full"})
        if resp.status_code == 401:
            raise PermissionError("Gmail access token expired or invalid")
        if not resp.is_success:
            detail = resp.text[:200]
            try:
                detail = resp.json().get("error", {}).get("message", detail)
            except Exception:
                pass
            raise RuntimeError(f"Gmail API {resp.status_code}: {detail}")
        detail = resp.json()
    shaped = _shape(detail)
    html, plain = _extract_bodies(detail.get("payload", {}))
    shaped["body_html"] = html
    shaped["body_text"] = plain
    return shaped


async def fetch_messages_by_query(access_token: str, q: str, max_results: int = 200) -> list[dict]:
    """Search the inbox and return shaped message metadata (newest-first).

    `q` is Gmail search syntax. Raises PermissionError on a 401 so callers can
    trigger a token refresh and retry.
    """
    headers = {"Authorization": f"Bearer {access_token}"}
    async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
        ids = await _list_ids(client, q, max_results)
        if not ids:
            return []
        sem = asyncio.Semaphore(_FETCH_CONCURRENCY)
        results = await asyncio.gather(*(_fetch_metadata(client, mid, sem) for mid in ids))
    return [m for m in results if m is not None]
