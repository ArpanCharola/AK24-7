import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.aggregation.quality import (
    RejectionReason,
    classify_rejection,
    deduplicate_batch,
    normalize_employer,
    normalize_job_url,
    normalize_title,
)
from app.aggregation.sources import FunctionSourceAdapter, SourceRegistry, SourceRequest


NOW = datetime(2026, 7, 11, 6, tzinfo=timezone.utc)


def job(**overrides):
    value = {
        "title": "Senior Software Engineer",
        "company": "Acme Technologies Pvt. Ltd.",
        "job_url": "https://jobs.acme.test/roles/42?utm_source=linkedin&job=42#apply",
        "location": "Bengaluru, India",
        "job_description": "Build Python services.",
        "posted_at": NOW - timedelta(days=1),
        "source": "linkedin",
    }
    value.update(overrides)
    return value


def test_normalization_preserves_identity_query_and_removes_tracking():
    assert normalize_job_url(job()["job_url"]) == "https://jobs.acme.test/roles/42?job=42"
    assert normalize_employer("Acme Technologies Pvt. Ltd.") == "acme"
    assert normalize_title("Hiring: Software Engineer Opening") == "software engineer"


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"company": "Talent Staffing Solutions"}, RejectionReason.STAFFING_OR_RECRUITMENT),
        ({"company": "LinkedIn"}, RejectionReason.JOB_BOARD_EMPLOYER),
        ({"posted_at": NOW - timedelta(days=8)}, RejectionReason.STALE),
        ({"location": "United States only"}, RejectionReason.FOREIGN_ONLY),
        ({"job_url": "javascript:alert(1)"}, RejectionReason.INVALID),
    ],
)
def test_reason_coded_rejections(change, reason):
    rejection = classify_rejection(job(**change), now=NOW)
    assert rejection and rejection.reason is reason


def test_batch_dedupe_retains_sightings_but_not_false_positive_roles():
    first = job()
    duplicate = job(source="naukri", job_url="https://jobs.acme.test/roles/42?job=42&utm_medium=cpc")
    separate = job(
        job_url="https://jobs.acme.test/roles/43?job=43",
        title="Principal Software Engineer",
        job_description="Lead distributed systems.",
    )
    result = deduplicate_batch([first, duplicate, separate], now=NOW)
    assert len(result.candidates) == 2
    assert [s.source for s in result.candidates[0].sightings] == ["linkedin", "naukri"]
    assert not result.rejections


def test_registry_isolates_source_failures():
    async def good(_request):
        return [job(source="")]

    async def bad(_request):
        raise RuntimeError("blocked")

    registry = SourceRegistry()
    registry.register(FunctionSourceAdapter("good", good))
    registry.register(FunctionSourceAdapter("bad", bad))
    jobs, errors = asyncio.run(registry.fetch_all(SourceRequest(("software engineer",))))
    assert jobs[0]["source"] == "good"
    assert errors == {"bad": "RuntimeError: blocked"}
