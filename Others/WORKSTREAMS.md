# AK24/7Jobs — Parallel Workstreams & Coordination

> Read this + `Others/PLAN.md` before doing anything. We run multiple Claude agents in parallel, each owning a disjoint set of files. **The golden rule: edit ONLY the files your workstream owns. Never touch another stream's files.** We are NOT in git — a collision = lost work.

## Repo
- Root: `d:\Code1\aiapply` · Backend: `backend/app` (FastAPI async + SQLAlchemy + Postgres) · Frontend: `frontend/src` (React 19 + Vite + Tailwind + TanStack Query).
- Conventions: `.context/skills.md`. All AI goes through `resume_tailor._generate(system, user, max_tokens)` (temp=0) + `_parse_json()`. async/await throughout; SQLAlchemy v2 `Mapped`; Pydantic v2.

## Lean stack decisions (locked)
- **Sized for ~100 test users.** No microservices. **Drop Celery/Beat → APScheduler** (in-process cron). **pgvector inside Postgres** for embeddings (no separate vector DB). Postgres FTS for lexical. 2 processes: API + scheduler.
- Matching = **retrieve (pgvector + FTS) → rerank top ~20 with gpt-4o → 0-100 score + why-fit**. Embeddings: OpenAI `text-embedding-3-small` (1536 dims), precomputed at ingest.

## Ownership matrix — EDIT ONLY YOUR FILES

| Stream | Owner | Files it may edit/create |
|---|---|---|
| **F — Foundation/Integration** | **Claude (me)** | `backend/app/models/*`, `backend/alembic/versions/*`, `backend/app/config.py`, `backend/.env.example`, `backend/requirements.txt`, `backend/app/main.py`, `backend/app/core/database.py`, `backend/app/workers/*` (→ scheduler), NEW `backend/app/services/embeddings.py`, NEW `backend/app/core/scheduler.py`, this doc |
| **A1 — Discovery** | agent | `backend/app/agents/job_discovery_agent.py`; NEW `backend/app/agents/ats_sources.py`, `backend/app/services/jobs_aggregators.py`, `backend/app/agents/scrape_sources.py`, `backend/app/services/query_builder.py`, `backend/app/data/india_company_slugs.json` |
| **A2 — Matching** | agent | `backend/app/services/job_scorer.py`; NEW `backend/app/services/matching.py` |
| **A3 — Resume/Profile** | agent | `backend/app/services/resume_tailor.py`, `backend/app/api/routes/profile.py`, `backend/app/api/routes/tailored_resumes.py`; NEW `backend/app/services/resume_parser.py`, `backend/app/services/jd_extractor.py` |
| **A4 — Gmail/Comms/Copilot** | agent | `backend/app/services/email_classifiers.py`, `application_tracker.py`, `gmail_client.py`, `gmail_labels.py`, `contact_finder.py`, `backend/app/api/routes/auth.py`; NEW `backend/app/api/routes/copilot.py`, `backend/app/services/copilot.py` |
| **A5 — Frontend** | agent | everything under `frontend/**` |

If you need a change in a file you DON'T own, write it as a request in your status file (below) — do not edit it. Foundation owns all model/schema/config/routing so streams never collide there.

## Shared contracts (depend on these; do NOT redefine)

**1. `_generate` (in `resume_tailor.py`, owned by A3 — signature is FROZEN, all streams import it):**
```python
async def _generate(system: str, user: str, max_tokens: int = 1000, model: str = "gpt-4o") -> str: ...
def _parse_json(raw: str) -> dict: ...   # tolerant JSON parse (handles ```json fences)
```

**2. `embeddings.py` (Foundation provides; A1/A2 import):**
```python
async def embed_text(text: str) -> list[float]        # 1536-dim, text-embedding-3-small
async def embed_texts(texts: list[str]) -> list[list[float]]   # batched
```

**3. Normalized job dict — every Discovery adapter returns list of these:**
```python
{
  "job_url": str, "title": str|None, "company": str|None, "location": str|None,
  "job_description": str|None, "source": str,            # "greenhouse"|"timesjobs"|"naukri"|...
  "work_arrangement": str|None,                          # remote|hybrid|onsite|unknown
  "posted_at": datetime|None,
  "salary_lpa": float|None, "salary_raw": str|None, "notice_period": str|None,
}
```

**4. Discovery entrypoint (A1 provides; Foundation's scheduler calls it):**
```python
# in agents/job_discovery_agent.py
async def discover_for_profile(profile_id: int, user_id: int) -> list[dict]: ...
```

**5. Matching entrypoint (A2 provides; Foundation's scheduler + routes call it):**
```python
# in services/matching.py
async def refresh_user_feed(user_id: int) -> int: ...   # returns count of matches written
```

**6. New/changed DB columns — ✅ LANDED & MIGRATED (rev `e1f2a3b4c5d6`, DB is at head). Everyone may READ/WRITE these now:**
- `discovered_jobs`: + `salary_lpa Float`, `salary_raw String(120)`, `notice_period String(20)`, `match_explanation Text`, `missing_skills Text`
- `job_search_profiles`: + `min_salary_lpa Float`, `max_notice_period_days Int`, `generated_queries Text`
- `job_pool`: + `salary_lpa`, `salary_raw`, `notice_period`  (+ GIN full-text index `ix_job_pool_fts` on title+company+description for lexical retrieval)
- `users`: + `profile_summary Text`, `work_experience/education/skills/projects/certifications` (JSON), `current_ctc_lpa Float`, `expected_ctc_lpa Float`, `notice_period_days Int`, `preferred_locations Text`
- `tailored_resumes`: + `job_url String(1024)`

**EMBEDDINGS / pgvector = FAST-FOLLOW (not yet):** the current Postgres image lacks the `vector` extension, so **v1 retrieval is Postgres FTS-only** (use `ix_job_pool_fts` / `to_tsvector`). `app/services/embeddings.py` (`embed_text`/`embed_texts`, 1536-dim, text-embedding-3-small) is READY — A2 should build retrieval **FTS-first now**, structured so a pgvector cosine (`<=>`, with `halfvec` for storage) layer drops in once Foundation swaps the DB image + adds embedding columns. Don't add embedding columns yourself.

**7. Routers — Foundation registers ALL routers in `main.py` (including NEW `copilot`). Route agents only implement their router module; do NOT edit main.py.**

## Coordination protocol
1. **File ownership is absolute.** Only edit files in your row.
2. **Status file:** each agent maintains `Others/status/<stream>.md` (e.g. `Others/status/A1-discovery.md`) — a short checklist + "current state" + "blocked on / requests for Foundation". Update it as you go. This is how we all see each terminal's progress. (Each agent owns only its own status file → no conflicts.)
3. **Don't run migrations** — Foundation owns Alembic + the DB schema. Code against contract #6; Foundation runs `alembic upgrade head`.
4. **Don't install/edit `requirements.txt`** — tell Foundation which package you need (e.g. `python-jobspy`, `pgvector`, `apscheduler`, `feedparser`) via your status file; Foundation adds it.
5. **Test only your unit** in isolation; Foundation does integration (`uvicorn` + scheduler) once streams land.
6. Conventions from `.context/skills.md`; reuse existing utilities; prefer editing existing files over new ones within your scope.

## Sequencing
- Foundation lands contracts (#1-#7) FIRST so everyone is unblocked. Agents can start writing their NEW files immediately against the contracts above (the shapes are fixed here) even before the migration runs.
- Integration order: Foundation migration → A1 discovery + A2 matching → A3 resume/profile + A4 gmail/copilot → A5 frontend binds to the APIs.