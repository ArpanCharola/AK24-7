from datetime import datetime, timedelta, timezone

from app.services.warehouse_views import (
    canonical_dedupe_key,
    canonical_rank,
    explanation_from_codes,
    public_job_quality_score,
    strict_location_match,
)


NOW = datetime(2026, 7, 14, 12, tzinfo=timezone.utc)


def test_explanation_from_codes_humanizes_backend_flags():
    reason, explanation = explanation_from_codes([
        "role_match",
        "skill_overlap",
        "location_match",
        "fresh_posting",
    ])

    assert reason == "role match"
    assert explanation == "role match, skill overlap, location match, fresh posting"


def test_strict_location_match_allows_remote_india_but_rejects_wrong_onsite_city():
    assert strict_location_match(
        location="Remote India",
        preferred_locations=["Pune"],
        work_arrangement="remote",
    )
    assert not strict_location_match(
        location="Bengaluru, Karnataka, India",
        preferred_locations=["Pune"],
        work_arrangement="onsite",
    )


def test_public_job_quality_score_prefers_recent_direct_fresher_jobs():
    direct_recent = public_job_quality_score(
        title="Graduate Software Engineer",
        source="greenhouse",
        posted_at=NOW - timedelta(hours=8),
        now=NOW,
        role="Software Engineer",
        experience_filter="fresher",
    )
    stale_aggregator = public_job_quality_score(
        title="Senior Software Engineer",
        source="linkedin",
        posted_at=NOW - timedelta(days=6),
        now=NOW,
        role="Software Engineer",
        experience_filter="fresher",
    )

    assert direct_recent > stale_aggregator


def test_canonical_dedupe_key_and_rank_are_stable_for_warehouse_rows():
    key = canonical_dedupe_key(
        company="Acme Technologies Pvt. Ltd.",
        title="Software Engineer",
        location="Pune, India",
        fallback_url="https://jobs.acme.test/42",
    )

    assert key == ("acme technologies pvt ltd", "software engineer", "pune india")
    assert canonical_rank(82, NOW - timedelta(days=1), NOW) > canonical_rank(70, NOW - timedelta(days=1), NOW)
