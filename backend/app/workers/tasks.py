import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# Jobs scored more recently than this are not re-scored on subsequent discovery runs.
_SCORE_CACHE_DAYS = 7


def _detect_portal(url: str) -> str:
    url = url.lower()
    if "jobs.adp.com" in url or "myjobs.adp.com" in url:
        return "adp"
    if "careers.oracle.com" in url:
        return "oracle"
    if any(x in url for x in ("myworkdayjobs.com", "workday.com", "wd1.myworkday", "wd3.myworkday", "wd5.myworkday")):
        return "workday"
    if "icims.com" in url:
        return "icims"
    # Greenhouse: direct domain OR company-hosted wrapper carrying ?gh_jid=
    if "greenhouse.io" in url or "boards.greenhouse.io" in url or "gh_jid=" in url:
        return "greenhouse"
    # Ashby: direct domain OR company-hosted wrapper carrying ?ashby_jid=
    if "ashbyhq.com" in url or "jobs.ashby.com" in url or "ashby_jid=" in url:
        return "ashby"
    if "lever.co" in url:
        return "lever"
    return "unknown"


@celery_app.task(bind=True, name="run_application")
def run_application_task(self, application_id: int, user_id: int):
    asyncio.run(_run_application(self, application_id, user_id))


async def _run_application(task, application_id: int, user_id: int):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select, delete
    from app.models.job_application import JobApplication, ApplicationStatus
    from app.models.tailored_resume import TailoredResume
    from app.models.cover_letter import CoverLetter
    from app.models.user import User
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # ── 1. Load application + user ────────────────────────────────────────
        async with AsyncSession() as db:
            app_result = await db.execute(select(JobApplication).where(JobApplication.id == application_id))
            application = app_result.scalar_one_or_none()
            if not application:
                return

            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()

            if not application.portal_type:
                application.portal_type = _detect_portal(application.job_url)

            application.status = ApplicationStatus.RUNNING
            await db.commit()

            # Idempotency for retries / re-runs: clear artifacts from any prior
            # attempt. CoverLetter.application_id is UNIQUE, so re-inserting would
            # raise IntegrityError and crash the task before the agent runs (which
            # left retried apps stuck in RUNNING). TailoredResume would also
            # accumulate duplicate rows. Regenerate fresh each run.
            await db.execute(delete(CoverLetter).where(CoverLetter.application_id == application_id))
            await db.execute(delete(TailoredResume).where(TailoredResume.application_id == application_id))
            await db.commit()

            job_description = application.job_description or ""
            job_url = application.job_url
            job_title = application.job_title or ""
            company = application.company or ""
            portal_type = application.portal_type

        user_profile = {
            "full_name": user.full_name if user else None,
            "email": user.email if user else None,
            "phone": user.phone if user else None,
            "location": user.location if user else None,
            "linkedin_url": user.linkedin_url if user else None,
            "github_url": user.github_url if user else None,
            "website": user.website_url if user else None,
            "career_history": user.career_history if user else None,
            "resume_text": user.resume_text if user else None,
            "portal_email": user.portal_email if user else None,
            "portal_password": user.portal_password if user else None,
            "tailored_resume_text": None,
            "cover_letter_text": None,
            "resume_pdf_bytes": None,  # Phase 6C — populated when resume builder is integrated
        }

        # ── 2. Prep artifacts concurrently (Phase 7 — parallelized) ──────────
        # Resume tailoring, PDF render, and cover letter were previously run
        # serially (~15-25s). They are independent except that the PDF needs the
        # tailored text, so we run three concurrent branches and chain only
        # tailor→PDF. DB writes happen AFTER the gather (concurrent AsyncSessions
        # on one engine are unsafe). Every branch is best-effort: a failure in
        # one must not abort the apply (the agent step decides success/failure).
        from app.services.resume_tailor import ResumeTailor
        from app.services.resume_builder import render_pdf_resume, resume_archive_path
        from app.services.progress import publish_step

        tailor = ResumeTailor()
        has_resume = bool(job_description and user and user.resume_text)
        # Cover-letter grounding falls back to resume_text when career_history is
        # empty (most users only fill resume_text), so more applies get a letter.
        cl_grounding = (user.career_history or user.resume_text) if user else None

        async def _do_keywords():
            if not has_resume:
                return None
            return await tailor.extract_keywords(job_description)

        async def _tailor_and_render():
            """Ordered chain: tailor → render PDF. Returns (tailored_text, pdf_bytes, archive_path)."""
            tailored_text = None
            if has_resume:
                await publish_step(application_id, "tailoring", "start", "Tailoring résumé to the job")
                try:
                    tailored_text = await tailor.tailor_resume(
                        user.resume_text, job_description, user.career_history or "",
                    )
                    await publish_step(application_id, "tailoring", "done", "Résumé tailored")
                except Exception as exc:
                    # Tailoring failed — still render a PDF from the raw resume.
                    logger.warning("Resume tailoring failed (continuing with raw resume): %s", exc)
                    await publish_step(application_id, "tailoring", "error", "Tailoring failed — using original résumé")

            source_text = tailored_text or (user.resume_text if user else None)
            pdf_bytes = None
            archive_path = None
            if source_text:
                await publish_step(application_id, "pdf", "start", "Rendering PDF résumé")
                archive_path = resume_archive_path(application_id)
                pdf_bytes = await render_pdf_resume(source_text, persist_to=archive_path)
                await publish_step(
                    application_id, "pdf",
                    "done" if pdf_bytes else "error",
                    "PDF ready" if pdf_bytes else "PDF unavailable — using plaintext résumé",
                )
            return tailored_text, pdf_bytes, archive_path

        async def _do_cover_letter():
            if not (job_description and cl_grounding):
                return None
            await publish_step(application_id, "cover_letter", "start", "Drafting cover letter")
            cl = await tailor.draft_cover_letter(job_description, company, job_title, cl_grounding)
            await publish_step(application_id, "cover_letter", "done", "Cover letter drafted")
            return cl

        keywords_res, tailor_res, cl_res = await asyncio.gather(
            _do_keywords(), _tailor_and_render(), _do_cover_letter(),
            return_exceptions=True,
        )

        # Normalize results — preserve per-branch best-effort behavior.
        keywords = keywords_res if not isinstance(keywords_res, Exception) else None
        if isinstance(keywords_res, Exception):
            logger.warning("extract_keywords failed (continuing): %s", keywords_res)

        if isinstance(tailor_res, Exception):
            logger.warning("tailor/PDF branch failed (continuing): %s", tailor_res)
            await publish_step(application_id, "pdf", "error", "Résumé prep failed")
            tailored_text, pdf_bytes, archive_path = None, None, None
        else:
            tailored_text, pdf_bytes, archive_path = tailor_res

        cl_text = cl_res if not isinstance(cl_res, Exception) else None
        if isinstance(cl_res, Exception):
            logger.warning("cover letter draft failed (continuing): %s", cl_res)
            await publish_step(application_id, "cover_letter", "error", "Cover letter failed")

        user_profile["tailored_resume_text"] = tailored_text
        user_profile["resume_pdf_bytes"] = pdf_bytes
        user_profile["cover_letter_text"] = cl_text

        # ── 2b. Persist artifacts (sequential, one session at a time) ────────
        # Best-effort: a DB write failure here must never crash the task before
        # the agent runs (that would leave the application stuck in RUNNING).
        if tailored_text is not None or keywords is not None:
            try:
                async with AsyncSession() as db:
                    tr = TailoredResume(
                        user_id=user_id,
                        application_id=application_id,
                        keywords_extracted=json.dumps(keywords) if keywords else None,
                        modifications_summary=tailored_text,
                        tailored_resume_path=archive_path if pdf_bytes else None,
                    )
                    db.add(tr)
                    await db.commit()
                logger.info("Resume artifacts stored for application %s", application_id)
            except Exception as exc:
                logger.warning("Storing tailored resume failed (continuing): %s", exc)

        if cl_text:
            try:
                async with AsyncSession() as db:
                    db.add(CoverLetter(
                        user_id=user_id,
                        application_id=application_id,
                        content=cl_text,
                    ))
                    await db.commit()
                logger.info("Cover letter stored for application %s", application_id)
            except Exception as exc:
                logger.warning("Storing cover letter failed (continuing): %s", exc)

        # ── 4. Run the browser/API agent ──────────────────────────────────────
        async with AsyncSession() as db:
            app_result = await db.execute(select(JobApplication).where(JobApplication.id == application_id))
            application = app_result.scalar_one_or_none()

            await publish_step(application_id, "submitting", "start", "Submitting application")
            try:
                agent = _build_agent(portal_type, application_id, user_id)
                await agent.run(job_url, user_profile=user_profile)
                # Only mark COMPLETED if the agent actually confirmed submission.
                # Otherwise the form ran but never submitted → surface as failure.
                if getattr(agent, "_submitted", False):
                    application.status = ApplicationStatus.COMPLETED
                    await publish_step(application_id, "submitting", "done", "Application submitted")
                else:
                    application.status = ApplicationStatus.FAILED
                    stop_reason = getattr(agent, "_stop_reason", None)
                    application.error_message = (
                        f"Agent did not confirm submission — reason: {stop_reason}."
                        if stop_reason else
                        "Agent finished without confirming submission. "
                        "Likely causes: form unfamiliar to LLM, validation blocked submit, "
                        "or success page not recognised."
                    )
                    await publish_step(application_id, "submitting", "error", "Could not confirm submission")
                    logger.warning(
                        "Application %s: agent ran but did not confirm submission (portal=%s, reason=%s)",
                        application_id, portal_type, stop_reason,
                    )
            except Exception as exc:
                logger.exception("Agent failed for application %s", application_id)
                application.status = ApplicationStatus.FAILED
                application.error_message = str(exc)
                await publish_step(application_id, "submitting", "error", f"Apply failed: {str(exc)[:120]}")
            finally:
                await db.commit()
    finally:
        await engine.dispose()


