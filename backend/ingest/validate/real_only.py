from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping

from backend.ingest.dedup.fingerprint import near_duplicate_score
from backend.ingest.normalize.canonicalize import CanonicalRecord

_BLOCKED_SOURCE_TYPES = {"synthetic", "mock", "dummy", "test_only", "placeholder"}


class ValidationAction(str, Enum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    QUARANTINE = "QUARANTINE"


@dataclass
class ValidationDecision:
    action: str
    reasons: list[str] = field(default_factory=list)
    near_duplicate_score: float = 0.0


def validate_real_only(
    record: CanonicalRecord,
    *,
    exact_hash_index: Mapping[str, str] | set[str],
    near_duplicates: Iterable[CanonicalRecord] = (),
    quarantine_threshold: float = 0.9,
) -> ValidationDecision:
    reasons: list[str] = []
    source_type = record.source_type.strip().lower()
    if not record.provenance:
        reasons.append("missing_provenance")
    if not record.content_sha256:
        reasons.append("missing_content_sha256")
    if not record.source_id and not record.source_url:
        reasons.append("missing_immutable_source_id_or_url")
    if source_type in _BLOCKED_SOURCE_TYPES:
        reasons.append(f"blocked_source_type:{source_type}")
    exact_hashes = (
        set(exact_hash_index.keys())
        if isinstance(exact_hash_index, Mapping)
        else set(exact_hash_index)
    )
    if record.content_sha256 and record.content_sha256 in exact_hashes:
        reasons.append("duplicate_exact_hash")
    if reasons:
        return ValidationDecision(action=ValidationAction.REJECT.value, reasons=reasons)

    best_score = 0.0
    for candidate in near_duplicates:
        score = near_duplicate_score(record.normalized_text, candidate.normalized_text)
        if score > best_score:
            best_score = score
    if best_score >= quarantine_threshold:
        return ValidationDecision(
            action=ValidationAction.QUARANTINE.value,
            reasons=["high_near_duplicate_score"],
            near_duplicate_score=best_score,
        )
    return ValidationDecision(action=ValidationAction.ACCEPT.value)
