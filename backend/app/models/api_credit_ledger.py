"""Monthly spend ledger for metered external APIs (SerpAPI free plan ~100/mo).

One row per (provider, month). Consumption goes through
services.credit_budget.try_consume, which does an atomic conditional UPDATE so
the budget can never be exceeded even under concurrent ticks.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ApiCreditLedger(Base):
    __tablename__ = "api_credit_ledger"
    __table_args__ = (
        UniqueConstraint("provider", "period_ym", name="uq_api_credit_provider_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)  # "serpapi"
    period_ym: Mapped[str] = mapped_column(String(7), nullable=False)  # "2026-07"
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    budget: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
