"""Small, testable source-adapter registry and fault-isolated orchestration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping, Protocol


@dataclass(frozen=True, slots=True)
class SourceRequest:
    queries: tuple[str, ...]
    locations: tuple[str, ...] = ()
    posted_since: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class SourceAdapter(Protocol):
    name: str

    async def fetch(self, request: SourceRequest) -> list[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class FunctionSourceAdapter:
    name: str
    function: Callable[[SourceRequest], Awaitable[list[dict[str, Any]]]]

    async def fetch(self, request: SourceRequest) -> list[dict[str, Any]]:
        jobs = await self.function(request)
        return [{**job, "source": job.get("source") or self.name} for job in jobs]


class SourceRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, SourceAdapter] = {}

    def register(self, adapter: SourceAdapter) -> None:
        name = adapter.name.strip().casefold()
        if not name:
            raise ValueError("source adapter name is required")
        if name in self._adapters:
            raise ValueError(f"source adapter already registered: {name}")
        self._adapters[name] = adapter

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    async def fetch_all(
        self, request: SourceRequest, *, enabled: set[str] | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, str]]:
        selected = [
            adapter for name, adapter in self._adapters.items()
            if enabled is None or name in {item.casefold() for item in enabled}
        ]
        outcomes = await asyncio.gather(
            *(adapter.fetch(request) for adapter in selected), return_exceptions=True
        )
        jobs: list[dict[str, Any]] = []
        errors: dict[str, str] = {}
        for adapter, outcome in zip(selected, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                errors[adapter.name] = f"{type(outcome).__name__}: {outcome}"
            else:
                jobs.extend(outcome)
        return jobs, errors
