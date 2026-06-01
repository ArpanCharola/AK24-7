import asyncio
from app.agents.base_portal_agent import BasePortalAgent


class WorkdayAgent(BasePortalAgent):
    async def run(self, job_url: str, user_profile: dict | None = None):
        self._profile = user_profile or {}
        await self._launch(headless=True)
        try:
            await self._log(f"Navigating to {job_url}")
            await self._page.goto(job_url, wait_until="networkidle", timeout=60_000)
            await self._page.wait_for_timeout(3000)
            await self._log(f"Page loaded: {self._page.url}")
            await self._send_screenshot()

            await self._click_apply_button()
            await self._handle_auth()
            await self._navigate_application_steps()
        finally:
            await self.close()

    # ------------------------------------------------------------------
    # Apply button
    # ------------------------------------------------------------------

    async def _click_apply_button(self):
        page = self._page
        await self._log("Looking for Apply button")

        selectors = [
            "[data-automation-id='applyButton']",
            "[data-automation-id='apply-button']",
            "a[href*='apply']",
            "button:has-text('Apply Now')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply for Job')",
            "a:has-text('Apply for Job')",
            "button:has-text('Apply')",
            "a:has-text('Apply')",
        ]

        # Try with explicit wait first for the most common selector
        try:
            await page.wait_for_selector(
                "[data-automation-id='applyButton']",
                timeout=8000,
                state="visible",
            )
            await page.locator("[data-automation-id='applyButton']").first.click()
            await self._log("Clicked apply button (data-automation-id)")
            await page.wait_for_load_state("networkidle", timeout=30_000)
            await page.wait_for_timeout(2000)
            await self._send_screenshot()
            return
        except Exception:
            pass

        for sel in selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await self._log(f"Clicked apply button ({sel})")
                    await page.wait_for_load_state("networkidle", timeout=30_000)
                    await page.wait_for_timeout(2000)
                    await self._send_screenshot()
                    return
            except Exception:
                continue

        await self._log(f"Apply button not found — current URL: {page.url}")
        await self._send_screenshot()

    # ------------------------------------------------------------------
    # Auth: create account or sign in
    # ------------------------------------------------------------------

    async def _handle_auth(self):
        page = self._page
        await self._log(f"Checking for auth prompt — URL: {page.url}")
        await page.wait_for_timeout(2000)
        await self._send_screenshot()

        create_selectors = [
            "[data-automation-id='createAccountLink']",
            "a:has-text('Create Account')",
            "button:has-text('Create Account')",
            "a:has-text('Create an Account')",
        ]
        signin_selectors = [
            "[data-automation-id='signInLink']",
            "[data-automation-id='signIn']",
            "a:has-text('Sign In')",
            "button:has-text('Sign In')",
            "a:has-text('Already have an account')",
        ]

        for sel in create_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await self._log("Found 'Create Account' prompt")
                    await loc.click()
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                    await page.wait_for_timeout(1500)
                    await self._fill_create_account_form()
                    return
            except Exception:
                continue

        for sel in signin_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await self._log("Found 'Sign In' prompt")
                    await loc.click()
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                    await page.wait_for_timeout(1500)
                    await self._fill_sign_in_form()
                    return
            except Exception:
                continue

        await self._log("No auth prompt — already on application form or not required")

    async def _fill_create_account_form(self):
        page = self._page
        portal_email = self._profile.get("portal_email") or self._profile.get("email", "")
        portal_password = self._profile.get("portal_password", "")

        if not portal_email or not portal_password:
            await self._log("WARNING: portal_email/portal_password not set — skipping account creation")
            return

        await self._log("Filling create account form")
        await self._send_screenshot()

        await self._fill_first_match(
            ["[data-automation-id='email']", "input[type='email']", "input[name='email']"],
            portal_email,
        )
        await self._fill_first_match(
            ["[data-automation-id='password']", "[data-automation-id='createPassword']", "input[type='password']"],
            portal_password,
        )
        await self._fill_first_match(
            ["[data-automation-id='verifyPassword']", "input[name='verifyPassword']", "input[placeholder*='erify']"],
            portal_password,
        )

        submit_sel = [
            "[data-automation-id='createAccountSubmitButton']",
            "button:has-text('Create Account')",
            "button[type='submit']",
        ]
        for sel in submit_sel:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click()
                    await self._log("Submitted account creation form")
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                    await page.wait_for_timeout(3000)
                    await self._send_screenshot()
                    return
            except Exception:
                continue

        await self._log("Create account submit button not found")

    async def _fill_sign_in_form(self):
        page = self._page
        portal_email = self._profile.get("portal_email") or self._profile.get("email", "")
        portal_password = self._profile.get("portal_password", "")

        if not portal_email or not portal_password:
            await self._log("WARNING: portal credentials not set — skipping sign in")
            return

        await self._log("Filling sign-in form")
        await self._send_screenshot()

        await self._fill_first_match(
            ["[data-automation-id='email']", "input[type='email']", "input[name='email']"],
            portal_email,
        )
        await self._fill_first_match(
            ["[data-automation-id='password']", "input[type='password']"],
            portal_password,
        )

        submit_sel = [
            "[data-automation-id='signInSubmitButton']",
            "button:has-text('Sign In')",
            "button[type='submit']",
        ]
        for sel in submit_sel:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.click()
                    await self._log("Submitted sign-in form")
                    await page.wait_for_load_state("networkidle", timeout=20_000)
                    await page.wait_for_timeout(2000)
                    await self._send_screenshot()
                    return
            except Exception:
                continue

        await self._log("Sign-in submit button not found")

    # ------------------------------------------------------------------
    # Multi-step application navigation
    # ------------------------------------------------------------------

    async def _navigate_application_steps(self):
        """Walk through Workday's multi-step application (up to 10 steps)."""
        page = self._page
        for step in range(1, 11):
            url = page.url
            await self._log(f"--- Step {step} — {url}")
            await self._send_screenshot()

            # Fill whatever fields are visible on this step
            await self._fill_visible_fields()
            await self._fill_visible_textareas()

            # Look for Next / Submit button
            next_sel = [
                "[data-automation-id='bottom-navigation-next-button']",
                "[data-automation-id='bottom-navigation-footer-button']",
                "button:has-text('Next')",
                "button:has-text('Continue')",
            ]
            submit_sel = [
                "[data-automation-id='bottom-navigation-next-button']",
                "button:has-text('Submit')",
                "button:has-text('Submit Application')",
                "button:has-text('Review')",
            ]

            # Check for final submit first
            for sel in submit_sel:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        text = (await loc.text_content() or "").strip()
                        if any(w in text for w in ("Submit", "Review")):
                            await loc.click()
                            await page.wait_for_load_state("networkidle", timeout=30_000)
                            await page.wait_for_timeout(2000)
                            await self._log(f"Clicked '{text}'")
                            await self._send_screenshot()
                            await self._check_confirmation()
                            return
                except Exception:
                    continue

            # Click Next
            clicked = False
            for sel in next_sel:
                try:
                    loc = page.locator(sel).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click()
                        await self._log(f"Clicked Next ({sel})")
                        await page.wait_for_load_state("networkidle", timeout=30_000)
                        await page.wait_for_timeout(2000)
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                await self._log("No Next/Submit button found — stopping")
                await self._send_screenshot()
                return

            # Detect if we're stuck on the same URL (no progress)
            if page.url == url:
                await self._log("URL unchanged after Next — may be a validation error")
                await self._send_screenshot()
                return

    async def _check_confirmation(self):
        page = self._page
        phrases = ["Application Submitted", "Thank you", "application has been submitted", "successfully submitted"]
        for phrase in phrases:
            if await page.locator(f"text={phrase}").count() > 0:
                self._submitted = True
                await self._log(f"Application submitted — confirmed: '{phrase}'")
                return
        await self._log("Submit clicked — confirmation text not detected")

    # ------------------------------------------------------------------
    # Field filling helpers
    # ------------------------------------------------------------------

    async def _fill_visible_fields(self):
        """Fill standard Workday fields that appear on the current step."""
        page = self._page
        full_name = self._profile.get("full_name", "") or ""
        parts = full_name.strip().split(" ", 1)
        first = parts[0] if parts else ""
        last = parts[1] if len(parts) > 1 else ""

        field_map = [
            (["[data-automation-id='legalNameSection_firstName']", "input[name='firstName']"], first),
            (["[data-automation-id='legalNameSection_lastName']", "input[name='lastName']"], last),
            (["[data-automation-id='phone-number']", "input[name='phone']", "input[type='tel']"], self._profile.get("phone", "") or ""),
            (["[data-automation-id='addressSection_city']", "input[name='city']"], (self._profile.get("location", "") or "").split(",")[0].strip()),
            (["[data-automation-id='email']"], self._profile.get("portal_email") or self._profile.get("email", "") or ""),
        ]

        for selectors, value in field_map:
            if value:
                await self._fill_first_match(selectors, value)

    async def _fill_visible_textareas(self):
        """Draft AI answers for any visible textareas (custom questions)."""
        page = self._page
        career_history = self._profile.get("career_history", "") or ""
        if not career_history:
            return

        textareas = await page.locator("textarea:visible").all()
        if not textareas:
            return

        await self._log(f"Found {len(textareas)} textarea(s) — drafting answers")
        from app.services.resume_tailor import ResumeTailor
        tailor = ResumeTailor()

        for i, textarea in enumerate(textareas):
            try:
                current = await textarea.input_value()
                if current.strip():
                    continue  # already filled

                aria_label = await textarea.get_attribute("aria-label") or ""
                placeholder = await textarea.get_attribute("placeholder") or ""
                label = aria_label or placeholder or f"Question {i + 1}"

                await self._log(f"  Drafting: {label[:80]}")
                answer = await tailor.draft_custom_answer(label, career_history)
                await textarea.fill(answer)
                await self._log(f"  Filled ({len(answer)} chars)")
            except Exception as e:
                await self._log(f"  Error on textarea {i}: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _fill_first_match(self, selectors: list[str], value: str):
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
