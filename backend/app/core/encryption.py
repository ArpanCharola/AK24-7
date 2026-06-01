"""Symmetric encryption for secrets stored at rest (Gmail OAuth tokens).

Uses Fernet (AES-128-CBC + HMAC). The key comes from `settings.ENCRYPTION_KEY`
when set; otherwise a stable key is derived from `SECRET_KEY` so encryption works
out of the box in dev without an extra env var. For production, set a dedicated
`ENCRYPTION_KEY` (a urlsafe-base64 32-byte Fernet key) and keep it stable —
rotating it orphans every stored token (users must reconnect).
"""
import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


@lru_cache
def _fernet() -> Fernet:
    key = (settings.ENCRYPTION_KEY or "").strip()
    if key:
        try:
            return Fernet(key)  # already a valid Fernet key
        except (ValueError, TypeError):
            material = key.encode()  # arbitrary passphrase → derive
    else:
        material = settings.SECRET_KEY.encode()
    derived = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(derived)


def encrypt(plaintext: str | None) -> str | None:
    """Encrypt a string for storage. Passes through None/empty unchanged."""
    if not plaintext:
        return plaintext
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str | None) -> str | None:
    """Decrypt a stored string. Returns None if the value can't be decrypted
    (e.g. key rotated or value corrupted) so callers can treat it as missing."""
    if not token:
        return token
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None
