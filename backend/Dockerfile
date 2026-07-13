FROM python:3.12-slim

# System deps:
#   libpq-dev / gcc — psycopg2 / asyncpg builds
#   libreoffice-core/writer + fonts — DOCX -> PDF via soffice (resume_builder.py)
#   playwright runtime libs come via `playwright install chromium --with-deps`
RUN apt-get update && apt-get install -y --no-install-recommends \
      libpq-dev \
      gcc \
      git \
      curl \
      libreoffice-core \
      libreoffice-writer \
      tesseract-ocr \
      fonts-liberation \
      fonts-dejavu-core \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir gunicorn==23.0.0

# Headless Chromium for SmartApplyAgent — pulls its own system libs
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install chromium

# Vendor the resume-formatter repo so PDF rendering works inside the image.
# RESUME_FORMATTER_PATH defaults to this location; override at runtime to swap.
ARG RESUME_FORMATTER_REPO=https://github.com/skilluence/resume-formatter.git
ARG RESUME_FORMATTER_REF=main
RUN git clone --depth 1 --branch ${RESUME_FORMATTER_REF} ${RESUME_FORMATTER_REPO} /opt/resume-formatter \
    && if [ -f /opt/resume-formatter/backend/requirements.txt ]; then \
         pip install --no-cache-dir -r /opt/resume-formatter/backend/requirements.txt; \
       fi
ENV RESUME_FORMATTER_PATH=/opt/resume-formatter

# App code
COPY . .

# Non-root runtime user (Playwright still works as long as it can write
# /home/app/.cache). Uploads dir is owned by app so volume mounts inherit perms.
RUN useradd -m -u 1000 app \
    && mkdir -p /app/uploads /home/app/.cache /ms-playwright \
    && chown -R app:app /app /home/app/.cache /ms-playwright /opt/resume-formatter \
        && chmod +x /app/start.sh
USER app

EXPOSE 8000

# Default command is the API. docker-compose overrides this for worker/beat.
# gunicorn manages uvicorn workers (proper signal handling, graceful reload,
# worker recycling on memory leaks).
CMD ["/bin/bash", "/app/start.sh"]
