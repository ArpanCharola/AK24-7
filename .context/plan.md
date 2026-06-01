# AI-Powered Job Application Agent: Full-Stack Technical Plan (v4)

## 1. Project Overview
A SaaS platform with a React frontend and FastAPI backend that runs autonomous AI agents.
The system discovers jobs, scores them against the user's profile, and applies automatically.
A WebSocket bridge handles real-time Human-in-the-Loop interactions (OTPs).

---

## 2. Technical Stack

| Layer | Technology |
|---|---|
| Frontend | React (Vite), Tailwind CSS, TanStack Query |
| Backend | FastAPI (async Python 3.12+) |
| Task orchestration | Celery + Redis |
| Database | PostgreSQL (SQLAlchemy async) |
| Browser engine | Playwright (headless/headed toggle) |
| AI model | **OpenAI — `gpt-4o`** via the Chat Completions endpoint |
| Proxy | Residential Proxy API (USA-based, optional) |

**OpenAI is the single AI provider.** One env var (`OPENAI_API_KEY`) drives:
- Job description keyword extraction
- Resume section tailoring
- Custom question answer drafting
- Cover letter generation (Phase 6B)
- Job match scoring (LLM portion of the hybrid score)

Provider history: started as local Mistral (too slow on dev hardware) → moved to Groq Cloud `llama-3.1-8b-instant` (fast and cheap but quality was inconsistent for nuanced JD analysis and cover letters) → now on OpenAI `gpt-4o` for higher-quality structured output. The `_generate()` helper signature is unchanged across migrations; only URL, model constant, and env var name swap.

---

## 3. Architecture & Data Flow

### A. Autonomous Job Discovery + Auto-Apply Flow
```
User defines JobSearchProfile (auto_apply_threshold, auto_apply_mode)
    → Celery Beat triggers scheduled_discovery (every 4 hours)
    → Fans out to discover_jobs_task per active profile
    → JobDiscoveryAgent hits Greenhouse/Lever/Ashby APIs + scrapes iCIMS/Workday
    → DiscoveredJob rows saved (unscored) for fast UI feedback
    → JobScorer (hybrid: regex skill match + OpenAI LLM) scores each 0-100
    → For each job with score ≥ threshold, run the auto-apply gate (Phase 6):
        1. User.auto_apply_enabled? else stop
        2. Today's auto-applies < daily_auto_apply_cap? else stop
        3. No existing JobApplication for (user_id, job_url)? else stop
        4. Profile.auto_apply_mode == "auto"?
              → create JobApplication(queued_by="auto") + dispatch run_application_task
           Profile.auto_apply_mode == "review"?
              → mark DiscoveredJob.status = "auto_queued" (user clicks Approve to dispatch)
    → Jobs below threshold sit in the Discovered Jobs feed for manual review
```

### B. Manual Apply Flow
```
User pastes URL on Dashboard
    → POST /api/apply → JobApplication created → run_application_task queued
    → _detect_portal() routes by URL → API agent (Greenhouse/Lever/Ashby)
        or Playwright agent (SmartApplyAgent for Workday/iCIMS/unknown)
    → ResumeTailor (OpenAI) extracts keywords + tailors resume before agent runs
    → Tailored text stored in TailoredResume, passed to agent
    → WS streams logs + screenshots to AgentConsole
```

### C. OTP / HITL Bridge
```
Agent hits OTP wall
    → Publishes require_otp to Redis
    → WS pushes to React OTPModal
    → User submits OTP → POST /api/otp/submit → Redis key set
    → Agent reads key, resumes
```

---

## 4. Database Schema

### Core models (current)
- `User` — auth + profile + career_history + resume_text + portal credentials + github_url + website_url
- `JobApplication` — url, title, company, status, portal_type, celery_task_id, agent_log, error_message
- `TailoredResume` — keywords_extracted + modifications_summary, FK to application
- `JobSearchProfile` — target_roles, locations, keywords, excluded_companies, work_arrangements, posted_within_days, experience_level, auto_apply_threshold, is_active, last_run_at
- `DiscoveredJob` — job_url (unique per user), title, company, location, job_description, source, work_arrangement, posted_at, match_score, match_reason, status

