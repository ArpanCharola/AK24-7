"""Atomic monthly budget for metered APIs.

The SerpAPI free plan is ~100 searches/month; overspending either fails hard or
silently bills. `try_consume` guarantees the ceiling holds with a single
conditional UPDATE — no read-then-write race, no lock — so concurrent ticks can
never push `used` past `budget`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)


def _period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def try_consume(provider: str, n: int, budget: int) -> bool:
    """Reserve `n` credits for this month, returning False (spending nothing) if
    that would exceed `budget`. Idempotently seeds the month's row on first use.

    The INSERT ... ON CONFLICT seeds `used=0, budget=:budget`; the UPDATE then
    only bumps `used` when it still fits. Both run in one statement each inside
    one transaction, so the check and the increment can't interleave.
    """
    if n <= 0:
        return True
    period = _period()
    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO api_credit_ledger (provider, period_ym, used, budget, updated_at)
                VALUES (:p, :ym, 0, :budget, now())
                ON CONFLICT (provider, period_ym) DO NOTHING
                """
            ),
            {"p": provider, "ym": period, "budget": budget},
        )
        row = (await session.execute(
            text(
                """
                UPDATE api_credit_ledger
                   SET used = used + :n, updated_at = now()
                 WHERE provider = :p AND period_ym = :ym AND used + :n <= :budget
             RETURNING used
                """
            ),
            {"p": provider, "ym": period, "n": n, "budget": budget},
        )).first()
        await session.commit()

    if row is None:
        logger.info("credit budget exhausted: %s %s (budget=%s)", provider, period, budget)
        return False
    return True


async def remaining(provider: str, budget: int) -> int:
    period = _period()
    async with AsyncSessionLocal() as session:
        used = (await session.execute(
            text("SELECT used FROM api_credit_ledger WHERE provider=:p AND period_ym=:ym"),
            {"p": provider, "ym": period},
        )).scalar()
    return max(0, budget - int(used or 0))
