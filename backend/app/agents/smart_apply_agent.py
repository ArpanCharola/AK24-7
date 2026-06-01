import json
import re
from app.agents.base_portal_agent import BasePortalAgent

MAX_FORM_STEPS = 10


class SmartApplyAgent(BasePortalAgent):
    """
    LLM-powered apply agent (OpenAI gpt-4o).
    Each form step: extract visible fields → ask LLM what to fill → execute → proceed.
    No hardcoded selectors or ATS-specific guessing.
    """

    async def run(self, job_url: str, user_profile: dict | None = None):
        self._profile = user_profile or {}
        job_url = self._normalize_ats_url(job_url)
        await self._launch(headless=True)
        try:
            await self._log(f"SmartAgent loading: {job_url}")
            await self._page.goto(job_url, wait_until="networkidle", timeout=60_000)
            await self._page.wait_for_timeout(2000)

            await self._dismiss_overlays()
            await self._send_screenshot("Page loaded")

            await self._click_apply_button()

            prev_url = None
            stuck_attempts = 0
            consecutive_errors = 0
            for step in range(MAX_FORM_STEPS):
                current_url = self._page.url
                await self._log(f"── Step {step + 1} ── {current_url}")

                try:
                    # Let any in-flight navigation settle so extraction sees stable DOM
                    try:
                        await self._page.wait_for_load_state("networkidle", timeout=5000)
                    except Exception:
                        pass

                    await self._dismiss_overlays()

                    body_text = await self._page.inner_text("body")
                    if self._submission_confirmed(body_text, current_url):
                        await self._log("✓ Application submitted!")
                        self._submitted = True
                        await self._send_screenshot("Application submitted ✓")
                        break

                    # Vision-first fill: the model SEES the form via Set-of-Marks
                    # (numbered badges on a screenshot) and says what goes where.
                    # Fall back to the DOM-text planner only if vision yields nothing.
                    filled_any = await self._vision_fill_step()
                    if not filled_any:
                        fields = await self._extract_text_fields()
                        choices = await self._extract_choice_fields()
                        if fields or choices:
                            instructions = await self._llm_fill_plan(fields, choices)
                            for instr in instructions:
                                await self._apply_fill(instr)
                    await self._page.wait_for_timeout(400)

                    # Email verification step (e.g. Workday account verify) — read
                    # the code from the connected Gmail and submit it.
                    if await self._handle_email_verification_step():
                        await self._page.wait_for_timeout(2000)
                        continue

                    # Handle any login/password fields separately
                    await self._handle_credential_fields()

                    # File uploads — route resume / cover letter to the right inputs by label
                    if await self._page.locator("input[type='file']").count() > 0:
                        await self._upload_files_smart()

                    # Textareas — custom questions answered by the LLM
                    await self._answer_visible_textareas()

                    await self._send_screenshot(f"Step {step + 1} — filled")

                    # Advance to next step
                    if not await self._click_next_or_submit():
                        await self._log("No Next/Submit found — stopping")
                        # A visible password field with no way forward almost
                        # always means an account/login wall blocked the form.
                        has_pw = await self._page.locator("input[type='password']:visible").count() > 0
                        self._stop_reason = "login_or_account_wall" if has_pw else "no_submit_button"
                        break

                    await self._page.wait_for_timeout(2500)

                    # Stronger post-submit check (success icons/headings + body
                    # text), so a final "Submit" that lands on a thank-you page is
                    # recognised immediately instead of being treated as a new step.
                    if await self._submission_confirmed_dom():
                        await self._log("✓ Application submitted!")
                        self._submitted = True
                        await self._send_screenshot("Application submitted ✓")
                        break

                    if self._page.url == current_url:
                        errors = await self._collect_validation_errors()
                        if errors:
                            await self._log(f"Validation errors on this step: {' | '.join(errors[:5])}")
                        stuck_attempts += 1
                        if stuck_attempts >= 2:
                            await self._log("Page hasn't advanced after 2 attempts — stopping")
                            await self._send_screenshot("Stuck — needs review")
                            self._stop_reason = (
                                "validation_failed: " + " | ".join(errors[:3])
                                if errors else "stuck_no_progress"
                            )
                            break
                        await self._log(f"Page didn't advance — retrying step (attempt {stuck_attempts + 1})")
                        continue
                    stuck_attempts = 0
                    prev_url = current_url
                    consecutive_errors = 0
                except Exception as exc:
                    consecutive_errors += 1
                    await self._log(f"Step {step + 1} raised: {exc}")
                    if consecutive_errors >= 2:
                        await self._log("Two consecutive step errors — stopping")
                        await self._send_screenshot("Error — stopped")
                        self._stop_reason = f"step_errors: {str(exc)[:120]}"
                        break
                    await self._page.wait_for_timeout(1500)
                    continue
            else:
                # Loop ran the full MAX_FORM_STEPS without breaking out — the form
                # had more steps than we allow (or kept looping).
                if not self._submitted:
                    self._stop_reason = "max_steps_reached"

        finally:
            await self.close()

    # ── URL normalisation ─────────────────────────────────────────────────

    def _normalize_ats_url(self, url: str) -> str:
        """
        Rewrite company-wrapper URLs to their canonical ATS form so the agent
        lands directly on the application form rather than a marketing page.
        """
        # Greenhouse embed: ?gh_jid=12345
        m = re.search(r"[?&]gh_jid=(\d+)", url)
        if m:
            job_id = m.group(1)
            domain_m = re.search(r"(?:www\.)?([^.]+)\.[a-z]{2,}", url)
            if domain_m:
                slug = domain_m.group(1).lower()
                new_url = f"https://boards.greenhouse.io/{slug}/jobs/{job_id}"
                return new_url

        # Ashby embed: ?ashby_jid=<uuid>
        m = re.search(r"[?&]ashby_jid=([\w-]+)", url)
        if m:
            job_id = m.group(1)
            domain_m = re.search(r"(?:www\.)?([^.]+)\.[a-z]{2,}", url)
            if domain_m:
                slug = domain_m.group(1).lower()
                return f"https://jobs.ashbyhq.com/{slug}/{job_id}"

        return url

    # ── Apply button ──────────────────────────────────────────────────────

    async def _click_apply_button(self):
        """Try common patterns, then ask the LLM to identify the apply button text.

        Workday tenants (e.g. Target's `target.wd5.myworkdayjobs.com`) often
        show a two-step apply flow: clicking "Apply" reveals a dropdown with
        "Apply Manually" / "Use My Last Application" — the second-step button
        is what actually navigates to the form. After clicking the primary
        Apply button, we look for a follow-up.
        """
        common = [
            # Workday — primary
            "[data-automation-id='applyButton']",
            "[data-automation-id='adventureButton']",
            "button[data-automation-id*='apply' i]",
            "a[data-automation-id*='apply' i]",
            # Generic
            "a:has-text('Apply for this Job')",
            "a:has-text('Apply for this job')",
            "a:has-text('Apply Now')",
            "button:has-text('Apply Now')",
            "button:has-text('Apply')",
            "a:has-text('Apply')",
            "button[aria-label*='Apply' i]",
            ".template-btn-submit",
            "#apply-button",
            ".apply-btn",
        ]
        for sel in common:
            try:
                loc = self._page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await self._page.wait_for_timeout(1500)
                    await self._switch_to_new_tab_if_opened()
                    # Workday two-step: handle the "Apply Manually" dropdown
                    await self._handle_workday_apply_dropdown()
                    await self._page.wait_for_load_state("networkidle", timeout=20_000)
                    await self._log(f"Clicked apply ({sel})")
                    await self._send_screenshot()
                    return
            except Exception:
                continue

        # Fallback: ask the LLM to pick the right button from visible link/button text
        await self._log("Common apply selectors failed — asking LLM")
        btn_texts = await self._visible_clickable_texts(limit=40)
        if btn_texts:
            from app.services.resume_tailor import _generate
            result = (await _generate(
                "You identify the apply button on job postings.",
                f"These are clickable elements on the page: {btn_texts}\n"
                "Which one is the job application button? Reply with ONLY the exact text, nothing else.",
                max_tokens=16,
            )).strip().strip('"\'')
            try:
                loc = self._page.get_by_text(result, exact=True).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click()
                    await self._page.wait_for_timeout(1500)
                    await self._switch_to_new_tab_if_opened()
                    await self._handle_workday_apply_dropdown()
                    await self._page.wait_for_load_state("networkidle", timeout=20_000)
                    await self._log(f"LLM identified apply button: '{result}'")
                    await self._send_screenshot()
                    return
            except Exception:
                pass

        await self._log("Apply button not found — assuming already on form")

    async def _handle_workday_apply_dropdown(self):
        """Some Workday tenants reveal a dropdown after the primary Apply click
        with options like 'Apply Manually' / 'Use My Last Application'. Click
        the manual option (or first option) to advance to the application form."""
        followups = [
            "[data-automation-id='applyManually']",
            "[data-automation-id='useMyLastApplication']",
            "[data-automation-id='autofillWithResume']",
            "a:has-text('Apply Manually')",
            "button:has-text('Apply Manually')",
            "a:has-text('Use My Last Application')",
            "button:has-text('Use My Last Application')",
            "a:has-text('Autofill with Resume')",
            "button:has-text('Autofill with Resume')",
        ]
        for sel in followups:
            try:
                loc = self._page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=2500)
                    await self._page.wait_for_timeout(1500)
                    await self._log(f"Workday two-step: clicked '{sel}'")
                    return
            except Exception:
                continue

    async def _switch_to_new_tab_if_opened(self):
        """If a new browser tab was opened (e.g. by an Apply button), switch to it."""
        pages = self._page.context.pages
        if len(pages) > 1:
            new_page = pages[-1]
            if new_page != self._page:
                await self._log(f"New tab detected → switching to {new_page.url}")
                self._page = new_page

    # ── Field extraction ──────────────────────────────────────────────────

    async def _extract_text_fields(self) -> list[dict]:
        """Return metadata for all visible, fillable text/email/tel/url inputs."""
        elements = await self._page.locator(
            "input:visible:not([type='hidden']):not([type='file'])"
            ":not([type='submit']):not([type='button'])"
            ":not([type='checkbox']):not([type='radio']):not([type='password']),"
            " select:visible"
        ).all()

        fields = []
        for el in elements[:50]:  # cap raised from 30 for longer multi-section forms
            try:
                tag = await el.evaluate("e => e.tagName.toLowerCase()")
                type_ = (await el.get_attribute("type") or "text").lower()
                id_ = await el.get_attribute("id") or ""
                name = await el.get_attribute("name") or ""
                placeholder = await el.get_attribute("placeholder") or ""
                aria_label = await el.get_attribute("aria-label") or ""
                current_val = await el.input_value() if tag in ("input", "select") else ""

                # Build label from associated <label> element
                label_text = ""
                if id_:
                    lbl = self._page.locator(f"label[for='{id_}']").first
                    if await lbl.count() > 0:
                        label_text = (await lbl.text_content() or "").strip()

                human_label = label_text or aria_label or placeholder or name or id_
                if not human_label:
                    continue

                # Skip job-board search boxes (a search/keyword field on a career
                # landing page, e.g. Deloitte's #form__autocomplete-q). Typing the
                # role into these turns an "apply" into a "search".
                search_hay = f"{type_} {id_} {name} {placeholder} {aria_label} {label_text}".lower()
                if type_ == "search" or any(
                    k in search_hay for k in ("autocomplete-q", "search", "keyword", "site-search")
                ):
                    continue

                # Best selector
                if id_:
                    selector = f"#{id_}"
                elif name:
                    selector = f"[name='{name}']"
                elif placeholder:
                    selector = f"[placeholder='{placeholder}']"
                else:
                    continue

                # For selects, collect options
                options = []
                if tag == "select":
                    options = await el.evaluate(
                        "e => Array.from(e.options).map(o => o.text)"
                    )

                fields.append({
                    "selector": selector,
                    "label": human_label,
                    "tag": tag,
                    "type": type_,
                    "current_value": current_val,
                    "options": options,
                })
            except Exception:
                continue

        return fields

    # ── Choice field extraction (radios + checkboxes) ────────────────────

    async def _extract_choice_fields(self) -> list[dict]:
        """Return radio groups and visible checkboxes.

        Radio shape: {kind: "radio_group", label, options: [{label, selector}], current_value}
        Checkbox shape: {kind: "checkbox", label, selector, checked}
        """
        choices: list[dict] = []

        # Radio groups — group by name attribute
        radios = await self._page.locator("input[type='radio']:visible").all()
        by_name: dict[str, list] = {}
        for r in radios[:100]:  # cap raised from 60 for longer forms
            try:
                name = await r.get_attribute("name") or ""
                if not name:
                    continue
                by_name.setdefault(name, []).append(r)
            except Exception:
                continue

        for name, items in by_name.items():
            options: list[dict] = []
            group_label = ""
            current_value = ""
            for item in items:
                try:
                    value = await item.get_attribute("value") or ""
                    id_ = await item.get_attribute("id") or ""
                    opt_label = ""
                    if id_:
                        lbl = self._page.locator(f"label[for='{id_}']").first
                        if await lbl.count() > 0:
                            opt_label = (await lbl.text_content() or "").strip()
                    if not opt_label:
                        # Try parent <label>
                        opt_label = await item.evaluate(
                            "el => { const l = el.closest('label'); return l ? l.innerText.trim() : ''; }"
                        ) or ""
                    if not opt_label:
                        opt_label = value or "(option)"
                    selector = f"#{id_}" if id_ else f"input[type='radio'][name='{name}'][value='{value}']"
                    if await item.is_checked():
                        current_value = opt_label
                    options.append({"label": opt_label[:120], "value": value, "selector": selector})
                    if not group_label:
                        try:
                            legend = await item.evaluate(
                                "el => { const fs = el.closest('fieldset'); "
                                "return fs ? (fs.querySelector('legend')?.innerText || '') : ''; }"
                            )
                            if legend:
                                group_label = legend.strip()
                        except Exception:
                            pass
                except Exception:
                    continue
            if options:
                choices.append({
                    "kind": "radio_group",
                    "name": name,
                    "label": (group_label or name)[:200],
                    "options": options,
                    "current_value": current_value,
                })

        # Standalone checkboxes
        checkboxes = await self._page.locator("input[type='checkbox']:visible").all()
        for cb in checkboxes[:40]:  # cap raised from 20 for longer forms
            try:
                id_ = await cb.get_attribute("id") or ""
                name = await cb.get_attribute("name") or ""
                aria_label = await cb.get_attribute("aria-label") or ""
                checked = await cb.is_checked()
                label_text = ""
                if id_:
                    lbl = self._page.locator(f"label[for='{id_}']").first
                    if await lbl.count() > 0:
                        label_text = (await lbl.text_content() or "").strip()
                if not label_text:
                    label_text = await cb.evaluate(
                        "el => { const l = el.closest('label'); return l ? l.innerText.trim() : ''; }"
                    ) or ""
                label = (label_text or aria_label or name or "checkbox")[:200]
                if id_:
                    selector = f"#{id_}"
                elif name:
                    selector = f"input[type='checkbox'][name='{name}']"
                else:
                    continue
                choices.append({
                    "kind": "checkbox",
                    "label": label,
                    "selector": selector,
                    "checked": checked,
                })
            except Exception:
                continue

        return choices

    def _candidate_summary(self) -> str:
        """The candidate facts string shared by the DOM and vision fill planners."""
        p = self._profile
        location = p.get('location', '')
        city = location.split(',')[0].strip() if location else ''
        facts = (
            f"Full name: {p.get('full_name', '')}\n"
            f"Email: {p.get('portal_email') or p.get('email', '')}\n"
            f"Phone: {p.get('phone', '')}\n"
            f"Location: {location}\n"
            f"City: {city}\n"
            f"LinkedIn URL: {p.get('linkedin_url', '')}\n"
            f"GitHub URL: {p.get('github_url', '')}\n"
            f"Personal website: {p.get('website', '')}\n"
            f"Work authorization: Yes — authorized to work in the United States\n"
            f"Requires sponsorship: No\n"
            f"Gender: Decline to self-identify (use this for optional diversity questions)\n"
            f"Ethnicity: Decline to self-identify (use this for optional diversity questions)\n"
            f"Veteran status: I am not a protected veteran\n"
            f"Disability status: I don't wish to answer\n"
        )
        # Give the planner the candidate's actual experience so it can answer
        # inline form fields (years of experience, current/most-recent employer,
        # skills, "why this role", etc.). Without this the planner only sees
        # contact details and guesses blind. Lengths are capped to bound the prompt.
        career = (p.get('career_history') or '').strip()
        resume = (p.get('tailored_resume_text') or p.get('resume_text') or '').strip()
        if career:
            facts += f"\nCareer history (use to answer experience questions):\n{career[:1500]}\n"
        if resume:
            facts += f"\nRésumé (source of truth for skills, employers, dates):\n{resume[:2500]}\n"
        return facts

    # ── Set-of-Marks vision fill ──────────────────────────────────────────
    # Overlay numbered badges on every interactive element, screenshot the
    # page, and let gpt-4o *see* the form and say which mark gets what value.
    # Each mark maps back to a real element via the data-som attribute, so
    # execution stays selector-reliable (no fragile coordinate clicking).

    _MARK_JS = r"""
    () => {
      document.querySelectorAll('.__som_badge').forEach(e => e.remove());
      const sel = "input:not([type=hidden]):not([type=file]), select, button, [role=button], [role=radio], [role=checkbox], a[href]";
      const els = Array.from(document.querySelectorAll(sel));
      const items = [];
      let i = 0;
      for (const el of els) {
        if (i >= 45) break;
        const r = el.getBoundingClientRect();
        if (r.width < 6 || r.height < 6) continue;
        const cs = getComputedStyle(el);
        if (cs.visibility === 'hidden' || cs.display === 'none' || parseFloat(cs.opacity) === 0) continue;
        if (r.bottom < 0 || r.right < 0) continue;
        const tag = el.tagName.toLowerCase();
        const type = (el.getAttribute('type') || '').toLowerCase();
        let label = '';
        if (el.labels && el.labels.length) label = el.labels[0].innerText;
        if (!label) label = el.getAttribute('aria-label') || '';
        if (!label && el.getAttribute('aria-labelledby')) {
          const l = document.getElementById(el.getAttribute('aria-labelledby'));
          if (l) label = l.innerText;
        }
        if (!label) label = el.getAttribute('placeholder') || '';
        if (!label && (tag === 'button' || tag === 'a' || el.getAttribute('role') === 'button')) label = (el.innerText || '').trim();
        if (!label) label = el.getAttribute('name') || '';
        label = (label || '').replace(/\s+/g, ' ').trim().slice(0, 120);
        let options = null;
        if (tag === 'select') options = Array.from(el.options).map(o => (o.text || '').trim()).filter(Boolean).slice(0, 40);
        let value = '';
        let checked = null;
        if (type === 'checkbox' || type === 'radio') checked = el.checked;
        else if ('value' in el) value = String(el.value || '').slice(0, 80);
        el.setAttribute('data-som', i);
        const b = document.createElement('div');
        b.className = '__som_badge';
        b.textContent = i;
        b.style.cssText = 'position:absolute;z-index:2147483647;background:#ff2d55;color:#fff;font:bold 12px monospace;padding:0 4px;border-radius:3px;pointer-events:none;top:' + (r.top + window.scrollY) + 'px;left:' + (r.left + window.scrollX) + 'px;';
        document.body.appendChild(b);
        items.push({id: i, tag, type, label, options, value, checked});
        i++;
      }
      return items;
    }
    """

    async def _mark_elements(self) -> list[dict]:
        """Tag interactive elements with data-som=<id>, draw numbered badges,
        and return their metadata list."""
        try:
            return await self._page.evaluate(self._MARK_JS)
        except Exception as exc:
            await self._log(f"mark elements failed: {exc}")
            return []

    async def _clear_marks(self):
        try:
            await self._page.evaluate("() => document.querySelectorAll('.__som_badge').forEach(e => e.remove())")
        except Exception:
            pass

    async def _vision_fill_step(self) -> bool:
        """One screenshot-driven fill pass. Returns True if any field was filled.

        Marks the form, screenshots it (badges visible), asks gpt-4o vision what
        to put where, then executes each action against the real element by its
        mark id. Falls back to the DOM planner if vision yields nothing."""
        items = await self._mark_elements()
        if not items:
            return False
        # Screenshot WITH badges so the model sees the numbering, then strip the
        # badges (keeping the data-som attributes used for execution).
        import base64
        shot = await self._page.screenshot(full_page=True, type="jpeg", quality=70)
        await self._clear_marks()
        # Stream the annotated view to the live console too.
        await self._publish({
            "type": "screenshot",
            "data": base64.b64encode(shot).decode(),
            "caption": f"Reading {len(items)} fields",
        })

        actions = await self._vision_fill_plan(items, base64.b64encode(shot).decode())
        if not actions:
            return False
        filled = 0
        for act in actions:
            if await self._apply_vision_action(act):
                filled += 1
        await self._log(f"Vision filled {filled}/{len(actions)} field(s)")
        return filled > 0

    async def _vision_fill_plan(self, items: list[dict], image_b64: str) -> list[dict]:
        """Ask gpt-4o (vision) which marked field gets what. Returns a list of
        {mark:int, action:'type'|'select'|'check', value:str}."""
        from app.services.resume_tailor import _generate_vision

        mark_lines = []
        for it in items:
            extra = ""
            if it.get("options"):
                extra = f" options={it['options']}"
            elif it.get("checked") is not None:
                extra = f" checked={it['checked']}"
            elif it.get("value"):
                extra = f" current='{it['value'][:40]}'"
            mark_lines.append(
                f"[{it['id']}] {it['tag']}"
                + (f"/{it['type']}" if it.get("type") else "")
                + f" label=\"{it.get('label','')}\"{extra}"
            )

        system = (
            "You analyze annotated screenshots of online forms and emit a structured "
            "action plan in JSON. The screenshot shows red numbered badges on each "
            "interactive element; each badge id corresponds to an entry in the mark "
            "list provided in the user message.\n"
            "\n"
            "Output schema: a JSON array of objects, each shaped "
            '{"mark": <int>, "action": "type"|"select"|"check", "value": "<text>"}.\n'
            "- type: text the candidate would enter into a text/email/phone/url input.\n"
            "- select: for a <select>, value MUST exactly match one of its listed options.\n"
            "- check: pick this radio option or checkbox (value = the option label).\n"
            "\n"
            "Mapping guidelines (use only when the candidate info clearly supplies the answer):\n"
            "- Skip fields already populated correctly (current=… or checked=true).\n"
            "- US work authorization → Yes; visa sponsorship required → No.\n"
            "- EEOC demographic fields (gender, race/ethnicity, veteran status, disability) → "
            "  emit the 'decline to self-identify' / 'prefer not to answer' option.\n"
            "- Required consent/terms/privacy boxes → check. Marketing/newsletter → leave unchecked.\n"
            "- For radio groups, emit one action for the correct option's mark.\n"
            "- Do not act on navigation controls (Apply, Submit, Next, Back).\n"
            "- Skip any field where the candidate info doesn't supply an answer.\n"
            "\n"
            "Edge cases — return an empty array [] when:\n"
            "- The screenshot is a login, sign-in, account-creation, or password page.\n"
            "- The screenshot does not contain a fillable form.\n"
            "- You cannot confidently map any mark to candidate data.\n"
            "\n"
            "Output the raw JSON array only. No markdown fences, no commentary, no apology."
        )
        user = (
            f"Candidate info:\n{self._candidate_summary()}\n\n"
            f"Marked fields:\n" + "\n".join(mark_lines)
        )
        try:
            raw = await _generate_vision(system, user, image_b64, max_tokens=900)
        except Exception as exc:
            await self._log(f"Vision plan failed: {exc}")
            return []

        # Detect model refusals (vision hits a safety filter, e.g. on a login/
        # account-creation screen). Log distinctly so the DOM fallback path is
        # the clear next step in the run.
        raw_low = raw.lower().strip()
        if (
            raw_low.startswith(("i'm sorry", "i am sorry", "sorry,", "i cannot", "i can't"))
            or "can't assist" in raw_low
            or "cannot assist" in raw_low
            or "unable to help" in raw_low
        ):
            await self._log("Vision refused — falling back to DOM-only fill")
            return []

        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            await self._log(f"Vision plan parse failed — raw: {raw[:150]}")
            return []
        try:
            result = json.loads(match.group())
        except json.JSONDecodeError:
            await self._log(f"Vision plan JSON error — raw: {raw[:150]}")
            return []
        valid = [a for a in result if isinstance(a, dict) and a.get("mark") is not None]
        await self._log(f"Vision planned {len(valid)} action(s)")
        return valid

    async def _apply_vision_action(self, action: dict) -> bool:
        """Execute one vision action against the element carrying its mark id."""
        mark = action.get("mark")
        act = (action.get("action") or "").lower()
        value = action.get("value")
        value = str(value).strip() if value is not None else ""
        sel = f'[data-som="{mark}"]'
        try:
            loc = self._page.locator(sel).first
            if await loc.count() == 0 or not await loc.is_visible():
                return False
            tag = await loc.evaluate("e => e.tagName.toLowerCase()")
            itype = (await loc.get_attribute("type") or "").lower() if tag == "input" else ""

            if act == "check" or itype in ("radio", "checkbox"):
                await loc.check()
                await self._log(f"  ✓ [{mark}] checked ({value[:40]})")
                return True
            if tag == "select":
                try:
                    await loc.select_option(label=value)
                except Exception:
                    await loc.select_option(value=value)
                await self._log(f"  ✓ [{mark}] select = '{value[:40]}'")
                return True
            if not value:
                return False
            await loc.fill(value)
            await self._log(f"  ✓ [{mark}] = '{value[:40]}'")
            return True
        except Exception as exc:
            await self._log(f"  ✗ [{mark}]: {exc}")
            return False

    # ── LLM fill plan ────────────────────────────────────────────────────

    async def _llm_fill_plan(self, fields: list[dict], choices: list[dict] | None = None) -> list[dict]:
        """Ask the LLM to map candidate info onto form fields. Returns instruction list.

        Each instruction: {"selector": str, "value": str}.
        For radios, value is ignored — the agent just clicks the chosen selector.
        For checkboxes, value is "check" or "uncheck".
        """
        choices = choices or []
        from app.services.resume_tailor import _generate

        candidate_summary = self._candidate_summary()

        field_lines = []
        for f in fields:
            status = "[ALREADY FILLED — skip]" if f["current_value"] else "[EMPTY — fill]"
            opts = f" | options: {f['options']}" if f["options"] else ""
            field_lines.append(
                f'TEXT label="{f["label"]}" selector="{f["selector"]}" type="{f["type"]}"{opts} {status}'
            )

        choice_lines = []
        for c in choices:
            if c["kind"] == "radio_group":
                status = f"[ALREADY SELECTED: {c['current_value']}]" if c["current_value"] else "[EMPTY — pick one]"
                opt_str = " | ".join(f'"{o["label"]}" -> selector="{o["selector"]}"' for o in c["options"])
                choice_lines.append(f'RADIO_GROUP question="{c["label"]}" {status}\n    options: {opt_str}')
            elif c["kind"] == "checkbox":
                status = "[CHECKED]" if c["checked"] else "[UNCHECKED]"
                choice_lines.append(f'CHECKBOX label="{c["label"]}" selector="{c["selector"]}" {status}')

        system = (
            "You are filling a job application form. "
            "Given candidate info and a list of form fields, return a JSON array of instructions. "
            "Each element: {\"selector\": \"...\", \"value\": \"...\"}.\n"
            "Rules by field type:\n"
            "- TEXT fields [EMPTY — fill]: value is the text to type. For SELECT fields, value must exactly match a listed option.\n"
            "- RADIO_GROUP [EMPTY — pick one]: emit ONE instruction with the selector of the chosen option. value can be the option label (the agent will just click the selector).\n"
            "- CHECKBOX [UNCHECKED]: only emit if it should be checked. value=\"check\". Always check terms/agreement/privacy/consent boxes (these are required for submission). Do NOT check marketing/newsletter/contact-me boxes.\n"
            "- Skip anything marked [ALREADY FILLED], [ALREADY SELECTED], or [CHECKED] — these are already correct.\n"
            "Decision policy:\n"
            "- US work authorization questions → 'Yes'\n"
            "- Visa sponsorship questions → 'No'\n"
            "- City/location fields → candidate's city\n"
            "- Gender / ethnicity / veteran / disability EEOC → pick 'decline' or 'prefer not' option\n"
            "- Salary expectations → leave blank if no candidate data\n"
            "- Skip fields you have no data for\n"
            "Output ONLY the raw JSON array, no markdown, no explanation."
        )
        all_lines = field_lines + choice_lines
        user = (
            f"Candidate info:\n{candidate_summary}\n\n"
            f"Form fields:\n" + "\n".join(all_lines)
        )

        raw = await _generate(system, user, max_tokens=512)

        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group())
                valid = [
                    r for r in result
                    if isinstance(r, dict) and r.get("selector") and r.get("value") is not None
                ]
                await self._log(f"LLM planned {len(valid)} fills")
                return valid
            except json.JSONDecodeError:
                pass

        await self._log(f"LLM fill plan parse failed — raw: {raw[:150]}")
        return []

    async def _apply_fill(self, instr: dict):
        selector = instr.get("selector", "")
        raw_value = instr.get("value", "")
        value = str(raw_value).strip() if raw_value is not None else ""
        if not selector:
            return
        try:
            loc = self._page.locator(selector).first
            if await loc.count() == 0 or not await loc.is_visible():
                return
            tag = await loc.evaluate("e => e.tagName.toLowerCase()")
            input_type = (await loc.get_attribute("type") or "").lower() if tag == "input" else ""

            if input_type == "radio":
                await loc.check()
                await self._log(f"  ✓ radio {selector}")
                return
            if input_type == "checkbox":
                should_check = value.lower() in ("check", "true", "yes", "on", "1", "checked")
                if should_check:
                    await loc.check()
                else:
                    await loc.uncheck()
                await self._log(f"  ✓ checkbox {selector} → {'checked' if should_check else 'unchecked'}")
                return
            if not value:
                return  # text fields need a value
            if tag == "select":
                try:
                    await loc.select_option(label=value)
                except Exception:
                    await loc.select_option(value=value)
            else:
                await loc.fill(value)
            await self._log(f"  ✓ {selector} = '{value[:40]}'")
        except Exception as exc:
            await self._log(f"  ✗ {selector}: {exc}")

    # ── Email verification step ───────────────────────────────────────────

    _VERIFY_FIELD_RE = re.compile(
        r"(verif|confirmation code|one[\s-]?time|security code|\botp\b|access code)", re.I
    )

    async def _detect_verification_input(self):
        """Return a locator for a visible email/account verification-code input,
        or None. Deliberately narrow (matches verify/OTP/confirmation-code wording
        on label, placeholder, aria-label, or name) so we never type a code into
        an unrelated field."""
        inputs = await self._page.locator(
            "input[type='text']:visible, input[type='tel']:visible, "
            "input[type='number']:visible, input:not([type]):visible"
        ).all()
        for el in inputs[:30]:
            try:
                id_ = await el.get_attribute("id") or ""
                hay = " ".join(filter(None, [
                    await el.get_attribute("placeholder") or "",
                    await el.get_attribute("aria-label") or "",
                    await el.get_attribute("name") or "",
                ]))
                if id_:
                    lbl = self._page.locator(f"label[for='{id_}']").first
                    if await lbl.count() > 0:
                        hay += " " + (await lbl.text_content() or "")
                if self._VERIFY_FIELD_RE.search(hay):
                    return el
            except Exception:
                continue
        return None

    async def _handle_email_verification_step(self) -> bool:
        """If this step asks for an emailed verification code, read it from Gmail
        and submit. Returns True if a code was entered. Best-effort, non-breaking."""
        field = await self._detect_verification_input()
        if field is None:
            return False
        await self._log("Email verification step detected — reading code from Gmail")
        code = await self._read_email_verification_code(timeout=90)
        if not code:
            self._stop_reason = "email_verification_code_unavailable"
            return False
        try:
            await field.fill(code)
        except Exception as exc:
            await self._log(f"Could not fill verification code: {exc}")
            return False
        await self._send_screenshot("Verification code entered")
        # Submit the code (Verify / Continue / Submit), falling back to generic nav.
        if not await self._click_first_visible([
            "button:has-text('Verify')", "button:has-text('Confirm')",
            "button:has-text('Continue')", "button:has-text('Submit')",
            "button[type='submit']",
        ]):
            await self._click_next_or_submit()
        await self._log("Submitted email verification code")
        return True

    # ── Credential fields ─────────────────────────────────────────────────

    async def _handle_credential_fields(self):
        """Fill email + password fields for portal login screens."""
        p = self._profile
        email = p.get("portal_email") or p.get("email") or ""
        password = p.get("portal_password") or ""

        pw_inputs = await self._page.locator("input[type='password']:visible").all()
        if not pw_inputs:
            return  # Not a login screen

        await self._log("Login screen detected — filling credentials")
        await self._fill_first_match(
            ["input[type='email']:visible", "input[name='email']:visible",
             "input[name='username']:visible"],
            email,
        )
        for pw_input in pw_inputs:
            try:
                await pw_input.fill(password)
            except Exception:
                pass

        # Submit the login
        await self._click_first_visible([
            "button[type='submit']",
            "button:has-text('Sign In')",
            "button:has-text('Log In')",
            "button:has-text('Create Account')",
        ])
        await self._page.wait_for_timeout(2000)

    # ── Navigation ────────────────────────────────────────────────────────

    # Button text/value that means "search/filter the job board", NOT "advance
    # the application". On career-site landing/search pages the search button is
    # a type=submit, so without this guard the agent searches instead of applying.
    _NON_SUBMIT_RE = re.compile(
        r"\b(search|find jobs?|filter|view jobs?|see jobs?|browse jobs?|refine)\b", re.I
    )

    async def _click_next_or_submit(self) -> bool:
        selectors = [
            "button:has-text('Submit Application')",
            "button:has-text('Submit application')",
            "input[type='submit']",
            "[data-automation-id='bottom-navigation-next-button']",
            "button:has-text('Next')",
            "button:has-text('Continue')",
            "button:has-text('Save & Continue')",
            "button:has-text('Save and Continue')",
            "button:has-text('Review')",
            "button:has-text('Submit')",
            "button[type='submit']",
            # Greenhouse / careerpuck embedded form
            "input[value='Submit Application']",
            "input[value='Submit']",
            "[data-qa='btn-submit']",
            "button:has-text('Apply')",
        ]
        for sel in selectors:
            try:
                loc = self._page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    text = (await loc.text_content() or await loc.get_attribute("value") or "").strip()
                    if text and self._NON_SUBMIT_RE.search(text):
                        continue  # a job-search/filter button, not the application submit
                    await loc.click()
                    await self._page.wait_for_load_state("networkidle", timeout=30_000)
                    await self._log(f"Clicked '{text or sel}'")
                    return True
            except Exception:
                continue

        # Last resort: pick from keyword matches on visible button text
        btn_texts = await self._visible_clickable_texts(limit=15)
        submit_keywords = {"submit", "apply", "next", "continue", "send", "finish"}
        for t in btn_texts:
            if self._NON_SUBMIT_RE.search(t):
                continue
            if any(kw in t.lower() for kw in submit_keywords):
                try:
                    loc = self._page.get_by_text(t, exact=True).first
                    if await loc.count() > 0 and await loc.is_visible():
                        await loc.click()
                        await self._page.wait_for_load_state("networkidle", timeout=30_000)
                        await self._log(f"Clicked '{t}' (keyword match)")
                        return True
                except Exception:
                    continue
        return False

    # ── Validation error collection ───────────────────────────────────────

    async def _collect_validation_errors(self) -> list[str]:
        """Scrape visible validation messages so the agent can surface WHY a step failed."""
        selectors = (
            "[role='alert']:visible",
            "[aria-invalid='true'] + *",
            ".error-message:visible",
            ".error:visible",
            ".field-error:visible",
            ".field--error:visible",
            ".invalid-feedback:visible",
            ".form-error:visible",
            ".validation-error:visible",
            ".help-block-error:visible",
            "[data-error]:visible",
            "span.error:visible",
            "p.error:visible",
            "div.error:visible",
        )
        out: list[str] = []
        seen = set()
        for sel in selectors:
            try:
                for el in await self._page.locator(sel).all():
                    try:
                        if not await el.is_visible():
                            continue
                        text = (await el.text_content() or "").strip()
                        text = " ".join(text.split())
                        if not text or len(text) > 200:
                            continue
                        if text in seen:
                            continue
                        seen.add(text)
                        out.append(text)
                    except Exception:
                        continue
            except Exception:
                continue
        return out

    # ── Smart file upload routing ─────────────────────────────────────────

    async def _upload_files_smart(self):
        """Upload resume / cover letter into the right file inputs by inspecting nearby
        labels. Avoids the common bug of uploading the resume into the cover-letter slot."""
        import os, tempfile
        file_inputs = await self._page.locator("input[type='file']").all()
        if not file_inputs:
            return

        cover_letter_text = (self._profile.get("cover_letter_text") or "").strip()
        resume_pdf_bytes = self._profile.get("resume_pdf_bytes")
        resume_text = (
            self._profile.get("tailored_resume_text")
            or self._profile.get("resume_text")
            or ""
        )

        async def _label_for(input_handle) -> str:
            try:
                id_ = await input_handle.get_attribute("id") or ""
                if id_:
                    lbl = self._page.locator(f"label[for='{id_}']").first
                    if await lbl.count() > 0:
                        t = (await lbl.text_content() or "").strip()
                        if t:
                            return t.lower()
                # Aria-label / name / accept hint
                for attr in ("aria-label", "name", "data-testid", "placeholder"):
                    v = await input_handle.get_attribute(attr) or ""
                    if v:
                        return v.lower()
                # Closest parent text (limited depth)
                txt = await input_handle.evaluate(
                    "el => { let p = el.parentElement; for (let i=0;i<3 && p;i++){ const t=(p.innerText||'').trim(); if (t && t.length<200) return t; p = p.parentElement; } return ''; }"
                )
                return (txt or "").lower()
            except Exception:
                return ""

        async def _write_temp(suffix: str, mode: str, data) -> str:
            kwargs = {"suffix": suffix, "delete": False}
            if mode == "w":
                kwargs["mode"] = "w"
                kwargs["encoding"] = "utf-8"
            else:
                kwargs["mode"] = "wb"
            tmp = tempfile.NamedTemporaryFile(**kwargs)
            tmp.write(data)
            tmp.close()
            return tmp.name

        resume_path = None
        cover_path = None
        try:
            for inp in file_inputs:
                label = await _label_for(inp)
                if "cover" in label and cover_letter_text:
                    if cover_path is None:
                        cover_path = await _write_temp(".txt", "w", cover_letter_text)
                    try:
                        await inp.set_input_files(cover_path)
                        await self._log(f"Cover letter uploaded into: {label[:60]}")
                    except Exception as exc:
                        await self._log(f"Cover letter upload failed ({label[:40]}): {exc}")
                    continue

                # Skip non-resume slots we don't have content for (transcript, portfolio, etc.)
                if any(k in label for k in ("transcript", "portfolio", "writing sample", "reference")):
                    await self._log(f"Skipping {label[:40]} (no candidate file for this slot)")
                    continue

                # Default: treat as resume slot
                if resume_pdf_bytes:
                    if resume_path is None:
                        resume_path = await _write_temp(".pdf", "wb", resume_pdf_bytes)
                    suffix_used = "PDF"
                elif resume_text:
                    if resume_path is None:
                        resume_path = await _write_temp(".txt", "w", resume_text)
                    suffix_used = "TXT"
                else:
                    await self._log("No resume content available — skipping file input")
                    continue
                try:
                    await inp.set_input_files(resume_path)
                    await self._log(f"Resume uploaded ({suffix_used}) into: {label[:60] or '(unlabeled)'}")
                except Exception as exc:
                    await self._log(f"Resume upload failed ({label[:40]}): {exc}")
        finally:
            for p in (resume_path, cover_path):
                if p:
                    try:
                        os.unlink(p)
                    except Exception:
                        pass

    # ── Overlay / consent banner dismissal ────────────────────────────────

    async def _dismiss_overlays(self):
        """Best-effort dismissal of cookie banners, GDPR popups, and generic modals
        that overlap the apply form. Failures are silent — never block the main flow."""
        accept_button_texts = (
            "Accept all", "Accept All", "Accept all cookies", "Accept",
            "I agree", "I Agree", "Agree", "Allow all", "Allow All",
            "Got it", "Got It", "OK", "Ok",
            "Continue", "Reject all", "Reject All",  # any choice closes the banner
        )
        close_selectors = (
            "button[aria-label='Close']",
            "button[aria-label='close']",
            "button[aria-label='Dismiss']",
            "[data-testid='close-button']",
            ".cookie-banner button",
            "#onetrust-accept-btn-handler",
            "#truste-consent-button",
            ".CookieConsent button",
        )
        dismissed = 0
        for text in accept_button_texts:
            try:
                loc = self._page.get_by_role("button", name=text, exact=True).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=2000)
                    dismissed += 1
                    await self._page.wait_for_timeout(500)
            except Exception:
                continue
        for sel in close_selectors:
            try:
                loc = self._page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    await loc.click(timeout=2000)
                    dismissed += 1
                    await self._page.wait_for_timeout(500)
            except Exception:
                continue
        if dismissed:
            await self._log(f"Dismissed {dismissed} overlay(s)")

    # ── Helpers ───────────────────────────────────────────────────────────

    async def _visible_clickable_texts(self, limit: int = 20) -> list[str]:
        texts = []
        els = await self._page.locator("a:visible, button:visible").all()
        for el in els[:limit]:
            try:
                t = (await el.text_content() or "").strip()
                if t and len(t) < 60:
                    texts.append(t)
            except Exception:
                continue
        return texts

    def _submission_confirmed(self, body_text: str, url: str) -> bool:
        text = (body_text or "").lower()
        url_l = (url or "").lower()

        # Only phrases that appear AFTER a successful submit. Deliberately excludes
        # ambiguous ones like "review your application" / "we'll be in touch" /
        # "look forward to reviewing" — those also show on review/confirm steps
        # BEFORE submission and caused false-positive "submitted" reports.
        body_phrases = (
            "application submitted", "thank you for applying", "thanks for applying",
            "we received your application", "we've received your application",
            "successfully submitted", "application received", "you've applied",
            "you have applied", "your application has been received",
            "application complete", "submission successful",
        )
        if any(p in text for p in body_phrases):
            return True

        url_markers = (
            "thank", "thanks", "confirm", "submitted",
            "/success", "/complete", "/confirmation", "/applied",
            "?status=success", "&status=success",
        )
        if any(m in url_l for m in url_markers):
            return True

        return False

    async def _submission_confirmed_dom(self) -> bool:
        """Stronger check that also looks at DOM markers (success icons, headings)
        in addition to body text. Call after a perceived submit click."""
        # Class / role markers commonly used for success state
        markers = [
            "[role='status']:has-text('submit')",
            "[role='alert']:has-text('submit')",
            ".success-message",
            ".application-success",
            "h1:has-text('Thank')",
            "h2:has-text('Thank')",
            "h1:has-text('Submitted')",
            "h2:has-text('Submitted')",
            "h1:has-text('Received')",
        ]
        for sel in markers:
            try:
                if await self._page.locator(sel).first.is_visible():
                    return True
            except Exception:
                continue
        try:
            body = await self._page.inner_text("body")
        except Exception:
            body = ""
        return self._submission_confirmed(body, self._page.url)