### Phase 6 additions (planned)
- `User.auto_apply_enabled` (Bool, default False) — master switch; must be true before any auto-queue happens
- `User.daily_auto_apply_cap` (Int, default 5) — hard upper bound per 24h
- `JobSearchProfile.auto_apply_mode` (Enum: `"auto"`, `"review"`, default `"review"`)
- `DiscoveredJob.status` gains `"auto_queued"` value (waiting on user approval)
- `DiscoveredJob.scored_at` (DateTime, nullable) — avoids re-scoring within 7 days
- `JobApplication.queued_by` (Enum: `"manual"`, `"auto"`, default `"manual"`) — audit + UI badge
- `CoverLetter` — new table: `id, user_id, application_id (FK), content (Text), generated_at`

### Migrations
- `10863820fde7_initial_schema_with_work_arrangement_` — initial schema
- `de46f82dc80b_add_github_url_and_website_url_to_users` — profile URL fields
- Phase 6 will add one migration per sub-phase (6A schema, 6B cover_letter, 6D scored_at)

---

## 5. AI Logic — OpenAI

**Endpoint:** `https://api.openai.com/v1/chat/completions`
**Model:** `gpt-4o`
**Shared helper:** `_generate(system, user, max_tokens)` in [resume_tailor.py](../backend/app/services/resume_tailor.py) — `temperature=0`, JSON parsed via regex fallback (`re.search(r"\{.*\}", text, re.DOTALL)`).

Phase 6 will wrap `_generate` with a shared semaphore (max ~5 concurrent) + exponential backoff on 429 + 5xx so the discovery loop doesn't melt on rate limits. With `gpt-4o` (slower + pricier than the prior Groq llama-3.1-8b), this matters more — typical tailor call now ~2-4s vs ~500ms previously.

### ResumeTailor
- `extract_keywords(jd)` → `{required_skills, preferred_skills, years_experience, deal_breakers, keywords}`
- `tailor_resume(resume, jd, career_history)` → rewritten resume text (Phase 6D renames from `tailor_resume_section`; the input has always been the full resume)
- `draft_custom_answer(question, career_history)` → 2-4 sentence answer
- `draft_cover_letter(jd, company, role, career_history)` → full cover letter (Phase 6B — new). Stored as `CoverLetter` row, plumbed to agents via `user_profile["cover_letter_text"]`.

### JobScorer (hybrid)
- Deterministic regex skill match (40 pts max) + experience-level alignment (20 pts max) + OpenAI LLM role-fit score (40 pts max) − title-relevance penalty
- Returns `{score: int (0-100), reason: str}` with a human-readable reason combining skill coverage + LLM justification
- Phase 6D adds `DiscoveredJob.scored_at` so re-runs skip jobs scored within 7 days when JD unchanged

### Resume Builder (external, integrating in Phase 6C)
- A separate standalone resume builder project outputs tailored PDFs
- Integration contract: builder returns `resume_pdf_bytes` per `(user_id, job_id)` request
- `base_api_agent._resume_bytes()` will prefer PDF bytes; the current plaintext path is a fallback only

---

## 6. Implementation Status

### Phase 1: Database & Core API ✅ COMPLETE
- SQLAlchemy async models for all entities
- JWT + bcrypt auth
- Routes: /auth, /apply, /status, /applications, /otp/submit, /profile

### Phase 2: Agentic Worker ✅ COMPLETE
- `BasePortalAgent` (Playwright launch, proxy, stealth, screenshot streaming)
- `WorkdayAgent` (multi-step form flow, AI textarea answers)

### Phase 3: OTP & WebSocket Bridge ✅ COMPLETE
- Redis pub/sub → WebSocket → React AgentConsole
- OTPModal triggered by `require_otp` event
- POST /api/otp/submit resumes agent via Redis key

### Phase 4: AI Integration ✅ COMPLETE
- ResumeTailor wired into `run_application_task` ([tasks.py:80-108](../backend/app/workers/tasks.py))
- TailoredResume row written per application when JD + resume_text exist
- Portal detection `_detect_portal()` covers workday/icims/greenhouse/ashby/lever/adp/oracle
- **AI provider:** OpenAI `gpt-4o` (previously Groq llama-3.1-8b-instant; before that local Mistral)

### Phase 5: Autonomous Job Discovery ✅ COMPLETE

**Discovery sources:** Greenhouse, Lever, Ashby (HTTP APIs); iCIMS, Workday (Playwright scrape). No Indeed/Glassdoor.

