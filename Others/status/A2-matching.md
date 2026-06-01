# A2 — Matching (resume ↔ job matching engine)

Owner: Matching Engineer. Status file for stream A2.

## Checklist
- [x] `job_scorer.py` — LLM call extended to also return `{score, explanation, missing_skills}` (keeps existing `score`/`reason`)
- [x] `job_scorer.py` — "fresher"/"freshers" added to the entry-level experience regex
- [x] `matching.py` — `refresh_user_feed(user_id) -> int` (contract #5)
- [x] Stage 1 RETRIEVE — hybrid pgvector cosine + Postgres FTS over `job_pool`, RRF-fused to ~100 candidates; India/freshness/salary filters in SQL
- [x] Stage 2 RERANK — top ~30 fused candidates scored by `JobScorer`; results written into `discovered_jobs` (match_score, match_reason, match_explanation, missing_skills, salary_*/notice)
- [x] In-process verdict cache keyed by `(job_pool_id, profile_hash)`
- [ ] Integration test on a real DB once Foundation's migration + pgvector land (DEPENDENCY below)

## Current state
Code complete and byte-compiles. `job_scorer.score()` now returns
`{score, reason, explanation, missing_skills}` — `missing_skills` merges our regex
skill-taxonomy gaps with the LLM's free-form gaps (deduped, regex-first, capped at 8).

`matching.refresh_user_feed(user_id)`:
1. Loads the user; builds `users.profile_embedding` via `embeddings.embed_text` if NULL
   and persists it (writing a value, not schema).
2. Loads the user's active `JobSearchProfile` for filters + FTS query text.
3. Stage 1: two ranked SQL queries over `job_pool` — vector (`embedding <=> profile_embedding`)
   and FTS (`ts_rank` over title+description) — fused with reciprocal-rank fusion (k=60).
   Filters pushed into SQL: India location (POSIX `~*`, NULL/remote kept), freshness
   (`COALESCE(posted_at, last_seen_at) >= cutoff`), min salary (NULL kept).
4. Stage 2: top 30 scored via `JobScorer` (cached), upserted into `discovered_jobs`
   keyed on `(user_id, job_url)`. Returns the count written.

All cross-schema access (embedding/salary/why-fit columns the ORM models don't declare
yet) is done with raw `text()` SQL so the module is correct against contract #6 without
my touching Foundation's models.

### Decisions worth flagging
- **Candidate source = `job_pool`** (the shared pool — the only table with `embedding`
  per contract #6). `discovered_jobs` is the per-user write target, not a retrieval
  source (it has no embedding). I read the brief's "jobs.embedding / job_pool.embedding"
  as "the job pool's embedding".
- **`missing_skills` storage format**: JSON array string (`json.dumps([...])`) in the
  `discovered_jobs.missing_skills` Text column — unambiguous for the frontend to render
  as chips. Flagging for A5/A3: parse with `json.loads`.
- `embeddings` is imported **lazily** inside `refresh_user_feed` so this module imports
  cleanly even before Foundation lands `embeddings.py`.

## Blocked on / DEPENDENCIES for Foundation
These must land before `refresh_user_feed` can run end-to-end (it is coded against them
now, per the brief):
1. **pgvector extension** enabled + **HNSW index** on `job_pool.embedding` (contract #6).
2. **Migration columns** (contract #6) — read/written by this code:
   - `job_pool`: `embedding vector(1536)`, `salary_lpa`, `salary_raw`, `notice_period`
   - `users`: `profile_embedding vector(1536)`
   - `discovered_jobs`: `match_explanation Text`, `missing_skills Text`, `salary_lpa`,
     `salary_raw`, `notice_period`
   - `job_search_profiles`: `min_salary_lpa Float`, `posted_within_days` (exists)
3. **`embeddings.py`** providing `embed_text` / `embed_texts` (1536-dim) — contract #2.
4. **Job-pool population must include embeddings** at ingest (A1/Foundation): a pool row
   needs `embedding` set or it's invisible to Stage-1 vector retrieval. FTS still works
   without it, but hybrid quality needs both.

## Requests for Foundation (pip packages — I do NOT edit requirements.txt)
- None beyond what's already implied by contract #2 (`pgvector`, OpenAI client for
  `embeddings.py`). No new packages needed by A2 itself.

## Contracts honored
- `refresh_user_feed(user_id: int) -> int` (#5) — count of matches written.
- Imports `embed_text` from `app.services.embeddings` (#2); does not build its own embedder.
- `JobScorer` reuses `_generate`/`_parse_json` from `resume_tailor` (#1) — no second client.
- Writes only contract-#6 fields on `discovered_jobs` / `users` / reads `job_pool`.
- Edited/created ONLY: `job_scorer.py`, `matching.py`, this status file.

## Verify (once dependencies land)
Seed a test user with `resume_text`, an active `JobSearchProfile`, and ≥1 `job_pool`
row with `embedding` set, then `await refresh_user_feed(user_id)` → expect rows in
`discovered_jobs` with non-null `match_score`, `match_explanation`, `missing_skills`.
