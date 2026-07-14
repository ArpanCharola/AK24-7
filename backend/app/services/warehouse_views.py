from __future__ import annotations

from datetime import datetime, timezone

from app.services.experience_filters import FRESHER_TERMS, ROLE_QUERY_ALIASES, normalize_experience
from app.services.india_locations import location_matches_preference


_SOURCE_WEIGHTS = {
    "greenhouse": 13,
    "lever": 13,
    "ashby": 13,
    "workday": 11,
    "smartrecruiters": 11,
    "company_site": 10,
    "instahyre": 9,
    "cutshort": 9,
    "wellfound": 8,
    "hirist": 8,
    "linkedin": 8,
    "indeed": 7,
    "google_jobs": 6,
}
_REMOTE_INDIA_MARKERS = (
    "remote india",
    "pan india",
    "pan-india",
    "anywhere in india",
    "india remote",
)


def _normalized_text(value: str | None) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in (value or "")).split())


def explanation_from_codes(codes: list[str] | None) -> tuple[str | None, str | None]:
    parts = [str(code).replace("_", " ").strip() for code in (codes or []) if str(code).strip()]
    if not parts:
        return None, None
    return parts[0], ", ".join(parts)


def strict_location_match(
    location: str | None,
    preferred_locations: list[str],
    work_arrangement: str | None,
) -> bool:
    text = (location or "").strip().lower()
    if any(marker in text for marker in _REMOTE_INDIA_MARKERS):
        return True
    return location_matches_preference(location, preferred_locations, work_arrangement=work_arrangement)


def public_job_quality_score(
    *,
    title: str | None,
    source: str | None,
    posted_at: datetime | None,
    now: datetime | None,
    role: str | None,
    experience_filter: str | None,
) -> float:
    title_low = (title or "").lower()
    score = float(_SOURCE_WEIGHTS.get((source or "").lower(), 4))

    if role:
        role_key = role.lower().strip()
        aliases = ROLE_QUERY_ALIASES.get(role_key, [role])
        alias_lows = [alias.lower() for alias in aliases]
        if any(alias in title_low for alias in alias_lows):
            score += 35
        if role_key in title_low:
            score += 12

    if normalize_experience(experience_filter) == "fresher":
        if any(term in title_low for term in FRESHER_TERMS):
            score += 20
        if any(term in title_low for term in ("junior", "entry", "fresher", "graduate", "trainee", "associate")):
            score += 8
        if any(term in title_low for term in ("senior", "lead", "principal", "manager", "architect")):
            score -= 20

    when = now or datetime.now(timezone.utc)
    if posted_at:
        posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=timezone.utc)
        age_days = (when - posted).total_seconds() / 86400
        if age_days <= 1:
            score += 12
        elif age_days <= 3:
            score += 8
        elif age_days <= 7:
            score += 4

    return score


def canonical_dedupe_key(
    *,
    company: str | None,
    title: str | None,
    location: str | None,
    fallback_url: str | None,
) -> tuple[str, str, str] | tuple[str]:
    key = (
        _normalized_text(company),
        _normalized_text(title),
        _normalized_text(location),
    )
    if all(key):
        return key
    return (((fallback_url or "").strip().lower()) or "",)


def canonical_rank(score: float | int | None, posted_at: datetime | None, matched_at: datetime | None) -> tuple[int, datetime, datetime]:
    def _safe(value: datetime | None) -> datetime:
        if value is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    return int(score or 0), _safe(posted_at), _safe(matched_at)
