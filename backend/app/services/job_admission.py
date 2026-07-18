"""Single source of truth for "is this an India job, and how sure are we?".

Before this module three code paths disagreed: the feed's `_is_india_strict`
(drops blank + bare-"Remote"), the warehouse's `classify_rejection` (only
rejects explicit-foreign, so it *keeps* blanks), and slug discovery's stricter
probe. A job could be admitted by one and dropped by another. Everything now
routes through `classify_india` + `india_confidence`, which return a graded
verdict instead of a hard boolean — so blank and global-remote postings are
stored with a low confidence and ranked/filtered by the serving layer, not
silently thrown away (throwing them away is what starved supply).

Reuses the token lists in india_locations; this module only adds the grading.
"""
from __future__ import annotations

import re
from enum import Enum

from app.services.india_locations import (
    INDIA_MARKERS,
    REMOTE_INDIA_TERMS,
    GLOBAL_REMOTE_TERMS,
    UNKNOWN_LOCATION_RE,
    _has_phrase,
    _low,
    is_foreign_only,
)


class IndiaVerdict(str, Enum):
    INDIA = "india"                # explicit India city/state/country token
    REMOTE_INDIA = "remote_india"  # "remote india" / "pan india"
    GLOBAL_REMOTE = "global_remote"  # bare "remote"/"worldwide", no geo
    UNKNOWN = "unknown"            # blank / "multiple locations" / unparseable
    FOREIGN = "foreign"            # explicit non-India, no India marker


def classify_india(
    location: str | None,
    *,
    work_arrangement: str | None = None,
    country_hint: str | None = None,
) -> IndiaVerdict:
    text = _low(location)
    blank = not text.strip() or bool(UNKNOWN_LOCATION_RE.search(text))

    if not blank:
        if is_foreign_only(location):
            return IndiaVerdict.FOREIGN
        if _has_phrase(text, REMOTE_INDIA_TERMS):
            return IndiaVerdict.REMOTE_INDIA
        if _has_phrase(text, INDIA_MARKERS):
            return IndiaVerdict.INDIA
        if _has_phrase(text, GLOBAL_REMOTE_TERMS):
            return IndiaVerdict.GLOBAL_REMOTE

    # Blank, or a "remote"-ish string with no geo. A board we've already shown to
    # be India-centric (>=40% India-explicit roles) makes an unlabelled posting
    # very likely India — free precision we earn during slug probing.
    if country_hint == "IN":
        return IndiaVerdict.INDIA
    if blank:
        return IndiaVerdict.UNKNOWN
    return IndiaVerdict.GLOBAL_REMOTE


# Confidence that a row is applicable to an India seeker. The feed shows
# >=0.5 by default; UNKNOWN/foreign-board-remote sit below that so they exist
# (searchable, badged) without polluting the default view.
_CONFIDENCE = {
    IndiaVerdict.INDIA: 1.0,
    IndiaVerdict.REMOTE_INDIA: 0.9,
    IndiaVerdict.GLOBAL_REMOTE: 0.6,
    IndiaVerdict.UNKNOWN: 0.4,
    IndiaVerdict.FOREIGN: 0.0,
}


def india_confidence(
    location: str | None,
    *,
    work_arrangement: str | None = None,
    country_hint: str | None = None,
) -> float:
    verdict = classify_india(
        location, work_arrangement=work_arrangement, country_hint=country_hint
    )
    conf = _CONFIDENCE[verdict]
    # A global-remote posting on a non-India board is usually US-remote; keep it
    # in the catalogue but below the default cut.
    if verdict is IndiaVerdict.GLOBAL_REMOTE and country_hint not in (None, "IN"):
        return 0.35
    return conf


# ── Employment type ──────────────────────────────────────────────────────────
# Internships are un-excluded (highest-intent fresher supply) but classified so
# the feed can filter/badge them, rather than dropped by _EXCLUDED_TITLE_RE.
_INTERNSHIP_RE = re.compile(r"\b(intern|internship|trainee|apprentice|co-?op)\b", re.I)
_CONTRACT_RE = re.compile(r"\b(contract|contractor|freelance|temporary|temp|c2h)\b", re.I)
_PARTTIME_RE = re.compile(r"\bpart[\s-]?time\b", re.I)


def employment_type(title: str | None, description: str | None = None) -> str:
    t = title or ""
    if _INTERNSHIP_RE.search(t):
        return "internship"
    if _PARTTIME_RE.search(t):
        return "parttime"
    if _CONTRACT_RE.search(t):
        return "contract"
    return "fulltime"
