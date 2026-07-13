"""Deterministic normalization, admission, and in-batch deduplication.

The module is deliberately database-free.  An aggregation worker can validate a
source batch here, then persist ``CanonicalCandidate`` and ``SourceSighting``
objects using its own transaction boundary.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Iterable, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.services.india_locations import is_foreign_only


_TRACKING_KEYS = {
    "fbclid", "gclid", "msclkid", "ref", "referrer", "source", "trk",
    "trackingid", "gh_jid", "gh_src",
}
_TRACKING_PREFIXES = ("utm_", "trk_")
_STAFFING_RE = re.compile(
    r"\b(staffing|recruit(?:ing|ment)?|manpower|rpo|placement|consultanc(?:y|ies)|"
    r"talent\s+solutions|hr\s+services|teamlease|quess(?:corp)?|randstad|adecco|"
    r"manpowergroup|careernet|xpheno|collabera|spectraforce)\b", re.I
)
_AGENCY_COPY_RE = re.compile(
    r"\b(hiring\s+for\s+(?:our|a)\s+client|on\s+behalf\s+of\s+(?:our|a)\s+client|"
    r"our\s+client\s+is|leading\s+mnc\s+client)\b", re.I
)
_JOB_BOARD_RE = re.compile(
    r"\b(linkedin|indeed|naukri|glassdoor|wellfound|cutshort|instahyre|hirist|"
    r"google\s+jobs?|timesjobs|monster|foundit|jooble)\b", re.I
)
_FOREIGN_ONLY_RE = re.compile(
    r"\b(us|usa|united states|canada|united kingdom|uk|europe|emea|singapore|"
    r"australia|germany|france|uae|dubai)\s*(?:only)?\b", re.I
)
_INDIA_OR_GLOBAL_RE = re.compile(
    r"\b(india|bengaluru|bangalore|mumbai|delhi|ncr|gurugram|gurgaon|noida|"
    r"hyderabad|chennai|pune|kolkata|remote|worldwide|anywhere|global)\b", re.I
)
_CORPORATE_SUFFIX_RE = re.compile(
    r"\b(private|pvt|limited|ltd|incorporated|inc|llc|llp|corp(?:oration)?|"
    r"technologies|technology|solutions)\b", re.I
)
_TITLE_NOISE_RE = re.compile(r"\b(?:job|opening|vacancy|hiring)\b", re.I)


class RejectionReason(StrEnum):
    INVALID = "invalid"
    STAFFING_OR_RECRUITMENT = "staffing_or_recruitment"
    JOB_BOARD_EMPLOYER = "job_board_employer"
    STALE = "stale"
    FOREIGN_ONLY = "foreign_only"


@dataclass(frozen=True, slots=True)
class Rejection:
    reason: RejectionReason
    detail: str


@dataclass(frozen=True, slots=True)
class SourceSighting:
    source: str
    source_url: str
    source_native_id: str | None
    observed_at: datetime
    raw: Mapping[str, Any]


@dataclass(slots=True)
class CanonicalCandidate:
    fingerprint: str
    canonical_url: str
    employer: str
    normalized_employer: str
    title: str
    normalized_title: str
    location: str
    posted_at: datetime
    description: str
    sightings: list[SourceSighting] = field(default_factory=list)


@dataclass(slots=True)
class BatchResult:
    candidates: list[CanonicalCandidate] = field(default_factory=list)
    rejections: list[tuple[Mapping[str, Any], Rejection]] = field(default_factory=list)


def normalize_job_url(url: str) -> str:
    """Normalize a URL while retaining query keys that can identify a job."""
    raw = (url or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw if "://" in raw else f"https://{raw}")
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return ""
        host = parts.hostname.lower()
        if parts.port and parts.port not in {80, 443}:
            host = f"{host}:{parts.port}"
        path = re.sub(r"/{2,}", "/", parts.path or "/").rstrip("/") or "/"
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in _TRACKING_KEYS
            and not key.lower().startswith(_TRACKING_PREFIXES)
        ]
        return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))
    except (TypeError, ValueError):
        return ""


def _words(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9+#]+", (value or "").casefold()))


def normalize_employer(name: str) -> str:
    return " ".join(_CORPORATE_SUFFIX_RE.sub(" ", _words(name)).split())


def normalize_title(title: str) -> str:
    normalized = _TITLE_NOISE_RE.sub(" ", _words(title))
    return " ".join(normalized.split())


def _as_utc(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
        except ValueError:
            return None
    return None


def classify_rejection(
    job: Mapping[str, Any], *, now: datetime | None = None, max_age_days: int = 7
) -> Rejection | None:
    title = str(job.get("title") or "").strip()
    employer = str(job.get("company") or job.get("employer") or "").strip()
    url = normalize_job_url(str(job.get("job_url") or job.get("url") or ""))
    posted = _as_utc(job.get("posted_at"))
    if not title or not employer or not url or not posted:
        return Rejection(RejectionReason.INVALID, "title, employer, URL, and posting date are required")
    current = _as_utc(now) or datetime.now(timezone.utc)
    if posted > current + timedelta(hours=24):
        return Rejection(RejectionReason.INVALID, "posting date is implausibly in the future")
    if posted < current - timedelta(days=max_age_days):
        return Rejection(RejectionReason.STALE, f"posting is older than {max_age_days} days")
    description = str(job.get("job_description") or job.get("description") or "")
    if _STAFFING_RE.search(employer) or _AGENCY_COPY_RE.search(description):
        return Rejection(RejectionReason.STAFFING_OR_RECRUITMENT, "third-party recruiter or staffing employer")
    if _JOB_BOARD_RE.fullmatch(normalize_employer(employer)):
        return Rejection(RejectionReason.JOB_BOARD_EMPLOYER, "job board cannot be the hiring employer")
    location = str(job.get("location") or "").strip()
    if is_foreign_only(location):
        return Rejection(RejectionReason.FOREIGN_ONLY, "role is not open to India")
    return None


def job_fingerprint(job: Mapping[str, Any]) -> str:
    employer = normalize_employer(str(job.get("company") or job.get("employer") or ""))
    title = normalize_title(str(job.get("title") or ""))
    location = _words(str(job.get("location") or "unknown"))
    posted = _as_utc(job.get("posted_at"))
    date_bucket = posted.date().isoformat() if posted else "unknown"
    description = _words(str(job.get("job_description") or job.get("description") or ""))[:500]
    description_digest = hashlib.sha256(description.encode()).hexdigest()[:12]
    evidence = "|".join((employer, title, location, date_bucket, description_digest))
    return hashlib.sha256(evidence.encode()).hexdigest()


def deduplicate_batch(
    jobs: Iterable[Mapping[str, Any]], *, now: datetime | None = None, max_age_days: int = 7
) -> BatchResult:
    """Admit clean jobs and attach all exact in-batch sightings.

    URL equality wins over fingerprints. Fingerprints intentionally include
    location, posting date, and description evidence to avoid destructive
    merging of separate requisitions with similar titles.
    """
    result = BatchResult()
    by_url: dict[str, CanonicalCandidate] = {}
    by_fingerprint: dict[str, CanonicalCandidate] = {}
    for raw in jobs:
        rejection = classify_rejection(raw, now=now, max_age_days=max_age_days)
        if rejection:
            result.rejections.append((raw, rejection))
            continue
        url = normalize_job_url(str(raw.get("job_url") or raw.get("url") or ""))
        fingerprint = job_fingerprint(raw)
        observed = _as_utc(raw.get("observed_at")) or _as_utc(now) or datetime.now(timezone.utc)
        sighting = SourceSighting(
            source=str(raw.get("source") or "unknown").casefold(),
            source_url=url,
            source_native_id=str(raw.get("source_native_id")) if raw.get("source_native_id") else None,
            observed_at=observed,
            raw=raw,
        )
        existing = by_url.get(url) or by_fingerprint.get(fingerprint)
        if existing:
            existing.sightings.append(sighting)
            by_url[url] = existing
            continue
        posted = _as_utc(raw.get("posted_at"))
        assert posted is not None
        employer = str(raw.get("company") or raw.get("employer") or "").strip()
        title = str(raw.get("title") or "").strip()
        candidate = CanonicalCandidate(
            fingerprint=fingerprint,
            canonical_url=url,
            employer=employer,
            normalized_employer=normalize_employer(employer),
            title=title,
            normalized_title=normalize_title(title),
            location=str(raw.get("location") or "").strip(),
            posted_at=posted,
            description=str(raw.get("job_description") or raw.get("description") or "").strip(),
            sightings=[sighting],
        )
        result.candidates.append(candidate)
        by_url[url] = candidate
        by_fingerprint[fingerprint] = candidate
    return result
