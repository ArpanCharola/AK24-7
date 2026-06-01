# A4 — Gmail / Comms / Copilot

Owner: A4 agent. Files: `email_classifiers.py`, `application_tracker.py`,
`gmail_client.py`, `gmail_labels.py`, `contact_finder.py`,
`api/routes/auth.py`; NEW `api/routes/copilot.py`, `services/copilot.py`.

## Checklist
- [x] **email_classifiers.py — India accuracy** (ADD-only label safety preserved)
  - `_AGGREGATOR_DOMAINS` += foundit.in, monsterindia.com, timesjobs.com, apna.co, internshala.com, glassdoor.co.in
  - `_ASSESSMENT_DOMAINS` += doselect.com, wheebox.com, cocubes.com
  - `_ATS_DOMAINS` += keka.com, darwinbox.com, darwinbox.in, zohorecruit.com, freshteam.com, peoplestrong.com
  - Assessment primary regex += doselect|wheebox|cocubes|amcat|aspiringminds
  - Indian-English confirmations (`your candidature`, `profile has been received`, …) accepted in `is_genuine_application` **only when a job-context signal is also present** (`_has_job_context`) — keeps precision.
  - India anchors added to `build_scan_query`.
- [x] **application_tracker.py — India context**
  - `_JOB_CONTEXT` += `candidature` and a `ctc|lpa|notice period|in-hand` pattern.
  - `_NON_JOB_APPLICATION` += `emi|upi|kyc|pan|aadhaar|aadhar` (insurance already present).
  - India confirmation anchors added to `_APPLICATION_PHRASES` (body-search recall; second-signal classify() still gates precision).
- [x] **gmail_client.py — scopes**
  - `SCOPES` now = openid, userinfo.email, **userinfo.profile** (was missing), gmail.modify, gmail.send.
  - Added `BASIC_SCOPES` (identity only) + `login_redirect_uri()`; `build_flow`/`authorization_url`/`exchange_code` take optional `scopes`/`redirect_uri` overrides.
- [x] **auth.py — Google Sign-In**
  - `GET /api/auth/google` → 302 to Google consent with BASIC scopes (no Gmail access).
  - `GET /api/auth/google/callback` → find-or-create user by Google email, issue app JWT, redirect to `FRONTEND_URL/login?token=...`. Stores **no** Gmail tokens (Gmail stays gated behind the separate Connect-Gmail consent in the email router).
- [x] **copilot.py (service) + routes/copilot.py — Orion**
  - `copilot.chat(user, messages, job=None)` over `_generate()`; context = profile + optional focused `DiscoveredJob` (new salary/why-fit/missing-skills columns read via `getattr` so it works before/after Foundation's migration). Capabilities: explain fit, interview prep, skill-gap advice; India/LPA framing; grounded (no invented facts).
  - `POST /chat` (mount suggested at `/api/copilot`). Body: `{messages[], message?, job_id?}` → `{reply}`.
- [x] **contact_finder.py — free sources (Apify dropped)**
  - Tiers: (1) JD regex → (2) LLM named recruiter → (3) **public careers/about/team/contact page fetch** (free httpx, opt-in via `deep`/legacy `use_apify`) → (4) generic `careers@domain` guess.
  - `draft_outreach(job, contact)` drafts a short grounded outreach email via `_generate()`. `find_contact(..., with_draft=True)` attaches it.
  - Signature kept route-compatible: `find_contact(job, *, deep=False, use_apify=False, with_draft=False)` — the existing `/discovered-jobs/{id}/find-contact` route (passes `use_apify`) still works; `use_apify=True` now triggers the free public-page fetch instead of paid Apify.

## Verified
- `py_compile` clean on all 7 files.
- Behavioral tests pass: India aggregator veto; doselect/keka/darwinbox bucketing; candidature/profile-received gated correctly; KYC/EMI/PAN/Aadhaar non-job rejection; CTC/LPA job-context; genuine confirmation NOT mis-flagged as non-job; contact domain inference (skips ATS/boards), on-domain email preference, blocklist filtering.
- (Sandbox lacks `pydantic_settings`/`httpx`/`google-*` so full-import runtime tests of tracker/contact_finder were validated against extracted logic.)

## Requests for Foundation (files I don't own)
1. **Register the copilot router** in `main.py` (contract #7): `app.include_router(copilot.router, prefix="/api/copilot", tags=["copilot"])` + add `copilot` to the routes import line.
2. **Config + OAuth redirect URIs:** add `GOOGLE_LOGIN_REDIRECT_URI: str = "http://localhost:8000/api/auth/google/callback"` to `config.py` and `.env.example`. (gmail_client falls back to deriving it from `GOOGLE_REDIRECT_URI` if unset, so this is not blocking.) In the AK24/7Jobs Google Cloud OAuth client, register **both** redirect URIs: `/api/email/callback` and `/api/auth/google/callback`. Consent screen must list `userinfo.profile` (now in SCOPES).
3. **Verify-prompt India line** (out of my file allowlist): `services/label_ai.py` and `services/application_ai.py` `_SYSTEM_PROMPT`s should get one India line. Suggested:
   - label_ai: *"Indian-English wording is common: 'your candidature', 'shortlisted', 'assessment link' from platforms like DoSelect/Wheebox/CoCubes count. Salaries appear as CTC/LPA."*
   - application_ai: *"Indian-English acknowledgements like 'we have received your candidature' or 'your profile has been received for the <role>' count as genuine job-application confirmations; CTC/LPA/notice-period signal job context."*
4. **Apify cleanup (non-urgent):** `contact_finder.py` no longer uses Apify. `APIFY_TOKEN` / `APIFY_CONTACT_ACTOR_ID` in `config.py`/`.env` are now unused and can be removed when convenient.

## Notes for other streams
- A5 (frontend): "Sign in with Google" button links to `GET /api/auth/google`; on return read `?token=` from `/login`. Copilot UI hits `POST /api/copilot/chat`.
- The job-detail route can surface an outreach draft by passing `with_draft=true` to `find_contact` or calling `contact_finder.draft_outreach(job, contact)`; `/api/email/compose` (discovered_job_id) already drafts outreach too.

## Blocked on
- Nothing blocking. Copilot endpoint is live once Foundation registers the router.
