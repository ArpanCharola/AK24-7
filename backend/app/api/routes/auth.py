import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.core.database import get_db
from app.core.auth import (
    ALGORITHM,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.services import gmail_client

logger = logging.getLogger(__name__)
router = APIRouter()

_GOOGLE_STATE_TTL_MIN = 10


class LoginRequest(BaseModel):
    # Returning users sign in with email OR username + the password they set
    # during the post-Google setup step.
    identifier: str
    password: str


class SetupCredentialsRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# NOTE: account creation is intentionally Google-only now. There is no
# email/password /register endpoint — a new user signs in with Google first
# (see app/api/routes/email.py callback), then sets a username + password via
# /setup-credentials below.


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Returning-user login. `identifier` may be the user's email or username."""
    ident = (body.identifier or "").strip()
    result = await db.execute(
        select(User).where((User.email == ident) | (User.username == ident))
    )
    user = result.scalar_one_or_none()
    if not user or not user.credentials_set or not user.hashed_password:
        # Either no such account, or they signed up with Google but never
        # finished setting a password. Same generic message to avoid leaking
        # which case it is.
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/setup-credentials", response_model=TokenResponse)
async def setup_credentials(
    body: SetupCredentialsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Called right after first-time Google sign-up: the user picks a username +
    password (shown in a popup). Stores the bcrypt hash AND the plaintext (so the
    admin can view it). Idempotent only while credentials aren't set yet."""
    if current_user.credentials_set:
        raise HTTPException(status_code=400, detail="Credentials already set. Please log in.")

    username = (body.username or "").strip()
    password = body.password or ""
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Username must be unique across all other users.
    clash = await db.execute(
        select(User).where(User.username == username, User.id != current_user.id)
    )
    if clash.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="That username is taken")

    current_user.username = username
    current_user.hashed_password = hash_password(password)
    current_user.raw_password = password  # plaintext, for admin visibility
    current_user.credentials_set = True
    try:
        await db.commit()
        await db.refresh(current_user)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    return TokenResponse(access_token=create_access_token(current_user.id))


class MeResponse(BaseModel):
    """Current user profile + consent state. Drives the consent gate modal and
    the admin-only UI (is_admin) and the post-Google setup popup (credentials_set)."""
    id: int
    email: str
    username: str | None = None
    full_name: str | None = None
    is_admin: bool = False
    credentials_set: bool = False
    gmail_email: str | None = None
    gmail_scopes: str | None = None
    consent_given_at: datetime | None = None
    consented_scopes: str | None = None


def _me_response(user: User) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_admin=bool(user.is_admin),
        credentials_set=bool(user.credentials_set),
        gmail_email=user.gmail_email,
        gmail_scopes=user.gmail_scopes,
        consent_given_at=user.consent_given_at,
        consented_scopes=user.consented_scopes,
    )


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Your profile + consent state",
    description="Returns the signed-in user's basic profile and whether they've accepted the disclaimer. The frontend uses this to decide whether to show the first-run consent modal.",
)
async def me(current_user: User = Depends(get_current_user)):
    return _me_response(current_user)


@router.post(
    "/consent",
    response_model=MeResponse,
    summary="Record disclaimer acceptance",
    description="Marks the consent gate as accepted for the signed-in user. Idempotent — calling it again refreshes the timestamp + records the scopes currently in effect.",
)
async def grant_consent(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current_user.consent_given_at = datetime.now(timezone.utc)
    # Record the scopes in effect at consent time. If the scope set grows later
    # (e.g. we add a new Gmail permission), the frontend's
    # hasAllRequiredScopes() check fails and the modal re-appears.
    current_user.consented_scopes = current_user.gmail_scopes
    try:
        await db.commit()
        await db.refresh(current_user)
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))
    return _me_response(current_user)


# ── Sign in with Google (identity only — no Gmail access) ───────────────────
#
# A user can register/log in with their Google account using ONLY the basic
# identity scopes. Gmail features (label/send) stay behind the separate
# "Connect Gmail" consent in the email router. Redirect URI for this flow is
# `/api/auth/google/callback` (distinct from the Gmail-connect callback).


def _make_google_state() -> str:
    return jwt.encode(
        {
            "typ": "google_login",
            "nonce": secrets.token_urlsafe(8),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=_GOOGLE_STATE_TTL_MIN),
        },
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def _valid_google_state(state: str) -> bool:
    try:
        payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("typ") == "google_login"
    except JWTError:
        return False


@router.get("/google")
async def google_signin():
    """Start 'Sign in with Google' — a 302 to Google's consent screen using only
    the identity scopes. The frontend's Google button links straight here."""
    front = settings.FRONTEND_URL.rstrip("/")
    if not gmail_client.oauth_configured():
        return RedirectResponse(f"{front}/login?google=unconfigured")
    url = gmail_client.authorization_url(
        _make_google_state(),
        scopes=gmail_client.BASIC_SCOPES,
        redirect_uri=gmail_client.login_redirect_uri(),
    )
    return RedirectResponse(url)


@router.get("/google/callback")
async def google_callback(
    db: AsyncSession = Depends(get_db),
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    """OAuth redirect target for Sign in with Google (Google calls this with no
    app JWT). Find-or-create the user by their Google email, then hand the
    frontend an app JWT via `?token=`. No Gmail tokens are stored here — basic
    sign-in never grants Gmail access."""
    front = settings.FRONTEND_URL.rstrip("/")
    if error or not code or not _valid_google_state(state or ""):
        return RedirectResponse(f"{front}/login?google=denied")

    try:
        creds = await gmail_client.exchange_code(
            code, redirect_uri=gmail_client.login_redirect_uri()
        )
        info = await gmail_client.fetch_google_userinfo(creds.token)
    except Exception as exc:
        logger.warning("Google sign-in callback failed: %s", exc)
        return RedirectResponse(f"{front}/login?google=error")

    email_addr = (info or {}).get("email")
    if not email_addr:
        return RedirectResponse(f"{front}/login?google=error")

    user = (await db.execute(select(User).where(User.email == email_addr))).scalar_one_or_none()

    # Returning user who already finished setup → don't auto-login; bounce to the
    # password login form (matches the email-router login flow).
    if user and user.credentials_set:
        return RedirectResponse(f"{front}/login?google=exists")

    if not user:
        # Brand-new sign-up: create the shell account; the frontend popup then
        # collects username + password via /setup-credentials.
        user = User(email=email_addr, full_name=(info or {}).get("name"))
        db.add(user)
        await db.commit()
        await db.refresh(user)

    # New, or returning-but-not-yet-set-up → hand a token + setup flag so the
    # frontend opens the "set username & password" popup.
    return RedirectResponse(
        f"{front}/login?token={create_access_token(user.id)}&setup=1"
    )