| ATS | Mechanism |
|---|---|
| **Greenhouse** | `GET https://boards-api.greenhouse.io/v1/boards/{slug}/jobs` (JSON API) |
| **Lever** | `GET https://api.lever.co/v0/postings/{slug}?mode=json` (JSON API) |
| **Ashby** | `GET https://api.ashbyhq.com/posting-api/job-board/{slug}` (JSON API) |
| **iCIMS** | Playwright scrape |
| **Workday** | Playwright scrape |

Company slugs live in [company_slugs.json](../backend/app/data/company_slugs.json) and are user-extendable.

**Shipped files:**
- Models: `job_search_profile.py`, `discovered_job.py`
- Agents: `job_discovery_agent.py`, `greenhouse_agent.py`, `lever_agent.py`, `ashby_agent.py`, `smart_apply_agent.py`, `universal_agent.py`, `base_api_agent.py`
- Services: `job_scorer.py` (hybrid scoring)
- Tasks: `scheduled_discovery` (Beat trigger) + `discover_jobs_task` (per profile)
- Routes: `job_searches.py`, `discovered_jobs.py`
- Frontend: `JobPreferences.jsx`, `DiscoveredJobs.jsx`, `useJobSearches.js`, `useDiscoveredJobs.js`
- Layout: `Sidebar.jsx`, `AppLayout.jsx`

**Celery Beat:**
```python
beat_schedule = {
    "scheduled-discovery-every-4h": {
        "task": "scheduled_discovery",
        "schedule": crontab(minute=0, hour="*/4"),
    },
}
```

### Phase 6: AI Auto-Apply Revisit ✅ SHIPPED (6A, 6B, 6D); 🚧 6C pending external builder

**Why this exists:** Phase 5 documented auto-apply but the queue gate was never built. `auto_apply_threshold` was read and then ignored. Phase 6 wired up the missing gate, added AI cover letters, and prepped the resume builder integration point. Migration: `a1b2c3d4e5f6_phase6_auto_apply_and_cover_letter`.

#### Phase 6A — Auto-Apply Queue Gate ✅
1. Migration: add `User.auto_apply_enabled` (Bool, default False), `User.daily_auto_apply_cap` (Int, default 5), `JobSearchProfile.auto_apply_mode` (Enum: `"auto"|"review"`, default `"review"`), `DiscoveredJob.status` accepts `"auto_queued"`, `JobApplication.queued_by` (Enum: `"manual"|"auto"`, default `"manual"`)
2. In `_run_discovery`, after the scoring loop, for each job with `score ≥ profile.auto_apply_threshold`:
   - Stop if `user.auto_apply_enabled` is False (explicit consent gate)
   - Stop if today's auto-applied count for the user ≥ `daily_auto_apply_cap`
   - Stop if any `JobApplication` exists for `(user_id, job_url)` (dedupe across manual + auto)
   - If `profile.auto_apply_mode == "review"`: set `DiscoveredJob.status = "auto_queued"` — UI surfaces these in the Discovered Jobs feed with a one-click "Approve & Apply" button (which calls the existing `/queue` endpoint)
   - If `profile.auto_apply_mode == "auto"`: create `JobApplication(queued_by="auto")` and dispatch `run_application_task` immediately
3. Audit log: every auto-queue decision (queued / skipped / capped / duplicate) emits a structured log line for observability
4. API: extend `/api/profile` to include the new User fields; extend `/api/job-searches` PUT to accept `auto_apply_mode`
5. UI:
   - Profile page: master "Enable auto-apply" toggle + "Daily cap" input
   - JobPreferences page: per-profile `auto_apply_mode` radio (Review-first vs Fully auto)
   - DiscoveredJobs page: new pill "Auto-queued — needs review" with Approve / Skip buttons
   - ApplicationFeed: "🤖 Auto" badge on auto-queued items

#### Phase 6B — Cover Letter Generation ✅
1. New `CoverLetter` model: `id, user_id, application_id (FK), content (Text), generated_at`
2. New method `ResumeTailor.draft_cover_letter(jd, company, role, career_history) -> str`
3. Called in `_run_application` after resume tailoring; stores `CoverLetter` row; populates `user_profile["cover_letter_text"]`
4. Agent integration:
   - SmartApplyAgent: detect cover-letter textareas (name/label matches `cover`, `letter`, `motivation`) → fill with `cover_letter_text`
   - GreenhouseAgent / LeverAgent / AshbyAgent: add `cover_letter` to multipart payload (all three APIs accept it)
5. API: `GET /api/applications/{id}/cover-letter` to read, `POST /api/applications/{id}/cover-letter/regenerate` to retry

#### Phase 6C — Resume Builder Integration ✅

