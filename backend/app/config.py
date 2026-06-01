from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", case_sensitive=True, extra="ignore"
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

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # AI
    OPENAI_API_KEY: str = ""
    EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Background scheduler (APScheduler replaces Celery Beat). Off until discovery/
    # matching streams land; flip to true to run periodic discovery + daily digest.
    ENABLE_SCHEDULER: bool = False

    # Gmail + Google Sign-In — new "AK24/7Jobs" Google Cloud project (read/label/send).
    GOOGLE_PROJECT_ID: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/email/callback"
    FRONTEND_URL: str = "http://localhost:5173"

    # India job sources (Tier 2). Free; leave blank to disable that source.
    JOOBLE_API_KEY: str = ""          # direct Jooble API: POST https://jooble.org/api/{key}
    # Tier-3 scraping toggles (all-in but per-source switchable; off by default in hosted env).
    ENABLE_JOBSPY: bool = False       # python-jobspy: naukri/indeed/linkedin/google/glassdoor
    ENABLE_SCRAPE_TIMESJOBS: bool = True   # official RSS — low risk
    SCRAPE_PROXIES: str = ""          # comma-separated residential proxies for Tier-3
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
