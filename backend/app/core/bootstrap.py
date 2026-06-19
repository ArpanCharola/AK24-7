"""Idempotent startup bootstrap — guarantees the admin account always exists.

Runs on every app start (see app/main.py lifespan). It never deletes anything;
the one-time wipe of pre-existing users lives in scripts/reset_and_seed.py.

Admin credentials default to the values requested for this deployment but can be
overridden with env vars ADMIN_EMAIL / ADMIN_USERNAME / ADMIN_PASSWORD.
"""
import logging
import os

from sqlalchemy import select

from app.core.auth import hash_password
from app.core.database import AsyncSessionLocal
from app.models.user import User

logger = logging.getLogger(__name__)

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "arpancharola11@gmail.com")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "arpancharola11")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Code@1234")


async def ensure_admin() -> None:
    """Create the admin if missing; otherwise make sure the flag + login
    credentials are in place. Does not clobber an already-configured admin."""
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        ).scalar_one_or_none()

        if user is None:
            user = User(
                email=ADMIN_EMAIL,
                username=ADMIN_USERNAME,
                full_name="Admin",
                hashed_password=hash_password(ADMIN_PASSWORD),
                raw_password=ADMIN_PASSWORD,
                is_admin=True,
                credentials_set=True,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            logger.info("Admin account created: %s", ADMIN_EMAIL)
            return

        changed = False
        if not user.is_admin:
            user.is_admin = True
            changed = True
        # Make sure the admin can always log in with a password.
        if not user.credentials_set or not user.hashed_password:
            user.username = user.username or ADMIN_USERNAME
            user.hashed_password = hash_password(ADMIN_PASSWORD)
            user.raw_password = ADMIN_PASSWORD
            user.credentials_set = True
            changed = True
        if changed:
            await db.commit()
            logger.info("Admin account ensured: %s", ADMIN_EMAIL)