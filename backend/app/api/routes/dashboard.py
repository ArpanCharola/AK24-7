"""Dashboard summary stats for the connected user."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.sent_email import SentEmail
from app.models.user import User

router = APIRouter()


@router.get("/stats")
async def stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Headline counters for the dashboard. `emailsSent` = rows this user has in
    the sent-email audit log."""
    emails_sent = (await db.execute(
        select(func.count()).select_from(SentEmail).where(SentEmail.user_id == current_user.id)
    )).scalar_one()
    return {"emailsSent": emails_sent}
