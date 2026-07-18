"""SQL-side job search: role → tsquery, plus the ranking expression.

Moves role/location/quality out of the old fetch-1500-then-filter-in-Python
loop (which broke deep pagination: it sliced `ranked[offset:offset+limit]` after
a capped fetch, so any offset past the survivor count returned nothing). The
query now filters and paginates entirely in SQL against the indexed columns
added in migration 0023.

Role synonym expansion reuses `_expand_term` so search and the discovery-time
matcher stay consistent by construction.
"""
from __future__ import annotations

import re

from sqlalchemy import func

from app.models.job_pool import JobPool


def role_tsquery(role: str | None) -> str | None:
    """Build a 'simple'-config tsquery from a role, synonym-expanded.

    Each comma-separated role and each synonym becomes a phrase (words joined by
    the FOLLOWED-BY operator `<->`); the phrases are OR'd. Returns None when the
    role is empty so the caller can skip the predicate.
    """
    if not role or not role.strip():
        return None
    from app.agents.job_discovery_agent import _expand_term

    variants: list[str] = []
    for part in role.split(","):
        for v in _expand_term(part.strip()):
            v = v.strip()
            if v and v not in variants:
                variants.append(v)

    phrases: list[str] = []
    for v in variants:
        words = [re.sub(r"[^a-z0-9]", "", w.lower()) for w in v.split()]
        words = [w for w in words if w]
        if words:
            phrases.append(" <-> ".join(words))
    if not phrases:
        return None
    return " | ".join(f"({p})" for p in phrases)


def role_predicate(role: str | None):
    tsq = role_tsquery(role)
    if tsq is None:
        return None
    return JobPool.search_tsv.op("@@")(func.to_tsquery("simple", tsq))


def location_predicate(location: str | None):
    """Trigram-backed location match, still admitting remote-India phrasings.

    Accepts a CSV of cities ("Kochi,Pune") so a multi-city UI selection filters
    server-side across the whole result set — the old client-side filter only
    saw one page, so a city with no hits on page 1 looked empty."""
    if not location:
        return None
    from sqlalchemy import or_
    cities = [
        c.strip().lower() for c in location.split(",")
        if c.strip() and c.strip().lower() not in {"india", "all india", "pan india"}
    ]
    if not cities:
        return None
    conds = [func.lower(JobPool.location).contains(c) for c in cities]
    conds += [
        func.lower(JobPool.location).contains("remote india"),
        func.lower(JobPool.location).contains("pan india"),
        func.lower(JobPool.location).contains("anywhere in india"),
    ]
    return or_(*conds)


_SENIOR_TERMS = ("senior", "sr.", "sr ", "lead", "principal", "staff",
                 "manager", "director", "head of", "architect", "vp ", "iii", " iv")


def experience_predicate(experience_filter: str | None):
    """Coarse experience gate kept in SQL so pagination counts stay exact.

    For fresher/junior we exclude senior-signal titles; a precise
    title+description check (is_experience_match) is deliberately NOT used as a
    filter here — running it in Python after a capped fetch is exactly what broke
    deep pagination. It can still inform ranking."""
    from sqlalchemy import and_, not_, or_
    level = (experience_filter or "").strip().lower()
    if level not in {"fresher", "junior", "entry"}:
        return None
    return and_(*[
        not_(func.lower(func.coalesce(JobPool.title, "")).contains(term))
        for term in _SENIOR_TERMS
    ])


def ranking_order(now):
    """quality_score minus a freshness decay, computed in SQL so ordering is
    stable across pages. ~3 points/day off the age of the posting (or its first
    sighting when undated) — mirrors the old Python ranking intent."""
    age_days = func.extract(
        "epoch", func.coalesce(now, func.now()) - func.coalesce(JobPool.posted_at, JobPool.first_seen_at)
    ) / 86400.0
    return (func.coalesce(JobPool.quality_score, 0.0) - 3.0 * age_days).desc()
