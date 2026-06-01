"""Job-description extraction from a URL.

Given a job link, recover the posting's text and project it into a structured
job description: ``{job_title, company, location, job_description}``.

Two-stage fetch — fast path first, heavy path only when needed:
  1. ``httpx`` GET with browser-ish headers, HTML stripped to text.
  2. If that yields too little (JS-rendered boards), fall back to a headless
     Playwright Chromium that waits for ``networkidle`` and reads the body text.

Everything here is best-effort and NEVER raises: ``jd_from_url`` always returns
the structured dict (with empty fields on failure) so callers can branch on
``job_description`` being empty rather than guarding exceptions.
"""
import logging
import re

import httpx

from app.services.resume_tailor import _generate, _parse_json

logger = logging.getLogger(__name__)

# Process-wide cache: a job link's text doesn't change within a session, and
# extraction is expensive (network + an LLM call). Keyed by raw URL.
_CACHE: dict[str, dict] = {}
_CACHE_MAX = 256

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}

# Below this many characters the httpx fetch is treated as "thin" (likely a JS
# shell) and we escalate to Playwright.
_MIN_USEFUL_CHARS = 600
# Cap text handed to the LLM — postings rarely need more and it bounds tokens.
_MAX_JD_CHARS = 16000

_SCRIPT_STYLE_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\f\v]+")
_BLANKLINES_RE = re.compile(r"\n\s*\n\s*\n+")


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    text = _SCRIPT_STYLE_RE.sub(" ", html)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", text, flags=re.IGNORECASE)
    text = _TAG_RE.sub(" ", text)
    text = _unescape(text)
    text = _WS_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _BLANKLINES_RE.sub("\n\n", text)
    return text.strip()


def _unescape(text: str) -> str:
    import html as _html
    return _html.unescape(text)


async def _fetch_httpx(url: str) -> str:
    async with httpx.AsyncClient(
        timeout=20.0, follow_redirects=True, headers=_BROWSER_HEADERS
    ) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "html" not in ctype and "text" not in ctype and "xml" not in ctype:
            return ""
        return _html_to_text(resp.text)


async def _fetch_playwright(url: str) -> str:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=_BROWSER_HEADERS["User-Agent"],
                locale="en-IN",
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass  # networkidle can never settle on chatty pages — body is enough
            body = await page.inner_text("body")
            return (body or "").strip()
        finally:
            await browser.close()


async def fetch_url_text(url: str) -> str:
    """Recover the readable text of a job page. httpx first, Playwright fallback.

    Never raises — returns "" if both paths fail.
    """
    url = (url or "").strip()
    if not url:
        return ""
    text = ""
    try:
        text = await _fetch_httpx(url)
    except Exception as exc:
        logger.info("httpx fetch of %s failed (%s) — trying Playwright", url, exc)

    if len(text) >= _MIN_USEFUL_CHARS:
        return text[:_MAX_JD_CHARS]

    try:
        rendered = await _fetch_playwright(url)
        if len(rendered) > len(text):
            text = rendered
    except Exception as exc:
        logger.warning("Playwright fetch of %s failed: %s", url, exc)

    return text[:_MAX_JD_CHARS]


_EXTRACT_SYSTEM = (
    "You extract a job posting from raw page text. Return a SINGLE JSON object with EXACTLY "
    'these keys: "job_title", "company", "location", "job_description". '
    "job_description must be the full role description (responsibilities + requirements), "
    "cleaned of site navigation, cookie banners, footers, and 'related jobs'. "
    "Use null for any field genuinely absent. Do not invent details. "
    "Output only the JSON — no explanation, no markdown fences."
)


def _empty_jd() -> dict:
    return {"job_title": None, "company": None, "location": None, "job_description": None}


async def extract_jd_from_text(text: str) -> dict:
    """LLM-project page text into a structured JD. Never raises."""
    text = (text or "").strip()
    if not text:
        return _empty_jd()
    try:
        raw = await _generate(_EXTRACT_SYSTEM, f"Page text:\n\n{text[:_MAX_JD_CHARS]}", max_tokens=2000)
        parsed = _parse_json(raw)
    except Exception as exc:
        logger.warning("JD extraction LLM call failed: %s", exc)
        return _empty_jd()

    out = _empty_jd()
    if isinstance(parsed, dict):
        for key in out:
            v = parsed.get(key)
            if isinstance(v, str):
                out[key] = v.strip() or None
            elif v is not None:
                out[key] = v
    # Last-resort: if the model gave no description but we have page text, keep
    # the raw text so the caller still has something to tailor against.
    if not out["job_description"]:
        out["job_description"] = text[:_MAX_JD_CHARS] or None
    return out


def _cache_put(url: str, data: dict) -> None:
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)), None)
    _CACHE[url] = data


async def jd_from_url(url: str) -> dict:
    """Fetch + extract a structured JD from a job link. Cached. Never raises.

    Returns ``{job_title, company, location, job_description}``; fields are None
    (and job_description may be empty) when the page could not be read.
    """
    url = (url or "").strip()
    if not url:
        return _empty_jd()
    if url in _CACHE:
        return _CACHE[url]

    try:
        text = await fetch_url_text(url)
        data = await extract_jd_from_text(text)
    except Exception as exc:  # belt-and-suspenders — sub-calls already guard
        logger.warning("jd_from_url(%s) failed: %s", url, exc)
        data = _empty_jd()

    _cache_put(url, data)
    return data
