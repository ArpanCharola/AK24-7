from celery import Celery
from celery.schedules import crontab
from app.config import settings

celery_app = Celery(
    "ai_apply",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

# Explicit import so all tasks register regardless of how -A is specified
import app.workers.tasks  # noqa: E402, F401

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # ── Hardening ────────────────────────────────────────────────────────────
    # Soft kill at 10 min: task gets SoftTimeLimitExceeded — code can catch it
    # and clean up (close Playwright pages, commit partial progress).
    # Hard kill at 12 min: worker forcibly terminates the task. Together they
    # ensure no apply attempt / discovery run hangs the worker indefinitely.
    task_soft_time_limit=10 * 60,
    task_time_limit=12 * 60,
    # Drop result rows after a day. We don't poll Celery for results in code
    # (status comes via WebSocket / DB), so keeping forever just bloats Redis.
    result_expires=24 * 3600,
    # Reject tasks from a worker we lost contact with (rather than letting
    # them complete twice).
    task_reject_on_worker_lost=True,
    # Cap broker memory growth — Redis evicts the oldest under maxmemory anyway.
    broker_transport_options={"visibility_timeout": 15 * 60},
    beat_schedule={
        # APScheduler in the single web process owns warehouse cadence. The
        # Celery aggregation tasks remain callable for operations, but Beat
        # must not create duplicate source traffic.
        # Discovery is user-triggered only (Job Preferences → Run profile).
        # The scheduled task remains registered so it can be invoked manually
        # via `celery call scheduled_discovery` if needed.

        # Scan connected users' Gmail hourly to confirm submissions + advance lifecycle
        "scan-email-confirmations-hourly": {
            "task": "scan_email_confirmations",
            "schedule": crontab(minute=30, hour="*"),
        },
        # Autonomous follow-ups — once daily (opt-in, capped, in-thread only)
        "auto-followups-daily": {
            "task": "auto_followups",
            "schedule": crontab(minute=0, hour=13),  # 13:00 UTC
        },
        # Job-pool TTL — drop rows we haven't re-seen for 24h. Pool is meant
        # as a short-lived shared cache, not a permanent index.
    },
)