@celery_app.task(bind=True, name="scheduled_discovery")
def scheduled_discovery_task(self):
    """Triggered by Celery Beat — fans out to discover_jobs_task for every active profile."""
    asyncio.run(_run_scheduled_discovery())


async def _run_scheduled_discovery():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select
    from app.models.job_search_profile import JobSearchProfile
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with AsyncSession() as db:
            result = await db.execute(
                select(JobSearchProfile).where(JobSearchProfile.is_active == True)
            )
            profiles = result.scalars().all()
        for profile in profiles:
            discover_jobs_task.delay(profile.id, profile.user_id)
            logger.info("Queued discovery for profile %s (user %s)", profile.id, profile.user_id)
    finally:
        await engine.dispose()


# ── Gmail confirmation/lifecycle scan (Phase 7) ───────────────────────────────

@celery_app.task(bind=True, name="scan_email_confirmations")
def scan_email_confirmations_task(self):
    asyncio.run(_scan_email_confirmations())


async def _scan_email_confirmations():
    """Scan every Gmail-connected user's inbox and advance matched applications'
    stages. Per-user errors are isolated so one bad account can't break the run."""
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select
    from app.models.user import User
    from app.services.email_tracker import scan_user
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with AsyncSession() as db:
            users = (await db.execute(
                select(User).where(User.gmail_refresh_token.isnot(None))
            )).scalars().all()
            logger.info("Email scan: %d connected user(s)", len(users))
            for user in users:
                try:
                    await scan_user(db, user)
                except Exception as exc:
                    logger.warning("Email scan failed for user %s: %s", user.id, exc)
    finally:
        await engine.dispose()


