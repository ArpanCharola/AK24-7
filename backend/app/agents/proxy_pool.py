"""Tier-3 shared infra: proxy rotation + per-source circuit breaker.

Both are intentionally tiny and dependency-free.

* ``ProxyPool`` is the single seam every Tier-3 fetch acquires a proxy through,
  so residential proxies (or, later, a managed scraping API) can be plugged in
  via ``settings.SCRAPE_PROXIES`` with zero changes to any adapter.
* ``CircuitBreaker`` stops a board that is actively blocking us (Cloudflare 403s,
  rate-limit 429s) from wasting the rest of a discovery run, and lets it recover
  on its own after a cooldown.

State is in-memory and process-local. The scheduler runs in-process (APScheduler),
so a tripped breaker survives across discovery runs in the same worker and resets
on restart — acceptable for free-first. A Redis-backed variant would survive
restarts and be shared across workers; left as a future upgrade.
"""

import logging
import threading
import time
from itertools import cycle

from app.config import settings

logger = logging.getLogger(__name__)


class ProxyPool:
    """Round-robins live proxies; benches a proxy briefly after it fails.

    ``get()`` returns ``None`` when no proxies are configured (direct
    connection) or when every proxy is currently benched.
    """

    def __init__(self, proxies: list[str] | None = None, revive_after: int = 600):
        self._all = [p.strip() for p in (proxies or []) if p and p.strip()]
        self._dead: dict[str, float] = {}        # proxy -> monotonic time it may return
        self._cycle = cycle(self._all) if self._all else None
        self._revive_after = revive_after
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return bool(self._all)

    def get(self) -> str | None:
        if not self._cycle:
            return None
        with self._lock:
            now = time.monotonic()
            for _ in range(len(self._all)):
                proxy = next(self._cycle)
                revive_at = self._dead.get(proxy)
                if revive_at and now < revive_at:
                    continue
                self._dead.pop(proxy, None)
                return proxy
            return None  # all benched → fall back to direct

    def mark_dead(self, proxy: str | None) -> None:
        if not proxy:
            return
        with self._lock:
            self._dead[proxy] = time.monotonic() + self._revive_after

    def as_list(self) -> list[str] | None:
        """Live (non-benched) proxies, for libraries that rotate internally
        (e.g. jobspy). Returns ``None`` for a direct connection."""
        if not self._all:
            return None
        with self._lock:
            now = time.monotonic()
            live = [p for p in self._all if now >= self._dead.get(p, 0)]
        return live or None


class CircuitBreaker:
    """Per-source consecutive-failure breaker.

    A key (e.g. ``"linkedin"``) trips OPEN after ``threshold`` consecutive
    failures and is skipped until ``cooldown`` seconds elapse; the first call
    after that is a HALF-OPEN trial. ``record_success`` resets the key;
    ``record_failure`` increments it and re-opens the circuit when the policy
    in ``_trip_after`` says so.
    """

    def __init__(self, threshold: int, cooldown: int):
        self._threshold = max(1, threshold)
        self._cooldown = max(1, cooldown)
        self._fails: dict[str, int] = {}
        self._open_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        with self._lock:
            until = self._open_until.get(key)
            if until is None:
                return True
            if time.monotonic() >= until:
                del self._open_until[key]   # cooldown elapsed → one half-open trial
                return True
            return False

    def record_success(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
            self._open_until.pop(key, None)

    def record_failure(self, key: str) -> None:
        with self._lock:
            n = self._fails.get(key, 0) + 1
            self._fails[key] = n
            if self._trip_after(key, n):
                self._open_until[key] = time.monotonic() + self._cooldown
                logger.warning(
                    "Circuit OPEN for %r after %d consecutive fails — cooling down %ds",
                    key, n, self._cooldown,
                )

    def _trip_after(self, key: str, consecutive_fails: int) -> bool:
        """Policy hook: should the circuit OPEN given this many consecutive fails?

        Default policy is a flat threshold. This is the one knob that meaningfully
        shapes Tier-3 behaviour, so it is isolated here for you to tune — see the
        note in the chat for the trade-offs (flat vs. escalating cooldown, or
        treating a hard 403/ban differently from a soft 429 rate-limit).
        """
        return consecutive_fails >= self._threshold


# Module-level singletons — shared across all Tier-3 adapters in this process.
proxy_pool = ProxyPool(
    [p for p in (settings.SCRAPE_PROXIES or "").split(",")]
)
circuit = CircuitBreaker(
    threshold=settings.SCRAPE_CIRCUIT_THRESHOLD,
    cooldown=settings.SCRAPE_CIRCUIT_COOLDOWN,
)