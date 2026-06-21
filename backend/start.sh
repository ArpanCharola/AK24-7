#!/bin/bash
set -e

# Create tables + stamp Alembic on a fresh DB (safe no-op on an existing one).
python bootstrap_db.py

# Bind to the platform-injected $PORT (Render/most PaaS); fall back to 8000 for
# local/docker-compose. Worker count defaults to 1 to fit free-tier RAM
# (LibreOffice + the app); override with WEB_CONCURRENCY on a larger instance.
exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}"
