# A3 — Resume / Profile · status

Owner: Resume/Profile Engineer. Scope (edit/create ONLY):
`services/resume_tailor.py`, `api/routes/profile.py`, `api/routes/tailored_resumes.py`,
NEW `services/resume_parser.py`, NEW `services/jd_extractor.py`, this file.

## State: DONE (pending Foundation migration to fully persist)

All five files implemented, byte-compile clean, pure-logic smoke-tested, route
modules import and register correctly.

## Checklist
- [x] `_generate` + `_parse_json` signatures left FROZEN (only added rules to the
      `tailor_resume` system prompt; new code imports them, never redefines).
- [x] **resume_parser.py** (NEW)
  - `extract_text_from_upload(filename, data)` — PDF (pypdf) + DOCX (python-docx),
    routes by extension, cross-fallback. Returns "" on failure.
  - `parse_resume_text(text)` / `parse_resume_file(filename, data)` → structured
    draft via `_generate`. **Never raises** — returns an empty-but-shaped draft on
    any failure. `parse_resume_file` also returns recovered `resume_text`.
  - Draft shape: `contact{full_name,email,phone,location,linkedin_url,github_url,website_url}`,
    `summary`, `work_experience[]`, `education[]`, `skills[]`, `projects[]`, `certifications[]`.
  - `load_structured_profile(user)` / `has_structured_profile(user)` / `empty_profile()`
    read the saved profile back off the User row (defensive: works before columns exist;
    accepts JSON or JSON-encoded-Text storage).
- [x] **jd_extractor.py** (NEW)
  - `fetch_url_text(url)` — httpx (browser headers, redirects, HTML→text) → Playwright
    Chromium `wait_for_load_state("networkidle")` fallback when the httpx result is thin.
  - `extract_jd_from_text(text)` → `{job_title,company,location,job_description}` via `_generate`.
  - `jd_from_url(url)` orchestrates + in-process LRU-ish cache (256). **Never raises.**
- [x] **resume_tailor.py** (edit)
  - Strengthened `tailor_resume` prompt: ATS formatting (single-column/no-tables/standard
    headings/keyword mirroring) + India conventions (Indian English, INR/LPA never USD).
  - `tailor_from_profile(profile, jd)` — renders the structured base profile to text then
    tailors (grounded; base profile is source of truth).
  - `profile_to_resume_text(profile)` — structured dict → clean ATS resume text.
  - `score_ats(resume, keywords)` → `{coverage_pct, matched, missing, required_missing}`
    (deterministic string match over required+preferred+keywords; no AI call).
- [x] **profile.py** (edit)
  - `GET /profile` now returns scalar contact fields + structured sections.
  - `PUT /profile` saves scalars to columns + summary + sections (JSON-serialised to Text).
  - NEW `POST /profile/import-resume` — upload PDF/DOCX → parsed structured DRAFT (returned
    for review, NOT auto-saved); recovered `resume_text` IS saved immediately.
  - Existing `/profile/upload-resume` + `/parse-pdf` left unchanged (PDF-only).
- [x] **tailored_resumes.py** (edit)
  - `QuickTailorRequest`: `resume_text` now optional + new `job_url`; requires
    `job_description` OR `job_url`; resume source defaults to saved base profile
    (structured profile preferred, else profile `resume_text`).
  - `quick_tailor` auto-extracts JD from `job_url`, tailors grounded, stores `job_url`.
  - `TailoredResumeDetail` gains `ats_score` (computed from keywords + tailored text).
  - NEW `POST /tailored-resumes/extract-jd` — JD preview from a URL.

## Requests for Foundation (model-field dependencies — WORKSTREAMS #6)
Code is written defensively (getattr/setattr) so it runs now, but these fields only
**persist** once the migration + model land:

1. **`users` — confirm column TYPE = `Text` for the structured sections.** I store
   `work_experience`, `education`, `skills`, `projects`, `certifications` as
   **`json.dumps(...)` strings**. `load_structured_profile` reads both `Text(JSON-string)`
   and native `JSON`, but writes assume Text. If you make them native `JSON` columns
   instead, tell me and I'll drop the `json.dumps` on write.
2. **`users` — ADD a `summary` Text column.** Not in the #6 list but required by the
   parsed/structured profile (PLAN Phase 3b lists it). Until added, `summary` round-trips
   in the API response but does not persist.
3. **`tailored_resumes.job_url String(1024)`** — already in #6; `quick_tailor` writes it
   and `GET /tailored-resumes/{id}` reads it. Just confirm it lands.
4. **Routers**: `profile` and `tailored_resumes` routers already exist/registered — no new
   router from A3 (resume_parser/jd_extractor are services). Nothing to wire in `main.py`.

## Packages: none needed
playwright, httpx, pypdf, python-docx are all already in requirements.txt. No additions.

## Notes / blocked on: nothing blocking
- End-to-end tailoring + JD-fetch need a live OpenAI key + network; verified the pure
  helpers (`score_ats`, `profile_to_resume_text`, `_html_to_text`) and all imports/routes.
- `_OPENAI_MODEL` in resume_tailor is `gpt-4.1` (pre-existing); `_generate`'s `model`
  default param is the frozen signature — left untouched.
