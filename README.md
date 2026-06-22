# AK24/7

An **India-focused job aggregator**. It discovers fresh India tech/business roles across hundreds of employer ATS boards, scores each posting against the user's résumé, and tracks the application lifecycle through Gmail. A single-admin console oversees every user.

> Modeled on Jobright.ai / Tsenta: there is no one magic feed. We aggregate **hundreds of employer career pages** by discovering ATS "board tokens" (slugs) at scale, probing each ATS's public API, and keeping the ones with live **India** roles. See [sources/](sources/) for the durable sourcing strategy.

---

## Live app & requesting access

**Live:** **<https://ak-24-7.vercel.app>**

Access is **invite-based** while the app is in early rollout. **Want to try it?** Email **[arpantech1130@gmail.com](mailto:arpantech1130@gmail.com)** with the Google address you'll sign in with, and you'll be added as a user. Once added, open the live link and **Sign in with Google**.

---

## What it does

| Stage | What runs |
|---|---|
| **Discover** | Pulls India postings from a DB-backed registry of employer ATS slugs across **Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Breezy, Recruitee, Personio, Workday, Zoho** plus aggregator feeds. Every source is filtered to India (or India‑open remote) and de‑staffed (no consultancy / RPO / "hiring for our client"). |
| **Score** | Each posting is ranked against the user's `JobSearchProfile` (target roles, skills, locations, work arrangement) and surfaced as a match feed with a why‑fit explanation. |
| **Track** | A spreadsheet‑parity **Job Tracker**: paste any job link to auto‑extract company/role/location, or auto‑populate cards from classified Gmail threads. Gmail OAuth (consent‑gated) auto‑labels lifecycle messages and can send optional follow‑ups. |
| **Admin** | Single‑admin console: list every user, drill into their full profile / applications / searches / discovered jobs / emails, enable/disable or delete accounts, view discovery‑run history, and check slug‑registry health. |

---

## Architecture

```
┌──────────────┐    ┌──────────────────┐    ┌─────────────────────┐
│  React/Vite  │───▶│   FastAPI API    │───▶│  Postgres (asyncpg) │
│  frontend    │    │  (JWT + Google)  │    │  + SQLAlchemy 2.0   │
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

The scheduler is a lightweight in‑process cron — no separate worker processes are required.

---

## Tech stack

- **Backend:** FastAPI 0.115 · SQLAlchemy 2.0 async + asyncpg · Alembic · Pydantic v2 (`pydantic-settings`)
- **Scheduler:** APScheduler 3.10 (in‑process, `Asia/Kolkata`) · Redis 5 (cache/sessions)
- **Frontend:** React 19 · Vite 8 · Tailwind 3.4 · TanStack Query 5 · React Router 7 · Framer Motion · shadcn‑style HSL tokens
- **AI:** OpenAI (JD scoring + résumé–job match ranking)
- **Sources:** public ATS APIs · `feedparser` (RSS) · `beautifulsoup4` + `lxml` (JD‑from‑URL)
- **Auth:** Google sign‑in (identity) → post‑Google username + password (bcrypt) · JWT in `localStorage`
- **Gmail:** Google OAuth 2.0 (`gmail.modify` + `gmail.send`) · Fernet‑encrypted tokens at rest
- **Résumé parsing:** `pdfplumber` · `python-docx` — extract text from the uploaded résumé for scoring

---

## Job sources & the slug registry

The supply of employers lives in the **`company_source`** table (the slug registry), not in a static JSON file. Each row is an `(ats, slug)` pair with a status (`unverified` → `active` → `dead`), India/total role counts from the last probe, discovery provenance, and dead‑check hysteresis (only demoted to `dead` after 3 consecutive failed probes).

| Tier | Sources | Cost | Default |
|---|---|---|---|
| 1 | Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Breezy, Recruitee, Personio, Workday, Zoho | free public APIs | **on** |
| 2 | Jooble API, TimesJobs RSS | free / API key | on (key‑gated) |

---

## Project layout

```
backend/
├── app/
│   ├── agents/
│   │   ├── job_discovery_agent.py   # India discovery orchestrator (normalize, India/LPA/staffing filters)
│   │   ├── ats_sources.py           # public ATS adapters + fetch_all_ats() fan-out
│   │   └── hirist_source.py         # supplemental source adapter
│   ├── api/routes/                  # auth, admin, matches, dashboard, job_searches,
│   │                                #   saved_applications, discovered_jobs, email, ...
│   ├── core/
│   │   ├── bootstrap.py             # ensure_admin() — idempotent single-admin seed
│   │   ├── scheduler.py             # APScheduler in-process cron (IST)
│   │   └── auth.py, database.py
│   ├── data/                        # india_curated_slugs.json, top_india_companies.json
│   ├── models/                      # User, CompanySource, DiscoveryRun, SavedApplication, JobPool, ...
│   ├── scripts/slug_discovery.py    # registry growth + revalidation engine
│   └── services/                    # scoring/matching, email, discovery
├── alembic/versions/                # incl. company_source, discovery_run, tracker parity, admin/creds
├── scripts/discover_slugs.py        # CLI: grow / revalidate the slug registry
├── scripts/reset_and_seed.py        # CLI: one-time wipe + admin reseed
└── requirements.txt

