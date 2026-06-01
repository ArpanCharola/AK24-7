import difflib
import json
import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.models.tailored_resume import TailoredResume
from app.models.job_application import JobApplication

router = APIRouter()


# ── Pydantic responses ────────────────────────────────────────────────────────

class TailoredResumeListItem(BaseModel):
    id: int
    application_id: Optional[int]  # None for standalone Quick-Tailor entries
    job_title: Optional[str]
    company: Optional[str]
    application_status: Optional[str]
    queued_by: Optional[str]
    keyword_count: int
    has_pdf: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DiffSegment(BaseModel):
    """One contiguous run of lines in the diff."""
    type: str  # "equal" | "insert" | "delete"
    text: str


class TailoredResumeDetail(BaseModel):
    id: int
    application_id: Optional[int]  # None for standalone Quick-Tailor entries
    job_title: Optional[str]
    company: Optional[str]
    job_url: Optional[str]
    application_status: Optional[str]
    queued_by: Optional[str]
    original_text: str
    tailored_text: str
    diff_segments: list[DiffSegment]
    keywords: dict
    ats_score: Optional[dict] = None
    has_pdf: bool
    created_at: datetime


# ── Diff computation ──────────────────────────────────────────────────────────

def _line_diff(original: str, tailored: str) -> list[DiffSegment]:
    """Compute a line-level diff and return segments suitable for UI rendering.

    Each segment is a contiguous run of lines with the same disposition.
    Replacements are expanded into a delete-run followed by an insert-run so
    the UI can show old + new clearly.
    """
    original_lines = (original or "").splitlines()
    tailored_lines = (tailored or "").splitlines()

    matcher = difflib.SequenceMatcher(a=original_lines, b=tailored_lines, autojunk=False)
    segments: list[DiffSegment] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            segments.append(DiffSegment(type="equal", text="\n".join(original_lines[i1:i2])))
        elif tag == "delete":
            segments.append(DiffSegment(type="delete", text="\n".join(original_lines[i1:i2])))
        elif tag == "insert":
            segments.append(DiffSegment(type="insert", text="\n".join(tailored_lines[j1:j2])))
        elif tag == "replace":
            segments.append(DiffSegment(type="delete", text="\n".join(original_lines[i1:i2])))
            segments.append(DiffSegment(type="insert", text="\n".join(tailored_lines[j1:j2])))

    return segments


def _keyword_count(keywords_json: Optional[str]) -> int:
    if not keywords_json:
        return 0
    try:
        data = json.loads(keywords_json)
    except (TypeError, ValueError):
        return 0
    total = 0
    for key in ("required_skills", "preferred_skills", "keywords"):
        v = data.get(key)
        if isinstance(v, list):
            total += len(v)
    return total


def _has_pdf(tr: TailoredResume) -> bool:
    path = tr.tailored_resume_path
    return bool(path) and os.path.exists(path)


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/tailored-resumes", response_model=list[TailoredResumeListItem])
async def list_tailored_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Outer join so standalone (Quick Tailor) entries with no application also appear.
    result = await db.execute(
        select(TailoredResume, JobApplication)
        .outerjoin(JobApplication, TailoredResume.application_id == JobApplication.id)
        .where(TailoredResume.user_id == current_user.id)
        .order_by(TailoredResume.created_at.desc())
    )
    out: list[TailoredResumeListItem] = []
    for tr, app in result.all():
        title = (app.job_title if app else None) or tr.label
        out.append(TailoredResumeListItem(
            id=tr.id,
            application_id=tr.application_id,
            job_title=title,
            company=app.company if app else None,
            application_status=app.status.value if app and app.status else None,
            queued_by=getattr(app, "queued_by", None) if app else None,
            keyword_count=_keyword_count(tr.keywords_extracted),
            has_pdf=_has_pdf(tr),
            created_at=tr.created_at,
        ))
    return out


