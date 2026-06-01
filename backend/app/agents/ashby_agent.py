import json
import re
import logging
import httpx
from app.agents.base_api_agent import BaseAPIAgent

logger = logging.getLogger(__name__)

_GRAPHQL_URL = "https://jobs.ashbyhq.com/api/non-user-graphql"
_POSTING_API = "https://api.ashbyhq.com/posting-api/job-board"

# Returned by _resolve_static for free-text fields needing an LLM answer, so
# _build_submissions can batch those calls concurrently.
_NEEDS_LLM = object()

# Ashby system field paths → profile keys / static values
_SYSTEM_FIELDS: dict[str, callable] = {
    "_systemfield_name":         lambda p: (p.get("full_name") or "").strip(),
    "_systemfield_firstname":    lambda p: (p.get("full_name") or "").split(" ", 1)[0],
    "_systemfield_lastname":     lambda p: ((p.get("full_name") or "").split(" ", 1)[1:] or [""])[0],
    "_systemfield_email":        lambda p: p.get("portal_email") or p.get("email") or "",
    "_systemfield_phone":        lambda p: p.get("phone") or "",
    "_systemfield_linkedin_url": lambda p: p.get("linkedin_url") or "",
    "_systemfield_website_url":  lambda p: p.get("website") or "",
    "_systemfield_github_url":   lambda p: p.get("github_url") or "",
}

# GraphQL query used by the Ashby frontend to load an application form
_FORM_QUERY = """
query ApiApplicationFormQuery($jobPostingId: String!) {
  jobPosting(id: $jobPostingId) {
    id
    title
    applicationFormDefinition {
      sections {
        fields {
          path
          isRequired
          descriptionPlain
          type
          selectableValues { label value }
        }
      }
    }
  }
}
"""

# GraphQL mutation used by the Ashby frontend to submit an application
_SUBMIT_MUTATION = """
mutation SubmitApplicationMutation($input: SubmitApplicationInput!) {
  submitApplication(input: $input) {
    errors { message }
    jobApplicationId
  }
}
"""


def _parse_url(url: str) -> tuple[str, str] | None:
    """Extract (company_slug, job_id) from any Ashby job URL variant.

    Handles:
      - jobs.ashbyhq.com/{slug}/{job_id}
      - Company-hosted wrappers like example.com/jobs?ashby_jid={uuid} —
        the company subdomain is used as the slug.
    """
    m = re.search(r"jobs\.ashbyhq\.com/([^/?#]+)/([^/?#]+)", url)
    if m:
        return (m.group(1), m.group(2))

    m = re.search(r"[?&]ashby_jid=([\w-]+)", url)
    if m:
        job_id = m.group(1)
        domain_m = re.search(r"https?://(?:www\.)?([^./]+)\.", url)
        if domain_m:
            return (domain_m.group(1).lower(), job_id)

    return None


