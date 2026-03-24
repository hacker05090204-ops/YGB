"""Verified dataset ingestion for accuracy-first training.

Only validated findings are accepted for supervised learning. Unverified or noisy
records are rejected before they reach the training pipeline.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from impl_v1.training.evaluation.accuracy_metrics import normalize_text, token_set


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VERIFIED_RECORD_PATH = REPO_ROOT / "reports" / "verified_findings.jsonl"


@dataclass(frozen=True, slots=True)
class VerifiedFindingRecord:
    """Single validated finding outcome used for supervised learning."""

    fingerprint: str
    category: str
    severity: str
    title: str
    description: str
    url: str
    actual_positive: bool
    verification_status: str
    duplicate: bool = False
    validation_source: str = "verification-layer"
    confidence: float = 0.0
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


def verified_dataset_paths(paths: Optional[Iterable[str | Path]] = None) -> list[Path]:
    if paths is None:
        return [DEFAULT_VERIFIED_RECORD_PATH]
    resolved: list[Path] = []
    for item in paths:
        path = Path(item)
        resolved.append(path if path.is_absolute() else (REPO_ROOT / path))
    return resolved


def _stable_split(fingerprint: str, holdout_fraction: float) -> bool:
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) / 0xFFFFFFFF
    return bucket < holdout_fraction


def _record_is_validated(payload: dict[str, Any]) -> bool:
    if bool(payload.get("validated")):
        return True
    status = str(payload.get("verification_status", "")).upper()
    proof_status = str(payload.get("proof_status", "")).upper()
    if proof_status in {"REAL", "NOT_REAL"}:
        return True
    if status in {"CONFIRMED", "REJECTED_FALSE_POSITIVE", "NOT_REAL", "DUPLICATE"}:
        evidence = payload.get("evidence") or {}
        if not isinstance(evidence, dict):
            evidence = {}
        return bool(
            evidence.get("response_validated")
            or evidence.get("exploit_confirmed")
            or evidence.get("verification_failed")
            or evidence.get("proof_verified")
            or payload.get("duplicate")
        )
    return False


def _record_actual_positive(payload: dict[str, Any]) -> Optional[bool]:
    if "actual_positive" in payload:
        return bool(payload.get("actual_positive"))
    status = str(payload.get("verification_status", "")).upper()
    proof_status = str(payload.get("proof_status", "")).upper()
    if proof_status == "REAL" or status == "CONFIRMED":
        return True
    if (
        status in {"REJECTED_FALSE_POSITIVE", "NOT_REAL", "DUPLICATE"}
        or proof_status == "NOT_REAL"
    ):
        return False
    return None


def load_verified_records(
    paths: Optional[Iterable[str | Path]] = None,
) -> list[VerifiedFindingRecord]:
    records: list[VerifiedFindingRecord] = []
    seen: set[str] = set()
    for path in verified_dataset_paths(paths):
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(payload, dict) or not _record_is_validated(payload):
                    continue
                actual_positive = _record_actual_positive(payload)
                fingerprint = str(payload.get("fingerprint") or "").strip()
                if actual_positive is None or not fingerprint or fingerprint in seen:
                    continue
                evidence = payload.get("evidence") or {}
                if not isinstance(evidence, dict):
                    evidence = {}
                record = VerifiedFindingRecord(
                    fingerprint=fingerprint,
                    category=str(payload.get("category") or "UNKNOWN"),
                    severity=str(payload.get("severity") or "INFO"),
                    title=str(payload.get("title") or ""),
                    description=str(payload.get("description") or ""),
                    url=str(payload.get("url") or ""),
                    actual_positive=actual_positive,
                    verification_status=str(
                        payload.get("verification_status") or "UNVERIFIED"
                    ),
                    duplicate=bool(payload.get("duplicate")),
                    validation_source=str(
                        payload.get("validation_source") or "verification-layer"
                    ),
                    confidence=float(payload.get("confidence") or 0.0),
                    evidence=evidence,
                    created_at=str(payload.get("created_at") or ""),
                )
                records.append(record)
                seen.add(fingerprint)
    records.sort(key=lambda item: item.created_at)
    return records


def encode_verified_record(
    record: VerifiedFindingRecord, feature_dim: int = 256
) -> list[float]:
    """Encode validated record content into a deterministic dense vector."""
    vector = [0.0] * feature_dim
    severity_scale = {
        "CRITICAL": 1.0,
        "HIGH": 0.8,
        "MEDIUM": 0.6,
        "LOW": 0.4,
        "INFO": 0.2,
    }
    vector[0] = severity_scale.get(record.severity.upper(), 0.1)
    vector[1] = min(len(normalize_text(record.title)) / 120.0, 1.0)
    vector[2] = min(len(normalize_text(record.description)) / 500.0, 1.0)
    vector[3] = 1.0 if record.duplicate else 0.0
    vector[4] = min(max(record.confidence, 0.0), 1.0)
    vector[5] = 1.0 if "http" in record.url.lower() else 0.0
    vector[6] = 1.0 if record.evidence.get("payload_tested") else 0.0
    vector[7] = min(len(record.evidence.get("sql_errors") or []) / 5.0, 1.0)
    vector[8] = min(len(record.evidence.get("reflected_parameters") or []) / 5.0, 1.0)
    vector[9] = 1.0 if record.evidence.get("needs_manual_review") else 0.0

    tokens = []
    tokens.extend(token_set(record.category))
    tokens.extend(token_set(record.severity))
    tokens.extend(token_set(record.title))
    tokens.extend(token_set(record.description))
    tokens.extend(token_set(record.url))
    tokens.extend(sorted(token_set(" ".join(sorted(record.evidence.keys())))))
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = 10 + (int.from_bytes(digest[:2], "big") % max(feature_dim - 10, 1))
        sign = 1.0 if digest[2] % 2 == 0 else -1.0
        vector[index] += sign * 0.1

    magnitude = max(sum(value * value for value in vector) ** 0.5, 1.0)
    return [value / magnitude for value in vector]


def split_verified_records(
    records: Iterable[VerifiedFindingRecord],
    holdout_fraction: float = 0.2,
) -> tuple[list[VerifiedFindingRecord], list[VerifiedFindingRecord]]:
    train: list[VerifiedFindingRecord] = []
    holdout: list[VerifiedFindingRecord] = []
    for record in records:
        if _stable_split(record.fingerprint, holdout_fraction):
            holdout.append(record)
        else:
            train.append(record)
    return train, holdout


def verified_dataset_statistics(
    records: Iterable[VerifiedFindingRecord],
) -> dict[str, Any]:
    items = list(records)
    positives = sum(1 for record in items if record.actual_positive)
    duplicates = sum(1 for record in items if record.duplicate)
    return {
        "total": len(items),
        "positive": positives,
        "negative": len(items) - positives,
        "duplicates": duplicates,
        "sources": sorted({record.validation_source for record in items}),
    }
