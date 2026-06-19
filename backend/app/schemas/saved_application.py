from datetime import datetime

from pydantic import BaseModel, Field, field_validator

# Pipeline stages a saved application can sit in. Kept in lockstep with the
# frontend's status filter + badge colors. "to apply" is the pre-application
# stage from the user's spreadsheet (a job saved but not yet applied to).
ALLOWED_STATUSES = ("to apply", "applied", "assessment", "interview")


def _validate_status(value: str) -> str:
    v = value.strip().lower()
    if v not in ALLOWED_STATUSES:
        raise ValueError(f"status must be one of: {', '.join(ALLOWED_STATUSES)}")
    return v


class SavedApplicationCreate(BaseModel):
    company: str = Field(..., min_length=1, max_length=200, description="Company you applied to.")
    role: str = Field(..., min_length=1, max_length=200, description="Job title / role.")
    applied_at: datetime = Field(..., description="When you applied (ISO 8601, timezone-aware).")
    mail_url: str | None = Field(default=None, max_length=2000, description="Optional link to the email or job posting.")
    status: str = Field(default="applied", description="Pipeline stage: to apply, applied, assessment, or interview.")
    notes: str | None = Field(default=None, max_length=4000)
    # Tracker-board / spreadsheet-parity fields (all optional).
    job_link: str | None = Field(default=None, max_length=2000)
    job_portal: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    salary: str | None = Field(default=None, max_length=100)
    job_type: str | None = Field(default=None, max_length=100)
    work_arrangement: str | None = Field(default=None, max_length=50)
    resume_label: str | None = Field(default=None, max_length=200)
    contact: str | None = Field(default=None, max_length=2000)
    source_thread_id: str | None = Field(
        default=None, max_length=128,
        description="Gmail thread id this came from. When set, the same thread is never saved twice.",
    )

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str) -> str:
        return _validate_status(v)

    @field_validator("company", "role")
    @classmethod
    def _strip_required(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("mail_url", "notes")
    @classmethod
    def _empty_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class SavedApplicationUpdate(BaseModel):
    """PATCH — every field optional; only what you send is changed."""

    company: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = Field(default=None, min_length=1, max_length=200)
    applied_at: datetime | None = None
    mail_url: str | None = Field(default=None, max_length=2000)
    status: str | None = None
    notes: str | None = Field(default=None, max_length=4000)
    job_link: str | None = Field(default=None, max_length=2000)
    job_portal: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    salary: str | None = Field(default=None, max_length=100)
    job_type: str | None = Field(default=None, max_length=100)
    work_arrangement: str | None = Field(default=None, max_length=50)
    resume_label: str | None = Field(default=None, max_length=200)
    contact: str | None = Field(default=None, max_length=2000)

    @field_validator("status")
    @classmethod
    def _check_status(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return _validate_status(v)

    @field_validator("company", "role")
    @classmethod
    def _strip_required(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("mail_url", "notes")
    @classmethod
    def _empty_to_none(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


class SavedApplicationOut(BaseModel):
    id: str
    company: str
    role: str
    applied_at: datetime
    mail_url: str | None = None
    status: str
    notes: str | None = None
    job_link: str | None = None
    job_portal: str | None = None
    location: str | None = None
    salary: str | None = None
    job_type: str | None = None
    work_arrangement: str | None = None
    resume_label: str | None = None
    contact: str | None = None
    source_thread_id: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    class Config:
        from_attributes = True