class AshbyAgent(BaseAPIAgent):
    """Applies to Ashby jobs via their non-user GraphQL API — no browser needed.

    Flow:
      1. Fetch form schema via GraphQL ApiApplicationFormQuery.
         Fallback: parse __NEXT_DATA__ from the job page HTML.
      2. Build fieldSubmissions list from profile + LLM for custom questions.
      3. Submit via GraphQL SubmitApplicationMutation.

    Note: Ashby's file-upload path requires a separate upload step that returns
    a handle; for now the resume is submitted as plain text in the resume field
    when available (Ashby also accepts LinkedIn profile in lieu of a file).
    """

    async def run(self, job_url: str, user_profile: dict | None = None):
        profile = user_profile or {}
        await self._connect()
        try:
            parsed = _parse_url(job_url)
            if not parsed:
                msg = f"Cannot parse Ashby URL: {job_url}"
                await self._log(msg)
                raise RuntimeError(msg)

            slug, job_id = parsed
            await self._log(f"Ashby API  slug={slug}  job={job_id}")

            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                # ── 1. Get form schema ─────────────────────────────────────
                fields = await self._get_form_fields(client, slug, job_id)
                if fields is None:
                    msg = f"Could not fetch Ashby form schema (slug={slug}, job={job_id})"
                    await self._log(msg)
                    raise RuntimeError(msg)
                await self._log(f"Form has {len(fields)} field(s)")

                # ── 2. Build field submissions ─────────────────────────────
                submissions = await self._build_submissions(fields, profile)
                await self._log(f"Built {len(submissions)} submission(s)")

                # ── 3. Submit via GraphQL ──────────────────────────────────
                payload = {
                    "operationName": "SubmitApplicationMutation",
                    "variables": {
                        "input": {
                            "jobPostingId": job_id,
                            "applicationForm": {
                                "fieldSubmissions": submissions,
                            },
                        }
                    },
                    "query": _SUBMIT_MUTATION,
                }
                resp = await client.post(
                    _GRAPHQL_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code != 200:
                    msg = f"Ashby submit returned {resp.status_code}: {resp.text[:300]}"
                    await self._log(msg)
                    raise RuntimeError(msg)

                data = resp.json()
                errors = (
                    data.get("data", {})
                    .get("submitApplication", {})
                    .get("errors") or []
                )
                if errors:
                    msgs = "; ".join(e.get("message", "") for e in errors)
                    await self._log(f"Ashby returned errors: {msgs}")
                    raise RuntimeError(f"Ashby rejected application: {msgs}")
                app_id = (
                    data.get("data", {})
                    .get("submitApplication", {})
                    .get("jobApplicationId", "")
                )
                await self._log(f"✓ Application submitted (id={app_id})")
                self._submitted = True

        except Exception as exc:
            await self._log(f"Error: {exc}")
            raise
        finally:
            await self.close()

    # ── Form schema fetching ─────────────────────────────────────────────────

    async def _get_form_fields(
        self, client: httpx.AsyncClient, slug: str, job_id: str
    ) -> list[dict] | None:
        """Try GraphQL first, fall back to __NEXT_DATA__ HTML parsing."""
        fields = await self._fetch_via_graphql(client, job_id)
        if fields is not None:
            return fields
        return await self._fetch_via_next_data(client, slug, job_id)

    async def _fetch_via_graphql(
        self, client: httpx.AsyncClient, job_id: str
    ) -> list[dict] | None:
        try:
            resp = await client.post(
                _GRAPHQL_URL,
                json={
                    "operationName": "ApiApplicationFormQuery",
                    "variables": {"jobPostingId": job_id},
                    "query": _FORM_QUERY,
                },
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code != 200:
                return None
            sections = (
                resp.json()
                .get("data", {})
                .get("jobPosting", {})
                .get("applicationFormDefinition", {})
                .get("sections", [])
            )
            fields: list[dict] = []
            for section in sections:
                fields.extend(section.get("fields", []))
            return fields if fields else None
        except Exception as exc:
            logger.debug("Ashby GraphQL form fetch failed: %s", exc)
            return None

    async def _fetch_via_next_data(
        self, client: httpx.AsyncClient, slug: str, job_id: str
    ) -> list[dict] | None:
        """Parse __NEXT_DATA__ from the job page as a fallback."""
        try:
            resp = await client.get(f"https://jobs.ashbyhq.com/{slug}/{job_id}")
            if resp.status_code != 200:
                return None
            m = re.search(
                r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
                resp.text,
                re.DOTALL,
            )
            if not m:
                return None
            next_data = json.loads(m.group(1))
            sections = (
                next_data.get("props", {})
                .get("pageProps", {})
                .get("jobPosting", {})
                .get("applicationFormDefinition", {})
                .get("sections", [])
            )
            fields: list[dict] = []
            for section in sections:
                fields.extend(section.get("fields", []))
            return fields if fields else None
        except Exception as exc:
            logger.debug("Ashby __NEXT_DATA__ parse failed: %s", exc)
            return None

    # ── Submission building ──────────────────────────────────────────────────

    async def _build_submissions(
        self, fields: list[dict], profile: dict
    ) -> list[dict]:
        submissions: list[dict] = []
        llm_fields: list[tuple[str, str]] = []  # (path, label) needing an LLM answer
        for field in fields:
            path = field.get("path", "")
            ftype = field.get("type", "")
            label = field.get("descriptionPlain", "")
            opts = field.get("selectableValues", [])

            value = self._resolve_static(path, label, ftype, opts, profile)
            if value is _NEEDS_LLM:
                llm_fields.append((path, label))
            elif value is not None and value != "":
                submissions.append({"path": path, "value": value})

        # Draft all free-text answers concurrently (was sequential per field).
        if llm_fields:
            answers = await self._llm_answers([lbl for _, lbl in llm_fields], profile)
            for (path, _), ans in zip(llm_fields, answers):
                if ans:
                    submissions.append({"path": path, "value": ans[:2000]})

        return submissions

    def _resolve_static(
        self,
        path: str,
        label: str,
        ftype: str,
        opts: list,
        profile: dict,
    ):
        """Resolve an Ashby field without any LLM call. Returns a value, None
        (skip), or the `_NEEDS_LLM` sentinel for free-text fields."""
        # System fields — direct profile mapping
        if path in _SYSTEM_FIELDS:
            return _SYSTEM_FIELDS[path](profile)

        # Resume field — submit as plain text (file handle requires a separate
        # upload step which needs a dedicated endpoint; text is accepted as fallback)
        if path == "_systemfield_resume":
            text = profile.get("tailored_resume_text") or profile.get("resume_text") or ""
            return text[:8000] if text else None

        if path == "_systemfield_cover_letter":
            cl = (profile.get("cover_letter_text") or "").strip()
            return cl[:8000] if cl else None

        ll = label.lower()

        if "cover letter" in ll:
            cl = (profile.get("cover_letter_text") or "").strip()
            return cl[:8000] if cl else None

        # Work authorization
        if any(x in ll for x in ("authorized", "authorization", "eligible", "permitted to work")):
            return self._pick_opt(opts, "yes") or "Yes"

        # Sponsorship
        if any(x in ll for x in ("sponsor", "sponsorship", "visa")):
            return self._pick_opt(opts, "no") or "No"

        # EEOC / diversity → decline
        if any(x in ll for x in ("gender", "race", "ethnicity", "veteran", "disability")):
            return self._pick_opt(opts, "decline") or self._pick_opt(opts, "prefer not") or ""

        # Single-select: pick first option whose label matches a keyword
        if ftype in ("Select", "MultiSelect") and opts:
            return None  # Can't safely guess non-EEO selects

        # Free-text custom questions → defer to a batched LLM call by the caller
        if ftype in ("LongText", "ShortText", "Textarea", "String"):
            return _NEEDS_LLM

        return None

    @staticmethod
    def _pick_opt(opts: list, keyword: str) -> str | None:
        kw = keyword.lower()
        for o in opts:
            if kw in o.get("label", "").lower():
                return str(o.get("value", o.get("label", "")))
        return None
