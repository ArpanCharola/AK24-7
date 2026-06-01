"""APScheduler — lightweight in-process cron (replaces Celery Beat for the lean
100-user build). Runs periodic discovery + the daily digest.

Gated behind settings.ENABLE_SCHEDULER (default False) so it stays off until the
discovery/matching streams (A1/A2) land. Job bodies lazily import those modules, so
a not-yet-built entrypoint never breaks app startup — it just logs and skips.
"""
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


async def _run_scheduled_discovery() -> None:
    """Discover + refresh feeds for all active search profiles."""
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.job_search_profile import JobSearchProfile
        from app.agents.job_discovery_agent import discover_for_profile  # A1 provides
        from app.services.matching import refresh_user_feed  # A2 provides
        from sqlalchemy import select

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobSearchProfile).where(JobSearchProfile.is_active.is_(True))
            )
            profiles = result.scalars().all()
        for p in profiles:
            try:
                await discover_for_profile(p.id, p.user_id)
                await refresh_user_feed(p.user_id)
            except Exception as e:  # noqa: BLE001
                logger.error("scheduled discovery failed for profile %s: %s", p.id, repr(e)[:200])
    except ImportError as e:
        logger.info("scheduled discovery skipped (component not built yet): %s", e)
    except Exception as e:  # noqa: BLE001
        logger.error("scheduled discovery error: %s", repr(e)[:200])


async def _run_daily_digest() -> None:
    try:
        from app.services.matching import send_daily_digests  # A2/A4 provide later
        await send_daily_digests()
    except ImportError:
        logger.info("daily digest skipped (not built yet)")
    except Exception as e:  # noqa: BLE001
        logger.error("daily digest error: %s", repr(e)[:200])


def start_scheduler() -> None:
    if not settings.ENABLE_SCHEDULER:
        logger.info("scheduler disabled (ENABLE_SCHEDULER=false)")
        return
    if scheduler.running:
        return
    # Discovery every 6h; digest ~07:30 IST.
    scheduler.add_job(_run_scheduled_discovery, CronTrigger(hour="*/6", minute=0), id="discovery", replace_existing=True)
    scheduler.add_job(_run_daily_digest, CronTrigger(hour=7, minute=30), id="digest", replace_existing=True)
    scheduler.start()
    logger.info("APScheduler started (discovery */6h, digest 07:30 IST)")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
