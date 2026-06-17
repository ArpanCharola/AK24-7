"""Stealth browser fetch for JS-heavy / anti-bot boards (Wellfound, and a
fallback path for Glassdoor/LinkedIn).

Reuses the Playwright stack already vendored for the apply agents (see
base_portal_agent.py) with the same stealthy launch args + ``navigator.webdriver``
mask. Camoufox would be a stronger anti-detect engine, but it is an extra
dependency; Playwright + manual stealth is free and already installed. Every
entry point degrades to ``None`` on any failure so callers fall back to ``[]``
and never break the discovery run.

Gated by ``settings.STEALTH_ENABLED`` — when off, the helpers return ``None`` and
browser-dependent sources simply yield no jobs.
"""

import logging
from urllib.parse import urlsplit

from app.config import settings

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_WEBDRIVER_MASK = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


def _proxy_config(proxy: str | None) -> dict | None:
    """Turn a ``http://user:pass@host:port`` string into Playwright's proxy dict."""
    if not proxy:
        return None
    parts = urlsplit(proxy if "://" in proxy else f"http://{proxy}")
    server = f"{parts.scheme}://{parts.hostname}"
    if parts.port:
        server += f":{parts.port}"
    cfg: dict = {"server": server}
    if parts.username:
        cfg["username"] = parts.username
    if parts.password:
        cfg["password"] = parts.password
    return cfg


async def fetch_rendered(
    url: str,
    *,
    proxy: str | None = None,
    wait_selector: str | None = None,
    wait_until: str = "networkidle",
    timeout_ms: int = 30000,
) -> str | None:
    """Load ``url`` in a stealth browser and return the fully-rendered HTML.

    Returns ``None`` if stealth is disabled, Playwright is unavailable, or the
    page errors/blocks — the caller treats ``None`` as "no jobs from this source".
    """
    if not settings.STEALTH_ENABLED:
        return None

    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001 — playwright may be absent in some envs
        logger.warning("stealth_fetch: playwright unavailable (%s)", exc)
        return None

    pw = browser = None
    try:
        pw = await async_playwright().start()
        browser = await pw.chromium.launch(
            headless=True,
            proxy=_proxy_config(proxy),
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=_USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-IN",
        )
        await context.add_init_script(_WEBDRIVER_MASK)
        page = await context.new_page()
        await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        if wait_selector:
            try:
                await page.wait_for_selector(wait_selector, timeout=timeout_ms)
            except Exception:  # noqa: BLE001 — selector may never appear if blocked
                logger.info("stealth_fetch: selector %r not found on %s", wait_selector, url)
        return await page.content()
    except Exception as exc:  # noqa: BLE001 — any nav/block failure → None
        logger.warning("stealth_fetch failed for %s: %s", url, exc)
        return None
    finally:
        if browser:
            await browser.close()
        if pw:
            await pw.stop()