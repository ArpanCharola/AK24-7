"""Pure ingestion contracts for the shared job warehouse."""

from app.aggregation.quality import (
    BatchResult,
    CanonicalCandidate,
    Rejection,
    RejectionReason,
    SourceSighting,
    classify_rejection,
    deduplicate_batch,
    job_fingerprint,
    normalize_employer,
    normalize_job_url,
    normalize_title,
)

__all__ = [
    "BatchResult",
    "CanonicalCandidate",
    "Rejection",
    "RejectionReason",
    "SourceSighting",
    "classify_rejection",
    "deduplicate_batch",
    "job_fingerprint",
    "normalize_employer",
    "normalize_job_url",
    "normalize_title",
]
