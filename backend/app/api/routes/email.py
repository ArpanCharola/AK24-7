"""Gmail "connect email" — Google OAuth connect/callback + status/scan endpoints.

OAuth is tied to the JWT-authenticated user via a short signed `state` token,
because Google calls our /callback without our Authorization header.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.auth import ALGORITHM, create_access_token, get_current_user
from app.core.database import get_db
from app.core.encryption import encrypt
from app.models.job_application import JobApplication
from app.models.sent_email import SentEmail
from app.models.user import User
from app.services import gmail_client
from app.services.email_classifiers import classify_email
from app.services.email_compose import draft_email
from app.services.email_tracker import scan_user
from app.services.gmail_client import GmailScopeError
from app.services.gmail_labels import list_labels
from app.services.gmail_send import send_email as gmail_send_email
from app.services.gmail_service import fetch_inbox_page, fetch_message_full

logger = logging.getLogger(__name__)
router = APIRouter()

_STATE_TTL_MIN = 10


class EmailStatus(BaseModel):
    connected: bool
    gmail_email: str | None = None
    last_synced_at: datetime | None = None
    oauth_configured: bool = True
    can_label: bool = False
    can_send: bool = False
    needs_reconnect: bool = False
    auto_label_enabled: bool = False
    auto_followup_enabled: bool = False
    followup_after_days: int = 7


def _status_for(user: User) -> EmailStatus:
    connected = bool(user.gmail_refresh_token)
    can_label = gmail_client.scopes_can_label(user.gmail_scopes)
    can_send = gmail_client.scopes_can_send(user.gmail_scopes)
    return EmailStatus(
        connected=connected,
        gmail_email=user.gmail_email,
        last_synced_at=user.gmail_last_synced_at,
        oauth_configured=gmail_client.oauth_configured(),
        can_label=can_label,
        can_send=can_send,
        needs_reconnect=connected and not (can_label and can_send),
        auto_label_enabled=bool(user.auto_label_enabled),
        auto_followup_enabled=bool(user.auto_followup_enabled),
        followup_after_days=int(user.followup_after_days or 7),
    )


def _make_state(purpose: str, user_id: int | None = None) -> str:
    """Signed OAuth state. `purpose` is "connect" (an authed user linking Gmail)
    or "login" (Sign in with Google). Connect carries the user id; login carries
    a random nonce for CSRF."""
    claims = {
        "typ": "gmail_oauth",
        "purpose": purpose,
        "nonce": secrets.token_urlsafe(8),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_TTL_MIN),
    }
    if user_id is not None:
        claims["sub"] = str(user_id)
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=ALGORITHM)


def _read_state(state: str) -> tuple[str | None, int | None]:
    """Return (purpose, user_id) — purpose None if the state is invalid."""
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("typ") != "gmail_oauth":
            return None, None
        uid = int(payload["sub"]) if payload.get("sub") is not None else None
        return payload.get("purpose"), uid
    except (JWTError, KeyError, ValueError, TypeError):
        return None, None


def _store_tokens(user: User, creds) -> None:
    expiry = creds.expiry
    if expiry and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    user.gmail_access_token = encrypt(creds.token)
    if creds.refresh_token:  # only present on first consent (prompt=consent forces it)
        user.gmail_refresh_token = encrypt(creds.refresh_token)
    user.gmail_token_expiry = expiry
    user.gmail_connected_at = datetime.now(timezone.utc)
    user.gmail_scopes = " ".join(gmail_client.granted_scopes(creds))


@router.get("/connect")
async def connect(current_user: User = Depends(get_current_user)):
    """Return the Google consent URL to connect an already-signed-in user's Gmail."""
    if not gmail_client.oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET in the backend .env.",
        )
    return {"auth_url": gmail_client.authorization_url(_make_state("connect", current_user.id))}


@router.get("/login")
async def google_login():
    """Start 'Sign in with Google' — a public 302 to Google's consent screen.
    The same consent grants Gmail read access, so these users never need the
    separate Connect-Gmail step. Frontend links the button straight here."""
    front = settings.FRONTEND_URL.rstrip("/")
    if not gmail_client.oauth_configured():
        return RedirectResponse(f"{front}/login?google=unconfigured")
    return RedirectResponse(gmail_client.authorization_url(_make_state("login")))


