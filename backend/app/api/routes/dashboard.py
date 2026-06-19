"""Dashboard summary stats for the connected user."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.discovered_job import DiscoveredJob
from app.models.job_search_profile import JobSearchProfile
from app.models.saved_application import SavedApplication
from app.models.sent_email import SentEmail
from app.models.tailored_resume import TailoredResume
from app.models.user import User

router = APIRouter()


async def _count(db: AsyncSession, model, *where) -> int:
    return int((await db.execute(
        select(func.count()).select_from(model).where(*where)
    )).scalar() or 0)


@router.get("/stats")
async def stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Headline counters for the 4 dashboard tiles + email audit count."""
    uid = current_user.id
    jobs_found = await _count(db, DiscoveredJob, DiscoveredJob.user_id == uid)
    jobs_applied = await _count(
        db, SavedApplication,
        SavedApplication.user_id == uid,
        SavedApplication.status.in_(("applied", "assessment", "interview")),
    )
    tailored_resumes = await _count(db, TailoredResume, TailoredResume.user_id == uid)
    emails_sent = await _count(db, SentEmail, SentEmail.user_id == uid)

    # Top-3 target roles across the user's active search profiles.
    roles_rows = (await db.execute(
        select(JobSearchProfile.target_roles).where(
            JobSearchProfile.user_id == uid, JobSearchProfile.is_active.is_(True)
        )
    )).scalars().all()
    seen, target_roles = set(), []
    for raw in roles_rows:
        for r in (raw or "").split(","):
            r = r.strip()
            key = r.lower()
            if r and key not in seen:
                seen.add(key)
                target_roles.append(r)
            if len(target_roles) >= 3:
                break
        if len(target_roles) >= 3:
            break

    return {
        "jobs_found": jobs_found,
        "jobs_applied": jobs_applied,
        "target_roles": target_roles,
        "tailored_resumes": tailored_resumes,
        "emailsSent": emails_sent,
    }
