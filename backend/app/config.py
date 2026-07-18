from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache


_ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE), case_sensitive=True, extra="ignore"
    )

    # App
    APP_NAME: str = "AK24/7Jobs"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Comma-separated list of allowed frontend origins for CORS. Production:
    # set to e.g. "https://app.yourdomain.com". Dev default keeps the
    # localhost ports the Vite dev server typically lands on.
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_apply"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _force_asyncpg_driver(cls, v: str) -> str:
        """Coerce a plain Postgres URL to the asyncpg driver.

        Managed hosts (Render, Neon, Heroku, …) hand out connection strings as
        ``postgresql://`` or ``postgres://``. SQLAlchemy's async engine needs the
        ``postgresql+asyncpg://`` driver prefix, so paste the host's URL verbatim
        and this normalizes it. URLs that already name a driver are left as-is.
        """
        if not isinstance(v, str):
            return v
        if v.startswith("postgresql+") or v.startswith("postgres+"):
            return v
        if v.startswith("postgresql://"):
            return "postgresql+asyncpg://" + v[len("postgresql://"):]
        if v.startswith("postgres://"):
            return "postgresql+asyncpg://" + v[len("postgres://"):]
        return v

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # AI
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # The shared warehouse is a product capability, not a user-triggered scrape.
    # Deploy a single scheduler-owning API worker or set this false in replicas.
    ENABLE_SCHEDULER: bool = True

    # Gmail + Google Sign-In — new "AK24/7Jobs" Google Cloud project (read/label/send).
    GOOGLE_PROJECT_ID: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/email/callback"
    FRONTEND_URL: str = "http://localhost:5173"

    # India job sources (Tier 2). Free; leave blank to disable that source.
    JOOBLE_API_KEY: str = ""          # direct Jooble API: POST https://jooble.org/api/{key}
    ENABLE_SCRAPE_TIMESJOBS: bool = True   # official RSS — low risk

    # ── Tier-3 scraping (all-in, self-host, free) ────────────────────────────
    # Master gate. Off by default so a hosted env never scrapes unintentionally;
    # flip to true (in .env) to enable the per-source toggles below.
    TIER3_ENABLED: bool = True
    # Per-source toggles. jobspy boards + the custom adapters. A source that is
    # off is skipped entirely; a source that is on but fails degrades to [].
    SCRAPE_INDEED: bool = True
    SCRAPE_GOOGLE: bool = True
    # Naukri currently challenges direct JobSpy traffic with reCAPTCHA. Keep
    # it opt-in so a normal local run does not emit repeated 406 errors.
    SCRAPE_NAUKRI: bool = False
    SCRAPE_LINKEDIN: bool = True       # Cloudflare/rate-limited — best-effort without proxies
    # Glassdoor commonly rejects direct scraper traffic (403). Enable it only
    # when SCRAPE_PROXIES points at a proxy known to work for the board.
    SCRAPE_GLASSDOOR: bool = False
    SCRAPE_INSTAHYRE: bool = True      # custom adapter (internal JSON API)
    SCRAPE_CUTSHORT: bool = True       # custom adapter (__NEXT_DATA__ / JSON-LD)
    SCRAPE_WELLFOUND: bool = True      # custom adapter (stealth browser) — best-effort
    SCRAPE_HIRECT: bool = False        # mobile-API spike — off until an endpoint is confirmed
    SCRAPE_HIRIST: bool = False        # hirist.tech (Next.js SSR) — opt-in; robots allows listing pages (Crawl-delay 10)
    SCRAPE_HIRIST: bool = True
    HIRIST_API_BASE: str = ""          # reserved if a hirist JSON API is later confirmed

    # Comma-separated proxies for Tier-3 (e.g. "http://user:pass@host:port,..").
    # Empty = direct connection. The protected boards (LinkedIn/Glassdoor/
    # Wellfound) are unreliable without residential proxies — plug them here
    # with no code change when budget allows.
    SCRAPE_PROXIES: str = ""
    # Circuit breaker: after N consecutive failures a source self-disables for
    # COOLDOWN seconds so a blocked board stops wasting the run, then retries.
    SCRAPE_CIRCUIT_THRESHOLD: int = 3
    SCRAPE_CIRCUIT_COOLDOWN: int = 1800
    # Stealth browser (Camoufox/Playwright) for JS + anti-bot boards (Wellfound,
    # Glassdoor/LinkedIn fallback). Off → those sources skip their browser path.
    STEALTH_ENABLED: bool = True

    # Hirect mobile API (reverse-engineered). HIRECT_TOKEN is a captured/refreshed
    # bearer token; HIRECT_API_BASE is the discovered endpoint host. Both blank
    # until the spike confirms them — adapter returns [] when unset.
    HIRECT_TOKEN: str = ""
    HIRECT_API_BASE: str = ""
    # Fernet key for encrypting stored OAuth tokens at rest. If unset, a stable
    # key is derived from SECRET_KEY (see core/encryption.py).
    ENCRYPTION_KEY: str = ""
    # When true, outbound email (compose/send + autonomous follow-ups) is LOGGED
    # instead of actually sent — safe default for first rollout of sending.
    EMAIL_SEND_DRYRUN: bool = False

    # Resume builder integration — local path to the skilluence/resume-formatter clone.
    # The resume_builder service imports modules from "<this path>/backend/".
    # Set this in .env to wherever you cloned the resume-formatter repo.
    RESUME_FORMATTER_PATH: str = ""

    # Apify — used by services/contact_finder.py to scrape company careers/
    # about pages for recruiter contact info. Leave APIFY_TOKEN blank to
    # disable the paid enrichment tier (free tiers still run).
    APIFY_TOKEN: str = ""
    APIFY_CONTACT_ACTOR_ID: str = "vdrmota~contact-info-scraper"

    # SerpAPI — used by services/serpapi_jobs.py for Google Jobs aggregator
    # discovery (LinkedIn / Indeed / Glassdoor / company pages). Leave blank
    # to disable; the other discovery sources continue to work.
    SERPAPI_KEY: str = ""

    # Proxy
    PROXY_URL: str = ""
    PROXY_USERNAME: str = ""
    PROXY_PASSWORD: str = ""

    # Storage
    S3_BUCKET: str = ""
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
