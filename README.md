# AK24/7 Jobs

An **India-focused job aggregator**. It discovers fresh India tech/business roles across hundreds of employer ATS boards, scores each posting against the user's résumé, tailors a résumé + cover letter per JD, and tracks the application lifecycle through Gmail. A single-admin console oversees every user.

> Modeled on Jobright.ai / Tsenta: there is no one magic feed. We aggregate **hundreds of employer career pages** by discovering ATS "board tokens" (slugs) at scale, probing each ATS's public API, and keeping the ones with live **India** roles. See [sources/](sources/) for the durable sourcing strategy.

---

## What it does

| Stage | What runs |
|---|---|
| **Discover** | Pulls India postings from a DB-backed registry of employer ATS slugs. **Tier‑1** (free public APIs): Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Breezy, Recruitee, Personio, Workday, Zoho. **Tier‑2**: Jooble API, TimesJobs RSS. **Tier‑3** (opt‑in scraping, off by default): Indeed, Google, Naukri, LinkedIn, Glassdoor, Instahyre, Cutshort, Wellfound, Hirect, hirist.tech. Every source is filtered to India (or India‑open remote) and de‑staffed (no consultancy / RPO / "hiring for our client"). |
| **Score** | Each posting is ranked against the user's `JobSearchProfile` (target roles, skills, locations, work arrangement). pgvector embedding ranking is a fast‑follow; `/api/matches/refresh` is defensive and never 500s if pgvector isn't migrated yet. |
| **Tailor** | OpenAI rewrites the résumé per JD (keeps original sections, surfaces JD‑relevant skills — never fabricates). Cover letter generated separately. PDF rendered via the in‑process [skilluence/resume-formatter](https://github.com/skilluence/resume-formatter) clone (Word COM on Windows, `docx2pdf` fallback). |
| **Track** | A spreadsheet‑parity **Job Tracker**: paste any job link to auto‑extract company/role/location, or auto‑populate cards from classified Gmail threads. Gmail OAuth (consent‑gated) auto‑labels lifecycle messages and can send optional follow‑ups. |
| **Admin** | Single‑admin console: list every user, drill into their full profile / applications / searches / discovered jobs / résumés / emails, enable/disable or delete accounts, view discovery‑run history, and check slug‑registry health. |

---

## Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│  React/Vite  │───▶│   FastAPI API    │───▶│  Postgres (asyncpg) │
│  frontend    │    │  (JWT + Google)  │    │  + pgvector (f-f)   │
└──────────────┘    └────────┬─────────┘    └─────────────────────┘
                             │  Redis (cache/sessions)
                             ▼
                  ┌──────────────────────────┐
                  │  APScheduler (in-process)│   gated: ENABLE_SCHEDULER
                  │  IST cron, no workers    │   • pool warm   */3h :10
                  └──────────┬───────────────┘   • discovery   */3h :30
                             │                    • revalidate  03:00
        ┌────────────────────┼──────────────┐    • digest      07:30
        ▼                    ▼              ▼
┌────────────────┐  ┌─────────────────┐  ┌────────────────────┐
│ Slug registry  │  │ Discovery agent │  │ Gmail tracker      │
│ company_source │  │ Tier-1/2/3 fan- │  │ - OAuth (consent)  │
│ (ATS tokens)   │  │ out + India     │  │ - Auto-label       │
│ + discovery    │  │ filter + LPA    │  │ - Follow-ups       │
│ run history    │  │ parse           │  │ - Tracker bridge   │
└────────────────┘  └─────────────────┘  └────────────────────┘
```

The scheduler is a lightweight in‑process cron — **no Celery worker/beat processes** are required for the lean build. Celery is retained in `requirements.txt` only for legacy apply tasks.

---

## Tech stack

- **Backend:** FastAPI 0.115 · SQLAlchemy 2.0 async + asyncpg · Alembic · Pydantic v2 (`pydantic-settings`)
- **Scheduler:** APScheduler 3.10 (in‑process, `Asia/Kolkata`) · Redis 5 (cache/sessions)
- **Frontend:** React 19 · Vite 8 · Tailwind 3.4 · TanStack Query 5 · React Router 7 · Framer Motion · shadcn‑style HSL tokens
- **AI:** OpenAI (résumé tailoring + JD scoring) · `text-embedding-3-small` + pgvector (fast‑follow)
- **Sources:** `feedparser` (Tier‑2 RSS) · `python-jobspy` (Tier‑3 scraping) · `beautifulsoup4` + `lxml` (JD‑from‑URL) · Playwright/stealth + proxy pool for gated scrapers
- **Auth:** Google sign‑in (identity) → post‑Google username + password (bcrypt) · JWT in `localStorage`
- **Gmail:** Google OAuth 2.0 (`gmail.modify` + `gmail.send`) · Fernet‑encrypted tokens at rest
- **Résumé render:** `pdfplumber` · `python-docx` · `docx2pdf` · `pywin32` (Windows Word COM)

---

## Job sources & the slug registry

The supply of employers lives in the **`company_source`** table (the slug registry), not in a static JSON file. Each row is an `(ats, slug)` pair with a status (`unverified` → `active` → `dead`), India/total role counts from the last probe, discovery provenance, and dead‑check hysteresis (only demoted to `dead` after 3 consecutive failed probes).

| Tier | Sources | Cost | Default |
|---|---|---|---|
| 1 | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Breezy, Recruitee, Personio, Workday, Zoho | free public APIs | **on** |
| 2 | Jooble API, TimesJobs RSS | free / API key | on (key‑gated) |
| 3 | Indeed, Google, Naukri, LinkedIn, Glassdoor, Instahyre, Cutshort, Wellfound, Hirect, hirist.tech | scraping | **off** (`TIER3_ENABLED` + per‑source flags) |

### Growing & maintaining the registry

```powershell
# Run from project root — no cd needed
backend\venv\Scripts\python.exe backend\scripts\discover_slugs.py              # full wave: curated + seed + Common Crawl
backend\venv\Scripts\python.exe backend\scripts\discover_slugs.py --no-cc      # skip Common Crawl (curated + seed only)
backend\venv\Scripts\python.exe backend\scripts\discover_slugs.py --max 400    # cap probes this run
backend\venv\Scripts\python.exe backend\scripts\discover_slugs.py --revalidate # re-probe existing slugs, prune dead
```

Discovery harvests ATS URLs from the **Common Crawl** CDX index plus curated lists ([`app/data/india_curated_slugs.json`](backend/app/data/india_curated_slugs.json), [`top_india_companies.json`](backend/app/data/top_india_companies.json)), probes each candidate against the live ATS adapter, and keeps rows with ≥ 1 India role. The registry started from a **34‑slug seed** and is grown toward **500–1,000+** active India endpoints.

**Live source of truth:** `GET /api/admin/registry` → total count, by‑status breakdown, active‑by‑ATS breakdown.

---

## Auth & admin model

- **Sign‑up is Google‑only.** "Continue with Google" find‑or‑creates the account, then a one‑time modal collects a **username + password** (`credentials_set` gate). Returning users log in with email **or** username + password.
- **Single admin.** `app/core/bootstrap.py` (`ensure_admin`, run on every startup) guarantees the admin account exists — defaults overridable via `ADMIN_EMAIL` / `ADMIN_USERNAME` / `ADMIN_PASSWORD`. It never deletes existing users.
- **`users.raw_password` stores the plaintext password on purpose** — the single admin console surfaces it. This is an intentional internal‑tool requirement, not a bug; do not "fix" it.
- One‑time destructive reset (wipes all users, reseeds admin) lives in `scripts/reset_and_seed.py` (`TRUNCATE users CASCADE`; `JobPool` is left intact).

---

## Project layout

```
backend/
├── app/
│   ├── agents/
│   │   ├── job_discovery_agent.py   # India discovery orchestrator (normalize, India/LPA/staffing filters)
│   │   ├── ats_sources.py           # 10 Tier-1 public ATS adapters + fetch_all_ats() fan-out
│   │   └── hirist_source.py         # hirist.tech (Tier-3, __NEXT_DATA__ parse, gated)
│   ├── api/routes/                  # auth, admin, matches, dashboard, job_searches,
│   │                                #   saved_applications, discovered_jobs, email, ...
│   ├── core/
│   │   ├── bootstrap.py             # ensure_admin() — idempotent single-admin seed
│   │   ├── scheduler.py             # APScheduler in-process cron (IST)
│   │   └── auth.py, database.py
│   ├── data/                        # india_curated_slugs.json, top_india_companies.json
│   ├── models/                      # User, CompanySource, DiscoveryRun, SavedApplication, JobPool, ...
│   ├── scripts/slug_discovery.py    # registry growth + revalidation engine
│   └── services/                    # tailoring, scoring/matching, email, PDF
├── alembic/versions/                # incl. company_source, discovery_run, tracker parity, admin/creds
├── scripts/discover_slugs.py        # CLI: grow / revalidate the slug registry
├── scripts/reset_and_seed.py        # CLI: one-time wipe + admin reseed
└── requirements.txt

frontend/
├── src/
│   ├── pages/                       # Dashboard, Admin, Settings, Profile, DiscoveredJobs,
│   │                                #   TailoredResumes, EmailAuto, Tracker, Login, public Jobs
│   ├── components/
│   │   ├── brand/Logo.jsx           # AK emblem + wordmark (5 variants, "ak-emblem" is the mark)
│   │   ├── AmbientBackground.jsx    # Aurora glows + dot grid
│   │   ├── Layout/                  # AppLayout, Sidebar (5 items), AvatarMenu
│   │   ├── Dashboard/JobMatchCard.jsx  # Jobright-style match card (logo, match ring, actions)
│   │   ├── AdminUserDrawer.jsx, SetCredentialsModal.jsx
│   ├── services/api.js              # axios + JWT interceptor (base http://localhost:8000/api)
│   └── index.css                    # brand tokens, aurora, glass utilities
└── tailwind.config.js               # brand color/shadow/keyframe theme
```

---

## Setup

### Prerequisites
- Python 3.12+ · Node 20+ · Postgres 14+ (pgvector image for the embedding fast‑follow) · Redis 6+
- Microsoft Word (Windows only — résumé PDF rendering)

### Backend

```powershell
cd backend
# Use the explicit Python 3.12 path — never "python -m venv" (picks up wrong interpreter)
C:\Users\x\AppData\Local\Programs\Python\Python312\python.exe -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt

copy .env.example .env
# Fill in OPENAI_API_KEY, GOOGLE_CLIENT_ID/SECRET, DATABASE_URL, etc.

.\venv\Scripts\python.exe -m alembic upgrade head
```

### Frontend

```powershell
cd frontend
npm install
# No frontend/.env needed — api.js defaults to http://localhost:8000/api
```

### Key environment variables (`backend/.env`)

| Var | Purpose |
|---|---|
| `OPENAI_API_KEY` | résumé tailoring + JD scoring |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Web OAuth client (sign‑in + Gmail) |
| `GOOGLE_REDIRECT_URI` | **must be** `http://localhost:8000/api/email/callback` (registered with Google — see below) |
| `DATABASE_URL`, `REDIS_URL` | Postgres (async) + Redis |
| `ENABLE_SCHEDULER` | turn on the in‑process APScheduler cron (default `false`) |
| `JOOBLE_API_KEY`, `ENABLE_SCRAPE_TIMESJOBS` | Tier‑2 sources |
| `TIER3_ENABLED` + `SCRAPE_*` | Tier‑3 scrapers, all off by default; `SCRAPE_PROXIES`, `STEALTH_ENABLED` for the proxy/stealth path |
| `ADMIN_EMAIL` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` | override the bootstrapped admin |
| `ENCRYPTION_KEY` | Fernet key for Gmail tokens (derived from `SECRET_KEY` if blank) |
| `EMAIL_SEND_DRYRUN` | log instead of sending real email |
| `RESUME_FORMATTER_PATH` | local clone of `skilluence/resume-formatter` |

> **Port 8000 is required.** `GOOGLE_REDIRECT_URI=http://localhost:8000/api/email/callback` is registered with Google, so the backend must run on **8000** or Google sign‑in breaks.

---

## Running locally

```powershell
# Infra — Postgres (5432) + Redis (6379)
docker compose up -d

# Terminal 1 — API (must stay on port 8000)
cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend (port 5173)
cd frontend
npm run dev
```

Open <http://localhost:5173>. Sign in with Google, set a username + password, then configure a `JobSearchProfile`. Discovery runs on demand (`POST /api/job-searches/{id}/run`) or on the APScheduler cadence once `ENABLE_SCHEDULER=true`.

---

## Database & migrations

```powershell
cd backend
alembic upgrade head          # apply all migrations
alembic revision --autogenerate -m "msg"   # author a new one
```

Migration files use ordered `NNNN_<slug>.py` names; the internal Alembic revision IDs (hashes) are what the chain and DB key off, so the filenames are just a readable sort order. Recent migrations:

| File | Adds |
|---|---|
| `0012_admin_and_credential_setup` | `users.username` (unique), `raw_password`, `credentials_set`, `is_admin`; relaxes `hashed_password` to nullable (Google sign‑up exists before a password) |
| `0013_company_source_registry` | `company_source` slug registry + seed |
| `0014_discovery_run_history` | `discovery_run` history (audit trail of every discovery/search run) |
| `0015_tracker_parity_columns` | tracker‑parity columns on `saved_applications` (job_link, job_portal, location, salary, job_type, work_arrangement, resume_label, contact) |

---

## API surface (selected)

| Prefix | Highlights |
|---|---|
| `/api/auth` | `login`, `setup-credentials`, `me`, `consent`, `google`, `google/callback` |
| `/api/admin` | `users` (list), `users/{id}` (detail / `PATCH` enable‑disable / `DELETE`), `discovery-runs`, `registry` |
| `/api/matches` | `feed` (résumé‑scored, filters: location, min_score, freshness, sort), `refresh`, `history` |
| `/api/saved-applications` | tracker CRUD + `from-link` (paste a URL → auto card) |
| `/api/dashboard` | `stats` (jobs found / applied / target roles / tailored résumés) |
| `/api/job-searches` | profile CRUD + `{id}/run` (seed pool, then background discovery) |
| `/api/email` | Gmail OAuth, inbox, labels, auto‑label, auto‑followup |
| `/api/public` | unauth job browse/search; authed import‑to‑profile |

---

## Frontend at a glance

- **Brand:** violet → cyan gradient on a cool near‑white canvas (light) / near‑black raised cards (dark). HSL design tokens (`--brand`, `--brand-2`, semantic `--success/--warning/--danger/--info`) in `index.css`; theme wired through `tailwind.config.js`. **No lightning mark; no OpenAI footer.**
- **Type:** Plus Jakarta Sans (display) · Inter (body) · JetBrains Mono (mono).
- **Mark:** the **AK emblem** (`components/brand/Logo.jsx`) — monogram inside a gradient‑outlined squircle; wordmark renders "AK**24/7**Jobs".
- **Chrome:** `AppLayout` centralizes the Aurora ambient background, 5‑item sidebar (Dashboard · Jobs · Resume · Emails · Job Tracker), and a top‑right `AvatarMenu`. Admins get an Admin‑only nav.
- **Dashboard:** 4 stat tiles + a recent‑matches strip of `JobMatchCard`s (company logo with fallback, conic match ring, Apply / Tailor / HR LinkedIn actions).

---

## Status

| Area | State |
|---|---|
| India aggregator pivot (discovery, India/LPA filters, slug registry) | ✅ |
| Google‑only auth + post‑Google credentials + single‑admin console | ✅ |
| Job Tracker (paste‑link + Gmail auto‑populate) | ✅ |
| Résumé tailoring + PDF | ✅ |
| Gmail OAuth + auto‑label + follow‑ups | ✅ |
| Tier‑3 scrapers (proxy pool + stealth) | wired, off by default |
| pgvector embedding ranking | fast‑follow (needs pgvector Postgres image) |
| APScheduler cron | in‑process, gated by `ENABLE_SCHEDULER` |

---

## Notes

- `gmail.modify` / `gmail.send` are Google **restricted** scopes — production use needs OAuth verification + CASA. Until then only added Test Users can connect.
- Résumé tailoring is *keyword‑friendly* by design — it surfaces JD‑relevant skills the candidate plausibly has; it does not fabricate.
- The full sourcing strategy (how Jobright/Tsenta scale, the ATS API reference, the Common‑Crawl discovery playbook, the curated India company list, contact/outreach cautions) is documented under [sources/](sources/).