frontend/
├── src/
│   ├── pages/                       # Dashboard, Admin, Settings, Profile, Jobs,
│   │                                #   EmailAuto, Tracker, Login
│   ├── components/
│   │   ├── brand/Logo.jsx           # AK emblem + wordmark (5 variants, "ak-emblem" is the mark)
│   │   ├── AmbientBackground.jsx    # Aurora glows + dot grid
│   │   ├── Layout/                  # AppLayout, Sidebar (4 items), AvatarMenu
│   │   ├── Dashboard/JobMatchCard.jsx  # Jobright-style match card (logo, match ring, actions)
│   │   ├── AdminUserDrawer.jsx, SetCredentialsModal.jsx
│   ├── services/api.js              # axios + JWT interceptor (base http://localhost:8000/api)
│   └── index.css                    # brand tokens, aurora, glass utilities
└── tailwind.config.js               # brand color/shadow/keyframe theme
```

---

## Setup

### Prerequisites
- Python 3.12+ · Node 20+ · Postgres 14+ · Redis 6+

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
| `OPENAI_API_KEY` | JD scoring + résumé–job match ranking |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Web OAuth client (sign‑in + Gmail) |
| `GOOGLE_REDIRECT_URI` | **must be** `http://localhost:8000/api/email/callback` (registered with Google — see below) |
| `DATABASE_URL`, `REDIS_URL` | Postgres (async) + Redis |
| `ENABLE_SCHEDULER` | turn on the in‑process APScheduler cron (default `false`) |
| `JOOBLE_API_KEY`, `ENABLE_SCRAPE_TIMESJOBS` | aggregator sources |
| `ADMIN_EMAIL` / `ADMIN_USERNAME` / `ADMIN_PASSWORD` | override the bootstrapped admin |
| `ENCRYPTION_KEY` | Fernet key for Gmail tokens (derived from `SECRET_KEY` if blank) |
| `EMAIL_SEND_DRYRUN` | log instead of sending real email |

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
| `/api/dashboard` | `stats` (jobs found / applied / target roles) |
| `/api/job-searches` | profile CRUD + `{id}/run` (seed pool, then background discovery) |
| `/api/email` | Gmail OAuth, inbox, labels, auto‑label, auto‑followup |
| `/api/public` | unauth job browse/search; authed import‑to‑profile |

---

## Frontend at a glance

- **Brand:** violet → cyan gradient on a cool near‑white canvas (light) / near‑black raised cards (dark). HSL design tokens (`--brand`, `--brand-2`, semantic `--success/--warning/--danger/--info`) in `index.css`; theme wired through `tailwind.config.js`. **No lightning mark; no OpenAI footer.**
- **Type:** Plus Jakarta Sans (display) · Inter (body) · JetBrains Mono (mono).
- **Mark:** the **AK emblem** (`components/brand/Logo.jsx`) — monogram inside a gradient‑outlined squircle; wordmark renders "AK**24/7**Jobs".
- **Chrome:** `AppLayout` centralizes the Aurora ambient background, 4‑item sidebar (Dashboard · Jobs · Email · Job Tracker), and a top‑right `AvatarMenu`. Admins get an Admin‑only nav.
- **Dashboard:** 3 stat tiles + a recent‑matches strip of `JobMatchCard`s (company logo with fallback, match badge, and an **Apply** button that opens the employer link).

---

## Status

| Area | State |
|---|---|
| India aggregator pivot (discovery, India/LPA filters, slug registry) | ✅ |
| Google‑only auth + post‑Google credentials + single‑admin console | ✅ |
| Job Tracker (paste‑link + Gmail auto‑populate) | ✅ |
| Deployed live (Render + Vercel) | ✅ |
| Gmail OAuth + auto‑label + follow‑ups | ✅ |

---

## Notes

- The full sourcing strategy (how Jobright/Tsenta scale, the ATS API reference, the Common‑Crawl discovery playbook, the curated India company list, contact/outreach cautions) is documented under [sources/](sources/).