# ── Autonomous follow-ups (Phase 7) ───────────────────────────────────────────
# Conservative by design: opt-in, daily, capped, one-per-application, and ONLY
# replies in-thread to a validated human sender — no-reply confirmations never
# populate the human-thread columns, so those applications never get a send.
FOLLOWUP_DAILY_CAP = 3


@celery_app.task(bind=True, name="cleanup_job_pool")
def cleanup_job_pool_task(self):
    """Delete JobPool rows we haven't re-seen in over 24 hours.

    Run on the hourly beat schedule. Uses `last_seen_at` (not first_seen_at)
    so popular jobs that keep getting re-searched stay in the pool.

    Defense-in-depth: the public browse endpoint also filters by age so
    even if this task hasn't run yet, users only see fresh results.
    """
    asyncio.run(_run_cleanup_job_pool())


async def _run_cleanup_job_pool():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import delete
    from datetime import datetime, timedelta, timezone
    from app.models.job_pool import JobPool
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        async with AsyncSession() as db:
            result = await db.execute(
                delete(JobPool).where(JobPool.last_seen_at < cutoff)
            )
            await db.commit()
            logger.info("Pool cleanup: deleted %d rows older than %s", result.rowcount, cutoff)
    finally:
        await engine.dispose()


@celery_app.task(bind=True, name="auto_followups")
def auto_followups_task(self):
    asyncio.run(_run_auto_followups())


