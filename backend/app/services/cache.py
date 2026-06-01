"""AI verdict cache — keeps the same mail from being judged twice.

Three per-message caches keyed by the stable Gmail message id:
  - label AI double-check       (labelai:<msg_id>, 7d TTL)
  - application AI double-check (appai:<msg_id>, 7d)
  - application company/role    (appextract:<msg_id>, 30d)

Plus a short-lived per-request cache for the daily application tracker
(tracker:<user>:<days>, 60s) that stabilises the count across mashed-refresh
clicks. Redis outages degrade silently to 'no cache' — never raise.

Stores only verdicts/counters — never email content.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.core.redis import get_redis

logger = logging.getLogger(__name__)


_LABEL_AI_TTL = 7 * 24 * 3600
_APPLICATION_AI_TTL = 7 * 24 * 3600
_APP_EXTRACT_TTL = 30 * 24 * 3600
_TRACKER_TTL = 60


async def _safe_get(key: str) -> Optional[str]:
    try:
        r = await get_redis()
        return await r.get(key)
    except Exception as exc:
        logger.debug("[cache] get(%s) failed: %s", key, exc)
        return None


async def _safe_setex(key: str, ttl: int, value: str) -> None:
    try:
        r = await get_redis()
        await r.setex(key, ttl, value)
    except Exception as exc:
        logger.debug("[cache] setex(%s) failed: %s", key, exc)


def _loads(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


# ── Label AI double-check ────────────────────────────────────────────────────

def _label_ai_key(msg_id: str) -> str:
    return f"labelai:{msg_id}"


async def get_label_ai_cache(msg_id: str) -> Optional[dict]:
    return _loads(await _safe_get(_label_ai_key(msg_id)))


async def set_label_ai_cache(msg_id: str, verdict: dict, ttl: int = _LABEL_AI_TTL) -> None:
    await _safe_setex(_label_ai_key(msg_id), ttl, json.dumps(verdict))


# ── Application AI double-check ──────────────────────────────────────────────

def _application_ai_key(msg_id: str) -> str:
    return f"appai:{msg_id}"


async def get_application_ai_cache(msg_id: str) -> Optional[dict]:
    return _loads(await _safe_get(_application_ai_key(msg_id)))


async def set_application_ai_cache(msg_id: str, verdict: dict, ttl: int = _APPLICATION_AI_TTL) -> None:
    await _safe_setex(_application_ai_key(msg_id), ttl, json.dumps(verdict))


# ── App company/role extraction ──────────────────────────────────────────────

def _app_extract_key(msg_id: str) -> str:
    return f"appextract:{msg_id}"


async def get_app_extract_cache(msg_id: str) -> Optional[dict]:
    return _loads(await _safe_get(_app_extract_key(msg_id)))


async def set_app_extract_cache(msg_id: str, data: dict, ttl: int = _APP_EXTRACT_TTL) -> None:
    await _safe_setex(_app_extract_key(msg_id), ttl, json.dumps(data))


# ── Application tracker per-request cache ────────────────────────────────────

def _tracker_key(user_id: int, days: int) -> str:
    return f"tracker:{user_id}:{days}"


async def get_tracker_cache(user_id: int, days: int) -> Optional[dict]:
    return _loads(await _safe_get(_tracker_key(user_id, days)))


async def set_tracker_cache(user_id: int, days: int, data: dict, ttl: int = _TRACKER_TTL) -> None:
    await _safe_setex(_tracker_key(user_id, days), ttl, json.dumps(data))
