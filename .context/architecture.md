# Folder Structure Logic

## Backend (`backend/app/`)

```
agents/         Browser automation agents — one class per portal type
                BasePortalAgent is the ABC with shared Playwright + Redis helpers
                Each subclass overrides run(job_url, user_profile)

api/
  routes/       One file per logical resource (auth, applications, otp, profile,
                job_searches, discovered_jobs). Thin route handlers only — delegate
                to services or workers, never contain business logic directly.
  websocket.py  Single WebSocket endpoint: /ws/agent/{job_id}
                Bridges Redis pub/sub → browser client

core/
  auth.py       JWT creation + verification, bcrypt helpers, get_current_user dependency
  database.py   SQLAlchemy async engine, session factory, Base, get_db dependency
  redis.py      Shared Redis connection pool, get_redis dependency

models/         SQLAlchemy ORM models — one file per table
                Import all in app/models/__init__.py so init_db() sees them all

services/
  resume_tailor.py   OpenAI gpt-4o for JD parsing, resume tailoring, question answering, cover letters
  job_scorer.py      Hybrid scorer: regex skill match + OpenAI LLM role-fit, returns 0-100
  websocket_manager.py  (legacy — superseded by direct Redis pub/sub in websocket.py)

workers/
  celery_app.py  Celery app instance + Beat schedule
  tasks.py       Task definitions — keep thin, call agents/services
```

## Frontend (`frontend/src/`)

```
pages/          Full-page route components (one per route)
components/     Reusable UI pieces, organized by feature area
  Dashboard/    AgentConsole, ApplicationFeed
  HITL/         OTPModal
  Layout/       Navbar
hooks/          TanStack Query hooks — data fetching + mutations
services/
  api.js        Axios instance + all API call functions (single source of truth for endpoints)
assets/         Static images
```

## Key Relationships

- A `User` has many `JobApplication` records and many `JobSearchProfile` records
- A `JobSearchProfile` produces many `DiscoveredJob` records
- A `DiscoveredJob` with status "queued" becomes a `JobApplication`
- A `JobApplication` may have one `TailoredResume`
- Celery tasks write status updates to both PostgreSQL and Redis pub/sub
- The WebSocket endpoint reads from Redis pub/sub and pushes to the browser