Integrated `skilluence/resume-formatter` in-process. New service [resume_builder.py](../backend/app/services/resume_builder.py) imports the formatter's `structure_resume`, `format_compact`, and DOCX→PDF converter via `sys.path` (formatter repo stays standalone with its own UI). Pipeline runs after `tailor_resume()` in [_run_application](../backend/app/workers/tasks.py): tailored text → gpt-4o-mini structuring → Calibri/cobalt-blue compact ATS DOCX → docx2pdf (Windows) or LibreOffice (Linux) → PDF bytes. The bytes are persisted at `backend/uploads/resumes/application_{id}.pdf` and the path saved to `TailoredResume.tailored_resume_path`. `user_profile["resume_pdf_bytes"]` flows through to all four ATS agents (Greenhouse, Lever, Ashby, SmartApply), which now upload real PDFs via [base_api_agent._resume_bytes()](../backend/app/agents/base_api_agent.py) and [base_portal_agent._upload_resume()](../backend/app/agents/base_portal_agent.py). On any failure (formatter path unset, OpenAI hiccup, no Word/LibreOffice) the function returns None and agents fall back to plaintext — non-blocking. Configured via `RESUME_FORMATTER_PATH` in [.env](../backend/.env).
1. Define interface contract with the external resume builder: input `(user_id, job_description)`, output `resume_pdf_bytes: bytes`
2. Refactor `base_api_agent._resume_bytes()` ([base_api_agent.py:59-66](../backend/app/agents/base_api_agent.py)) — prefer `user_profile["resume_pdf_bytes"]`, fall back to plaintext only if absent
3. SmartApplyAgent's `_upload_resume` accepts the PDF for `input[type='file']` portals
4. `TailoredResume` model becomes a pointer to the builder artifact + extracted keywords; `modifications_summary` repurposed or dropped (decision deferred until builder API is finalised)

#### Phase 6D — Pipeline Hardening ✅
1. Dedupe: pre-flight check `(user_id, job_url)` against `JobApplication` before any Celery dispatch (manual or auto path)
2. OpenAI rate-limit handling: shared semaphore (5 concurrent) + exponential backoff on 429/5xx in `_generate`. Currently a single non-2xx raises `RuntimeError` and fails the whole task
3. Scoring cache: add `DiscoveredJob.scored_at` so re-runs skip jobs with a fresh score (<7 days) when JD unchanged
4. Rename `tailor_resume_section` → `tailor_resume` (input is the full resume, name is misleading)
5. Drop stale "local Mistral" comment at [tasks.py:80](../backend/app/workers/tasks.py)
6. Fix the discovery loop's destructive re-scoring: currently `_run_discovery` deletes all prior `"discovered"` and `"skipped"` rows on each run, which throws away the score history. Switch to upsert keyed on `(user_id, job_url)` and only refresh fields that changed

---

### Phase 7: Production Hardening 📋 NEXT
(Formerly Phase 6 — deferred until auto-apply core ships)
- Encrypt `portal_password` at rest (Fernet symmetric encryption)
- Dedicated iCIMS agent (currently falls back to SmartApplyAgent)
- Dedicated Greenhouse Playwright agent for boards without a usable Apply API
- Email confirmation sync (IMAP / Gmail API) to verify successful submissions
- Fingerprint rotation: canvas, WebGL, timezone spoofing
- Rate limiting on discovery — respect `robots.txt` crawl-delay, randomized jitter
- Admin dashboard: per-portal success/fail rates, OpenAI token spend, queue depth, auto-apply gate metrics

### Phase 8: Scale & Monetization 📋 FUTURE
- Multi-tenant billing (Stripe)
- Tiered usage caps (free tier: N applications/month, includes auto-apply quota)
- Self-serve company slug submission with moderation queue
- Webhook for external systems (notify on application status change)

---

## 7. API Surface

