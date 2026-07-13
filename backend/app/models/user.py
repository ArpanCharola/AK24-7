from __future__ import annotations
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Text, Integer, Float, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.job_application import JobApplication
    from app.models.tailored_resume import TailoredResume
    from app.models.job_search_profile import JobSearchProfile
    from app.models.discovered_job import DiscoveredJob
    from app.models.cover_letter import CoverLetter
    from app.models.sent_email import SentEmail
    from app.models.saved_application import SavedApplication


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    # Username chosen in the post-Google "set credentials" step. Unique; users
    # can log in with either email or username. Null until credentials are set.
    username: Mapped[str | None] = mapped_column(String(150), unique=True, index=True, nullable=True)
    # Nullable: a brand-new Google sign-up exists before the user picks a password
    # (credentials_set gates login until they do).
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # SECURITY NOTE: plaintext password, stored ONLY so the single admin can view
    # what each user set (explicit product requirement). This is an internal,
    # single-admin tool — do NOT replicate this pattern in a public-facing app.
    raw_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # True once the user has completed the post-Google username+password setup.
    credentials_set: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Admin can watch all users + see raw passwords. Cannot edit passwords.
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Profile fields
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    github_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    career_history: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured profile (base resume) — populated by resume-import autofill or manual entry.
    # Stored as JSON (lists of objects) so the frontend can render/edit section-by-section.
    profile_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_experience: Mapped[list | None] = mapped_column(JSON, nullable=True)
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    projects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    certifications: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # India job-search context.
    current_ctc_lpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_ctc_lpa: Mapped[float | None] = mapped_column(Float, nullable=True)
    notice_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    preferred_locations: Mapped[str | None] = mapped_column(Text, nullable=True)
    desired_roles: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Total professional experience, split years + months. Drives the
    # Entry / Mid / Senior level the job search targets.
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    experience_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Credentials used by the agent on job portals (separate from app login)
    portal_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    portal_password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Auto-apply gate (Phase 6A) — opt-in master switch with a daily safety cap
    auto_apply_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    daily_auto_apply_cap: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    # Gmail connection (Phase 7) — read-only OAuth for application confirmation /
    # lifecycle tracking. Tokens are stored Fernet-encrypted (see core/encryption.py).
    gmail_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gmail_access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    gmail_token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gmail_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    gmail_last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Space-joined OAuth scopes actually granted (drives can_label / can_send).
    gmail_scopes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Gmail automation opt-ins (all off by default; sending is consequential).
    auto_label_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_followup_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    followup_after_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)

    # Consent gate (Automail-ported) — non-dismissible disclaimer recorded once
    # per user; ``consented_scopes`` is the space-joined OAuth scope set in
    # effect at the time of consent (so a later scope addition re-prompts).
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consented_scopes: Mapped[str | None] = mapped_column(Text, nullable=True)

    applications: Mapped[list["JobApplication"]] = relationship(back_populates="user")
    resumes: Mapped[list["TailoredResume"]] = relationship(back_populates="user")
    cover_letters: Mapped[list["CoverLetter"]] = relationship(back_populates="user")
    job_search_profiles: Mapped[list["JobSearchProfile"]] = relationship(back_populates="user")
    discovered_jobs: Mapped[list["DiscoveredJob"]] = relationship(back_populates="user")
    sent_emails: Mapped[list["SentEmail"]] = relationship(back_populates="user")
    saved_applications: Mapped[list["SavedApplication"]] = relationship(back_populates="user")
