import json

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.resume_parser import (
    PROFILE_SECTIONS,
    empty_profile,
    extract_text_from_upload,
    load_structured_profile,
    parse_resume_file,
)

router = APIRouter()

# Structured list/dict sections persisted as JSON-in-Text on `users`
# (landed by Foundation's migration — WORKSTREAMS #6).
_LIST_SECTIONS = PROFILE_SECTIONS  # work_experience, education, skills, projects, certifications


class ProfileResponse(BaseModel):
    id: int
    email: str
    full_name: str | None
    phone: str | None
    location: str | None
    linkedin_url: str | None
    github_url: str | None
    website_url: str | None
    resume_text: str | None
    portal_email: str | None
    auto_apply_enabled: bool
    daily_auto_apply_cap: int
    # Simplified profile inputs (replace CTC/notice): total experience + cities.
    experience_years: int | None = None
    experience_months: int | None = None
    preferred_locations: list[str] = []
    desired_roles: str | None = None
    # Structured base profile (drives tailoring + the profile editor)
    summary: str | None = None
    work_experience: list[dict] = []
    education: list[dict] = []
    skills: list[str] = []
    projects: list[dict] = []
    certifications: list[dict] = []


class ProfileUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    website_url: str | None = None
    portal_email: str | None = None
    portal_password: str | None = None
    auto_apply_enabled: bool | None = None
    daily_auto_apply_cap: int | None = None
    experience_years: int | None = None
    experience_months: int | None = None
    preferred_locations: list[str] | None = None
    desired_roles: str | None = None
    # Structured base profile
    summary: str | None = None
    work_experience: list[dict] | None = None
    education: list[dict] | None = None
    skills: list[str] | None = None
    projects: list[dict] | None = None
    certifications: list[dict] | None = None


# Scalar contact columns that live directly on the User row.
_SCALAR_FIELDS = (
    "full_name", "phone", "location", "linkedin_url", "github_url", "website_url",
    "portal_email", "portal_password", "auto_apply_enabled", "daily_auto_apply_cap",
    "experience_years", "experience_months", "desired_roles",
)


def _parse_locations(raw: str | None) -> list[str]:
    """Preferred locations persist as a JSON array (legacy rows may be CSV)."""
    if not raw:
        return []
    try:
        value = json.loads(raw)
        if isinstance(value, list):
            return [str(x) for x in value if x]
    except (ValueError, TypeError):
        pass
    return [s.strip() for s in raw.split(",") if s.strip()]


def _profile_response(user: User) -> ProfileResponse:
    structured = load_structured_profile(user)
    return ProfileResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        phone=user.phone,
        location=user.location,
        linkedin_url=user.linkedin_url,
        github_url=user.github_url,
        website_url=user.website_url,
        resume_text=user.resume_text,
        portal_email=user.portal_email,
        auto_apply_enabled=user.auto_apply_enabled,
        daily_auto_apply_cap=user.daily_auto_apply_cap,
        experience_years=user.experience_years,
        experience_months=user.experience_months,
        preferred_locations=_parse_locations(user.preferred_locations),
        desired_roles=user.desired_roles,
        summary=structured["summary"] or None,
        work_experience=structured["work_experience"],
        education=structured["education"],
        skills=structured["skills"],
        projects=structured["projects"],
        certifications=structured["certifications"],
    )


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(current_user: User = Depends(get_current_user)):
    return _profile_response(current_user)


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save the profile. Scalar contact fields write straight to columns;
    structured sections are JSON-serialised into their Text columns."""
    data = body.model_dump(exclude_unset=True)

    for field in _SCALAR_FIELDS:
        if field in data:
            setattr(current_user, field, data[field])

    if "preferred_locations" in data:
        current_user.preferred_locations = json.dumps(data["preferred_locations"])

    if "summary" in data:
        # `summary` column comes from Foundation's migration; setattr is a no-op
        # on persistence until it lands, then begins saving — see status file.
        setattr(current_user, "summary", data["summary"])

    for section in _LIST_SECTIONS:
        if section in data:
            setattr(current_user, section, json.dumps(data[section]))

    await db.commit()
    await db.refresh(current_user)
    return _profile_response(current_user)


@router.post("/profile/import-resume")
async def import_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a resume (PDF or DOCX), parse it into a structured profile DRAFT,
    and return it for the user to review/edit before saving via PUT /profile.

    The recovered raw text is saved to ``resume_text`` immediately (cheap, useful
    fallback for tailoring); the structured sections are NOT auto-saved — the user
    confirms them first.
    """
    name = (file.filename or "").lower()
    if not (name.endswith(".pdf") or name.endswith(".docx")):
        raise HTTPException(status_code=400, detail="Only PDF or DOCX files are accepted")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10 MB guard
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    draft = await parse_resume_file(file.filename, data)

    resume_text = draft.get("resume_text") or ""
    parse_warning = None
    if not resume_text:
        parse_warning = (
            "We could not extract readable text from this resume. "
            "If it is scanned, OCR will be used when available; please fill the details manually."
        )
        draft = empty_profile()
        draft["resume_text"] = ""

    current_user.resume_text = resume_text or "Resume uploaded; manual profile details required."
    await db.commit()

    contact = draft.get("contact") or {}
    flat = {
        **draft,
        "full_name": contact.get("full_name"),
        "phone": contact.get("phone"),
        "skills": draft.get("skills") or [],
        "desired_roles": draft.get("desired_roles") or [],
    }
    return {"draft": flat, "char_count": len(resume_text), "warning": parse_warning}


@router.post("/profile/upload-resume")
async def upload_resume(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept a PDF/DOCX resume, extract its text, and save it to the user profile."""
    name = file.filename or ""
    if not name.lower().endswith((".pdf", ".docx")):
        raise HTTPException(status_code=400, detail="Only PDF or DOCX files are accepted")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:  # 10 MB guard
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    text = extract_text_from_upload(name, data)

    if not text:
        raise HTTPException(status_code=422, detail="No readable text found in the file")

    current_user.resume_text = text
    await db.commit()
    return {"resume_text": text, "char_count": len(text)}


@router.post("/parse-pdf")
async def parse_pdf(
    file: UploadFile = File(...),
    _current_user: User = Depends(get_current_user),
):
    """Extract and return plain text from any PDF (e.g. a job description). Nothing is saved."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 10 MB)")

    text = extract_text_from_upload(file.filename, data)

    if not text:
        raise HTTPException(status_code=422, detail="No readable text found in PDF")

    return {"text": text, "char_count": len(text)}
