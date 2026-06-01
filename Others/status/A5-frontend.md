# A5 — Frontend (AK24/7Jobs) status

Owner: Frontend agent. Edits ONLY `frontend/**` + this file.

## Current state
Rebrand + India job-search UX built against the documented PLAN.md routes. All new
server calls go through `services/api.js`, wired with TanStack Query, and **degrade
gracefully (treat 404 as empty / show a friendly message) while the backends land**.

## Done
- [x] **api.js** endpoints
  - `profileApi.importResume(file)` → `POST /profile/import-resume`
  - `tailoredResumesApi.extractJd(jobUrl)` → `POST /tailored-resumes/extract-jd`
  - `tailoredResumesApi.quick()` now sends `job_url`
  - `matchesApi.feed({location,minScore,postedWithinDays,sort})` → `GET /matches/feed`; `matchesApi.refresh()` → `POST /matches/refresh`
  - `copilotApi.chat({message,job_id?,history?})` → `POST /copilot/chat`; `copilotApi.history()` → `GET /copilot/history`
  - public job search default location `United States` → `India`
- [x] **Hooks**: `useMatches`/`useRefreshMatches`, `useCopilotChat`/`useCopilotHistory`, `useImportResume` (in useProfile), `useExtractJd` (in useTailoredResumes). 404-tolerant.
- [x] **Dashboard.jsx** → discovery/matches feed. `JobMatchCard` shows score ring, why-fit, skill-gap chips, salary (LPA), notice period, work arrangement, source. India location chips (All India + 7 cities/Remote), score filter (All/60+/80+), sort (Best match / Most recent). Loading / empty / error states. Cards deep-link to Tailor (`/tailored-resumes?job_url=`) and Ask Orion (`/copilot?job_id=`).
- [x] **Profile.jsx** → Import-from-resume (upload → parse → review → Save) + manual section editors: Personal/summary, Career details (current/expected CTC LPA, notice period, work auth, preferred locations), Skills (tag input), Work experience, Education, Projects, Certifications. Kept base-resume (raw text) upload + Gmail connect. Dropped USA auto-apply/portal credentials. New components: `components/Profile/TagInput`, `components/Profile/RepeatableSection`. Form seeds from profile ONCE so an interim save the backend doesn't round-trip won't wipe edits.
- [x] **TailoredResumes.jsx** → "Paste JD | Job link" toggle + Fetch-JD preview (editable) + base-resume picker (profile/upload/paste, unchanged) + ATS score badge (`detail.ats_score`) on header & Keywords tab + missing-keyword chips (`detail.missing_keywords`). Sends `job_url` on quick-tailor. Honors `?job_url=` deep-link.
- [x] **Copilot.jsx** (new) → Orion chat UI: message thread, suggestion chips, typing indicator, job-focus via `?job_id=`. Route `/copilot` (PrivateRoute) + sidebar nav "Orion Copilot".
- [x] **Rebrand** "AI Apply" → "AK24/7Jobs" across Sidebar, AppLayout, Navbar, Login (headline/pitch/features → India job-search), PublicJobs, ConsentGate, index.html `<title>`. Currency framed as INR/LPA. **Left `Labels.jsx` `"AI Apply/*"` keys untouched — those are functional Gmail label IDs (contract #7, ADD-only).**
- [x] `npm run build` passes.

## Contracts I depend on (Foundation/route agents to provide)
1. `GET /matches/feed` → list of DiscoveredJob-shaped rows with `match_score`, `match_explanation` (or `match_reason`), `missing_skills` (JSON list / comma string / array all handled), `salary_lpa`, `salary_raw`, `notice_period`, `work_arrangement`, `posted_at`, `job_url`, `title`, `company`, `location`, `source`, `id`. `POST /matches/refresh`.
2. `POST /profile/import-resume` (multipart `file`) → structured `{ full_name, phone, location, summary, skills[], work_experience[], education[], projects[], certifications[], linkedin_url, github_url, website_url, resume_text? }`.
3. `PUT /profile` should accept + persist structured fields: `summary`, `skills`, `work_experience`, `education`, `projects`, `certifications`, `current_ctc_lpa`, `expected_ctc_lpa`, `notice_period`, `work_authorization`, `preferred_locations`. (Sent as JSON arrays/objects.) `GET /profile` should return them so the form can seed.
4. `POST /tailored-resumes/extract-jd` body `{ job_url }` → `{ job_description, job_title?, company? }`.
5. `POST /tailored-resumes/quick` accept optional `job_url`; `GET /tailored-resumes/{id}` add `ats_score` (number) + `missing_keywords` (string[]).
6. `POST /copilot/chat` body `{ message, job_id?, history:[{role,content}] }` → `{ reply }` (also accepts `message`/`content`). Optional `GET /copilot/history`.

## Blocked on / requests for Foundation
- None blocking — UI renders with mock/empty data today. Live data needs the routes above (built in parallel by A2/A3/A4 + registered in main.py by Foundation).

## Notes
- No backend files touched. TanStack Query for all server state; Tailwind only; pages thin (logic in hooks/components).