async def _run_auto_followups():
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select, func
    from app.models.user import User
    from app.models.job_application import JobApplication
    from app.models.sent_email import SentEmail
    from app.services import gmail_client
    from app.services.gmail_client import get_valid_access_token, GmailScopeError
    from app.services.gmail_send import send_email
    from app.services.email_compose import draft_email
    from app.services.email_classifiers import is_repliable_human
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with AsyncSession() as db:
            users = (await db.execute(
                select(User)
                .where(User.auto_followup_enabled.is_(True))
                .where(User.gmail_refresh_token.isnot(None))
            )).scalars().all()
            logger.info("Auto-followups: %d opted-in user(s)", len(users))

            for user in users:
                try:
                    if not gmail_client.scopes_can_send(user.gmail_scopes):
                        continue  # toggled on but never reconnected with send scope
                    token = await get_valid_access_token(db, user)
                    if not token:
                        continue

                    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    sent_today = (await db.execute(
                        select(func.count(SentEmail.id))
                        .where(SentEmail.user_id == user.id)
                        .where(SentEmail.kind == "follow_up")
                        .where(SentEmail.sent_at >= today_start)
                    )).scalar() or 0
                    remaining = max(0, FOLLOWUP_DAILY_CAP - sent_today)
                    if remaining == 0:
                        continue

                    cutoff = datetime.now(timezone.utc) - timedelta(days=int(user.followup_after_days or 7))
                    candidates = (await db.execute(
                        select(JobApplication)
                        .where(JobApplication.user_id == user.id)
                        .where(JobApplication.stage.in_(["assessment", "interview"]))
                        .where(JobApplication.followup_sent_at.is_(None))
                        .where(JobApplication.last_human_email_thread_id.isnot(None))
                        .where(JobApplication.last_human_email_from.isnot(None))
                        .where(JobApplication.stage_updated_at.isnot(None))
                        .where(JobApplication.stage_updated_at <= cutoff)
                        .order_by(JobApplication.stage_updated_at.asc())
                        .limit(remaining)
                    )).scalars().all()

                    for app in candidates:
                        if not is_repliable_human(app.last_human_email_from):
                            continue  # defensive re-check
                        try:
                            draft = await draft_email("follow_up", {
                                "candidate_name": user.full_name,
                                "career_history": user.career_history or user.resume_text or "",
                                "company": app.company, "role": app.job_title,
                            })
                            result = await send_email(
                                token, app.last_human_email_from, draft["subject"], draft["body"],
                                thread_id=app.last_human_email_thread_id, in_reply_to=app.last_human_email_msgid,
                            )
                            app.followup_sent_at = datetime.now(timezone.utc)
                            db.add(SentEmail(
                                user_id=user.id, application_id=app.id, to_addr=app.last_human_email_from,
                                subject=draft["subject"], body=draft["body"], gmail_message_id=result.get("id"),
                                thread_id=result.get("thread_id"), kind="follow_up",
                            ))
                            await db.commit()
                            logger.info("Auto follow-up sent: app=%s user=%s dry_run=%s", app.id, user.id, result.get("dry_run"))
                        except (GmailScopeError, PermissionError) as exc:
                            logger.warning("Auto follow-up scope/token error for user %s — skipping user: %s", user.id, exc)
                            await db.rollback()
                            break
                        except Exception as exc:
                            logger.warning("Auto follow-up failed for app %s: %s", app.id, exc)
                            await db.rollback()
                            continue
                except Exception as exc:
                    logger.warning("Auto follow-up run failed for user %s: %s", user.id, exc)
    finally:
        await engine.dispose()


def _build_agent(portal_type: str, application_id: int, user_id: int):
    """Route to a direct HTTP API agent where possible; everything else uses the
    vision-driven SmartApplyAgent (Playwright + Set-of-Marks gpt-4o)."""
    # Greenhouse's Boards API rejects unauthenticated application POSTs
    # (401 "HTTP Basic: Access denied" — submission needs the board's private
    # API key we don't have), so Greenhouse goes through the real web form.
    if portal_type == "lever":
        from app.agents.lever_agent import LeverAgent
        return LeverAgent(application_id=application_id, user_id=user_id)
    if portal_type == "ashby":
        from app.agents.ashby_agent import AshbyAgent
        return AshbyAgent(application_id=application_id, user_id=user_id)
    # Greenhouse, Workday, iCIMS, and unknown portals → vision Playwright agent
    from app.agents.smart_apply_agent import SmartApplyAgent
    return SmartApplyAgent(application_id=application_id, user_id=user_id)


