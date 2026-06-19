import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.core.database import init_db
from app.core.bootstrap import ensure_admin
from app.core.scheduler import start_scheduler, shutdown_scheduler
import app.models  # registers all models with SQLAlchemy before any query runs
from app.api.routes import auth, applications, otp, profile, job_searches, discovered_jobs, tailored_resumes, email, mail_tracker, saved_applications, dashboard, public_jobs, admin, matches
from app.api.websocket import ws_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.warning(f"Database init failed (is Postgres running?): {e}")
    try:
        await ensure_admin()
    except Exception as e:
        logger.warning(f"Admin bootstrap skipped: {e}")
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="AK24/7Jobs API",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins = (
    ["*"]
    if settings.DEBUG
    else [o.strip() for o in (settings.CORS_ORIGINS or "").split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # Credentials must be False when allow_origins=["*"] (browser rejects the
    # combo). Behind a real domain in prod, both are safe to flip on.
    allow_credentials=not settings.DEBUG,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(applications.router, prefix="/api", tags=["applications"])
app.include_router(otp.router, prefix="/api/otp", tags=["otp"])
app.include_router(profile.router, prefix="/api", tags=["profile"])
app.include_router(job_searches.router, prefix="/api", tags=["job-searches"])
app.include_router(discovered_jobs.router, prefix="/api", tags=["discovered-jobs"])
app.include_router(matches.router, prefix="/api/matches", tags=["matches"])
app.include_router(tailored_resumes.router, prefix="/api", tags=["tailored-resumes"])
app.include_router(email.router, prefix="/api/email", tags=["email"])
app.include_router(mail_tracker.router, prefix="/api/mail-applications", tags=["mail-applications"])
app.include_router(saved_applications.router, prefix="/api/saved-applications", tags=["saved-applications"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
# Public + pool: GET /api/public/{job-search,jobs} unauth, POST /api/public/import-to-profile/{id} authed
app.include_router(public_jobs.router, prefix="/api/public", tags=["public-jobs"])
app.include_router(ws_router, prefix="/ws", tags=["websocket"])

# Orion copilot (stream A4) — auto-registers once the router module exists.
try:
    from app.api.routes import copilot as _copilot
    app.include_router(_copilot.router, prefix="/api/copilot", tags=["copilot"])
except ImportError:
    logger.info("copilot router not present yet — skipping (stream A4 will add it)")


@app.get("/health")
async def health():
    return {"status": "ok"}
