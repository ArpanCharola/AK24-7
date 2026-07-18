# AGENTS.md — working context for AK24/7 Jobs

Read this before adding a feature or changing behavior. It captures the parts of
this repo that bite you if you don't know them. `CLAUDE.md` has the product
overview and conventions; this file is the operational map.

## What this app is

India-focused tech-jobs aggregator for freshers/entry-level. It discovers
employer ATS boards, ingests their India roles into a shared pool, grades and
ranks them, and serves search + résumé-matched recommendations. Live on
Vercel (frontend) + Render (backend, Docker) + managed Postgres/Redis.

## The two job stores — the single most important thing to understand

There are **two separate job tables**, filled by different paths and read by
different surfaces. Confusing them is the #1 source of "why are there no jobs":

| Table | Filled by | Read by |
|-------|-----------|---------|
| `job_pool` | the **ingest sweep** (`sweep_ingest_tick` / `warm_job_pool`) — broad, role-agnostic | **public search** (`/api/public/jobs`, the "Search Jobs" tab) |
| `canonical_job` (the "warehouse") | `run_aggregation` **and** `promote_pool_to_warehouse` | **Admin overview** + **Recommended feed** (`/api/matches`) |

`promote_pool_to_warehouse` (`services/aggregation.py`) is the **bridge**: it
runs pooled jobs through the same admission path (`deduplicate_batch` →
`_persist_candidate` → `_refresh_matches`) so the warehouse reflects pool supply.
It runs inside `_run_shared_aggregation` (in-process scheduler) and via
`POST /api/internal/tick/promote`. **If Admin/Recommended look empty but search
is full, the bridge isn't running.**

## Supply pipeline (how jobs get in)

```
company_source (slug registry)  ──probe──▶  active slugs
        ▲                                        │
   harvest_tick (names + Common Crawl)           │ sweep_ingest_tick
   probe_tick (validates candidates)             ▼
        └───────────────────────────────▶  job_pool  ──promote──▶  canonical_job
```

- **Slug registry** = `company_source`. It has a probe queue (`probe_state`:
  candidate → probing → active | no_india | dead). `no_india` ≠ `dead`: a live
  board with no India roles today is re-probed monthly, not discarded.
- **Grow it** via `services/slug_queue.py` (`harvest_tick`, `probe_tick`). Never
  let active supply hit zero — `get_india_slugs()` falls back to seed JSON.
- **Ingest** = `sweep_ingest_tick` (`agents/job_discovery_agent.py`), paging the
  active registry by a **stable id cursor** (not offset — offset skips rows
  inserted mid-sweep). Cursor lives in `ingest_cursor`.
- **ATS adapters** (`agents/ats_sources.py`) are all public JSON/XML APIs, fanned
  out with bounded concurrency via `_map_slugs`. Keep adapter signatures stable —
  `fetch_all_ats`, `quick_ats_search`, and `validate_candidate` all depend on them.

## Admission + India policy — one source of truth

`services/job_admission.py` (`classify_india`, `india_confidence`,
`employment_type`) is the **only** place India/quality is decided. Both the feed
and the warehouse (`aggregation.quality.classify_rejection`) call it. Don't add a
second India check — that's the bug this replaced (feed and warehouse used to
disagree). Verdicts are graded, not boolean: explicit-India 1.0, remote-India
0.9, global-remote 0.6, unknown 0.4, foreign 0.0. The serving filter shows
`india_confidence >= 0.5` by default.

## Search is in SQL, not Python

`services/job_search_sql.py` builds the query: role → `search_tsv` tsquery
(synonym-expanded via `_expand_term`), city → trigram, experience → coarse SQL
gate, ranking → `quality_score` minus a freshness decay. **Filtering, dedup
(`DISTINCT ON content_key`), and pagination all happen in SQL** so `offset` is
correct at any depth. Do NOT reintroduce a fetch-N-then-filter-in-Python pass —
that silently broke deep pagination (empty pages past the survivor count).

`job_pool.search_tsv` and `content_key` are **DB-generated columns**. In the ORM
model they MUST be declared `Computed(...)` or any `JobPool(...)` insert crashes
with "cannot insert into generated column". (This already bit once.)

## Free-tier scheduling — external ticks

Render free sleeps through in-process cron and kills long jobs, so supply runs as
short, resumable, externally-triggered ticks:

- Endpoints: `app/api/routes/internal_tasks.py`, prefix `/api/internal`, guarded
  by `INTERNAL_TASK_TOKEN` (404 when unset — invisible, not just 401). Each tick
  takes a Postgres advisory lock, is wall-clock bounded, checkpoints to
  `ingest_cursor`, and never 500s (errors return `{ok:false}`).
- Driver: `.github/workflows/supply-ticks.yml` (ingest + promote + probe, 10 min)
  and `supply-maintenance.yml` (revalidate / cleanup / harvest).
- `EXTERNAL_TICKS_ENABLED=true` makes the in-process scheduler drop the supply
  cron (keeps startup-warm + digest) so the two don't double-run. Left false
  (default), the in-process APScheduler runs everything — that's the self-host /
  always-on path.

SerpAPI (free ~100/mo) is **discovery-only** — never job fetching. Every call
goes through `services/credit_budget.try_consume` (atomic monthly ceiling,
`SERPAPI_MONTHLY_BUDGET`).

## Migrations — the deploy path

`start.sh` → `migrate_db.py`: a **fresh** DB gets `create_all` + stamp head; an
**existing** DB runs `alembic upgrade head`. So:
- New columns/indexes on existing tables MUST be in a migration (create_all is
  only hit on a brand-new DB and then stamped, so it never runs migrations).
- Anything a migration adds to an existing populated table needs a **backfill**
  if serving code filters on it (see 0023 backfilling `india_confidence`, or the
  whole existing catalogue would vanish from search on deploy).
- Extensions (`pg_trgm`) may be denied on a locked-down role — wrap in a guarded
  `DO $$ … EXCEPTION … $$` so a missing extension degrades gracefully instead of
  aborting the deploy.
- Filenames are `NNNN_<slug>.py`; the internal `revision` hash is what the DB
  keys on. Bump the pinned head in `tests/test_alembic_integrity.py` each time.

## Deployment (Vercel + Render)

- **Auto-deploys from `main`.** Push to main → Vercel rebuilds the frontend and
  Render rebuilds the backend (`backend/Dockerfile.prod` → `start.sh` runs
  migrations → gunicorn). Feature branches do NOT deploy.
- `frontend/vercel.json` rewrites `/api/*` → `https://ak247-api.onrender.com`.
  No frontend env var needed for the API base in prod.
- The app boots fine with **zero new env vars** (all have safe defaults). To
  enable autonomous supply growth on free tier, set on Render:
  `INTERNAL_TASK_TOKEN`, `EXTERNAL_TICKS_ENABLED=true`; and GitHub repo secrets
  `SUPPLY_API_BASE` + `INTERNAL_TASK_TOKEN`.
- Local dev is a **manual uvicorn from `backend/`** (see CLAUDE.md), NOT Docker.
  `docker compose up -d` brings up Postgres + Redis only — there is deliberately
  no `api` service (a stale one used to shadow :8000 and silently void code
  changes). Never add it back.

## Verifying a change actually works

Tests: `backend/venv/Scripts/python.exe -m pytest tests/ -q` (72+). But tests
don't cover the live pipeline — for supply/search changes, drive it:
`sweep_ingest_tick`, `promote_pool_to_warehouse`, then query `/api/public/jobs`
at several offsets and check counts + no duplicate URLs across pages. Confirm
`job_pool` and `canonical_job (status='live')` counts moved as expected.
