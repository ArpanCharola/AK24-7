import asyncio
import json
import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from jose import JWTError, jwt
from sqlalchemy import select

from app.config import settings
from app.core.auth import ALGORITHM
from app.core.database import AsyncSessionLocal
from app.models.job_application import JobApplication

ws_router = APIRouter()


async def _authorize(token: str | None, job_id: int) -> bool:
    """Validate the JWT and confirm the caller owns this application.

    Browsers can't set Authorization headers on a WebSocket, so the token
    arrives as a `?token=` query param. Returns True only when the token is
    valid and a JobApplication with this id belongs to the token's user —
    otherwise the socket must be rejected (prevents reading another user's
    live agent stream).
    """
    if not token:
        return False
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return False
        user_id = int(user_id)
    except (JWTError, ValueError):
        return False

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(JobApplication.id).where(
                JobApplication.id == job_id,
                JobApplication.user_id == user_id,
            )
        )
        return result.scalar_one_or_none() is not None


@ws_router.websocket("/agent/{job_id}")
async def agent_ws(websocket: WebSocket, job_id: int):
    if not await _authorize(websocket.query_params.get("token"), job_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()

    # Dedicated Redis connection for this pubsub subscription
    pubsub_redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = pubsub_redis.pubsub()
    # Subscribe BEFORE reading the snapshot so any step published in between is
    # buffered by the subscription (delivered in the loop) — no event lost.
    await pubsub.subscribe(f"agent:{job_id}")

    # Connect-race fix: Redis pub/sub has no history, and the client usually
    # connects after the prep pipeline has already emitted step events. Replay
    # the latest persisted pipeline state so a mid-run reconnect sees progress.
    try:
        snapshot = await pubsub_redis.get(f"agent_state:{job_id}")
        if snapshot:
            await websocket.send_text(snapshot)
    except Exception:
        pass

    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    pubsub.get_message(ignore_subscribe_messages=True),
                    timeout=20.0,
                )
                if message and message["type"] == "message":
                    await websocket.send_text(message["data"])
                elif message is None:
                    # No message yet — send ping to keep connection alive
                    await websocket.send_json({"type": "ping"})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await pubsub.unsubscribe(f"agent:{job_id}")
        await pubsub_redis.aclose()
