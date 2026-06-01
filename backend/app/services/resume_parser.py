"""Resume → structured profile parsing.

Takes an uploaded resume (PDF or DOCX), extracts its plain text, and asks the
shared LLM helper to project it into a structured profile draft that the user
reviews and edits before saving. Parsing is best-effort: nothing here raises —
on any failure we return a usable draft (empty structure + whatever raw text we
recovered) so the upload endpoint always responds with something editable.

The structured shape produced here is the contract the profile editor and the
tailored-resume engine both build on:

    {
      "contact": {full_name, email, phone, location,
                  linkedin_url, github_url, website_url},
      "summary": str,
      "work_experience": [{company, title, location, start_date, end_date,
                           bullets: [str]}],
      "education":       [{institution, degree, field, start_date, end_date, grade}],
      "skills":          [str],
      "projects":        [{name, description, tech: [str], url}],
      "certifications":  [{name, issuer, year}],
    }
"""
import io
import logging

from app.services.resume_tailor import _generate, _parse_json

logger = logging.getLogger(__name__)

# Scalar contact fields map straight onto existing User columns. `email` is the
# login identity — we surface it in the draft but never overwrite it on save.
CONTACT_FIELDS = (
    "full_name", "email", "phone", "location",
    "linkedin_url", "github_url", "website_url",
)
# Structured sections persisted as JSON-in-Text columns on `users`
# (landed by Foundation's migration — see WORKSTREAMS #6).
PROFILE_SECTIONS = ("work_experience", "education", "skills", "projects", "certifications")


def empty_profile() -> dict:
    """A fully-formed, empty draft — the shape every consumer can rely on."""
    return {
        "contact": {f: None for f in CONTACT_FIELDS},
        "summary": "",
        "work_experience": [],
        "education": [],
        "skills": [],
        "projects": [],
        "certifications": [],
    }


def _extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text)
    return "\n\n".join(pages).strip()


def _extract_docx_text(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text and c.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return "\n".join(parts).strip()


def extract_text_from_upload(filename: str | None, data: bytes) -> str:
    """Extract plain text from a PDF or DOCX upload.

    Routes by extension, then falls back to trying both parsers so a
    mislabelled file still has a chance. Returns "" if nothing readable.
    """
    name = (filename or "").lower()
    extractors = []
    if name.endswith(".pdf"):
        extractors = [_extract_pdf_text, _extract_docx_text]
    elif name.endswith(".docx"):
        extractors = [_extract_docx_text, _extract_pdf_text]
    else:
        extractors = [_extract_pdf_text, _extract_docx_text]

    for extract in extractors:
        try:
            text = extract(data)
        except Exception as exc:
            logger.debug("Resume text extraction via %s failed: %s", extract.__name__, exc)
            continue
        if text:
            return text
    return ""


_PARSE_SYSTEM = (
    "You are a resume parser. Read the resume text and return a SINGLE JSON object "
    "with EXACTLY these keys:\n"
    '  "contact": {"full_name","email","phone","location","linkedin_url","github_url","website_url"},\n'
    '  "summary": string (the professional summary/objective, "" if none),\n'
    '  "work_experience": [{"company","title","location","start_date","end_date","bullets":[string]}],\n'
    '  "education": [{"institution","degree","field","start_date","end_date","grade"}],\n'
    '  "skills": [string],\n'
    '  "projects": [{"name","description","tech":[string],"url"}],\n'
    '  "certifications": [{"name","issuer","year"}]\n'
    "Rules: use null for unknown scalar fields and [] for missing lists. Dates as written "
    "in the resume (e.g. 'Jan 2022', 'Present'). Split each role's responsibilities into "
    "separate bullet strings. Extract ONLY what is present — never invent employers, dates, "
    "skills, or metrics. Output only the JSON — no explanation, no markdown fences."
)


async def parse_resume_text(text: str) -> dict:
    """Project resume text into the structured draft. Never raises."""
    draft = empty_profile()
    text = (text or "").strip()
    if not text:
        return draft
    try:
        raw = await _generate(_PARSE_SYSTEM, f"Resume text:\n\n{text}", max_tokens=3000)
        parsed = _parse_json(raw)
    except Exception as exc:
        logger.warning("Resume LLM parse failed: %s", exc)
        return draft

    if not isinstance(parsed, dict) or (len(parsed) == 1 and "raw" in parsed):
        return draft
    return _coerce_profile(parsed)


def _coerce_profile(parsed: dict) -> dict:
    """Normalise model output into the exact draft shape, dropping junk."""
    out = empty_profile()

    contact = parsed.get("contact")
    if isinstance(contact, dict):
        for f in CONTACT_FIELDS:
            v = contact.get(f)
            if isinstance(v, str):
                out["contact"][f] = v.strip() or None
            elif v is not None:
                out["contact"][f] = v

    summary = parsed.get("summary")
    out["summary"] = summary.strip() if isinstance(summary, str) else ""

    for key in ("work_experience", "education", "projects", "certifications"):
        v = parsed.get(key)
        if isinstance(v, list):
            out[key] = [item for item in v if isinstance(item, dict)]

    skills = parsed.get("skills")
    if isinstance(skills, list):
        out["skills"] = [s.strip() for s in skills if isinstance(s, str) and s.strip()]

    return out


async def parse_resume_file(filename: str | None, data: bytes) -> dict:
    """Full pipeline: bytes → text → structured draft. Never raises.

    Returns the draft plus the recovered raw text under ``resume_text`` so the
    caller can persist it and show the user what was parsed against.
    """
    text = extract_text_from_upload(filename, data)
    draft = await parse_resume_text(text)
    draft["resume_text"] = text
    return draft


# ── Reading the saved profile back off the User row ───────────────────────────

def load_structured_profile(user) -> dict:
    """Reconstruct the structured draft from a User instance.

    Contact comes from scalar columns; the section lists come from the JSON
    columns landed by Foundation's migration. Defensive against the migration
    not having run yet (getattr default None) and against either JSON or
    JSON-encoded-Text storage.
    """
    import json

    out = empty_profile()
    for f in CONTACT_FIELDS:
        out["contact"][f] = getattr(user, f, None)

    summary = getattr(user, "summary", None)
    out["summary"] = summary or ""

    for key in PROFILE_SECTIONS:
        raw = getattr(user, key, None)
        if raw is None:
            continue
        if isinstance(raw, (list, dict)):
            value = raw
        elif isinstance(raw, str):
            try:
                value = json.loads(raw)
            except (TypeError, ValueError):
                continue
        else:
            continue
        if key == "skills":
            if isinstance(value, list):
                out[key] = [s for s in value if isinstance(s, str)]
        elif isinstance(value, list):
            out[key] = [item for item in value if isinstance(item, dict)]

    return out


def has_structured_profile(user) -> bool:
    """True if the user has saved any structured profile content."""
    profile = load_structured_profile(user)
    return bool(
        profile["summary"]
        or any(profile[s] for s in PROFILE_SECTIONS)
        or any(profile["contact"].values())
    )
