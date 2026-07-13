"""APScheduler — lightweight in-process cron (replaces Celery Beat for the lean
100-user build). Runs periodic discovery + the daily digest.

Gated behind settings.ENABLE_SCHEDULER so replica processes can opt out. The
scheduler-owning API process runs shared warehouse aggregation, while job bodies
still lazily import optional modules so startup remains resilient.
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


async def _run_pool_warm() -> None:
    """Generalized, role-agnostic refresh of the shared JobPool (freshness engine)."""
    try:
        from app.agents.job_discovery_agent import warm_job_pool
        await warm_job_pool(posted_within_days=7)
    except Exception as e:  # noqa: BLE001
        logger.error("pool warm error: %s", repr(e)[:200])


async def _run_shared_aggregation() -> None:
    """Run the warehouse once for all active demand clusters, never per user."""
    try:
        from app.services.aggregation import run_aggregation
        await run_aggregation(trigger="scheduled")
    except Exception as e:  # noqa: BLE001
        logger.error("shared aggregation error: %s", repr(e)[:200])


async def _run_entry_level_supply() -> None:
    """Refresh broad fresher/entry-level India tech jobs into JobPool."""
    try:
        from app.services.entry_level_supply import backfill_entry_level_supply
        await backfill_entry_level_supply(posted_within_days=7, use_stealth=False)
    except Exception as e:  # noqa: BLE001
        logger.error("entry-level supply error: %s", repr(e)[:200])


async def _cleanup_warehouse() -> None:
    try:
        from app.services.aggregation import cleanup_warehouse
        await cleanup_warehouse()
    except Exception as e:  # noqa: BLE001
        logger.error("warehouse cleanup error: %s", repr(e)[:200])


async def _run_slug_revalidation() -> None:
    """Re-probe registry slugs; refresh india_roles_count, prune dead with hysteresis."""
    try:
        from app.scripts.slug_discovery import revalidate_registry
        await revalidate_registry()
    except ImportError:
        logger.info("slug revalidation skipped (not built yet)")
    except Exception as e:  # noqa: BLE001
        logger.error("slug revalidation error: %s", repr(e)[:200])


def start_scheduler() -> None:
    if not settings.ENABLE_SCHEDULER:
        logger.info("scheduler disabled (ENABLE_SCHEDULER=false)")
        return
    if scheduler.running:
        return
    # The web deployment is intentionally a single worker. Keep one shared
    # warehouse refresh at 00:37 and 12:37 IST, rather than fanning out a
    # scrape for each profile. ``run_aggregation`` also guards an active run.
    scheduler.add_job(_run_entry_level_supply, CronTrigger(hour="2,14", minute=17), id="entry_level_supply", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(_run_shared_aggregation, CronTrigger(hour="0,12", minute=37), id="warehouse_aggregation", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(_cleanup_warehouse, CronTrigger(hour=1, minute=47), id="warehouse_cleanup", replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(_run_slug_revalidation, CronTrigger(hour=3, minute=0), id="slug_revalidate", replace_existing=True)
    scheduler.add_job(_run_daily_digest, CronTrigger(hour=7, minute=30), id="digest", replace_existing=True)
    scheduler.start()
    logger.info("APScheduler started (ancillary revalidation + digest only)")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
