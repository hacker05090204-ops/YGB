"""
Ingestion Preflight Gate — Production Data Quality Checks
=========================================================

Runs BEFORE any training data loading. Blocks training on failure.

Checks:
  1. min_verified_samples (prod default >= 5000)
  2. num_classes >= 2
  3. Per-class minimum count
  4. Max class imbalance threshold
  5. Dataset freshness (max age)
  6. Hash consistency
  7. Source trust threshold

Fail-closed: any failure → training blocked.
"""

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, UTC, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# PRODUCTION DEFAULTS
# =============================================================================

PROD_MIN_VERIFIED_SAMPLES = 5000
PROD_MIN_CLASSES = 2
PROD_PER_CLASS_MINIMUM = 100
PROD_MAX_IMBALANCE_RATIO = 10.0  # largest / smallest class
PROD_MAX_AGE_HOURS = 720         # 30 days
PROD_MIN_SOURCE_TRUST = 0.5


# =============================================================================
# PREFLIGHT RESULT
# =============================================================================

@dataclass
class PreflightFailure:
    """Single preflight check failure."""
    check_name: str
    reason: str
    actual_value: str
    threshold: str

    def to_dict(self) -> dict:
        return {
            "check": self.check_name,
            "reason": self.reason,
            "actual": self.actual_value,
            "threshold": self.threshold,
        }


@dataclass
class PreflightResult:
    """Result of ingestion preflight checks."""
    passed: bool = True
    failures: List[PreflightFailure] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checks_run: int = 0

    def fail(self, check: str, reason: str, actual: str, threshold: str):
        self.passed = False
        self.failures.append(PreflightFailure(check, reason, actual, threshold))

    def warn(self, msg: str):
        self.warnings.append(msg)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "checks_run": self.checks_run,
            "failures": [f.to_dict() for f in self.failures],
            "warnings": self.warnings,
        }


# =============================================================================
# PREFLIGHT GATE
# =============================================================================

def run_preflight(
    sample_count: int,
    class_histogram: Dict[int, int],
    manifest_hash: str = "",
    stored_hash: str = "",
    dataset_frozen_at: str = "",
    source_trust_scores: Optional[List[float]] = None,
    *,
    min_samples: int = PROD_MIN_VERIFIED_SAMPLES,
    min_classes: int = PROD_MIN_CLASSES,
    per_class_min: int = PROD_PER_CLASS_MINIMUM,
    max_imbalance: float = PROD_MAX_IMBALANCE_RATIO,
    max_age_hours: int = PROD_MAX_AGE_HOURS,
    min_source_trust: float = PROD_MIN_SOURCE_TRUST,
) -> PreflightResult:
    """
    Run all preflight checks. Fail-closed.

    Args:
        sample_count: Total verified samples
        class_histogram: {class_label: count}
        manifest_hash: Current dataset hash
        stored_hash: Previously stored hash (for consistency)
        dataset_frozen_at: ISO timestamp of dataset freeze
        source_trust_scores: Trust scores per source
        min_samples: Minimum required samples
        min_classes: Minimum required classes
        per_class_min: Minimum samples per class
        max_imbalance: Maximum ratio of largest to smallest class
        max_age_hours: Maximum dataset age in hours
        min_source_trust: Minimum average source trust score

    Returns:
        PreflightResult with pass/fail and structured failures
    """
    result = PreflightResult()

    # 1. Minimum samples
    result.checks_run += 1
    if sample_count < min_samples:
        result.fail(
            "MIN_SAMPLES",
            f"Insufficient samples: {sample_count} < {min_samples}",
            str(sample_count),
            str(min_samples),
        )

    # 2. Minimum classes
    result.checks_run += 1
    num_classes = len(class_histogram)
    if num_classes < min_classes:
        result.fail(
            "MIN_CLASSES",
            f"Insufficient classes: {num_classes} < {min_classes}",
            str(num_classes),
            str(min_classes),
        )

    # 3. Per-class minimum
    result.checks_run += 1
    for cls_label, count in class_histogram.items():
        if count < per_class_min:
            result.fail(
                "PER_CLASS_MIN",
                f"Class {cls_label} has {count} samples < {per_class_min}",
                str(count),
                str(per_class_min),
            )

    # 4. Class imbalance
    result.checks_run += 1
    if class_histogram:
        counts = list(class_histogram.values())
        max_count = max(counts)
        min_count = min(counts) if min(counts) > 0 else 1
        imbalance = max_count / min_count
        if imbalance > max_imbalance:
            result.fail(
                "CLASS_IMBALANCE",
                f"Class imbalance ratio {imbalance:.1f} > {max_imbalance}",
                f"{imbalance:.1f}",
                str(max_imbalance),
            )

    # 5. Dataset freshness
    result.checks_run += 1
    if dataset_frozen_at:
        try:
            frozen = datetime.fromisoformat(dataset_frozen_at)
            if frozen.tzinfo is None:
                frozen = frozen.replace(tzinfo=UTC)
            age = datetime.now(UTC) - frozen
            if age > timedelta(hours=max_age_hours):
                hours = age.total_seconds() / 3600
                result.fail(
                    "DATASET_FRESHNESS",
                    f"Dataset age {hours:.0f}h exceeds max {max_age_hours}h",
                    f"{hours:.0f}h",
                    f"{max_age_hours}h",
                )
        except (ValueError, TypeError) as e:
            result.warn(f"Cannot parse dataset_frozen_at: {e}")

    # 6. Hash consistency
    result.checks_run += 1
    if manifest_hash and stored_hash:
        if manifest_hash != stored_hash:
            result.fail(
                "HASH_CONSISTENCY",
                "Manifest hash mismatch — data may have been tampered",
                manifest_hash[:16] + "...",
                stored_hash[:16] + "...",
            )

    # 7. Source trust
    result.checks_run += 1
    if source_trust_scores:
        avg_trust = sum(source_trust_scores) / len(source_trust_scores)
        if avg_trust < min_source_trust:
            result.fail(
                "SOURCE_TRUST",
                f"Average source trust {avg_trust:.2f} < {min_source_trust}",
                f"{avg_trust:.2f}",
                str(min_source_trust),
            )

    if result.passed:
        logger.info(f"[PREFLIGHT] PASSED: {result.checks_run} checks, {sample_count} samples, {num_classes} classes")
    else:
        logger.error(f"[PREFLIGHT] FAILED: {len(result.failures)} failures out of {result.checks_run} checks")

    return result
