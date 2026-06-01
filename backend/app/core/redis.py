import asyncio
import redis.asyncio as aioredis
from app.config import settings

_redis: aioredis.Redis | None = None
_redis_loop: asyncio.AbstractEventLoop | None = None


async def get_redis() -> aioredis.Redis:
    global _redis, _redis_loop
    loop = asyncio.get_running_loop()
    # A redis.asyncio client is bound to the event loop it was created on. The
    # API runs one persistent loop (client is reused/pooled), but each Celery
    # task runs a fresh asyncio.run() loop — reusing the cached client there
    # raises "attached to a different loop". Recreate when the loop changes; the
    # stale client on a now-closed loop is dropped for GC.
    if _redis is None or _redis_loop is not loop:
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        _redis_loop = loop
    return _redis


async def close_redis():
    global _redis, _redis_loop
    if _redis:
        await _redis.aclose()
        _redis = None
        _redis_loop = None