# ── Job Discovery + Auto-Apply Gate ───────────────────────────────────────────

@celery_app.task(bind=True, name="discover_jobs")
def discover_jobs_task(self, search_profile_id: int, user_id: int):
    asyncio.run(_run_discovery(search_profile_id, user_id))


async def _run_discovery(search_profile_id: int, user_id: int):
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import select
    from app.models.job_search_profile import JobSearchProfile
    from app.models.discovered_job import DiscoveredJob
    from app.models.job_application import JobApplication
    from app.models.user import User
    from app.agents.job_discovery_agent import JobDiscoveryAgent
    from app.services.job_scorer import JobScorer
    from app.config import settings

    engine = create_async_engine(settings.DATABASE_URL)
    AsyncSession = async_sessionmaker(engine, expire_on_commit=False)

    try:
        # ── 1. Load profile + user ────────────────────────────────────────────
        async with AsyncSession() as db:
            sp_result = await db.execute(
                select(JobSearchProfile).where(JobSearchProfile.id == search_profile_id)
            )
            search_profile = sp_result.scalar_one_or_none()
            if not search_profile:
                return

            user_result = await db.execute(select(User).where(User.id == user_id))
            user = user_result.scalar_one_or_none()

            profile_dict = {
                "target_roles": search_profile.target_roles,
                "keywords": search_profile.keywords,
                "locations": search_profile.locations,
                "excluded_companies": search_profile.excluded_companies,
                "experience_level": search_profile.experience_level,
                "work_arrangements": search_profile.work_arrangements,
                "posted_within_days": search_profile.posted_within_days,
            }
            user_profile_for_scoring = {
                "career_history": user.career_history if user else "",
                "resume_text": user.resume_text if user else "",
                "experience_level": search_profile.experience_level or "",
                "target_roles": search_profile.target_roles or "",
            }
            threshold = search_profile.auto_apply_threshold
            auto_apply_mode = search_profile.auto_apply_mode
            auto_apply_enabled = bool(user and user.auto_apply_enabled)
            daily_cap = user.daily_auto_apply_cap if user else 0

        # ── 2. Run discovery (HTTP + Playwright) ──────────────────────────────
        agent = JobDiscoveryAgent()
        discovered = await agent.discover(profile_dict)
        logger.info("Discovery raw count for profile %s: %d", search_profile_id, len(discovered))

        # ── 3. Upsert discovered jobs (no destructive delete) ─────────────────
        # Map url → existing row id for this user, to decide insert vs update.
        async with AsyncSession() as db:
            urls = [j.get("job_url") for j in discovered if j.get("job_url")]
            if urls:
                existing_result = await db.execute(
                    select(DiscoveredJob.id, DiscoveredJob.job_url,
                           DiscoveredJob.scored_at, DiscoveredJob.status)
                    .where(DiscoveredJob.user_id == user_id)
                    .where(DiscoveredJob.job_url.in_(urls))
                )
                existing_by_url = {
                    row.job_url: {"id": row.id, "scored_at": row.scored_at, "status": row.status}
                    for row in existing_result.all()
                }
            else:
                existing_by_url = {}

            url_to_id: dict[str, int] = {}
            for job in discovered:
                url = job.get("job_url")
                if not url:
                    continue
                if url in existing_by_url:
                    # Refresh metadata on the existing row but preserve status + score history
                    url_to_id[url] = existing_by_url[url]["id"]
                    await db.execute(
                        DiscoveredJob.__table__.update()
                        .where(DiscoveredJob.id == existing_by_url[url]["id"])
                        .values(
                            title=job.get("title"),
                            company=job.get("company"),
                            location=job.get("location"),
                            job_description=job.get("job_description"),
                            work_arrangement=job.get("work_arrangement"),
                            posted_at=job.get("posted_at"),
                        )
                    )
                else:
                    # Free-tier contact extraction: regex over the JD, no LLM,
                    # no Apify. Only runs once at insert time. The on-demand
                    # /find-contact endpoint runs the paid tiers.
                    from app.services.contact_finder import extract_from_jd
                    contact = extract_from_jd(job.get("job_description"))

                    dj = DiscoveredJob(
                        user_id=user_id,
                        search_profile_id=search_profile_id,
                        job_url=url,
                        title=job.get("title"),
                        company=job.get("company"),
                        location=job.get("location"),
                        job_description=job.get("job_description"),
                        source=job.get("source", "unknown"),
                        work_arrangement=job.get("work_arrangement"),
                        posted_at=job.get("posted_at"),
                        status="discovered",
                        contact_email=contact.get("email"),
                        contact_linkedin=contact.get("linkedin"),
                        contact_source="jd_regex" if (contact.get("email") or contact.get("linkedin")) else None,
                        contact_enriched_at=datetime.now(timezone.utc) if contact else None,
                    )
                    db.add(dj)
            await db.commit()

            # Reload IDs for newly inserted rows
            if urls:
                id_result = await db.execute(
                    select(DiscoveredJob.id, DiscoveredJob.job_url)
                    .where(DiscoveredJob.user_id == user_id)
                    .where(DiscoveredJob.job_url.in_(urls))
                )
                for row in id_result.all():
                    url_to_id[row.job_url] = row.id

        # ── 4. Score each job (skip if cached fresh) ─────────────────────────
        cache_cutoff = datetime.now(timezone.utc) - timedelta(days=_SCORE_CACHE_DAYS)
        scored_jobs: list[tuple[int, dict, int]] = []  # (dj_id, raw_job_dict, score)

        if user_profile_for_scoring.get("career_history") or user_profile_for_scoring.get("resume_text"):
            scorer = JobScorer()
            for job in discovered:
                url = job.get("job_url")
                dj_id = url_to_id.get(url) if url else None
                if not dj_id:
                    continue

                prior = existing_by_url.get(url, {})
                if prior.get("scored_at") and prior["scored_at"] > cache_cutoff:
                    # Already scored recently — re-use the existing score for gate decisions
                    async with AsyncSession() as db:
                        cached = await db.execute(
                            select(DiscoveredJob.match_score).where(DiscoveredJob.id == dj_id)
                        )
                        cached_score = cached.scalar_one_or_none()
                    if cached_score is not None:
                        scored_jobs.append((dj_id, job, cached_score))
                    continue

                try:
                    score_result = await scorer.score(
                        job.get("job_description", ""),
                        user_profile_for_scoring,
                        job_title=job.get("title", ""),
                    )
                    score = int(score_result.get("score") or 0)
                    reason = score_result.get("reason") or ""
                except Exception as exc:
                    logger.warning("Scoring failed for %s: %s", job.get("title"), exc)
                    continue

                async with AsyncSession() as db:
                    await db.execute(
                        DiscoveredJob.__table__.update()
                        .where(DiscoveredJob.id == dj_id)
                        .values(
                            match_score=score,
                            match_reason=reason,
                            scored_at=datetime.now(timezone.utc),
                        )
                    )
                    await db.commit()
                scored_jobs.append((dj_id, job, score))

        # ── 5. Auto-apply gate ────────────────────────────────────────────────
        if auto_apply_enabled and scored_jobs:
            await _process_auto_apply_gate(
                AsyncSession,
                user_id=user_id,
                scored_jobs=scored_jobs,
                threshold=threshold,
                mode=auto_apply_mode,
                daily_cap=daily_cap,
            )
        elif scored_jobs:
            logger.info(
                "Auto-apply disabled for user %s — %d job(s) scored, none queued",
                user_id, len(scored_jobs),
            )

        # ── 6. Update last_run_at ─────────────────────────────────────────────
        async with AsyncSession() as db:
            sp_result = await db.execute(
                select(JobSearchProfile).where(JobSearchProfile.id == search_profile_id)
            )
            sp = sp_result.scalar_one_or_none()
            if sp:
                sp.last_run_at = datetime.now(timezone.utc)
                await db.commit()
    finally:
        await engine.dispose()


