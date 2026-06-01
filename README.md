# AI Apply

Autonomous job-application platform. Discovers fresh US-tech roles across 175+ ATS boards and proprietary career portals, tailors a résumé for each one with OpenAI, generates a PDF, fills the application form (Greenhouse / Lever / Ashby / Workday / iCIMS / company portals) via a Playwright + vision agent, and tracks the lifecycle through Gmail.

---

## What it does

| Stage | What runs |
|---|---|
| **Discover** | Pulls fresh postings every 4h from Greenhouse, Ashby, Workday, iCIMS, BambooHR, SmartRecruiters (tech-tilted), plus per-company adapters for Amazon, Microsoft, Google, Apple, Meta, Netflix. Filters: USA-only, no internships / part-time / staffing / gov, work-arrangement, freshness window. |
| **Score** | LLM scorer ranks each posting against the user's `JobSearchProfile` (target roles, skills, locations, work arrangement). |
| **Tailor** | gpt-4o rewrites the résumé per JD (keeps original sections, surfaces JD-relevant skills). |
| **Render** | PDF generated via Word COM on Windows (`ExportAsFixedFormat`) or `docx2pdf` fallback. Cover letter generated separately. |
| **Submit** | API-first agents for Greenhouse / Lever / Ashby. Greenhouse falls back to a vision Set-of-Marks browser agent when the public submit API requires a board key (401). Workday/iCIMS/portals use Playwright with form-mapping heuristics. |
| **Track** | Gmail OAuth (modify + send scopes). Auto-labels classified messages (`AI Apply/{Confirmed,Assessment,Interview,Offer,Rejected}`). Optional autonomous follow-ups: replies in-thread to validated human recruiters only, daily cap, full audit. |

---

## Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  React/Vite  │───▶│   FastAPI API    │───▶│   Postgres      │
│  frontend    │    │  (JWT auth)      │    │  (asyncpg)      │
└──────────────┘    └────────┬─────────┘    └─────────────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Celery worker       │
                  │  + Celery Beat       │
                  │  (Redis broker)      │
                  └──────────┬───────────┘
                             │
        ┌────────────────────┼────────────────────────┐
        ▼                    ▼                        ▼
┌────────────────┐  ┌──────────────────┐   ┌────────────────────┐
│ Discovery      │  │ Apply agents     │   │ Email tracker      │
│ - ATS APIs     │  │ - Greenhouse API │   │ - Gmail REST       │
│ - Tier-2 ports │  │ - Vision (gpt-4o)│   │ - Auto-label       │
│ - Playwright   │  │ - Playwright     │   │ - Follow-ups       │
└────────────────┘  └──────────────────┘   └────────────────────┘
```

---

## Tech stack

- **Backend:** FastAPI · SQLAlchemy async + asyncpg · Alembic · Pydantic v2
- **Workers:** Celery + Celery Beat · Redis
- **Frontend:** React 19 · Vite 8 · Tailwind 3.4 · TanStack Query · shadcn-style tokens
- **AI:** OpenAI `gpt-4o` (chat + vision) with shared `Semaphore(5)` and retry/backoff
- **Browser:** Playwright (Chromium) with Set-of-Marks overlay for vision-based form filling
- **Auth:** Email + password (bcrypt) · Sign-in-with-Google · JWT in localStorage
- **Gmail:** Google OAuth 2.0 (`gmail.modify` + `gmail.send`) · Fernet-encrypted tokens at rest

---

## Project layout

```
backend/
├── app/
│   ├── agents/                 # Discovery + apply agents
│   │   ├── job_discovery_agent.py     # Orchestrator across all ATS sources
│   │   ├── portal_adapters.py         # Tier-2 proprietary career portals
│   │   ├── greenhouse_agent.py        # API-first + fallback
│   │   ├── ashby_agent.py
│   │   ├── lever_agent.py
│   │   ├── workday_agent.py           # Playwright-driven
│   │   ├── smart_apply_agent.py       # Vision (Set-of-Marks) fallback
│   │   └── universal_agent.py
│   ├── api/routes/             # FastAPI routers
│   ├── data/company_slugs.json # Verified ATS slug universe (175+ Tier-1)
│   ├── models/                 # SQLAlchemy ORM
│   ├── services/               # Tailoring, scoring, email, PDF, etc.
│   ├── workers/                # Celery tasks + beat schedule
│   └── core/                   # DB, auth, encryption, Redis
├── alembic/versions/
├── build_slugs.py              # Re-validates ATS slug universe
├── smoke_portals.py            # Re-validates Tier-2 adapters
└── requirements.txt

