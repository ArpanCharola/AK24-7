# AK24/7 Jobs

AK24/7 Jobs is a full-stack job-search and application-tracking platform for
India-focused candidates. It combines a React dashboard, FastAPI backend,
Postgres database, background job aggregation, resume-aware matching, and Gmail
workflow tools into one workspace.

## Highlights

- Browse and search technical job opportunities from a shared job pool.
- Match jobs against a user profile, skills, locations, and target roles.
- Track applications with recruiter email context and saved application records.
- Use Google sign-in and optional Gmail permissions for inbox-based workflows.
- Manage users, discovery runs, and job data from an admin console.

## Tech Stack

- Frontend: React, Vite, Tailwind CSS, TanStack Query, React Router
- Backend: FastAPI, SQLAlchemy async, Pydantic, Alembic
- Data: Postgres, Redis
- Background work: scheduler-driven aggregation and cleanup jobs
- Integrations: Google OAuth, Gmail API, OpenAI-assisted matching and drafting

## Project Structure

```text
backend/
  app/
    agents/        job discovery and source adapters
    api/routes/    FastAPI route modules
    core/          auth, database, scheduler, bootstrap
    models/        SQLAlchemy models
    services/      matching, aggregation, email, resume services
  alembic/         database migrations
  tests/           backend tests

frontend/
  src/
    components/    reusable UI components
    pages/         dashboard, jobs, email, tracker, admin
    services/      API client
```

## Local Setup

### Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env
.\venv\Scripts\python.exe bootstrap_db.py
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` after the API is running on port `8000`.

## Database

Fresh local databases can be initialized with:

```powershell
cd backend
.\venv\Scripts\python.exe bootstrap_db.py
```

Existing databases should continue forward through Alembic:

```powershell
cd backend
alembic upgrade head
```

## Tests

```powershell
cd backend
pytest -q

cd frontend
npm run build
```

## Notes

This repository keeps local secrets, environment files, generated build output,
and private working notes out of Git through `.gitignore`.
