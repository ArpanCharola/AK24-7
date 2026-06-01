"""Resume <-> job matching engine (stream A2).

Two stages:

1. RETRIEVE — hybrid candidate generation over the shared ``job_pool``:
   pgvector cosine similarity (``job_pool.embedding`` vs ``users.profile_embedding``)
   fused with Postgres full-text search via reciprocal-rank fusion (RRF).
   India / freshness / salary filters are pushed into SQL. Yields ~100 candidates.

2. RERANK — the top ~30 fused candidates are scored by ``JobScorer`` (regex skill
   match + gpt-4o role-fit + why-fit explanation + missing skills), and the
   verdicts are written into the per-user ``discovered_jobs`` table.

Verdicts are cached in-process keyed by ``(job_pool_id, profile_hash)`` so repeated
feed refreshes for an unchanged profile don't re-pay the LLM cost.

Schema dependency: the embedding/salary/why-fit columns this module reads and writes
(``job_pool.embedding``, ``users.profile_embedding``, ``discovered_jobs.match_explanation``,
``discovered_jobs.missing_skills``, ``*.salary_lpa`` …) are landed by Foundation's
migration (WORKSTREAMS contract #6) + the pgvector extension. We code against them via
raw SQL; if the migration hasn't run yet, these queries will fail until it does.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.services.job_scorer import JobScorer

logger = logging.getLogger(__name__)

# Stage-1 fused candidate budget; stage-2 LLM rerank budget (top slice of the fusion).
_CANDIDATE_POOL_SIZE = 100
_RERANK_TOP_N = 30
# Default lookback when the profile doesn't pin a freshness window.
_DEFAULT_FRESHNESS_DAYS = 30
# Reciprocal-rank-fusion constant (standard ~60): dampens the head so a single
# list can't dominate the fused order.
_RRF_K = 60
# Cap on resume/career text fed to the embedder.
_MAX_EMBED_CHARS = 8000

# POSIX (~*) location filter — India metros + common spellings + remote. Best-effort:
# rows with a NULL location are kept (the pool is India-only post-pivot, and a job
# whose location simply wasn't parsed shouldn't be silently dropped).
_INDIA_LOCATION_RE = (
    r"(india|bangalore|bengaluru|mumbai|navi mumbai|delhi|new delhi|noida|gurgaon|"
    r"gurugram|hyderabad|pune|chennai|kolkata|ahmedabad|jaipur|kochi|cochin|"
    r"coimbatore|indore|chandigarh|trivandrum|thiruvananthapuram|nagpur|vadodara|"
    r"surat|visakhapatnam|mysore|mysuru|remote)"
)

_FTS_EXPR = (
    "to_tsvector('english', coalesce(title,'') || ' ' || coalesce(job_description,''))"
)

# Process-wide verdict cache: (job_pool_id, profile_hash) -> score dict.
_VERDICT_CACHE: dict[tuple[int, str], dict] = {}


def _profile_hash(profile: dict) -> str:
    blob = "|".join(
        [
            profile.get("resume_text") or "",
            profile.get("career_history") or "",
            profile.get("experience_level") or "",
            profile.get("target_roles") or "",
        ]
    )
    return hashlib.md5(blob.encode("utf-8")).hexdigest()


def _format_vector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"


async def refresh_user_feed(user_id: int) -> int:
    """Retrieve -> rerank -> write scored, explained matches for ``user_id``.

    Returns the number of ``discovered_jobs`` rows written (inserted or updated).
    """
    from app.services.embeddings import embed_text  # lazy: Foundation provides this module

    async with AsyncSessionLocal() as db:
        # ── 0. Load user + ensure a profile embedding exists ──────────────────
        prof = (
            await db.execute(
                text(
                    "SELECT resume_text, career_history, "
                    "(profile_embedding IS NOT NULL) AS has_emb "
                    "FROM users WHERE id = :uid"
                ),
                {"uid": user_id},
            )
        ).mappings().first()

        if not prof:
            logger.info("refresh_user_feed: user %s not found", user_id)
            return 0

        profile_text = f"{prof['career_history'] or ''}\n{prof['resume_text'] or ''}".strip()
        if not profile_text:
            logger.info("refresh_user_feed: user %s has no resume/career text", user_id)
            return 0

        if not prof["has_emb"]:
            emb = await embed_text(profile_text[:_MAX_EMBED_CHARS])
            await db.execute(
                text("UPDATE users SET profile_embedding = CAST(:emb AS vector) WHERE id = :uid"),
                {"emb": _format_vector(emb), "uid": user_id},
            )
            await db.commit()

        # ── 1. Load the active search profile for filters / FTS query ─────────
        sp = (
            await db.execute(
                text(
                    "SELECT id, target_roles, keywords, locations, experience_level, "
                    "posted_within_days, min_salary_lpa "
                    "FROM job_search_profiles "
                    "WHERE user_id = :uid AND is_active = true "
                    "ORDER BY last_run_at DESC NULLS LAST, created_at DESC "
                    "LIMIT 1"
                ),
                {"uid": user_id},
            )
        ).mappings().first()
        sp = sp or {}

        fts_query = " ".join(
            part for part in [sp.get("target_roles"), sp.get("keywords")] if part
        ).strip()
        if not fts_query:
            fts_query = profile_text[:300]

        freshness_days = sp.get("posted_within_days") or _DEFAULT_FRESHNESS_DAYS
        cutoff = datetime.now(timezone.utc) - timedelta(days=int(freshness_days))

        filters = [
            "embedding IS NOT NULL",
            "(location ~* :india OR location IS NULL OR work_arrangement = 'remote')",
            "COALESCE(posted_at, last_seen_at) >= :cutoff",
        ]
        params: dict = {"india": _INDIA_LOCATION_RE, "cutoff": cutoff}
        min_salary = sp.get("min_salary_lpa")
        if min_salary:
            filters.append("(salary_lpa IS NULL OR salary_lpa >= :min_salary)")
            params["min_salary"] = float(min_salary)
        where = " AND ".join(filters)

        # ── 2. Stage 1: hybrid retrieval (vector + FTS) ───────────────────────
        vec_rows = (
            await db.execute(
                text(
                    f"SELECT id, embedding <=> (SELECT profile_embedding FROM users WHERE id = :uid) AS dist "
                    f"FROM job_pool WHERE {where} "
                    f"ORDER BY dist ASC LIMIT :limit"
                ),
                {**params, "uid": user_id, "limit": _CANDIDATE_POOL_SIZE},
            )
        ).all()

        fts_rows = (
            await db.execute(
                text(
                    f"SELECT id, ts_rank({_FTS_EXPR}, plainto_tsquery('english', :q)) AS rank "
                    f"FROM job_pool WHERE {where} "
                    f"AND {_FTS_EXPR} @@ plainto_tsquery('english', :q) "
                    f"ORDER BY rank DESC LIMIT :limit"
                ),
                {**params, "q": fts_query, "limit": _CANDIDATE_POOL_SIZE},
            )
        ).all()

        # Reciprocal-rank fusion of the two ranked lists.
        fused: dict[int, float] = {}
        for rank, row in enumerate(vec_rows):
            fused[row.id] = fused.get(row.id, 0.0) + 1.0 / (_RRF_K + rank + 1)
        for rank, row in enumerate(fts_rows):
            fused[row.id] = fused.get(row.id, 0.0) + 1.0 / (_RRF_K + rank + 1)

        if not fused:
            logger.info("refresh_user_feed: no candidates for user %s", user_id)
            return 0

        ordered_ids = [jid for jid, _ in sorted(fused.items(), key=lambda kv: kv[1], reverse=True)]
        top_ids = ordered_ids[:_RERANK_TOP_N]

        jobs = (
            await db.execute(
                text(
                    "SELECT id, job_url, title, company, location, job_description, source, "
                    "work_arrangement, posted_at, salary_lpa, salary_raw, notice_period "
                    "FROM job_pool WHERE id = ANY(:ids)"
                ),
                {"ids": top_ids},
            )
        ).mappings().all()
        jobs_by_id = {j["id"]: j for j in jobs}

        # ── 3. Stage 2: rerank (LLM score + why-fit) and write matches ────────
        profile = {
            "career_history": prof["career_history"],
            "resume_text": prof["resume_text"],
            "experience_level": sp.get("experience_level"),
            "target_roles": sp.get("target_roles"),
        }
        phash = _profile_hash(profile)
        search_profile_id = sp.get("id")
        scorer = JobScorer()
        now = datetime.now(timezone.utc)
        written = 0

        for jid in top_ids:  # preserve fused order
            job = jobs_by_id.get(jid)
            if not job:
                continue

            cache_key = (jid, phash)
            verdict = _VERDICT_CACHE.get(cache_key)
            if verdict is None:
                try:
                    verdict = await scorer.score(
                        job["job_description"] or "",
                        profile,
                        job_title=job["title"] or "",
                    )
                except Exception as exc:
                    logger.warning("Rerank scoring failed for pool job %s: %s", jid, exc)
                    continue
                _VERDICT_CACHE[cache_key] = verdict

            await _upsert_match(db, user_id, search_profile_id, job, verdict, now)
            written += 1

        await db.commit()
        logger.info("refresh_user_feed: wrote %d matches for user %s", written, user_id)
        return written


async def _upsert_match(
    db,
    user_id: int,
    search_profile_id: int | None,
    job,
    verdict: dict,
    now: datetime,
) -> None:
    """Insert or update the per-user discovered_jobs row for this pool job."""
    try:
        score = int(verdict.get("score") or 0)
    except (TypeError, ValueError):
        score = 0
    reason = verdict.get("reason") or ""
    explanation = verdict.get("explanation") or reason
    missing = verdict.get("missing_skills") or []
    missing_str = json.dumps(missing) if isinstance(missing, list) else str(missing)

    values = {
        "uid": user_id,
        "spid": search_profile_id,
        "url": job["job_url"],
        "title": job["title"],
        "company": job["company"],
        "location": job["location"],
        "jd": job["job_description"],
        "source": (job["source"] or "pool")[:50],
        "work": job["work_arrangement"],
        "posted": job["posted_at"],
        "slpa": job["salary_lpa"],
        "sraw": job["salary_raw"],
        "notice": job["notice_period"],
        "score": score,
        "reason": reason,
        "expl": explanation,
        "missing": missing_str,
        "now": now,
    }

    existing = (
        await db.execute(
            text("SELECT id FROM discovered_jobs WHERE user_id = :uid AND job_url = :url"),
            {"uid": user_id, "url": job["job_url"]},
        )
    ).first()

    if existing:
        values["id"] = existing[0]
        await db.execute(
            text(
                "UPDATE discovered_jobs SET "
                "match_score = :score, match_reason = :reason, match_explanation = :expl, "
                "missing_skills = :missing, salary_lpa = :slpa, salary_raw = :sraw, "
                "notice_period = :notice, scored_at = :now "
                "WHERE id = :id"
            ),
            values,
        )
    else:
        await db.execute(
            text(
                "INSERT INTO discovered_jobs "
                "(user_id, search_profile_id, job_url, title, company, location, job_description, "
                "source, work_arrangement, posted_at, salary_lpa, salary_raw, notice_period, "
                "match_score, match_reason, match_explanation, missing_skills, scored_at, "
                "status, discovered_at) "
                "VALUES (:uid, :spid, :url, :title, :company, :location, :jd, :source, :work, "
                ":posted, :slpa, :sraw, :notice, :score, :reason, :expl, :missing, :now, "
                "'discovered', :now)"
            ),
            values,
        )
