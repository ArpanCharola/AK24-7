import re
import logging
import httpx
from app.agents.base_api_agent import BaseAPIAgent

logger = logging.getLogger(__name__)

_GH_API = "https://boards-api.greenhouse.io/v1/boards"

# Returned by _resolve_static for free-text fields that need an LLM answer, so
# the run() loop can batch those calls concurrently instead of awaiting each.
_NEEDS_LLM = object()

# Standard field names the Greenhouse API always includes
_STANDARD: dict[str, callable] = {
    "first_name": lambda p: (p.get("full_name") or "").split(" ", 1)[0],
    "last_name":  lambda p: ((p.get("full_name") or "").split(" ", 1)[1:] or [""])[0],
    "email":      lambda p: p.get("portal_email") or p.get("email") or "",
    "phone":      lambda p: p.get("phone") or "",
}


def _parse_url(url: str) -> tuple[str, str] | None:
    """Extract (board_token, job_id) from any Greenhouse job URL variant.

    Handles:
      - boards.greenhouse.io/{token}/jobs/{id}
      - job-boards.greenhouse.io/{token}/jobs/{id}
      - Company-hosted wrappers like stripe.com/jobs/search?gh_jid={id} —
        the company subdomain is used as the board token (works for the
        vast majority of Greenhouse-powered company career pages).
    """
    m = re.search(r"greenhouse\.io/([^/?#]+)/jobs/(\d+)", url)
    if m:
        return (m.group(1), m.group(2))

    m = re.search(r"[?&]gh_jid=(\d+)", url)
    if m:
        job_id = m.group(1)
        # Derive slug from the company's domain: stripe.com → "stripe"
        domain_m = re.search(r"https?://(?:www\.)?([^./]+)\.", url)
        if domain_m:
            return (domain_m.group(1).lower(), job_id)

    return None


class GreenhouseAgent(BaseAPIAgent):
    """Applies to Greenhouse jobs via the public Boards API — no browser needed."""

    async def run(self, job_url: str, user_profile: dict | None = None):
        profile = user_profile or {}
        await self._connect()
        try:
            parsed = _parse_url(job_url)
            if not parsed:
                msg = f"Cannot parse Greenhouse URL: {job_url}"
                await self._log(msg)
                raise RuntimeError(msg)

            board_token, job_id = parsed
            await self._log(f"Greenhouse API  board={board_token}  job={job_id}")

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                # ── 1. Fetch job schema (questions=true returns form fields) ──
                resp = await client.get(
                    f"{_GH_API}/{board_token}/jobs/{job_id}?questions=true"
                )
                if resp.status_code != 200:
                    msg = f"Greenhouse job fetch failed: {resp.status_code} (board={board_token}, job={job_id})"
                    await self._log(msg)
                    raise RuntimeError(msg)

                questions = resp.json().get("questions", [])
                await self._log(f"Form has {len(questions)} question(s)")

                # ── 2. Build multipart payload ─────────────────────────────
                # httpx accepts: files=[(name, value), (name, (fname, bytes, mime))]
                # Using files= forces multipart/form-data even for text fields.
                parts: list[tuple] = []
                llm_fields: list[tuple[str, str]] = []  # (field_name, label) needing an LLM answer

                for q in questions:
                    label = q.get("label", "")
                    for field in q.get("fields", []):
                        name = field.get("name", "")
                        ftype = field.get("type", "")
                        opts = field.get("values", [])

                        if ftype == "input_file":
                            # The file slot's true identity is on the field name
                            # (Greenhouse uses name="cover_letter"/"resume"); the
                            # question label can be generic, so check the name first
                            # and fall back to the label.
                            is_cover = "cover" in name.lower() or "cover" in label.lower()
                            if is_cover:
                                cl = self._cover_letter_bytes(profile)
                                if cl:
                                    parts.append((name, cl))
                            else:
                                fname, fbytes, fmime = self._resume_bytes(profile)
                                parts.append((name, (fname, fbytes, fmime)))
                            continue

                        value = self._resolve_static(name, label, ftype, opts, profile)
                        if value is _NEEDS_LLM:
                            llm_fields.append((name, label))
                        elif value:
                            parts.append((name, value))

                # Draft all free-text answers concurrently (was sequential per field).
                if llm_fields:
                    answers = await self._llm_answers([lbl for _, lbl in llm_fields], profile)
                    for (name, _), ans in zip(llm_fields, answers):
                        if ans:
                            parts.append((name, ans[:500]))

                # ── 3. Submit ──────────────────────────────────────────────
                await self._log(f"Submitting {len(parts)} field(s) to Greenhouse")
                post_resp = await client.post(
                    f"{_GH_API}/{board_token}/jobs/{job_id}",
                    files=parts,
                )
                if post_resp.status_code in (200, 201):
                    await self._log("✓ Application submitted successfully")
                    self._submitted = True
                else:
                    msg = f"Greenhouse submit returned {post_resp.status_code}: {post_resp.text[:300]}"
                    await self._log(msg)
                    raise RuntimeError(msg)

        except Exception as exc:
            await self._log(f"Error: {exc}")
            raise
        finally:
            await self.close()

    def _resolve_static(
        self,
        name: str,
        label: str,
        ftype: str,
        opts: list,
        profile: dict,
    ):
        """Map a Greenhouse field to a value without any network/LLM call.

        Returns a string value, None (skip), or the `_NEEDS_LLM` sentinel for
        free-text fields — the caller batches those LLM answers concurrently.
        """
        # Standard identity fields
        if name in _STANDARD:
            return _STANDARD[name](profile)

        ll = label.lower()

        # Cover letter as free-text field (some Greenhouse forms expose it that way)
        if "cover letter" in ll:
            cl = (profile.get("cover_letter_text") or "").strip()
            return cl[:5000] if cl else None

        # Profile links — match by label keyword
        if "linkedin" in ll:
            return profile.get("linkedin_url") or ""
        if any(x in ll for x in ("website", "portfolio", "personal site")):
            return profile.get("website") or ""
        if "github" in ll:
            return profile.get("github_url") or ""

        # Work authorization — always "Yes" for US applicants
        if any(x in ll for x in (
            "authorized", "authorization", "eligible to work",
            "legally permitted", "work in the us", "permitted to work",
        )):
            return self._pick_opt(opts, "yes") or "Yes"

        # Sponsorship — always "No"
        if any(x in ll for x in ("sponsor", "sponsorship", "require visa", "need visa")):
            return self._pick_opt(opts, "no") or "No"

        # EEOC diversity questions → decline / prefer not to answer
        if any(x in ll for x in ("gender", "race", "ethnicity", "veteran", "disability")):
            return (
                self._pick_opt(opts, "decline")
                or self._pick_opt(opts, "prefer not")
                or ""
            )

        # Free-text custom questions → defer to a batched LLM call by the caller
        if ftype == "input_text":
            return _NEEDS_LLM

        return None

    @staticmethod
    def _pick_opt(opts: list, keyword: str) -> str | None:
        """Return the first option value whose label contains `keyword`."""
        kw = keyword.lower()
        for o in opts:
            if kw in o.get("label", "").lower():
                return str(o.get("value", ""))
        return None
