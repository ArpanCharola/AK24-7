"""Gmail label automation (requires gmail.modify). ADD-ONLY — we never remove
labels, archive, trash, or delete. Mirrors Automail's safety invariant for real
candidate inboxes."""
from __future__ import annotations

import logging
import httpx

from app.services.gmail_client import GmailScopeError

logger = logging.getLogger(__name__)

GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# One nested label per lifecycle kind.
_LABEL_NAME = {
    "confirmed":  "AI Apply/Confirmed",
    "assessment": "AI Apply/Assessment",
    "interview":  "AI Apply/Interview",
    "offer":      "AI Apply/Offer",
    "rejected":   "AI Apply/Rejected",
}
# Best-effort colors (Gmail validates bg/text pairs; on a 400 we retry w/o color).
_COLORS = {
    "confirmed":  {"backgroundColor": "#16a766", "textColor": "#ffffff"},
    "assessment": {"backgroundColor": "#ffad47", "textColor": "#ffffff"},
    "interview":  {"backgroundColor": "#4986e7", "textColor": "#ffffff"},
    "offer":      {"backgroundColor": "#fad165", "textColor": "#000000"},
    "rejected":   {"backgroundColor": "#999999", "textColor": "#ffffff"},
}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _raise_for(resp: httpx.Response):
    if resp.status_code == 401:
        raise PermissionError("Gmail access token expired or invalid")
    if resp.status_code == 403:
        raise GmailScopeError("label", "Reconnect Gmail to grant label (modify) permission")
    if not resp.is_success:
        detail = resp.text[:200]
        try:
            detail = resp.json().get("error", {}).get("message", detail)
        except Exception:
            pass
        raise RuntimeError(f"Gmail API {resp.status_code}: {detail}")


async def _list(client: httpx.AsyncClient) -> dict[str, str]:
    resp = await client.get(f"{GMAIL_BASE}/labels")
    _raise_for(resp)
    return {lab["name"]: lab["id"] for lab in resp.json().get("labels", []) or []}


async def _create(client: httpx.AsyncClient, name: str, color: dict | None) -> str | None:
    body = {"name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"}
    if color:
        body["color"] = color
    resp = await client.post(f"{GMAIL_BASE}/labels", json=body)
    if resp.status_code == 400 and color:  # likely an invalid color pair — retry plain
        body.pop("color", None)
        resp = await client.post(f"{GMAIL_BASE}/labels", json=body)
    if resp.status_code == 409:  # already exists (race) — caller re-lists
        return None
    _raise_for(resp)
    return resp.json().get("id")


async def ensure_labels(token: str) -> dict[str, str]:
    """Idempotently create the AI Apply lifecycle labels. Returns {kind: labelId}."""
    async with httpx.AsyncClient(timeout=15.0, headers=_auth(token)) as client:
        existing = await _list(client)
        result: dict[str, str] = {}
        created_any = False
        for kind, name in _LABEL_NAME.items():
            if name in existing:
                result[kind] = existing[name]
                continue
            lid = await _create(client, name, _COLORS.get(kind))
            if lid:
                result[kind] = lid
            else:
                created_any = True  # 409 race — re-list below to pick up the id
        if created_any:
            for name, lid in (await _list(client)).items():
                for kind, n in _LABEL_NAME.items():
                    if n == name:
                        result[kind] = lid
        return result


async def apply_label(token: str, msg_id: str, label_id: str) -> None:
    """Add a label to a message — never removes anything."""
    async with httpx.AsyncClient(timeout=10.0, headers=_auth(token)) as client:
        resp = await client.post(
            f"{GMAIL_BASE}/messages/{msg_id}/modify",
            json={"addLabelIds": [label_id]},
        )
        _raise_for(resp)


async def list_labels(token: str) -> list[dict]:
    """List the user's labels (for the inbox/labels browser)."""
    async with httpx.AsyncClient(timeout=10.0, headers=_auth(token)) as client:
        resp = await client.get(f"{GMAIL_BASE}/labels")
        _raise_for(resp)
        labs = resp.json().get("labels", []) or []
        return [{"id": l.get("id"), "name": l.get("name"), "type": l.get("type")} for l in labs]


async def create_label(token: str, name: str, color: dict | None = None) -> dict:
    """Create one user label. Gmail nests via a 'Parent/Child' name. If the label
    already exists (409), returns the existing id instead of erroring."""
    async with httpx.AsyncClient(timeout=10.0, headers=_auth(token)) as client:
        lid = await _create(client, name, color)
        if lid is None:  # 409 — already exists, look up its id
            lid = (await _list(client)).get(name)
        return {"id": lid, "name": name}
