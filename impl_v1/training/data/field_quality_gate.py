"""
Field Quality Gate — Per-field sample count and quality enforcement.

HARD GATES:
  - Minimum 125,000 samples per field for LAB profile
  - Minimum 125,000 samples per field for REAL profile
  - Promotion/freeze BLOCKED if any field is below threshold

QUALITY CHECKS (per field):
  - Class balance ratio (reject if outside [0.3, 0.7])
  - Shannon entropy (reject if < 0.5 bits)
  - Hash consistency (reject if duplicates > 5%)
  - Forbidden field check (reject if any forbidden fields present)
  - Source trust (reject if avg trust < 0.5)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import math
import hashlib
import logging

logger = logging.getLogger(__name__)

# =============================================================================
# CONSTANTS
# =============================================================================

MIN_SAMPLES_PER_FIELD_LAB = 125_000
MIN_SAMPLES_PER_FIELD_REAL = 125_000

FORBIDDEN_FIELDS = frozenset([
    "valid", "accepted", "rejected", "severity",
    "platform_decision", "decision", "outcome", "verified",
])

CLASS_BALANCE_MIN = 0.30
CLASS_BALANCE_MAX = 0.70
ENTROPY_MIN_BITS = 0.5
DUPLICATE_HASH_MAX_RATIO = 0.05
SOURCE_TRUST_MIN = 0.5


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass(frozen=True)
class FieldQualityResult:
    """Quality check result for a single field."""
    field_name: str
    sample_count: int
    meets_minimum: bool
    class_balance_ratio: float
    entropy_bits: float
    duplicate_ratio: float
    has_forbidden_fields: bool
    source_trust_avg: float
    passed: bool
    rejection_reasons: Tuple[str, ...]


@dataclass(frozen=True)
class GateResult:
    """Aggregate result of the field quality gate."""
    profile: str  # "LAB" or "REAL"
    all_passed: bool
    total_fields: int
    passed_fields: int
    failed_fields: int
    field_results: Tuple[FieldQualityResult, ...]
    blocking_reasons: Tuple[str, ...]


# =============================================================================
# QUALITY CHECKS
# =============================================================================

def _check_class_balance(labels: List[int]) -> Tuple[float, bool, str]:
    """Check class balance ratio. Returns (ratio, passed, reason)."""
    if not labels:
        return 0.0, False, "No labels to check"
    positive = sum(1 for l in labels if l == 1)
    ratio = positive / len(labels)
    passed = CLASS_BALANCE_MIN <= ratio <= CLASS_BALANCE_MAX
    reason = "" if passed else f"Class balance {ratio:.3f} outside [{CLASS_BALANCE_MIN}, {CLASS_BALANCE_MAX}]"
    return ratio, passed, reason


def _check_entropy(labels: List[int]) -> Tuple[float, bool, str]:
    """Check Shannon entropy. Returns (entropy_bits, passed, reason)."""
    if not labels:
        return 0.0, False, "No labels for entropy"
    counts: Dict[int, int] = {}
    for l in labels:
        counts[l] = counts.get(l, 0) + 1
    total = len(labels)
    entropy = 0.0
    for count in counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)
    passed = entropy >= ENTROPY_MIN_BITS
    reason = "" if passed else f"Entropy {entropy:.4f} bits < minimum {ENTROPY_MIN_BITS}"
    return entropy, passed, reason


def _check_hash_consistency(feature_hashes: List[str]) -> Tuple[float, bool, str]:
    """Check for duplicate samples via hash. Returns (dup_ratio, passed, reason)."""
    if not feature_hashes:
        return 0.0, True, ""
    unique = len(set(feature_hashes))
    total = len(feature_hashes)
    dup_ratio = 1.0 - (unique / total) if total > 0 else 0.0
    passed = dup_ratio <= DUPLICATE_HASH_MAX_RATIO
    reason = "" if passed else f"Duplicate ratio {dup_ratio:.4f} > max {DUPLICATE_HASH_MAX_RATIO}"
    return dup_ratio, passed, reason


def _check_forbidden_fields(field_names: List[str]) -> Tuple[bool, str]:
    """Check for forbidden fields. Returns (has_forbidden, reason)."""
    found = [f for f in field_names if f.lower() in FORBIDDEN_FIELDS]
    if found:
        return True, f"Forbidden fields found: {', '.join(found)}"
    return False, ""


def _check_source_trust(trust_scores: List[float]) -> Tuple[float, bool, str]:
    """Check average source trust. Returns (avg_trust, passed, reason)."""
    if not trust_scores:
        return 0.0, False, "No trust scores available"
    avg = sum(trust_scores) / len(trust_scores)
    passed = avg >= SOURCE_TRUST_MIN
    reason = "" if passed else f"Avg source trust {avg:.4f} < minimum {SOURCE_TRUST_MIN}"
    return avg, passed, reason


def compute_feature_hash(features: List[float]) -> str:
    """Compute SHA-256 hash of a feature vector for dedup checking."""
    content = ",".join(f"{v:.6f}" for v in features)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


# =============================================================================
# PER-FIELD VALIDATION
# =============================================================================

def validate_field(
    field_name: str,
    sample_count: int,
    labels: List[int],
    feature_hashes: List[str],
    field_names_in_data: List[str],
    trust_scores: List[float],
    min_samples: int = MIN_SAMPLES_PER_FIELD_LAB,
) -> FieldQualityResult:
    """
    Validate a single field against all quality checks.

    Returns FieldQualityResult with pass/fail and reasons.
    """
    reasons: List[str] = []

    # 1. Minimum sample count
    meets_minimum = sample_count >= min_samples
    if not meets_minimum:
        reasons.append(f"Sample count {sample_count} < minimum {min_samples}")

    # 2. Class balance
    balance_ratio, balance_ok, balance_reason = _check_class_balance(labels)
    if not balance_ok:
        reasons.append(balance_reason)

    # 3. Entropy
    entropy, entropy_ok, entropy_reason = _check_entropy(labels)
    if not entropy_ok:
        reasons.append(entropy_reason)

    # 4. Hash consistency
    dup_ratio, hash_ok, hash_reason = _check_hash_consistency(feature_hashes)
    if not hash_ok:
        reasons.append(hash_reason)

    # 5. Forbidden fields
    has_forbidden, forbidden_reason = _check_forbidden_fields(field_names_in_data)
    if has_forbidden:
        reasons.append(forbidden_reason)

    # 6. Source trust
    trust_avg, trust_ok, trust_reason = _check_source_trust(trust_scores)
    if not trust_ok:
        reasons.append(trust_reason)

    passed = meets_minimum and balance_ok and entropy_ok and hash_ok and not has_forbidden and trust_ok

    return FieldQualityResult(
        field_name=field_name,
        sample_count=sample_count,
        meets_minimum=meets_minimum,
        class_balance_ratio=balance_ratio,
        entropy_bits=entropy,
        duplicate_ratio=dup_ratio,
        has_forbidden_fields=has_forbidden,
        source_trust_avg=trust_avg,
        passed=passed,
        rejection_reasons=tuple(reasons),
    )


# =============================================================================
# AGGREGATE GATE
# =============================================================================

def validate_all_fields(
    lab_counts: Dict[str, int],
    real_counts: Dict[str, int],
    min_per_field: int = MIN_SAMPLES_PER_FIELD_LAB,
) -> Tuple[bool, Dict[str, object]]:
    """
    Validate that ALL fields meet minimum sample count in BOTH profiles.

    Args:
        lab_counts: {field_name: sample_count} for LAB profile
        real_counts: {field_name: sample_count} for REAL profile
        min_per_field: minimum samples per field (default 125,000)

    Returns:
        (all_passed, details_dict)
    """
    blocking: List[str] = []

    for field_name, count in lab_counts.items():
        if count < min_per_field:
            blocking.append(
                f"LAB/{field_name}: {count} < {min_per_field}"
            )

    for field_name, count in real_counts.items():
        if count < min_per_field:
            blocking.append(
                f"REAL/{field_name}: {count} < {min_per_field}"
            )

    all_passed = len(blocking) == 0

    return all_passed, {
        "all_passed": all_passed,
        "lab_fields": len(lab_counts),
        "real_fields": len(real_counts),
        "blocking_reasons": blocking,
        "min_per_field": min_per_field,
        "lab_counts": dict(lab_counts),
        "real_counts": dict(real_counts),
    }


def block_promotion_if_insufficient(
    profile: str,
    field_counts: Dict[str, int],
    min_per_field: int = MIN_SAMPLES_PER_FIELD_LAB,
) -> None:
    """
    Raise RuntimeError if ANY field in the given profile has fewer
    than min_per_field samples. Used to hard-block promotion/freeze.

    Args:
        profile: "LAB" or "REAL"
        field_counts: {field_name: sample_count}
        min_per_field: minimum required

    Raises:
        RuntimeError with detailed message listing all failing fields.
    """
    failures = []
    for field_name, count in field_counts.items():
        if count < min_per_field:
            failures.append(f"  {field_name}: {count}/{min_per_field}")

    if failures:
        detail = "\n".join(failures)
        raise RuntimeError(
            f"PROMOTION BLOCKED — {profile} profile has fields below "
            f"{min_per_field} sample minimum:\n{detail}\n"
            f"Training cannot proceed. Collect more data."
        )


def generate_quality_report(
    lab_field_results: List[FieldQualityResult],
    real_field_results: List[FieldQualityResult],
) -> Dict:
    """
    Generate machine-readable quality report for all fields.

    Returns dict with per-field LAB/REAL sample counts, quality metrics,
    and overall pass/fail status.
    """
    lab_all_pass = all(r.passed for r in lab_field_results)
    real_all_pass = all(r.passed for r in real_field_results)

    return {
        "overall_passed": lab_all_pass and real_all_pass,
        "lab_passed": lab_all_pass,
        "real_passed": real_all_pass,
        "lab_fields": [
            {
                "field": r.field_name,
                "count": r.sample_count,
                "meets_min": r.meets_minimum,
                "balance": round(r.class_balance_ratio, 4),
                "entropy": round(r.entropy_bits, 4),
                "dup_ratio": round(r.duplicate_ratio, 4),
                "trust": round(r.source_trust_avg, 4),
                "passed": r.passed,
                "reasons": list(r.rejection_reasons),
            }
            for r in lab_field_results
        ],
        "real_fields": [
            {
                "field": r.field_name,
                "count": r.sample_count,
                "meets_min": r.meets_minimum,
                "balance": round(r.class_balance_ratio, 4),
                "entropy": round(r.entropy_bits, 4),
                "dup_ratio": round(r.duplicate_ratio, 4),
                "trust": round(r.source_trust_avg, 4),
                "passed": r.passed,
                "reasons": list(r.rejection_reasons),
            }
            for r in real_field_results
        ],
        "min_per_field_lab": MIN_SAMPLES_PER_FIELD_LAB,
        "min_per_field_real": MIN_SAMPLES_PER_FIELD_REAL,
    }
