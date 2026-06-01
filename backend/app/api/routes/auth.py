import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr
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


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.id))


class MeResponse(BaseModel):
    """Current user profile + consent state. Drives the consent gate modal."""
    id: int
    email: str
    full_name: str | None = None
    gmail_email: str | None = None
    gmail_scopes: str | None = None
    consent_given_at: datetime | None = None
    consented_scopes: str | None = None


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Your profile + consent state",
    description="Returns the signed-in user's basic profile and whether they've accepted the disclaimer. The frontend uses this to decide whether to show the first-run consent modal.",
)
async def me(current_user: User = Depends(get_current_user)):
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        gmail_email=current_user.gmail_email,
        gmail_scopes=current_user.gmail_scopes,
        consent_given_at=current_user.consent_given_at,
        consented_scopes=current_user.consented_scopes,
    )


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
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        gmail_email=current_user.gmail_email,
        gmail_scopes=current_user.gmail_scopes,
        consent_given_at=current_user.consent_given_at,
        consented_scopes=current_user.consented_scopes,
    )


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
    if not user:
        # Random password → this account can only sign in via Google until the
        # user sets one through a future reset flow.
        user = User(
            email=email_addr,
            full_name=(info or {}).get("name"),
            hashed_password=hash_password(secrets.token_urlsafe(32)),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return RedirectResponse(f"{front}/login?token={create_access_token(user.id)}")