@router.get("/tailored-resumes/{tr_id}", response_model=TailoredResumeDetail)
async def get_tailored_resume(
    tr_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tr_id,
            TailoredResume.user_id == current_user.id,
        )
    )
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Tailored resume not found")

    app = None
    if tr.application_id:
        app_result = await db.execute(
            select(JobApplication).where(JobApplication.id == tr.application_id)
        )
        app = app_result.scalar_one_or_none()

    # For standalone Quick Tailor entries, the original is what the user pasted/uploaded
    # at creation time (stored on the row). For application-linked entries, fall back to
    # the user's profile resume since those were generated against User.resume_text.
    original = tr.original_resume_text or current_user.resume_text or ""
    tailored = tr.modifications_summary or ""

    keywords: dict = {}
    if tr.keywords_extracted:
        try:
            parsed = json.loads(tr.keywords_extracted)
            if isinstance(parsed, dict):
                keywords = parsed
        except (TypeError, ValueError):
            keywords = {}

    ats_score = None
    if keywords:
        from app.services.resume_tailor import ResumeTailor
        ats_score = ResumeTailor().score_ats(tailored, keywords)

    return TailoredResumeDetail(
        id=tr.id,
        application_id=tr.application_id,
        job_title=(app.job_title if app else None) or tr.label,
        company=app.company if app else None,
        job_url=(app.job_url if app else None) or getattr(tr, "job_url", None),
        application_status=app.status.value if app and app.status else None,
        queued_by=getattr(app, "queued_by", None) if app else None,
        original_text=original,
        tailored_text=tailored,
        diff_segments=_line_diff(original, tailored),
        keywords=keywords,
        ats_score=ats_score,
        has_pdf=_has_pdf(tr),
        created_at=tr.created_at,
    )


@router.get("/tailored-resumes/{tr_id}/pdf")
async def download_tailored_pdf(
    tr_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tr_id,
            TailoredResume.user_id == current_user.id,
        )
    )
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Tailored resume not found")
    if not tr.tailored_resume_path or not os.path.exists(tr.tailored_resume_path):
        raise HTTPException(status_code=404, detail="PDF not available for this tailored resume")
    return FileResponse(
        tr.tailored_resume_path,
        media_type="application/pdf",
        filename=f"tailored_resume_{tr_id}.pdf",
    )


# ── Edit / regenerate ─────────────────────────────────────────────────────────

class TailoredResumeUpdate(BaseModel):
    tailored_text: str
    regenerate_pdf: bool = False


@router.put("/tailored-resumes/{tr_id}", response_model=TailoredResumeDetail)
async def update_tailored_resume(
    tr_id: int,
    body: TailoredResumeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save user edits to the tailored resume text. Optionally re-render the PDF."""
    result = await db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tr_id,
            TailoredResume.user_id == current_user.id,
        )
    )
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Tailored resume not found")

    tr.modifications_summary = body.tailored_text

    if body.regenerate_pdf:
        from app.services.resume_builder import render_pdf_resume
        archive_path = _archive_path_for(tr)
        pdf_bytes = await render_pdf_resume(body.tailored_text, persist_to=archive_path)
        if pdf_bytes:
            tr.tailored_resume_path = archive_path
        else:
            # The user explicitly asked to regenerate the PDF; if it fails, treat
            # the whole update as failed and persist nothing — otherwise we'd save
            # the text edit while leaving tailored_resume_path pointing at a stale
            # PDF, so "has_pdf" would lie and the 502 would be misleading.
            await db.rollback()
            raise HTTPException(
                status_code=502,
                detail="PDF rendering failed. Check RESUME_FORMATTER_PATH and that Word/LibreOffice is installed.",
            )

    await db.commit()
    return await get_tailored_resume(tr_id, current_user, db)


@router.post("/tailored-resumes/{tr_id}/retailor", response_model=TailoredResumeDetail)
async def retailor_resume(
    tr_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-run the AI tailoring. For application-linked entries: uses the application's JD
    and the user's profile resume_text. For standalone entries: uses the JD and original
    resume text stored on the row at creation time."""
    result = await db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tr_id,
            TailoredResume.user_id == current_user.id,
        )
    )
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Tailored resume not found")

    # Resolve source resume + JD based on whether this is application-linked or standalone
    if tr.application_id:
        app_result = await db.execute(
            select(JobApplication).where(JobApplication.id == tr.application_id)
        )
        app = app_result.scalar_one_or_none()
        if not app or not app.job_description:
            raise HTTPException(status_code=422, detail="Application has no job description to tailor against")
        if not current_user.resume_text:
            raise HTTPException(status_code=422, detail="Profile resume text is empty — upload a resume first")
        source_resume = current_user.resume_text
        jd = app.job_description
    else:
        if not tr.original_resume_text or not tr.job_description:
            raise HTTPException(
                status_code=422,
                detail="This standalone entry is missing the original resume or job description needed for re-tailoring",
            )
        source_resume = tr.original_resume_text
        jd = tr.job_description

    from app.services.resume_tailor import ResumeTailor
    tailor = ResumeTailor()
    try:
        new_text = await tailor.tailor_resume(
            source_resume,
            jd,
            current_user.career_history or "",
        )
        keywords = await tailor.extract_keywords(jd)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI tailoring failed: {exc}") from exc

    tr.modifications_summary = new_text
    tr.keywords_extracted = json.dumps(keywords)
    await db.commit()
    return await get_tailored_resume(tr_id, current_user, db)