frontend/
├── src/
│   ├── pages/                  # Dashboard, JobPreferences, EmailAuto, …
│   ├── components/             # Layout, Dashboard panels, HITL/OTP modal
│   ├── hooks/                  # TanStack Query wrappers
│   └── services/api.js         # axios + JWT interceptor
└── tailwind.config.js
```

---

## Setup

### Prerequisites
- Python 3.12+
- Node 20+
- Postgres 14+ (or via `docker-compose.yml`)
- Redis 6+
- Chromium (installed via Playwright)
- Microsoft Word (Windows only — used for PDF rendering)

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium

copy .env.example .env
# Fill in OPENAI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, etc.

alembic upgrade head
```

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env
```

### Environment

Backend `.env` (see [backend/.env.example](backend/.env.example) for full list):
- `OPENAI_API_KEY` — required for tailoring + vision apply
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` — Web OAuth client (add `http://localhost:8000/api/email/callback` as a redirect URI)
- `GOOGLE_REDIRECT_URI` — match the OAuth client
- `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `RESUME_FORMATTER_PATH` — local clone of [skilluence/resume-formatter](https://github.com/skilluence/resume-formatter)
- `ENCRYPTION_KEY` (optional) — Fernet key for OAuth tokens; derived from `SECRET_KEY` if blank
- `EMAIL_SEND_DRYRUN` (optional) — log instead of sending real email; safe for first rollout

---

## Running locally (four processes)

```powershell
# Terminal 1 — API
cd backend; .\venv\Scripts\activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — Celery worker (solo pool required on Windows)
cd backend; .\venv\Scripts\activate
celery -A app.workers.celery_app worker --loglevel=info --pool=solo

# Terminal 3 — Celery Beat (discovery every 4h, follow-ups daily)
cd backend; .\venv\Scripts\activate
celery -A app.workers.celery_app beat --loglevel=info

# Terminal 4 — Frontend
cd frontend
npm run dev
```

Open <http://localhost:5173>. Sign in or sign in with Google. Configure your `JobSearchProfile` (target roles, skills, locations, work arrangement). Trigger discovery from the Job Preferences page or wait for the 4h beat.

---

## Sources currently active

| Tier | Source | Type | Status |
|---|---|---|---|
| 1 | Greenhouse | API | 109 verified tech slugs |
| 1 | Ashby | API | 56 verified tech slugs |
| 1 | Lever | API | 10 slugs, dropped from loop (low hit-rate) |
| 1 | SmartRecruiters | API | 4 tech-leaning slugs |
| 1 | Workday | API (JSON POST) | Target, Intel, Salesforce, NVIDIA, … |
| 1 | iCIMS | HTML | Playwright fallback |
| 1 | BambooHR | API | |
| 2 | Amazon | Proprietary JSON | **live** (~100+ roles/query) |
| 2 | Netflix | Proprietary JSON | **live** |
| 2 | Microsoft / Google / Apple / Meta | Proprietary | wired, endpoints need refresh |

Maintenance:
- `python backend/build_slugs.py` — re-validates the ATS slug universe; drops dead slugs
- `python backend/smoke_portals.py` — re-validates Tier-2 adapters

---

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Auth + profile + résumé upload | ✅ |
| 2 | Discovery + scoring | ✅ |
| 3 | Tailoring + PDF | ✅ |
| 4 | Apply agents (Greenhouse/Lever/Ashby) | ✅ |
| 5 | Workday/iCIMS via Playwright | ✅ |
| 6 | Auto-apply orchestration + retry + screenshot gallery | ✅ |
| 7 | Vision-based form filling (Set-of-Marks) | ✅ |
| Gmail 1 | OAuth + lifecycle classification | ✅ |
| Gmail 2 | Auto-label + AI compose + autonomous follow-ups | ✅ |
| Tier-2 sourcing | Proprietary career portals | partial (Amazon, Netflix live) |
| 8 | Hybrid HITL auto-apply | design |

---

## Notes

- The auto-apply agent submits real applications. The HITL "Review & Submit" surface (Phase 8) is the supervised path.
- `gmail.modify` and `gmail.send` are Google *restricted* scopes — for production use, the app needs OAuth verification + CASA assessment. Until then, only added Test Users can connect.
- The submit flow stores full screenshot trails per application (visible in the Agent Console) for debugging.
- Résumé tailoring is *keyword-friendly* by design — it surfaces JD-relevant skills the candidate plausibly has. It does not fabricate.
