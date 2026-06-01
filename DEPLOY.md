# Production deploy (Dokploy / any Docker host)

This document is a practical checklist, not a tutorial. Run things in order.

The production stack uses [`docker-compose.prod.yml`](docker-compose.prod.yml) — do NOT deploy the dev `docker-compose.yml` (it runs Vite in dev mode, uses bind mounts, and hot-reloads the API).

## Stack at a glance

| Service | What it is | Replicas |
|---|---|---|
| `postgres` | Postgres 16, persistent volume | 1 |
| `redis` | Redis 7, persistent volume, 256MB LRU cap | 1 |
| `migrate` | One-shot: runs `alembic upgrade head`, exits | 1 (per deploy) |
| `api` | FastAPI behind gunicorn (2 workers, uvicorn worker class) | 1+ |
| `worker` | Celery worker, concurrency 4, recycle every 50 tasks | 1+ |
| `beat` | Celery beat scheduler | **exactly 1** |
| `frontend` | nginx serving built Vite assets | 1+ |

## Pre-deploy

### 1. Rotate every credential

The following values were pasted around during development. Treat as compromised — rotate before going live:
- `OPENAI_API_KEY` → https://platform.openai.com/api-keys
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` → https://console.cloud.google.com/apis/credentials
- `SERPAPI_KEY` → https://serpapi.com/manage-api-key
- `APIFY_TOKEN` → https://console.apify.com/account/integrations

Then regenerate:
- `SECRET_KEY`: `openssl rand -hex 32`
- `ENCRYPTION_KEY`: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`

### 2. Update Google OAuth

In Google Cloud Console, on the OAuth client you'll use in production:
- **Authorized JavaScript origins:** add `https://app.yourdomain.com`
- **Authorized redirect URIs:** add `https://api.yourdomain.com/api/email/callback`
- Keep your existing test users — without OAuth verification + CASA, only listed test users can use Gmail features.

### 3. Build a production `backend/.env`

Start from [`backend/.env.example`](backend/.env.example) and set:

```
APP_NAME=AI Apply
DEBUG=false
SECRET_KEY=<openssl rand -hex 32>
ENCRYPTION_KEY=<Fernet.generate_key>
CORS_ORIGINS=https://app.yourdomain.com

DATABASE_URL=postgresql+asyncpg://postgres:<password>@postgres:5432/ai_apply
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

OPENAI_API_KEY=<rotated>

GOOGLE_CLIENT_ID=<rotated>
GOOGLE_CLIENT_SECRET=<rotated>
GOOGLE_REDIRECT_URI=https://api.yourdomain.com/api/email/callback
FRONTEND_URL=https://app.yourdomain.com

# Pre-cloned inside the backend image; leave as-is
RESUME_FORMATTER_PATH=/opt/resume-formatter

# Public job search via SerpAPI
SERPAPI_KEY=<your key>
APIFY_TOKEN=<your key>
APIFY_CONTACT_ACTOR_ID=vdrmota~contact-info-scraper

# Start true; flip to false once you've smoke-tested outbound mail
EMAIL_SEND_DRYRUN=true
```

Top-level `.env` (for `docker-compose.prod.yml` variable substitution — `POSTGRES_*` + frontend build args):

```
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<strong>
POSTGRES_DB=ai_apply

VITE_API_URL=https://api.yourdomain.com/api
VITE_WS_URL=wss://api.yourdomain.com/ws
```

## Dokploy deploy

1. Create a project in Dokploy, import this repo
2. Use `docker-compose.prod.yml` as the compose source
3. Attach both `.env` files via the UI (top-level + `backend/.env`)
4. Configure two domains via Dokploy's Traefik integration:
   - `app.yourdomain.com` → `frontend` service, port 80
   - `api.yourdomain.com` → `api` service, port 8000
5. Enable Let's Encrypt SSL on both (Dokploy handles renewal)
6. Deploy. On first boot:
   - `migrate` runs `alembic upgrade head` and exits
   - `api` / `worker` / `beat` come up after migration completes
   - `frontend` builds with the production VITE_API_URL baked in

