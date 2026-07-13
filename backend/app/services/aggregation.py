"""Shared, deterministic job warehouse aggregation.

The service deliberately reuses the existing discovery agent for v1 source
coverage, but persists only clean canonical jobs and lightweight profile matches.
It is idempotent: canonical URLs/fingerprints and sightings are upserted.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from sqlalchemy import delete, func, or_, select

from app.aggregation.quality import deduplicate_batch
from app.core.database import AsyncSessionLocal
from app.services.india_locations import location_matches_preference
from app.models.job_search_profile import JobSearchProfile
from app.models.user import User
from app.models.discovered_job import DiscoveredJob
from app.models.job_warehouse import (
    AggregationRun, CanonicalJob, DemandCluster, Employer, JobRejection,
    JobSourceSighting, ProfileDemandMembership, ProfileJobMatch, SourceRunMetric,
)

logger = logging.getLogger(__name__)
UTC = timezone.utc
DEFAULT_ROLES = (
    "Software Engineer", "Software Developer", "Frontend Developer",
    "Backend Developer", "Full Stack Developer", "React Developer",
    "Python Developer", "Java Developer", "AI Engineer", "Machine Learning Engineer",
    "Data Engineer", "Data Analyst", "DevOps Engineer", "QA Engineer", "SDET",
)


def _now() -> datetime:
    return datetime.now(UTC)


def _terms(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _user_locations(user: User | None) -> list[str]:
    """Read profile locations from both the current JSON format and legacy CSV."""
    if not user or not user.preferred_locations:
        return []
    try:
        parsed = json.loads(user.preferred_locations)
    except (TypeError, ValueError):
        parsed = None
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return _terms(user.preferred_locations)


def _user_skills(user: User | None) -> list[str]:
    if not user or not user.skills:
        return []
    if isinstance(user.skills, list):
        return [str(item).strip() for item in user.skills if str(item).strip()]
    # This is defensive for pre-JSON legacy rows.
    if isinstance(user.skills, str):
        try:
            parsed = json.loads(user.skills)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        return _terms(user.skills)
    return []


def _experience_band(user: User | None, legacy_value: str | None) -> str | None:
    """Targets inherit the canonical profile experience unless a legacy value exists."""
    if legacy_value:
        return legacy_value
    if not user:
        return None
    months = (user.experience_years or 0) * 12 + (user.experience_months or 0)
    if months < 24:
        return "entry"
    if months < 60:
        return "mid"
    return "senior"


def _role_family(roles: list[str]) -> str:
    value = " ".join(roles).lower()
    if "machine learning" in value or " ml " in f" {value} " or "ai" in value:
        return "AI / ML Engineer"
    if "front" in value:
        return "Frontend Developer"
    if "full" in value:
        return "Fullstack Developer"
    if "web" in value:
        return "Web Developer"
    return "Software Engineer"


def _signature(roles: list[str], locations: list[str], experience: str | None, arrangements: list[str]) -> str:
    payload = json.dumps({"roles": sorted(x.casefold() for x in roles), "locations": sorted(x.casefold() for x in locations), "experience": experience or "", "arrangements": sorted(x.casefold() for x in arrangements)}, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


async def ensure_profile_demand(
    profile: JobSearchProfile, db, user: User | None = None
) -> DemandCluster:
    roles = _terms(profile.target_roles) or list(DEFAULT_ROLES)
    # A Job Target only owns its role/location override and exclusions. Skills
    # and experience are inherited from the one personal Profile.
    locations = list(dict.fromkeys([*(_terms(profile.locations) or _user_locations(user) or ["India"]), "Remote India", "Pan India"]))
    arrangements = _terms(profile.work_arrangements)
    skills = _terms(profile.keywords) or _user_skills(user)
    experience = _experience_band(user, profile.experience_level)
    signature = _signature(roles, locations, experience, arrangements)
    cluster = (await db.execute(select(DemandCluster).where(DemandCluster.signature == signature))).scalar_one_or_none()
    if not cluster:
        cluster = DemandCluster(signature=signature, role_family=_role_family(roles), query_terms=roles, skill_cluster=skills or None, locations=locations, experience_band=experience, work_arrangements=arrangements or None, priority=100, status="queued")
        db.add(cluster)
        await db.flush()
    memberships = (await db.execute(
        select(ProfileDemandMembership).where(ProfileDemandMembership.profile_id == profile.id)
    )).scalars().all()
    membership = next((item for item in memberships if item.demand_cluster_id == cluster.id), None)
    # A changed target must stop warming its old cluster. Keeping that old
    # membership active would silently cause redundant shared discovery.
    for item in memberships:
        item.is_active = item.demand_cluster_id == cluster.id and bool(profile.is_active)
    if membership is None:
        db.add(ProfileDemandMembership(profile_id=profile.id, demand_cluster_id=cluster.id, is_active=bool(profile.is_active)))
    return cluster


async def sync_profile_demands(db) -> list[DemandCluster]:
    # The warehouse stays warm for the core technical roles even before users
    # create profiles. These rows are idempotent and share the India+remote
    # scope used by profile defaults.
    for role in DEFAULT_ROLES:
        signature = _signature([role], ["India", "Remote India", "Pan India"], None, [])
        existing = (await db.execute(select(DemandCluster).where(DemandCluster.signature == signature))).scalar_one_or_none()
        if not existing:
            db.add(DemandCluster(signature=signature, role_family=_role_family([role]), query_terms=[role], locations=["India", "Remote India", "Pan India"], is_default=True, status="queued", priority=200))
    profiles = (await db.execute(
        select(JobSearchProfile, User)
        .join(User, User.id == JobSearchProfile.user_id)
        .where(JobSearchProfile.is_active.is_(True))
    )).all()
    for profile, user in profiles:
        await ensure_profile_demand(profile, db, user)
    await db.flush()
    return (await db.execute(select(DemandCluster).where(DemandCluster.status.in_(("queued", "active"))).order_by(DemandCluster.priority.desc(), DemandCluster.created_at))).scalars().all()


def _profile_for_cluster(cluster: DemandCluster) -> dict:
    return {"target_roles": ", ".join(cluster.query_terms), "locations": ", ".join(cluster.locations or ["India", "Remote India"]), "keywords": ", ".join(cluster.skill_cluster or []), "experience_level": cluster.experience_band, "work_arrangements": ", ".join(cluster.work_arrangements or []), "posted_within_days": 7, "excluded_companies": ""}


def _url_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _domain(url: str) -> str | None:
    try:
        return urlsplit(url).hostname.lower().removeprefix("www.") if url else None
    except (TypeError, ValueError):
        return None


def _match_score(
    profile: JobSearchProfile,
    job: CanonicalJob,
    user: User | None = None,
    employer_name: str | None = None,
) -> tuple[float, dict]:
    exclusions = {item.casefold() for item in _terms(profile.excluded_companies)}
    if employer_name and employer_name.casefold() in exclusions:
        return 0.0, {
            "role_score": 0.0,
            "skill_score": 0.0,
            "location_score": 0.0,
            "experience_score": 0.0,
            "freshness_score": 0.0,
            "codes": ["excluded_employer"],
        }
    role_terms = {x.casefold() for x in _terms(profile.target_roles)}
    text = f"{job.title} {job.description or ''}".casefold()
    role = 35.0 if any(term in text for term in role_terms) else 0.0
    skills = {x.casefold() for x in (_terms(profile.keywords) or _user_skills(user))}
    skill = min(30.0, 30.0 * sum(1 for s in skills if s in text) / max(len(skills), 1)) if skills else 15.0
    locations = {x.casefold() for x in (_terms(profile.locations) or _user_locations(user))}
    location = 15.0 if not locations or location_matches_preference(
        job.location,
        list(locations),
        work_arrangement=job.work_arrangement,
    ) else 0.0
    experience = 15.0
    freshness = max(0.0, 5.0 * (1 - ((_now() - job.posted_at).days / 7)))
    score = round(role + skill + location + experience + freshness, 1)
    return score, {"role_score": role, "skill_score": skill, "location_score": location, "experience_score": experience, "freshness_score": freshness, "codes": [code for code, points in (("role_match", role), ("skill_overlap", skill), ("location_match", location), ("fresh_posting", freshness)) if points]}


async def _persist_candidate(db, candidate, run: AggregationRun) -> tuple[CanonicalJob, bool, int]:
    domain = _domain(candidate.canonical_url)
    employer = (await db.execute(select(Employer).where(Employer.normalized_name == candidate.normalized_employer, Employer.normalized_domain == domain))).scalar_one_or_none()
    if not employer:
        employer = Employer(name=candidate.employer, normalized_name=candidate.normalized_employer, normalized_domain=domain)
        db.add(employer)
        await db.flush()
    url_hash = _url_hash(candidate.canonical_url)
    job = (await db.execute(select(CanonicalJob).where((CanonicalJob.canonical_url_hash == url_hash) | (CanonicalJob.fingerprint == candidate.fingerprint)))).scalars().first()
    created = job is None
    now = _now()
    if not job:
        job = CanonicalJob(employer_id=employer.id, title=candidate.title, normalized_title=candidate.normalized_title, role_family=_role_family([candidate.title]), description=candidate.description or None, location=candidate.location or None, location_normalized=(candidate.location or "").casefold() or None, work_arrangement="remote" if "remote" in (candidate.location or "").casefold() else "onsite", canonical_url=candidate.canonical_url, canonical_url_hash=url_hash, preferred_source=candidate.sightings[0].source, fingerprint=candidate.fingerprint, posted_at=candidate.posted_at, expires_at=candidate.posted_at + timedelta(days=7), status="live", last_seen_at=now)
        db.add(job)
        await db.flush()
    else:
        job.last_seen_at = now; job.status = "live"; job.description = job.description or candidate.description or None
    new_sightings = 0
    for sighting in candidate.sightings:
        shash = _url_hash(sighting.source_url)
        existing = (await db.execute(select(JobSourceSighting).where(JobSourceSighting.source == sighting.source, JobSourceSighting.source_url_hash == shash))).scalar_one_or_none()
        if existing:
            existing.last_seen_at = now; existing.observed_at = now; existing.aggregation_run_id = run.id
        else:
            db.add(JobSourceSighting(canonical_job_id=job.id, aggregation_run_id=run.id, source=sighting.source, source_native_id=sighting.source_native_id, source_url=sighting.source_url, source_url_hash=shash, observed_metadata={"title": candidate.title, "company": candidate.employer}, source_posted_at=candidate.posted_at)); new_sightings += 1
    return job, created, new_sightings


async def _refresh_matches(db, clusters: list[DemandCluster], jobs: list[CanonicalJob]) -> None:
    profile_ids = (await db.execute(select(ProfileDemandMembership.profile_id).where(ProfileDemandMembership.demand_cluster_id.in_([c.id for c in clusters]), ProfileDemandMembership.is_active.is_(True)))).scalars().all()
    if not profile_ids: return
    employer_names = dict((await db.execute(
        select(Employer.id, Employer.name).where(Employer.id.in_([job.employer_id for job in jobs]))
    )).all())
    profiles = (await db.execute(
        select(JobSearchProfile, User)
        .join(User, User.id == JobSearchProfile.user_id)
        .where(JobSearchProfile.id.in_(profile_ids), JobSearchProfile.is_active.is_(True))
    )).all()
    for profile, user in profiles:
        for job in jobs:
            score, parts = _match_score(
                profile, job, user, employer_names.get(job.employer_id)
            )
            if score < 55: continue
            explanation_codes = parts["codes"]
            match = (await db.execute(select(ProfileJobMatch).where(ProfileJobMatch.profile_id == profile.id, ProfileJobMatch.canonical_job_id == job.id))).scalar_one_or_none()
            if not match:
                match = ProfileJobMatch(
                    profile_id=profile.id,
                    canonical_job_id=job.id,
                    score=score,
                    role_score=parts["role_score"],
                    skill_score=parts["skill_score"],
                    location_score=parts["location_score"],
                    experience_score=parts["experience_score"],
                    freshness_score=parts["freshness_score"],
                    explanation_codes=explanation_codes,
                )
                db.add(match)
            else:
                match.score = score; match.role_score = parts["role_score"]; match.skill_score = parts["skill_score"]; match.location_score = parts["location_score"]; match.experience_score = parts["experience_score"]; match.freshness_score = parts["freshness_score"]; match.explanation_codes = explanation_codes
            await _project_legacy_match(
                db, user_id=user.id, profile=profile, job=job, score=score,
                explanation_codes=explanation_codes, employer_name=employer_names.get(job.employer_id),
            )


async def _project_legacy_match(
    db,
    *,
    user_id: int,
    profile: JobSearchProfile,
    job: CanonicalJob,
    score: float,
    explanation_codes: list[str],
    employer_name: str | None,
) -> None:
    """Keep legacy ``/discovered-jobs`` consumers working during warehouse rollout.

    The table remains the old per-user read model, while the warehouse is the
    source of truth. One user-visible copy per canonical URL prevents duplicate
    cards when multiple targets match the same role. The first matching target
    stays attached for legacy target filtering; the warehouse association keeps
    the complete many-target relationship.
    """
    if not job.canonical_url:
        return
    row = (await db.execute(
        select(DiscoveredJob).where(
            DiscoveredJob.user_id == user_id,
            DiscoveredJob.job_url == job.canonical_url,
        )
    )).scalars().first()
    explanation = ", ".join(code.replace("_", " ") for code in explanation_codes)
    if row is None:
        db.add(DiscoveredJob(
            user_id=user_id,
            search_profile_id=profile.id,
            job_url=job.canonical_url,
            title=job.title,
            company=employer_name,
            location=job.location,
            job_description=job.description,
            source=job.preferred_source or "warehouse",
            work_arrangement=job.work_arrangement,
            posted_at=job.posted_at,
            match_score=round(score),
            match_reason=explanation or "warehouse match",
            match_explanation=explanation or None,
        ))
        return
    # Preserve a queued/applied lifecycle state created by the legacy UI, but
    # refresh the match data and incomplete metadata from the warehouse.
    row.match_score = max(row.match_score or 0, round(score))
    row.match_reason = explanation or row.match_reason
    row.match_explanation = explanation or row.match_explanation
    row.title = row.title or job.title
    row.company = row.company or employer_name
    row.location = row.location or job.location
    row.job_description = row.job_description or job.description
    row.work_arrangement = row.work_arrangement or job.work_arrangement
    row.posted_at = row.posted_at or job.posted_at


async def refresh_cluster_matches(cluster_id: int, db) -> int:
    """Project already-live warehouse jobs as soon as a target joins demand.

    This is deliberately read/match work only: it makes the shared warehouse
    useful immediately and never invokes a source adapter or user-specific
    scraper. The regular aggregation cadence fills any coverage gap later.
    """
    cluster = await db.get(DemandCluster, cluster_id)
    if cluster is None:
        return 0
    jobs = (await db.execute(
        select(CanonicalJob).where(
            CanonicalJob.status == "live",
            CanonicalJob.expires_at >= _now(),
        )
    )).scalars().all()
    await _refresh_matches(db, [cluster], jobs)
    await db.commit()
    return len(jobs)


async def run_aggregation(trigger: str = "scheduled") -> dict:
    from app.agents.job_discovery_agent import JobDiscoveryAgent
    async with AsyncSessionLocal() as db:
        active = (await db.execute(select(AggregationRun).where(AggregationRun.status == "running"))).scalars().first()
        if active: return {"status": "skipped", "reason": "aggregation already running", "run_id": active.id}
        run = AggregationRun(trigger=trigger, status="running", lease_key=f"warehouse:{_now().strftime('%Y%m%d%H')}", started_at=_now())
        db.add(run); await db.commit(); await db.refresh(run)
        try:
            clusters = await sync_profile_demands(db)
            raw_by_source: dict[str, list[dict]] = defaultdict(list)
            agent = JobDiscoveryAgent()
            for cluster in clusters:
                try:
                    jobs = await agent.discover(_profile_for_cluster(cluster))
                    cluster.status = "active"; cluster.last_run_at = _now(); cluster.next_run_at = _now() + timedelta(hours=12)
                    for item in jobs: raw_by_source[str(item.get("source") or "unknown")].append(item)
                except Exception as exc:
                    cluster.status = "failed"; logger.warning("cluster %s failed: %s", cluster.id, exc)
            raw = [item for items in raw_by_source.values() for item in items]
            batch = deduplicate_batch(raw, max_age_days=7)
            accepted_jobs: list[CanonicalJob] = []
            source_counts = Counter(item.get("source") or "unknown" for item in raw)
            for raw_job, rejection in batch.rejections:
                db.add(JobRejection(aggregation_run_id=run.id, source=str(raw_job.get("source") or "unknown"), title=raw_job.get("title"), employer_name=raw_job.get("company"), reason_code=str(rejection.reason), reason_detail=rejection.detail, retain_until=_now() + timedelta(days=30)))
            accepted = sightings = 0
            for candidate in batch.candidates:
                job, created, count = await _persist_candidate(db, candidate, run); accepted += int(created); sightings += count - int(created); accepted_jobs.append(job)
            for source, raw_count in source_counts.items():
                db.add(SourceRunMetric(aggregation_run_id=run.id, source=source, status="succeeded", raw_found=raw_count, accepted_unique=sum(1 for j in accepted_jobs if j.preferred_source == source), duplicate_sightings=0, rejected=sum(1 for raw_job, _ in batch.rejections if raw_job.get("source") == source), started_at=run.started_at or _now(), finished_at=_now()))
            await _refresh_matches(db, clusters, accepted_jobs)
            run.raw_found = len(raw); run.accepted_unique = accepted; run.duplicate_sightings = max(0, len(raw) - accepted - len(batch.rejections)); run.rejected = len(batch.rejections); run.status = "partial" if not accepted_jobs and raw else "succeeded"; run.finished_at = _now()
            await db.commit()
            return {"status": run.status, "run_id": run.id, "raw_found": run.raw_found, "accepted_unique": accepted}
        except Exception as exc:
            await db.rollback(); run.status = "failed"; run.error_summary = str(exc)[:1000]; run.finished_at = _now(); db.add(run); await db.commit(); raise


async def cleanup_warehouse() -> dict:
    now = _now(); expire_before = now - timedelta(days=7); purge_before = now - timedelta(days=30)
    async with AsyncSessionLocal() as db:
        live = (await db.execute(select(CanonicalJob).where(CanonicalJob.status == "live", CanonicalJob.posted_at < expire_before))).scalars().all()
        for job in live: job.status = "expired"; job.description = None
        purged = await db.execute(delete(JobRejection).where(JobRejection.retain_until < now))
        await db.execute(delete(ProfileJobMatch).where(ProfileJobMatch.canonical_job_id.in_(select(CanonicalJob.id).where(CanonicalJob.status == "expired", CanonicalJob.posted_at < purge_before))))
        await db.execute(delete(DiscoveredJob).where(or_(
            DiscoveredJob.posted_at < expire_before,
            (DiscoveredJob.posted_at.is_(None)) & (DiscoveredJob.discovered_at < expire_before),
        )))
        await db.commit()
        return {"expired": len(live), "rejections_purged": purged.rowcount or 0}
