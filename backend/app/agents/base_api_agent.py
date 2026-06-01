import asyncio
import json
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BaseAPIAgent(ABC):
    """Shared base for HTTP-only (no Playwright) apply agents.

    Provides Redis pub/sub logging and DB status helpers identical in
    interface to BasePortalAgent so the Celery task layer treats them
    the same way.
    """

    def __init__(self, application_id: int, user_id: int):
        self.application_id = application_id
        self.user_id = user_id
        self._redis = None
        # Set to True by the subclass when the ATS has confirmed receipt.
        # Used by the Celery task layer to distinguish real success from
        # an agent that just ran to completion without actually submitting.
        self._submitted: bool = False
        # Short machine-readable reason the run stopped without confirming a
        # submission, for per-portal failure telemetry. None on success.
        self._stop_reason: str | None = None

    async def _connect(self):
        import redis.asyncio as aioredis
        from app.config import settings
        self._redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    async def _publish(self, payload: dict):
        if self._redis:
            await self._redis.publish(
                f"agent:{self.application_id}", json.dumps(payload)
            )

    async def _log(self, message: str):
        await self._publish({"type": "log", "message": message})

    async def _set_db_status(self, status) -> None:
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        from app.models.job_application import JobApplication
        from app.config import settings
        from sqlalchemy import select

        engine = create_async_engine(settings.DATABASE_URL)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with Session() as db:
                result = await db.execute(
                    select(JobApplication).where(JobApplication.id == self.application_id)
                )
                app = result.scalar_one_or_none()
                if app:
                    app.status = status
                    await db.commit()
        finally:
            await engine.dispose()

    async def close(self):
        if self._redis:
            await self._redis.aclose()

    def _resume_bytes(self, profile: dict) -> tuple[str, bytes, str]:
        """Return (filename, content_bytes, mimetype) for the resume.

        Prefers PDF bytes from the external resume builder (Phase 6C). Falls back
        to plaintext only if no PDF is available — most ATS portals will reject
        or mangle plaintext, so the PDF path should be populated whenever possible.
        """
        pdf_bytes = profile.get("resume_pdf_bytes")
        if pdf_bytes:
            return "resume.pdf", pdf_bytes, "application/pdf"
        text = (
            profile.get("tailored_resume_text")
            or profile.get("resume_text")
            or ""
        ).strip()
        return "resume.txt", text.encode("utf-8"), "text/plain"

    def _cover_letter_bytes(self, profile: dict) -> tuple[str, bytes, str] | None:
        """Return (filename, content_bytes, mimetype) for the cover letter, or None if absent."""
        text = (profile.get("cover_letter_text") or "").strip()
        if not text:
            return None
        return "cover_letter.txt", text.encode("utf-8"), "text/plain"

    async def _llm_answer(self, question: str, profile: dict) -> str:
        """Draft a 2-4 sentence answer to a custom question using OpenAI."""
        career = profile.get("career_history", "")
        if not career:
            return ""
        from app.services.resume_tailor import ResumeTailor
        try:
            return await ResumeTailor().draft_custom_answer(question, career)
        except Exception as exc:
            logger.warning("LLM answer failed for %r: %s", question[:60], exc)
            return ""

    async def _llm_answers(self, questions: list[str], profile: dict) -> list[str]:
        """Draft answers for many custom questions concurrently, order-preserving.

        Returns a list aligned 1:1 with `questions` ("" for empty/failed). The
        process-wide Semaphore(5) in `_generate` bounds real OpenAI concurrency,
        and `_llm_answer` swallows its own errors, so this never raises.
        """
        if not questions:
            return []
        return list(await asyncio.gather(
            *(self._llm_answer(q, profile) for q in questions)
        ))

    @abstractmethod
    async def run(self, job_url: str, user_profile: dict | None = None): ...
