"""Live pipeline progress events for the apply flow.

The browser/API agents stream `log`/`screenshot`/`require_otp` to the Redis
channel `agent:{application_id}`, which the WebSocket route forwards to the
frontend. But the *prep* phase of `_run_application` (resume tailoring, PDF
render, cover-letter drafting) runs before any agent exists and previously
emitted nothing — the user saw a blank "running" state for 15-25s.

`publish_step` lets the Celery task emit structured step events to that same
channel. It also persists the latest event under `agent_state:{id}` so a
WebSocket client that connects mid-run (Redis pub/sub has no history) can be
replayed the current state on connect.

Everything here is best-effort: if Redis is unavailable, the apply must still
proceed, so failures are swallowed.
"""
import json
import logging

logger = logging.getLogger(__name__)

# Latest-state snapshot TTL. Long enough to cover a slow apply + a late
# reconnect, short enough that stale keys self-clean.
_STATE_TTL = 3600  # seconds

# Valid step / state values — documented here as the message contract.
STEPS = ("tailoring", "pdf", "cover_letter", "submitting")
STATES = ("start", "done", "error")


def channel(application_id: int) -> str:
    return f"agent:{application_id}"


def state_key(application_id: int) -> str:
    return f"agent_state:{application_id}"


async def publish_step(
    application_id: int, step: str, state: str, message: str = ""
) -> None:
    """Publish a `step` event to the agent channel and persist it as the
    latest snapshot. Best-effort — never raises.

    Message shape (matches the agent log/screenshot/require_otp contract):
        {"type": "step", "step": <step>, "state": <state>, "message": <str>}
    """
    import redis.asyncio as aioredis
    from app.config import settings

    payload = json.dumps(
        {"type": "step", "step": step, "state": state, "message": message}
    )
    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await r.publish(channel(application_id), payload)
        await r.set(state_key(application_id), payload, ex=_STATE_TTL)
    except Exception as exc:  # pragma: no cover - progress is non-critical
        logger.debug("publish_step failed (ignored): %s", exc)
    finally:
        try:
            await r.aclose()
        except Exception:
            pass