@router.get("/callback")
async def callback(
    db: AsyncSession = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """OAuth redirect target (Google calls this — no app JWT). Handles both the
    'connect' flow (store tokens on the signed-in user) and the 'login' flow
    (find-or-create the user, then hand the frontend an app JWT)."""
    front = settings.FRONTEND_URL.rstrip("/")
    purpose, user_id = _read_state(state or "")
    is_login = purpose == "login"
    err_url = f"{front}/login?google=error" if is_login else f"{front}/profile?gmail=error"

    if error or not code or purpose is None:
        if is_login:
            return RedirectResponse(f"{front}/login?google=denied")
        return RedirectResponse(f"{front}/profile?gmail=denied")

    try:
        creds = await gmail_client.exchange_code(code)
        info = await gmail_client.fetch_google_userinfo(creds.token)
    except Exception as exc:
        logger.warning("Google OAuth callback failed (purpose=%s): %s", purpose, exc)
        return RedirectResponse(err_url)

    email_addr = (info or {}).get("email")
    if not email_addr:
        return RedirectResponse(err_url)

    if is_login:
        # New refined flow:
        #  - brand-new email  → create a shell account, hand back a token + a
        #    `setup=1` flag so the frontend popup collects username + password.
        #  - returning + already set up → DON'T auto-login; bounce to the login
        #    form with "account already exists" (per product requirement).
        #  - returning but never finished setup → resume setup.
        user = (await db.execute(select(User).where(User.email == email_addr))).scalar_one_or_none()

        if user and user.credentials_set:
            return RedirectResponse(f"{front}/login?google=exists")

        if not user:
            user = User(email=email_addr, full_name=(info or {}).get("name"))
            db.add(user)
        # Connect Gmail too (the consent already granted the scopes) so inbox
        # tracking works without a separate step.
        user.gmail_email = email_addr
        _store_tokens(user, creds)
        await db.commit()
        await db.refresh(user)
        app_token = create_access_token(user.id)
        return RedirectResponse(f"{front}/login?token={app_token}&setup=1")

    # purpose == "connect"
    if user_id is None:
        return RedirectResponse(err_url)
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        return RedirectResponse(err_url)
    user.gmail_email = email_addr
    _store_tokens(user, creds)
    await db.commit()
    return RedirectResponse(f"{front}/profile?gmail=connected")


@router.get("/status", response_model=EmailStatus)
async def status(current_user: User = Depends(get_current_user)):
    return _status_for(current_user)


@router.post("/disconnect", response_model=EmailStatus)
async def disconnect(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    current_user.gmail_email = None
    current_user.gmail_access_token = None
    current_user.gmail_refresh_token = None
    current_user.gmail_token_expiry = None
    current_user.gmail_connected_at = None
    current_user.gmail_scopes = None
    await db.commit()
    return _status_for(current_user)


class ToggleRequest(BaseModel):
    enabled: bool


class FollowupSettings(BaseModel):
    enabled: bool
    after_days: int | None = None


@router.post("/auto-label", response_model=EmailStatus)
async def set_auto_label(body: ToggleRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if body.enabled and not gmail_client.scopes_can_label(current_user.gmail_scopes):
        raise HTTPException(status_code=403, detail="Reconnect Gmail to grant label permission, then enable this.")
    current_user.auto_label_enabled = body.enabled
    await db.commit()
    return _status_for(current_user)


@router.post("/auto-followup", response_model=EmailStatus)
async def set_auto_followup(body: FollowupSettings, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if body.enabled and not gmail_client.scopes_can_send(current_user.gmail_scopes):
        raise HTTPException(status_code=403, detail="Reconnect Gmail to grant send permission, then enable this.")
    current_user.auto_followup_enabled = body.enabled
    if body.after_days is not None:
        current_user.followup_after_days = max(3, min(30, body.after_days))
    await db.commit()
    return _status_for(current_user)


@router.post("/scan")
async def scan_now(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Scan the connected inbox now and update matched applications' stages."""
    if not current_user.gmail_refresh_token:
        raise HTTPException(status_code=409, detail="No Gmail account connected")
    summary = await scan_user(db, current_user)
    return summary


async def _require_token(current_user: User, db: AsyncSession) -> str:
    if not current_user.gmail_refresh_token:
        raise HTTPException(status_code=409, detail="No Gmail account connected")
    token = await gmail_client.get_valid_access_token(db, current_user)
    if not token:
        raise HTTPException(status_code=502, detail="Gmail token invalid — please reconnect")
    return token


@router.get("/inbox")
async def inbox(
    limit: int = Query(default=25, ge=1, le=100),
    page_token: str | None = Query(default=None),
    label: str | None = Query(default=None),
    fresh: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A page of inbox messages, each tagged with its auto-detected kind. Supports
    pagination (page_token) and label filtering for the inbox browser. `fresh`
    requests a cache bypass (accepted but currently a no-op — no cache layer yet)."""
    token = await _require_token(current_user, db)
    try:
        page = await fetch_inbox_page(token, page_token=page_token, label_id=label, max_results=limit)
    except Exception as exc:
        logger.warning("Inbox fetch failed for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=502, detail=f"Failed to read inbox from Gmail — {exc}")
    messages = [
        {
            "id": m.get("id"), "from_email": m.get("from_email"), "subject": m.get("subject"),
            "snippet": m.get("snippet"), "date": m.get("date"), "kind": classify_email(m),
        }
        for m in page["messages"]
    ]
    return {
        "messages": messages,
        "count": len(messages),
        "next_page_token": page["next_page_token"],
        "total_estimate": page["result_size_estimate"],
    }


@router.get("/message/{message_id}")
async def message_detail(
    message_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full body of a single message, for the in-app reader card."""
    token = await _require_token(current_user, db)
    try:
        msg = await fetch_message_full(token, message_id)
    except PermissionError:
        raise HTTPException(status_code=502, detail="Gmail token invalid — please reconnect")
    except Exception as exc:
        logger.warning("Message fetch failed for user %s (id=%s): %s", current_user.id, message_id, exc)
        raise HTTPException(status_code=502, detail=f"Failed to read message from Gmail — {exc}")
    return {
        "id": msg.get("id"),
        "thread_id": msg.get("thread_id"),
        "from_email": msg.get("from_email"),
        "to_email": msg.get("to_email"),
        "subject": msg.get("subject"),
        "date": msg.get("date"),
        "snippet": msg.get("snippet"),
        "body_html": msg.get("body_html"),
        "body_text": msg.get("body_text"),
    }


@router.get("/labels")
async def labels(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    token = await _require_token(current_user, db)
    try:
        return {"labels": await list_labels(token)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to list labels — {exc}")


@router.get("/labels/{label_id}/messages")
async def label_messages(
    label_id: str,
    limit: int = Query(25, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Messages carrying a given Gmail label — a bare list for the label browser."""
    token = await _require_token(current_user, db)
    try:
        # Scope purely by label — pass q="" so archived (non-inbox) mail carrying
        # the label still shows in the browser.
        page = await fetch_inbox_page(token, q="", label_id=label_id, max_results=limit)
    except Exception as exc:
        logger.warning("Label fetch failed for user %s (label=%s): %s", current_user.id, label_id, exc)
        raise HTTPException(status_code=502, detail=f"Failed to read label from Gmail — {exc}")
    return [
        {
            "id": m.get("id"), "thread_id": m.get("thread_id"), "from_email": m.get("from_email"),
            "to_email": m.get("to_email"), "subject": m.get("subject"),
            "snippet": m.get("snippet"), "date": m.get("date"),
        }
        for m in page["messages"]
    ]


@router.post("/labels/sync")
async def labels_sync(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Identify and apply AI Apply labels to the inbox now, then stamp the sync time.

    This is an explicit user action, so it labels regardless of the background
    auto-label toggle and regardless of whether any applications are tracked.
    Labeling needs the modify scope — if the grant is read-only, tell the user to
    reconnect rather than silently reporting "Up to date".
    """
    if not current_user.gmail_refresh_token:
        raise HTTPException(status_code=409, detail="No Gmail account connected")
    if not gmail_client.scopes_can_label(current_user.gmail_scopes):
        raise HTTPException(
            status_code=403,
            detail="Reconnect Gmail to grant label permission, then try Sync now again.",
        )
    summary = await scan_user(db, current_user, force_label=True)
    current_user.gmail_last_synced_at = datetime.now(timezone.utc)
    await db.commit()
    # Report what was *newly* labeled this sync (not every classification), so the
    # toast matches what actually changed in the user's inbox.
    per_label = summary.get("labeled_by_kind") or {
        k: 0 for k in ("confirmed", "assessment", "interview", "offer", "rejected")
    }
    return {"labeled": int(summary.get("labeled", 0)), "per_label": per_label}


class ComposeRequest(BaseModel):
    purpose: str = "follow_up"            # follow_up | thank_you | reply | outreach
    application_id: int | None = None
    discovered_job_id: int | None = None  # for outreach from DiscoveredJobs
    recipient_name: str | None = None
    last_message: str | None = None
    # Explicit overrides — used by outreach flow
    to: str | None = None
    company: str | None = None
    role: str | None = None


class ComposeResponse(BaseModel):
    to: str | None = None
    subject: str
    body: str
    kind: str


@router.post("/compose", response_model=ComposeResponse)
async def compose(body: ComposeRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Draft an email with AI (review-first — does NOT send)."""
    ctx = {
        "candidate_name": current_user.full_name,
        "career_history": current_user.career_history or current_user.resume_text or "",
        "recipient_name": body.recipient_name,
        "last_message": body.last_message,
    }
    to = body.to or None
    # Fill context from application (existing follow-up path)
    if body.application_id:
        app = (await db.execute(
            select(JobApplication).where(
                JobApplication.id == body.application_id,
                JobApplication.user_id == current_user.id,
            )
        )).scalar_one_or_none()
        if app:
            ctx["company"] = app.company
            ctx["role"] = app.job_title
            to = to or app.last_human_email_from
    # Fill context from a discovered job (outreach path)
    if body.discovered_job_id:
        from app.models.discovered_job import DiscoveredJob
        dj = (await db.execute(
            select(DiscoveredJob).where(
                DiscoveredJob.id == body.discovered_job_id,
                DiscoveredJob.user_id == current_user.id,
            )
        )).scalar_one_or_none()
        if dj:
            ctx["company"] = ctx.get("company") or dj.company
            ctx["role"] = ctx.get("role") or dj.title
            ctx["recipient_name"] = ctx.get("recipient_name") or dj.contact_name
            to = to or dj.contact_email
    # Explicit overrides win
    if body.company:
        ctx["company"] = body.company
    if body.role:
        ctx["role"] = body.role
    draft = await draft_email(body.purpose, ctx)
    return ComposeResponse(to=to, subject=draft["subject"], body=draft["body"], kind=body.purpose)


class SendRequest(BaseModel):
    to: str
    subject: str
    body: str
    application_id: int | None = None
    thread_id: str | None = None
    in_reply_to: str | None = None
    kind: str = "compose"


@router.post("/send")
async def send(body: SendRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not gmail_client.scopes_can_send(current_user.gmail_scopes):
        raise HTTPException(status_code=403, detail="Reconnect Gmail to grant send permission.")
    _, addr = parseaddr(body.to or "")
    if "@" not in addr:
        raise HTTPException(status_code=422, detail="A valid recipient address is required")
    token = await _require_token(current_user, db)
    try:
        result = await gmail_send_email(
            token, addr, body.subject, body.body,
            thread_id=body.thread_id, in_reply_to=body.in_reply_to,
        )
    except GmailScopeError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except PermissionError:
        raise HTTPException(status_code=502, detail="Gmail token invalid — please reconnect")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Send failed — {exc}")

    db.add(SentEmail(
        user_id=current_user.id, application_id=body.application_id, to_addr=addr,
        subject=body.subject, body=body.body, gmail_message_id=result.get("id"),
        thread_id=result.get("thread_id"), kind=body.kind,
    ))
    if body.application_id and body.kind == "follow_up":
        await db.execute(
            JobApplication.__table__.update()
            .where(JobApplication.id == body.application_id, JobApplication.user_id == current_user.id)
            .values(followup_sent_at=datetime.now(timezone.utc))
        )
    await db.commit()
    return {"sent": True, "dry_run": result.get("dry_run", False), "gmail_message_id": result.get("id")}