| Method | Path | Description |
|---|---|---|
| POST | /api/auth/register | Create account |
| POST | /api/auth/login | Get JWT token |
| GET | /api/profile | Get user profile |
| PUT | /api/profile | Update user profile |
| POST | /api/apply | Queue a job application |
| GET | /api/applications | List all applications |
| GET | /api/status/{job_id} | Get application status |
| POST | /api/otp/submit | Submit OTP for waiting agent |
| WS | /ws/agent/{job_id} | Live log + screenshot stream |
| GET | /api/job-searches | List search profiles |
| POST | /api/job-searches | Create search profile |
| PUT | /api/job-searches/{id} | Update search profile |
| DELETE | /api/job-searches/{id} | Delete search profile |
| POST | /api/job-searches/{id}/run | Trigger immediate discovery run |
| GET | /api/discovered-jobs | List discovered jobs (filterable) |
| POST | /api/discovered-jobs/{id}/queue | Queue a discovered job for apply (also used for "Approve & Apply" on auto_queued items) |
| POST | /api/discovered-jobs/{id}/skip | Mark a discovered job as skipped |
| GET | /api/discovered-jobs/export | Download discovered jobs as .xlsx |
| POST | /api/discovered-jobs/bulk-delete | Bulk delete discovered jobs |
| GET | /api/applications/{id}/cover-letter | 🚧 Phase 6B — get the generated cover letter |
| POST | /api/applications/{id}/cover-letter/regenerate | 🚧 Phase 6B — regenerate cover letter |

---

## 8. Success Verification
- **Automated confirmation:** Agent waits for "Application Submitted" text on-screen
- **Status tracking:** `ApplicationStatus` enum (pending → running → awaiting_otp → completed/failed)
- **Discovery metrics:** `DiscoveredJob.match_score` visible in UI so user can tune threshold

---

## 9. Folder Structure

```
ai apply/
├── backend/
│   ├── app/
│   │   ├── agents/
│   │   │   ├── base_portal_agent.py    ✅
│   │   │   ├── base_api_agent.py       ✅
│   │   │   ├── workday_agent.py        ✅
│   │   │   ├── smart_apply_agent.py    ✅
│   │   │   ├── universal_agent.py      ✅
│   │   │   ├── greenhouse_agent.py     ✅
│   │   │   ├── lever_agent.py          ✅
│   │   │   ├── ashby_agent.py          ✅
│   │   │   ├── job_discovery_agent.py  ✅
│   │   │   └── icims_agent.py          🚧 Phase 7
│   │   ├── api/routes/
│   │   │   ├── auth.py                 ✅
│   │   │   ├── applications.py         ✅
│   │   │   ├── otp.py                  ✅
│   │   │   ├── profile.py              ✅  (Phase 6A extends with auto_apply fields)
│   │   │   ├── job_searches.py         ✅  (Phase 6A adds auto_apply_mode)
│   │   │   └── discovered_jobs.py      ✅
│   │   ├── models/
│   │   │   ├── user.py                 ✅  (Phase 6A adds auto_apply_enabled, daily_auto_apply_cap)
│   │   │   ├── job_application.py      ✅  (Phase 6A adds queued_by)
│   │   │   ├── tailored_resume.py      ✅  (Phase 6C refactor pending)
│   │   │   ├── job_search_profile.py   ✅  (Phase 6A adds auto_apply_mode)
│   │   │   ├── discovered_job.py       ✅  (Phase 6A adds "auto_queued" status, Phase 6D adds scored_at)
│   │   │   └── cover_letter.py         🚧 Phase 6B
│   │   ├── services/
│   │   │   ├── resume_tailor.py        ✅ (OpenAI gpt-4o; Phase 6B adds draft_cover_letter, 6D renames tailor_resume_section)
│   │   │   ├── job_scorer.py           ✅ (OpenAI + regex hybrid)
│   │   │   └── websocket_manager.py    ✅
│   │   ├── data/
│   │   │   └── company_slugs.json      ✅
│   │   └── workers/
│   │       ├── celery_app.py           ✅
│   │       └── tasks.py                ✅
└── frontend/src/
    ├── pages/
    │   ├── Login.jsx                   ✅
    │   ├── Dashboard.jsx               ✅
    │   ├── Profile.jsx                 ✅
    │   ├── JobPreferences.jsx          ✅
    │   └── DiscoveredJobs.jsx          ✅
    ├── components/
    │   ├── Dashboard/                  ✅ (AgentConsole, ApplicationFeed)
    │   ├── HITL/                       ✅ (OTPModal)
    │   └── Layout/                     ✅ (Navbar, Sidebar, AppLayout)
    └── hooks/
        ├── useApplications.js          ✅
        ├── useProfile.js               ✅
        ├── useWebSocket.js             ✅
        ├── useJobSearches.js           ✅
        └── useDiscoveredJobs.js        ✅
```

Legend: ✅ Complete | 🚧 Phase 6 (Auto-Apply Revisit, in progress) | 📋 Phase 7+ (Production Hardening, Monetization)
