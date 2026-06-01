"""Google OAuth flow + token lifecycle for the Gmail "connect email" feature.

- build_flow / authorization_url — start the consent flow
- exchange_code — turn the callback `code` into credentials
- fetch_google_email — read the connected account's address
- get_valid_access_token — return a live access token for a user, refreshing
  (and persisting the refreshed token, encrypted) when expired
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request as GoogleRequest
from google_auth_oauthlib.flow import Flow

from app.config import settings
from app.core.encryption import decrypt, encrypt

logger = logging.getLogger(__name__)

# Google sometimes returns scopes in a different order / adds openid; relax so
# oauthlib doesn't raise "Scope has changed" on token exchange.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

SCOPE_MODIFY = "https://www.googleapis.com/auth/gmail.modify"  # read + label/modify (no delete)
SCOPE_SEND = "https://www.googleapis.com/auth/gmail.send"

# Identity-only scopes — enough for "Sign in with Google" (no Gmail access).
# Gmail features are gated behind a separate, explicit "Connect Gmail" consent.
BASIC_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
# Full grant for the Gmail-connected flow (the AK24/7Jobs Google Cloud project).
SCOPES = [
    *BASIC_SCOPES,
    SCOPE_MODIFY,  # supersedes gmail.readonly
    SCOPE_SEND,
]
_TOKEN_URI = "https://oauth2.googleapis.com/token"


class GmailScopeError(Exception):
    """Raised when a Gmail call needs a scope the user hasn't granted —
    the API layer maps this to a 403 telling the user to reconnect."""
    def __init__(self, capability: str, message: str | None = None):
        self.capability = capability  # "label" | "send"
        super().__init__(message or f"Reconnect Gmail to grant '{capability}' permission")


def oauth_configured() -> bool:
    return bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)


def granted_scopes(creds) -> list[str]:
    """Scopes actually granted on an OAuth credential (from the token response)."""
    scopes = getattr(creds, "scopes", None)
    if scopes:
        return list(scopes)
    raw = getattr(creds, "_scopes", None)
    return list(raw) if raw else []


def scopes_can_label(scope_str: str | None) -> bool:
    return bool(scope_str) and SCOPE_MODIFY in scope_str.split()


def scopes_can_send(scope_str: str | None) -> bool:
    return bool(scope_str) and SCOPE_SEND in scope_str.split()


def login_redirect_uri() -> str:
    """Redirect URI for the basic 'Sign in with Google' flow (`/api/auth/google/callback`).

    Prefers an explicit ``GOOGLE_LOGIN_REDIRECT_URI`` setting; otherwise derives
    it from ``GOOGLE_REDIRECT_URI`` (which points at the Gmail-connect callback)
    by swapping the path, so the two share a host without a second config var.
    """
    explicit = getattr(settings, "GOOGLE_LOGIN_REDIRECT_URI", "") or ""
    if explicit:
        return explicit
    base = settings.GOOGLE_REDIRECT_URI.split("/api/", 1)[0]
    return f"{base}/api/auth/google/callback"


def build_flow(
    state: str | None = None,
    *,
    scopes: list[str] | None = None,
    redirect_uri: str | None = None,
) -> Flow:
    redirect_uri = redirect_uri or settings.GOOGLE_REDIRECT_URI
    client_config = {
        "web": {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": _TOKEN_URI,
            "redirect_uris": [redirect_uri],
        }
    }
    return Flow.from_client_config(
        client_config, scopes=scopes or SCOPES, redirect_uri=redirect_uri, state=state
    )


def authorization_url(
    state: str,
    *,
    scopes: list[str] | None = None,
    redirect_uri: str | None = None,
) -> str:
    flow = build_flow(state=state, scopes=scopes, redirect_uri=redirect_uri)
    url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    return url


async def exchange_code(code: str, *, redirect_uri: str | None = None) -> Credentials:
    """Exchange an OAuth callback `code` for credentials (blocking call offloaded).

    ``redirect_uri`` must match the one used to start the flow — pass the login
    callback for the basic Sign-in-with-Google flow."""
    flow = build_flow(redirect_uri=redirect_uri)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: flow.fetch_token(code=code))
    return flow.credentials


async def fetch_google_userinfo(access_token: str) -> dict | None:
    """Return the Google account's userinfo ({email, name, ...}) or None."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.is_success:
            return resp.json()
    return None


async def fetch_google_email(access_token: str) -> str | None:
    info = await fetch_google_userinfo(access_token)
    return info.get("email") if info else None


def _aware(dt: datetime | None) -> datetime | None:
    if dt and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


async def get_valid_access_token(db, user) -> str | None:
    """Return a usable Gmail access token for `user`, refreshing if expired.
    Persists a refreshed token (encrypted). Returns None if not connected or
    refresh fails (caller treats as 'skip this user')."""
    refresh_token = decrypt(user.gmail_refresh_token)
    if not refresh_token:
        return None

    access_token = decrypt(user.gmail_access_token)
    expiry = _aware(user.gmail_token_expiry)
    now = datetime.now(timezone.utc)
    if access_token and expiry and expiry > now + timedelta(seconds=60):
        return access_token  # still valid

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=_TOKEN_URI,
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
    )
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, lambda: creds.refresh(GoogleRequest()))
    except Exception as exc:
        logger.warning("Gmail token refresh failed for user %s: %s", user.id, exc)
        return None

    user.gmail_access_token = encrypt(creds.token)
    user.gmail_token_expiry = _aware(creds.expiry)
    await db.commit()
    return creds.token
