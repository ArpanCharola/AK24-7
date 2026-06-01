import re
from app.agents.base_portal_agent import BasePortalAgent


class UniversalAgent(BasePortalAgent):
    """Fallback agent for redirect/unknown URLs.

    Opens the URL in a browser to resolve the final ATS domain, then:
    - For Greenhouse / Lever / Ashby: closes the browser and hands off to
      the dedicated HTTP API agent (no browser overhead for those portals).
    - For Workday / iCIMS / unknown: runs the generic pattern-based fill
      directly in the same browser session.
    """

    async def run(self, job_url: str, user_profile: dict | None = None):
        self._profile = user_profile or {}
        await self._launch(headless=True)
        try:
            await self._log(f"Universal: resolving {job_url}")
            await self._page.goto(job_url, wait_until="networkidle", timeout=60_000)
            await self._page.wait_for_timeout(3000)
            final_url = self._page.url
            await self._log(f"Resolved to: {final_url}")
            await self._send_screenshot()

            portal = self._detect(final_url)
            await self._log(f"Detected portal: {portal}")

            if portal in ("greenhouse", "lever", "ashby"):
                # Close Playwright — the HTTP agent manages its own connections
                await self.close()
                await self._run_api_agent(portal, final_url)
            elif portal == "workday":
                from app.agents.workday_agent import WorkdayAgent
                await self._hand_off_playwright(WorkdayAgent, final_url)
            else:
                await self._generic_apply()
        finally:
            # close() is idempotent — safe to call even if already closed above
            await self.close()

    # ── Routing helpers ───────────────────────────────────────────────────────

    def _detect(self, url: str) -> str:
        url = url.lower()
        if "jobs.adp.com" in url or "myjobs.adp.com" in url:
            return "adp"
        if "careers.oracle.com" in url:
            return "oracle"
        if any(x in url for x in ("myworkdayjobs.com", "workday.com")):
            return "workday"
        if "greenhouse.io" in url or "boards.greenhouse.io" in url:
            return "greenhouse"
        if "lever.co" in url:
            return "lever"
        if "ashbyhq.com" in url or "jobs.ashby.com" in url:
            return "ashby"
        return "unknown"

    async def _run_api_agent(self, portal: str, final_url: str):
        """Delegate to the appropriate HTTP-only API agent."""
        if portal == "greenhouse":
            from app.agents.greenhouse_agent import GreenhouseAgent
            agent = GreenhouseAgent(self.application_id, self.user_id)
        elif portal == "lever":
            from app.agents.lever_agent import LeverAgent
            agent = LeverAgent(self.application_id, self.user_id)
        else:
            from app.agents.ashby_agent import AshbyAgent
            agent = AshbyAgent(self.application_id, self.user_id)

        await agent.run(final_url, user_profile=self._profile)

    async def _hand_off_playwright(self, agent_cls, final_url: str):
        """Reuse the already-open Playwright session for browser-based agents."""
        specialist = agent_cls(
            application_id=self.application_id,
            user_id=self.user_id,
        )
        specialist._profile = self._profile
        specialist._page = self._page
        specialist._context = self._context
        specialist._browser = self._browser
        specialist._redis = self._redis
        # Navigate to the resolved URL and let the specialist take over
        await specialist.run(final_url, user_profile=self._profile)
        # Prevent double-close — specialist.close() already ran
        self._browser = None

    # ── Generic fallback ──────────────────────────────────────────────────────

    async def _generic_apply(self):
        """Best-effort form fill for completely unknown portals."""
        await self._log("Unknown portal — attempting generic apply")

        await self._click_first_visible([
            "button:has-text('Apply Now')", "a:has-text('Apply Now')",
            "button:has-text('Apply')", "a:has-text('Apply')",
            "#apply-button", ".apply-btn",
        ])

        p = self._profile
        name = (p.get("full_name") or "").strip()
        parts = name.split(" ", 1)
        first, last = parts[0], (parts[1] if len(parts) > 1 else "")
        email = p.get("portal_email") or p.get("email") or ""
        phone = p.get("phone") or ""

        for value, selectors in [
            (first, ["input[autocomplete='given-name']",  "input[name*='first']",  "input[placeholder*='First']"]),
            (last,  ["input[autocomplete='family-name']", "input[name*='last']",   "input[placeholder*='Last']"]),
            (name,  ["input[autocomplete='name']",        "input[name='name']",    "input[placeholder*='Name']"]),
            (email, ["input[type='email']",               "input[name*='email']"]),
            (phone, ["input[type='tel']",                 "input[name*='phone']"]),
        ]:
            if value:
                await self._fill_first_match(selectors, value)

        await self._upload_resume(["input[type='file']"])
        await self._answer_visible_textareas()
        await self._send_screenshot()

        await self._click_first_visible([
            "button[type='submit']", "input[type='submit']",
            "button:has-text('Submit')", "button:has-text('Apply')",
        ])
        await self._log("Generic apply done")