## Verification after first deploy

```bash
# 1. Database came up + migrations applied
curl -fsS https://api.yourdomain.com/health
# → {"status": "ok"}

# 2. Frontend renders
curl -fsS https://app.yourdomain.com/healthz
# → ok

# 3. Public search works without login (will fail if SERPAPI_KEY isn't set)
curl -fsS "https://api.yourdomain.com/api/public/job-search?role=Software+Engineer&pages=1" | head -c 400

# 4. Sign in with Google end-to-end
# Browser → https://app.yourdomain.com/login → Sign in with Google
# → consent gate appears → accept → /dashboard loads

# 5. Worker logs show the scheduled tasks running
docker logs <project>-worker-1 --tail 50
# Expected: "scan_email_confirmations" hourly, "auto_followups" daily
```

## Capacity sizing

| Concurrent active users | RAM | CPU | Notes |
|---|---|---|---|
| 1–10 | 4 GB | 2 vCPU | Single VPS handles everything |
| 10–50 | 8 GB | 4 vCPU | Bump `worker` concurrency from 4 → 8 |
| 50–200 | 16 GB | 8 vCPU | Split api / worker onto separate hosts; managed Postgres |
| 200+ | — | — | Move past Dokploy; introduce Kubernetes/ECS, read replicas, Redis cluster |

Playwright (Chromium) is the biggest RAM driver per concurrent apply attempt — budget ~300MB per active browser.

## Built-in load resilience

| Concern | Mitigation in this repo |
|---|---|
| Long-running apply tasks hang the worker | Celery `task_soft_time_limit=10min` + `task_time_limit=12min` |
| Playwright memory leaks | `--max-tasks-per-child=50` recycles workers |
| Postgres idle timeouts (managed PGs kill connections after 1h) | SQLAlchemy `pool_recycle=1800` |
| Stale connections after Postgres restart | `pool_pre_ping=True` |
| DB connection exhaustion | `pool_size=10 + max_overflow=10` per process, 6 processes → 120 max |
| Public search abuse | Redis-backed fixed-window rate limit (10/min/IP on search, 60/min/IP on browse), with in-memory fallback if Redis goes down |
| Multi-worker rate limiter consistency | Uses Redis INCR — counts across workers, not per-process |
| Browser request floods | gunicorn `--max-requests=1000 --max-requests-jitter=100` recycles uvicorn workers |
| Worker prefetch grabbing too many tasks | Celery `worker_prefetch_multiplier=1` keeps tasks distributed |
| Lost task on worker crash | `task_reject_on_worker_lost=True` |
| Beat duplicate scheduling | docker-compose `replicas: 1, mode: replicated` on `beat` |

## Backups

Dokploy can take volume snapshots — enable for `postgres_data` (daily, 7-day retention is fine for v1). Test restore once before relying on it.

For per-user files in `uploads_data`: same volume snapshot policy works.

## Updating after deploy

Push to `main` → Dokploy auto-redeploys → on each deploy the `migrate` service runs first, then `api`/`worker`/`beat` come up. Zero-downtime requires manual blue/green for v1 — Dokploy's built-in rolling update covers basic cases.

## Things NOT in v1 that you'll eventually want

- **Sentry or similar error tracking** — `logger.warning` lines disappear into stdout otherwise
- **Prometheus + Grafana metrics** — Celery + Postgres exporters are well-trodden
- **CDN (Cloudflare) in front of frontend + api** — drops latency for global users, adds bot/ddos protection
- **OAuth verification + CASA assessment** for Google — required to remove the "unverified app" screen for users outside your test list
- **Background job for old JobPool cleanup** — currently grows monotonically; add a Celery beat task to delete rows with `last_seen_at < now() - 30 days`
- **uploads/ cleanup** — generated PDFs persist forever; add cleanup for completed applications older than N days
