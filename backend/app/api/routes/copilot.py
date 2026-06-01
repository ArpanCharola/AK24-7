"""Orion AI career copilot — chat endpoint.

Stateless per request: the frontend sends the running message history (and an
optional focused job id); the service grounds the reply in the user's profile +
that job. Foundation mounts this router (suggested prefix ``/api/copilot``).
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.discovered_job import DiscoveredJob
from app.models.user import User
from app.services import copilot

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    # Prior turns of the conversation (user/assistant). May be empty for a first
    # message. `message` is a convenience for sending just the new user turn.
    messages: list[ChatMessage] = Field(default_factory=list, max_length=40)
    message: str | None = None
    job_id: int | None = None


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
async def chat(
    body: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send a message to Orion and get the next reply, grounded in the user's
    profile and (optionally) a focused discovered job."""
    msgs = [m.model_dump() for m in body.messages]
    if body.message and body.message.strip():
        msgs.append({"role": "user", "content": body.message})
    if not any((m.get("role") == "user" and (m.get("content") or "").strip()) for m in msgs):
        raise HTTPException(status_code=422, detail="A user message is required")

    job = None
    if body.job_id is not None:
        job = (
            await db.execute(
                select(DiscoveredJob).where(
                    DiscoveredJob.id == body.job_id,
                    DiscoveredJob.user_id == current_user.id,
                )
            )
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

    try:
        reply = await copilot.chat(current_user, msgs, job=job)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.warning("Copilot chat failed for user %s: %s", current_user.id, exc)
        raise HTTPException(status_code=502, detail="Copilot is unavailable right now — try again.")

    return ChatResponse(reply=reply)
