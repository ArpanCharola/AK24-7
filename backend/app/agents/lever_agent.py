import re
import logging
import httpx
from app.agents.base_api_agent import BaseAPIAgent

logger = logging.getLogger(__name__)


def _parse_url(url: str) -> tuple[str, str] | None:
    """Extract (company_slug, posting_id) from a Lever job URL."""
    # https://jobs.lever.co/{company}/{posting_id}
    # https://jobs.lever.co/{company}/{posting_id}/apply
    m = re.search(r"jobs\.lever\.co/([^/?#]+)/([^/?#]+)", url)
    return (m.group(1), m.group(2)) if m else None


def _extract_hidden_fields(html: str) -> dict[str, str]:
    """Pull every hidden <input> from the apply form HTML (e.g. CSRF token)."""
    hidden: dict[str, str] = {}
    for tag in re.finditer(
        r'<input[^>]+type=["\']hidden["\'][^>]*/?>',
        html,
        re.IGNORECASE,
    ):
        raw = tag.group()
        name_m = re.search(r'\bname=["\']([^"\']+)["\']', raw)
        val_m  = re.search(r'\bvalue=["\']([^"\']*)["\']', raw)
        if name_m:
            hidden[name_m.group(1)] = val_m.group(1) if val_m else ""
    return hidden


class LeverAgent(BaseAPIAgent):
    """Applies to Lever jobs via HTTP multipart POST — no browser needed.

    Flow:
      1. GET the /apply page to capture any hidden CSRF tokens.
      2. POST multipart/form-data with standard profile fields + resume.
    """

    async def run(self, job_url: str, user_profile: dict | None = None):
        profile = user_profile or {}
        await self._connect()
        try:
            parsed = _parse_url(job_url)
            if not parsed:
                msg = f"Cannot parse Lever URL: {job_url}"
                await self._log(msg)
                raise RuntimeError(msg)

            company, posting_id = parsed
            apply_url = f"https://jobs.lever.co/{company}/{posting_id}/apply"
            await self._log(f"Lever HTTP  company={company}  posting={posting_id}")

            full_name = (profile.get("full_name") or "").strip()
            email     = profile.get("portal_email") or profile.get("email") or ""
            phone     = profile.get("phone") or ""
            linkedin  = profile.get("linkedin_url") or ""
            website   = profile.get("website") or ""
            github    = profile.get("github_url") or ""

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": f"https://jobs.lever.co/{company}/{posting_id}",
            }

            async with httpx.AsyncClient(
                timeout=30, follow_redirects=True, headers=headers
            ) as client:
                # ── 1. GET apply page for hidden tokens ───────────────────
                page_resp = await client.get(apply_url)
                hidden = (
                    _extract_hidden_fields(page_resp.text)
                    if page_resp.status_code == 200
                    else {}
                )
                if hidden:
                    await self._log(f"Captured {len(hidden)} hidden field(s)")

                # ── 2. Build multipart payload ─────────────────────────────
                # Use files= so httpx sends multipart/form-data (required for
                # the resume file).  Text fields are passed as (None, value).
                fname, fbytes, fmime = self._resume_bytes(profile)

                parts: list[tuple] = [
                    ("name",            (None, full_name)),
                    ("email",           (None, email)),
                    ("phone",           (None, phone)),
                    ("urls[LinkedIn]",  (None, linkedin)),
                    ("urls[GitHub]",    (None, github)),
                    ("urls[Portfolio]", (None, website)),
                    ("resume",          (fname, fbytes, fmime)),
                ]

                cover_letter = (profile.get("cover_letter_text") or "").strip()
                if cover_letter:
                    parts.append(("cover_letter", (None, cover_letter[:5000])))

                # Inject hidden CSRF / form tokens
                for key, val in hidden.items():
                    parts.append((key, (None, val)))

                # ── 3. Fetch custom questions from posting JSON ────────────
                posting_resp = await client.get(
                    f"https://api.lever.co/v0/postings/{company}/{posting_id}?mode=json"
                )
                if posting_resp.status_code == 200:
                    posting = posting_resp.json()
                    parts += await self._answer_custom_questions(posting, profile)

                # ── 4. Submit ──────────────────────────────────────────────
                await self._log(f"Submitting {len(parts)} field(s) to Lever")
                post_resp = await client.post(apply_url, files=parts)

                body_lower = post_resp.text.lower()
                if post_resp.status_code in (200, 201) and any(
                    x in body_lower
                    for x in ("thank you", "application received", "successfully")
                ):
                    await self._log("✓ Application submitted successfully")
                    self._submitted = True
                elif post_resp.status_code in (200, 201):
                    await self._log(
                        f"Posted — status {post_resp.status_code} "
                        f"(confirm manually)"
                    )
                    # Treat as soft success: 2xx but no confirmation text.
                    # Better to surface as a needs-review failure than a silent pass.
                    raise RuntimeError(
                        f"Lever returned {post_resp.status_code} without confirmation text — submission unverified"
                    )
                else:
                    msg = f"Lever submit returned {post_resp.status_code}: {post_resp.text[:300]}"
                    await self._log(msg)
                    raise RuntimeError(msg)

        except Exception as exc:
            await self._log(f"Error: {exc}")
            raise
        finally:
            await self.close()

    async def _answer_custom_questions(
        self, posting: dict, profile: dict
    ) -> list[tuple]:
        """Build multipart tuples for Lever additional-card custom questions.

        Collects every free-text question first, then drafts all answers
        concurrently (was one sequential LLM call per field).
        """
        pending: list[tuple[str, str]] = []  # (field_name, question_text)
        for card in posting.get("additionalCards", []):
            for i, field in enumerate(card.get("fields", [])):
                question_text = field.get("text", "")
                field_id = field.get("id", "")
                if not field_id or not question_text:
                    continue
                ftype = field.get("type", "")
                if ftype in ("textarea", "input"):
                    # Lever custom field name: cards[FIELD_ID][field0]
                    pending.append((f"cards[{field_id}][field{i}]", question_text))

        if not pending:
            return []

        answers = await self._llm_answers([q for _, q in pending], profile)
        parts: list[tuple] = []
        for (field_name, _), answer in zip(pending, answers):
            if answer:
                parts.append((field_name, (None, answer[:2000])))
        return parts
