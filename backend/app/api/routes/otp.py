from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.core.redis import get_redis
from app.models.user import User

router = APIRouter()


class OTPSubmitRequest(BaseModel):
    job_id: int
    otp: str


@router.post("/submit")
async def submit_otp(
    body: OTPSubmitRequest,
    current_user: User = Depends(get_current_user),
    redis=Depends(get_redis),
):
    key = f"otp:{current_user.id}:{body.job_id}"
    await redis.set(key, body.otp, ex=120)
    return {"status": "received"}