@router.post("/tailored-resumes/{tr_id}/regenerate-pdf", response_model=TailoredResumeDetail)
async def regenerate_pdf(
    tr_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Re-render the PDF from the currently saved tailored text."""
    result = await db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tr_id,
            TailoredResume.user_id == current_user.id,
        )
    )
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Tailored resume not found")
    if not tr.modifications_summary:
        raise HTTPException(status_code=422, detail="No tailored text saved to render")

    from app.services.resume_builder import render_pdf_resume, resume_archive_path
    archive_path = _archive_path_for(tr)
    pdf_bytes = await render_pdf_resume(tr.modifications_summary, persist_to=archive_path)
    if not pdf_bytes:
        raise HTTPException(
            status_code=502,
            detail="PDF rendering failed. Check RESUME_FORMATTER_PATH and that Word/LibreOffice is installed.",
        )
    tr.tailored_resume_path = archive_path
    await db.commit()
    return await get_tailored_resume(tr_id, current_user, db)


# ── Standalone Quick Tailor (no JobApplication needed) ────────────────────────

class QuickTailorRequest(BaseModel):
    # Resume source is optional — defaults to the user's saved base profile
    # (structured profile, else profile resume_text).
    resume_text: Optional[str] = None
    # Require a JD: either pasted text OR a job link we extract it from.
    job_description: Optional[str] = None
    job_url: Optional[str] = None
    label: Optional[str] = None


class ExtractJDRequest(BaseModel):
    job_url: str


class ExtractJDResponse(BaseModel):
    job_title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    job_description: Optional[str] = None


@router.post("/tailored-resumes/extract-jd", response_model=ExtractJDResponse)
async def extract_jd_preview(
    body: ExtractJDRequest,
    _current_user: User = Depends(get_current_user),
):
    """Preview: fetch a job link and extract a structured JD the user can review
    before tailoring. Returns 422 if nothing usable could be read."""
    url = (body.job_url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="job_url is required")

    from app.services.jd_extractor import jd_from_url
    data = await jd_from_url(url)
    if not (data.get("job_description") or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract a job description from that URL. Paste the JD text instead.",
        )
    return ExtractJDResponse(**data)


def _archive_path_for(tr: TailoredResume) -> str:
    """Pick a stable on-disk archive path for the rendered PDF."""
    from app.services.resume_builder import resume_archive_path
    from pathlib import Path
    if tr.application_id:
        return resume_archive_path(tr.application_id)
    backend_root = Path(__file__).resolve().parents[3]  # backend/
    return str(backend_root / "uploads" / "resumes" / f"quick_{tr.id}.pdf")


@router.post("/tailored-resumes/quick", response_model=TailoredResumeDetail, status_code=201)
async def quick_tailor(
    body: QuickTailorRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a tailored resume on-the-fly without queueing a JobApplication.

    Flow:
      1. Resolve the JD — pasted ``job_description`` OR auto-extracted from ``job_url``
         (at least one is required).
      2. Resolve the source resume — provided ``resume_text``, else the user's saved
         base profile (structured profile preferred, else profile resume_text).
      3. AI-tailor (grounded) against the JD + extract keywords.
      4. Render PDF via the resume-formatter pipeline.
      5. Persist as a TailoredResume row (application_id=None) so it appears in the list.
    """
    from app.services.resume_tailor import ResumeTailor, profile_to_resume_text
    from app.services.resume_parser import has_structured_profile, load_structured_profile

    label = (body.label or "").strip() or None

    # ── 1. Resolve JD (text OR url) ──────────────────────────────────────────
    jd = (body.job_description or "").strip() or None
    job_url = (body.job_url or "").strip() or None
    jd_title = jd_company = None
    if not jd and job_url:
        from app.services.jd_extractor import jd_from_url
        extracted = await jd_from_url(job_url)
        jd = (extracted.get("job_description") or "").strip() or None
        jd_title = extracted.get("job_title")
        jd_company = extracted.get("company")
    if not jd:
        raise HTTPException(
            status_code=400,
            detail="Provide a job_description or a job_url to tailor against",
        )

    # ── 2. Resolve source resume + tailor (grounded) ─────────────────────────
    tailor = ResumeTailor()
    provided = (body.resume_text or "").strip()
    try:
        if provided:
            original_text = provided
            tailored_text = await tailor.tailor_resume(
                provided, jd, current_user.career_history or "",
            )
        elif has_structured_profile(current_user):
            profile = load_structured_profile(current_user)
            original_text = profile_to_resume_text(profile)
            tailored_text = await tailor.tailor_from_profile(profile, jd)
        elif current_user.resume_text:
            original_text = current_user.resume_text
            tailored_text = await tailor.tailor_resume(
                original_text, jd, current_user.career_history or "",
            )
        else:
            raise HTTPException(
                status_code=422,
                detail="No resume to tailor — provide resume_text or save a base profile first",
            )
        keywords = await tailor.extract_keywords(jd)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI tailoring failed: {exc}") from exc

    keywords_json = json.dumps(keywords)

    if not label:
        bits = [b for b in (jd_title, jd_company) if b]
        label = " · ".join(bits) if bits else f"Quick tailor · {datetime.utcnow().strftime('%b %d %H:%M')}"

    # Create row first so we can compute archive path off its id
    tr = TailoredResume(
        user_id=current_user.id,
        application_id=None,
        original_resume_text=original_text,
        modifications_summary=tailored_text,
        keywords_extracted=keywords_json,
        label=label,
        job_description=jd,
    )
    # `job_url` column comes from Foundation's migration (WORKSTREAMS #6); setattr
    # is harmless until it lands, then persists — see status file.
    if job_url:
        setattr(tr, "job_url", job_url)
    db.add(tr)
    await db.commit()
    await db.refresh(tr)

    # Render PDF
    from app.services.resume_builder import render_pdf_resume
    archive_path = _archive_path_for(tr)
    try:
        pdf_bytes = await render_pdf_resume(tailored_text, persist_to=archive_path)
        if pdf_bytes:
            tr.tailored_resume_path = archive_path
            await db.commit()
    except Exception:
        # Soft failure — entry still saved with text, user can re-render later
        pass

    return await get_tailored_resume(tr.id, current_user, db)


@router.delete("/tailored-resumes/{tr_id}", status_code=204)
async def delete_tailored_resume(
    tr_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(TailoredResume).where(
            TailoredResume.id == tr_id,
            TailoredResume.user_id == current_user.id,
        )
    )
    tr = result.scalar_one_or_none()
    if not tr:
        raise HTTPException(status_code=404, detail="Tailored resume not found")
    # Best-effort PDF cleanup for standalone entries
    if tr.application_id is None and tr.tailored_resume_path and os.path.exists(tr.tailored_resume_path):
        try:
            os.unlink(tr.tailored_resume_path)
        except OSError:
            pass
    await db.delete(tr)
    await db.commit()