async def _process_auto_apply_gate(
    AsyncSession,
    *,
    user_id: int,
    scored_jobs: list[tuple[int, dict, int]],
    threshold: int,
    mode: str,
    daily_cap: int,
):
    """Apply the queue gate to scored jobs.

    Order of checks (any failure = skip):
    1. Score must clear the profile threshold.
    2. No prior JobApplication exists for (user_id, job_url) — manual or auto.
    3. Daily cap not exceeded (counts today's auto-queued JobApplications).
    4. Mode branch: "review" → mark DiscoveredJob.status = "auto_queued";
       "auto" → create JobApplication(queued_by="auto") + dispatch task.
    """
    from sqlalchemy import select, func
    from app.models.discovered_job import DiscoveredJob
    from app.models.job_application import JobApplication

    above_threshold = [(dj_id, job, score) for dj_id, job, score in scored_jobs if score >= threshold]
    if not above_threshold:
        logger.info("Auto-apply: 0 jobs above threshold %d for user %s", threshold, user_id)
        return

    # Sort highest-score-first so the daily cap allocates the best matches first
    above_threshold.sort(key=lambda t: t[2], reverse=True)

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    async with AsyncSession() as db:
        # How many auto-applies have already fired today?
        count_result = await db.execute(
            select(func.count(JobApplication.id))
            .where(JobApplication.user_id == user_id)
            .where(JobApplication.queued_by == "auto")
            .where(JobApplication.created_at >= today_start)
        )
        today_auto_count = count_result.scalar() or 0
        remaining = max(0, daily_cap - today_auto_count)

        if mode == "auto" and remaining == 0:
            logger.info(
                "Auto-apply: daily cap %d reached for user %s — %d candidate(s) skipped",
                daily_cap, user_id, len(above_threshold),
            )
            return

        # Dedupe against already-applied URLs
        urls = [job.get("job_url") for _, job, _ in above_threshold if job.get("job_url")]
        applied_result = await db.execute(
            select(JobApplication.job_url)
            .where(JobApplication.user_id == user_id)
            .where(JobApplication.job_url.in_(urls))
        )
        already_applied = {row[0] for row in applied_result.all()}

        queued_count = 0
        review_count = 0
        pending_dispatch: list[tuple[int, int, str, int, str]] = []  # (app_id, user_id, url, score, task_id)

        for dj_id, job, score in above_threshold:
            url = job.get("job_url")
            if not url:
                continue
            if url in already_applied:
                logger.info("Auto-apply: skip %s (already applied)", url)
                continue

            if mode == "review":
                await db.execute(
                    DiscoveredJob.__table__.update()
                    .where(DiscoveredJob.id == dj_id)
                    .where(DiscoveredJob.status == "discovered")
                    .values(status="auto_queued")
                )
                review_count += 1
                continue

            if queued_count >= remaining:
                logger.info("Auto-apply: cap reached mid-loop (%d/%d)", queued_count, remaining)
                break

            portal_type = job.get("source") or _detect_portal(url)
            application = JobApplication(
                user_id=user_id,
                job_url=url,
                job_title=job.get("title"),
                company=job.get("company"),
                job_description=job.get("job_description"),
                portal_type=portal_type,
                queued_by="auto",
            )
            db.add(application)
            await db.flush()

            task_id = uuid.uuid4().hex
            application.celery_task_id = task_id  # committed with the row below
            await db.execute(
                DiscoveredJob.__table__.update()
                .where(DiscoveredJob.id == dj_id)
                .values(status="queued")
            )
            pending_dispatch.append((application.id, user_id, url, score, task_id))
            queued_count += 1

        # Commit all DB writes (incl. celery_task_id) BEFORE dispatching Celery
        # tasks. Workers reading the new application rows must see a committed
        # transaction with the task id already set.
        await db.commit()

    # Dispatch outside the DB transaction using the pre-committed task ids.
    for app_id, uid, url, score, task_id in pending_dispatch:
        run_application_task.apply_async(args=[app_id, uid], task_id=task_id)
        logger.info("Auto-apply: queued %s (score %d, app_id=%s)", url, score, app_id)

    if mode == "review":
        logger.info(
            "Auto-apply (review): marked %d job(s) as auto_queued for user %s",
            review_count, user_id,
        )
    else:
        logger.info(
            "Auto-apply (auto): dispatched %d job(s) for user %s (cap %d, used %d today)",
            queued_count, user_id, daily_cap, today_auto_count + queued_count,
        )
