import asyncio
import base64
import json
from abc import ABC, abstractmethod
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from app.config import settings


class BasePortalAgent(ABC):
    def __init__(self, application_id: int, user_id: int):
        self.application_id = application_id
        self.user_id = user_id
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._redis = None
        # Set to True when the agent has confirmed the ATS accepted the submission.
        # Distinguishes real success from "form filled but never submitted".
        self._submitted: bool = False
        # Short machine-readable reason the run stopped without confirming a
        # submission (e.g. "login_or_account_wall", "no_submit_button",
        # "stuck_no_progress", "max_steps_reached"). Surfaced for per-portal
        # failure telemetry. None while still running / on success.
        self._stop_reason: str | None = None

    async def _launch(self, headless: bool = True):
        import redis.asyncio as aioredis
        # Fresh Redis connection per agent instance — avoids closed event loop issues
        self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

        self._playwright = await async_playwright().start()
        proxy_config = None
        if settings.PROXY_URL:
            proxy_config = {
                "server": settings.PROXY_URL,
                "username": settings.PROXY_USERNAME,
                "password": settings.PROXY_PASSWORD,
            }

        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            proxy=proxy_config,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            user_agent=self._random_user_agent(),
            viewport={"width": 1280, "height": 800},
        )
        self._page = await self._context.new_page()
        await self._stealth_patch()

    async def _stealth_patch(self):
        await self._page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        """)

    def _random_user_agent(self) -> str:
        import random
        agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        ]
        return random.choice(agents)

    async def _publish(self, payload: dict):
        if self._redis:
            await self._redis.publish(f"agent:{self.application_id}", json.dumps(payload))

    async def _log(self, message: str):
        await self._publish({"type": "log", "message": message})

    async def _send_screenshot(self, label: str = ""):
        if self._page:
            screenshot = await self._page.screenshot(type="jpeg", quality=60)
            await self._publish({
                "type": "screenshot",
                "data": base64.b64encode(screenshot).decode(),
                "caption": label,
            })

    async def _set_db_status(self, status) -> None:
        """Update application status in DB without disrupting the main task session."""
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.models.job_application import JobApplication
        from app.config import settings
        from sqlalchemy import select

        engine = create_async_engine(settings.DATABASE_URL)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with Session() as db:
                result = await db.execute(
                    select(JobApplication).where(JobApplication.id == self.application_id)
                )
                app = result.scalar_one_or_none()
                if app:
                    app.status = status
                    await db.commit()
        finally:
            await engine.dispose()

    async def _wait_for_otp(self, timeout: int = 300) -> str:
        from app.models.job_application import ApplicationStatus
        key = f"otp:{self.user_id}:{self.application_id}"
        await self._publish({"type": "require_otp", "job_id": self.application_id})
        await self._set_db_status(ApplicationStatus.AWAITING_OTP)
        for _ in range(timeout):
            otp = await self._redis.get(key)
            if otp:
                await self._redis.delete(key)
                return otp
            await asyncio.sleep(1)
        raise TimeoutError("OTP not received within timeout")

    @staticmethod
    def _extract_code(text: str) -> str | None:
        """Pull a likely email verification code from text. Prefers a standalone
        6-digit code (the ATS norm), then any 4-8 digit run. Ignores years and
        long numbers so we don't fill garbage."""
        import re
        if not text:
            return None
        # Prefer 6-digit codes
        m = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        if m:
            return m.group(1)
        for cand in re.findall(r"(?<!\d)(\d{4,8})(?!\d)", text):
            # Skip obvious 4-digit years (19xx/20xx) to reduce false matches
            if len(cand) == 4 and (cand.startswith("19") or cand.startswith("20")):
                continue
            return cand
        return None

    async def _read_email_verification_code(self, timeout: int = 90) -> str | None:
        """Poll the user's connected Gmail for a recent email-verification code
        (e.g. Workday account verification). Returns the code or None.

        Best-effort and non-breaking: returns None if Gmail isn't connected, the
        token can't be refreshed, or no code email arrives within `timeout`s.
        Precondition: the code is delivered to the connected Gmail mailbox (i.e.
        the portal account email is that Gmail address)."""
        from app.core.database import AsyncSessionLocal
        from app.models.user import User
        from app.services import gmail_client, gmail_service
        from sqlalchemy import select

        query = (
            "newer_than:1h ("
            "subject:(verify OR verification OR confirm OR code OR activate) "
            'OR "verification code" OR "confirm your email" OR "one-time")'
        )
        for _ in range(max(1, timeout // 5)):
            try:
                async with AsyncSessionLocal() as db:
                    user = (
                        await db.execute(select(User).where(User.id == self.user_id))
                    ).scalar_one_or_none()
                    if not user:
                        return None
                    token = await gmail_client.get_valid_access_token(db, user)
                if not token:
                    await self._log("Email verification: no connected Gmail — cannot auto-read code")
                    return None
                msgs = await gmail_service.fetch_messages_by_query(token, query, max_results=5)
                for m in msgs:
                    code = self._extract_code(f"{m.get('subject','')} {m.get('snippet','')}")
                    if not code and m.get("id"):
                        full = await gmail_service.fetch_message_full(token, m["id"])
                        code = self._extract_code(
                            f"{full.get('subject','')} {full.get('body_text','')}"
                        )
                    if code:
                        await self._log(f"Email verification: read code {code[0]}{'*' * (len(code) - 1)}")
                        return code
            except Exception as exc:
                await self._log(f"Email verification read error: {exc}")
            await asyncio.sleep(5)
        await self._log("Email verification: no code email found within timeout")
        return None

    async def close(self):
        # Idempotent: a hand-off agent (UniversalAgent) may share these resources
        # and close them too, so guard each step and null it out after closing.
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None

    # ── Shared filling helpers (used by all portal agents) ────────────────

    async def _fill_first_match(self, selectors: list[str], value: str):
        """Fill the first visible input that matches any selector."""
        if not value:
            return
        for sel in selectors:
            try:
                loc = self._page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.fill(value)
                    return
            except Exception:
                continue

    async def _click_first_visible(self, selectors: list[str]) -> bool:
        """Click the first visible element. Returns True if clicked."""
        for sel in selectors:
            try:
                loc = self._page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await self._page.wait_for_load_state("networkidle", timeout=20_000)
                    await self._page.wait_for_timeout(2000)
                    await self._send_screenshot()
                    return True
            except Exception:
                continue
        return False

    async def _upload_resume(self, selectors: list[str]):
        """Upload the resume file (PDF if available, else plaintext) to the first file input found."""
        import os, tempfile
        pdf_bytes = self._profile.get("resume_pdf_bytes")
        if pdf_bytes:
            suffix, mode, data = ".pdf", "wb", pdf_bytes
        else:
            resume_text = (self._profile.get("tailored_resume_text") or
                           self._profile.get("resume_text") or "")
            if not resume_text:
                await self._log("No resume to upload")
                return
            suffix, mode, data = ".txt", "w", resume_text

        kwargs = {"suffix": suffix, "delete": False}
        if mode == "w":
            kwargs["mode"] = "w"
            kwargs["encoding"] = "utf-8"
        else:
            kwargs["mode"] = "wb"
        tmp = tempfile.NamedTemporaryFile(**kwargs)
        try:
            tmp.write(data)
            tmp.close()
            for sel in selectors:
                try:
                    loc = self._page.locator(sel).first
                    if await loc.count() > 0:
                        await loc.set_input_files(tmp.name)
                        await self._log(f"Resume uploaded ({suffix[1:].upper()})")
                        return
                except Exception:
                    continue
            await self._log("Resume file input not found")
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    async def _answer_visible_textareas(self):
        """Fill visible textareas. Cover-letter textareas use the pre-generated cover letter;
        other open-ended questions get a custom LLM-drafted answer.

        Three phases: (1) classify each textarea and fill cover-letter ones inline
        (no LLM), collecting the rest; (2) draft all custom answers concurrently;
        (3) fill them. Phase 2 was previously one sequential LLM call per textarea."""
        import asyncio
        career_history = self._profile.get("career_history", "") or ""
        cover_letter_text = (self._profile.get("cover_letter_text") or "").strip()
        textareas = await self._page.locator("textarea:visible").all()
        if not textareas:
            return
        if not career_history and not cover_letter_text:
            return

        # ── Phase 1: classify (Playwright reads only) ─────────────────────────
        pending: list[tuple] = []  # (textarea, label) needing an LLM answer
        for i, ta in enumerate(textareas):
            try:
                if (await ta.input_value()).strip():
                    continue
                label = (await ta.get_attribute("aria-label") or
                         await ta.get_attribute("placeholder") or
                         await ta.get_attribute("name") or
                         f"Question {i + 1}")
                label_lower = label.lower()
                is_cover = "cover letter" in label_lower or "cover-letter" in label_lower or (
                    "cover" in label_lower and ("why" in label_lower or "motivation" in label_lower or "letter" in label_lower)
                )
                if is_cover and cover_letter_text:
                    await ta.fill(cover_letter_text)
                    await self._log(f"  Cover letter filled into: {label[:60]}")
                    continue
                if not career_history:
                    continue
                pending.append((ta, label))
            except Exception as exc:
                await self._log(f"  textarea {i} classify error: {exc}")

        if not pending:
            return

        # ── Phase 2: draft all answers concurrently ───────────────────────────
        await self._log(f"Drafting answers for {len(pending)} textarea(s)")
        from app.services.resume_tailor import ResumeTailor
        tailor = ResumeTailor()
        answers = await asyncio.gather(
            *(tailor.draft_custom_answer(label, career_history) for _, label in pending),
            return_exceptions=True,
        )

        # ── Phase 3: fill ─────────────────────────────────────────────────────
        for (ta, label), answer in zip(pending, answers):
            if isinstance(answer, Exception):
                await self._log(f"  answer failed for {label[:60]}: {answer}")
                continue
            if not answer:
                continue
            try:
                await ta.fill(answer)
                await self._log(f"  Answered: {label[:60]}")
            except Exception as exc:
                await self._log(f"  textarea fill error for {label[:60]}: {exc}")

    @abstractmethod
    async def run(self, job_url: str): ...
