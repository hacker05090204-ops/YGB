"""
dataset_validator.py — Dataset Integrity Validation for DDP Nodes

Before any node participates in distributed training, it must prove
that its local dataset shard is identical to the authority-verified copy.

Checks:
  1. SHA-256 dataset hash match
  2. Sample count match
  3. Feature dimension match
  4. Label distribution within tolerance (max deviation)
  5. Shannon entropy of labels above threshold
"""

import hashlib
import logging
import math
from collections import Counter
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# =============================================================================
# DEFAULTS
# =============================================================================

DEFAULT_LABEL_TOLERANCE = 0.05   # Max allowed deviation per class
DEFAULT_ENTROPY_THRESHOLD = 0.5  # Bits — reject near-degenerate sets


# =============================================================================
# RESULT
# =============================================================================

@dataclass
class DatasetValidationResult:
    """Result of dataset integrity checks."""
    valid: bool
    dataset_hash: str
    hash_match: bool
    sample_count: int
    sample_count_match: bool
    feature_dim: int
    feature_dim_match: bool
    label_distribution: Dict[int, float]
    label_dist_within_tolerance: bool
    label_entropy: float
    entropy_above_threshold: bool
    errors: List[str]


# =============================================================================
# HASH
# =============================================================================

def compute_dataset_hash(X: np.ndarray, y: np.ndarray) -> str:
    """Compute SHA-256 hash of feature matrix + labels."""
    h = hashlib.sha256()
    h.update(X.tobytes())
    h.update(y.tobytes())
    return h.hexdigest()


# =============================================================================
# LABEL STATISTICS
# =============================================================================

def _compute_label_distribution(y: np.ndarray) -> Dict[int, float]:
    """Compute normalized label frequency distribution."""
    counts = Counter(y.tolist())
    total = len(y)
    return {int(k): round(v / total, 6) for k, v in sorted(counts.items())}


def _compute_shannon_entropy(distribution: Dict[int, float]) -> float:
    """Compute Shannon entropy in bits."""
    entropy = 0.0
    for p in distribution.values():
        if p > 0:
            entropy -= p * math.log2(p)
    return round(entropy, 6)


def _check_label_tolerance(
    actual: Dict[int, float],
    expected: Dict[int, float],
    tolerance: float,
) -> Tuple[bool, List[str]]:
    """Check that every class proportion is within tolerance of expected."""
    errors = []
    all_classes = set(actual.keys()) | set(expected.keys())

    for cls in all_classes:
        a = actual.get(cls, 0.0)
        e = expected.get(cls, 0.0)
        dev = abs(a - e)
        if dev > tolerance:
            errors.append(
                f"Class {cls}: deviation {dev:.4f} > tolerance {tolerance}"
            )

    return len(errors) == 0, errors


# =============================================================================
# MAIN VALIDATOR
# =============================================================================

def validate_dataset(
    X: np.ndarray,
    y: np.ndarray,
    expected_hash: str,
    expected_sample_count: int,
    expected_feature_dim: int,
    expected_label_distribution: Optional[Dict[int, float]] = None,
    label_tolerance: float = DEFAULT_LABEL_TOLERANCE,
    entropy_threshold: float = DEFAULT_ENTROPY_THRESHOLD,
) -> DatasetValidationResult:
    """Run all dataset integrity checks.

    Args:
        X: Feature matrix (N, D).
        y: Label vector (N,).
        expected_hash: Authority-provided SHA-256 hash.
        expected_sample_count: Expected number of samples.
        expected_feature_dim: Expected feature dimension.
        expected_label_distribution: Expected per-class proportions.
        label_tolerance: Max allowed per-class deviation.
        entropy_threshold: Minimum required Shannon entropy (bits).

    Returns:
        DatasetValidationResult with pass/fail details.
    """
    errors: List[str] = []

    # 1. Hash
    actual_hash = compute_dataset_hash(X, y)
    hash_ok = actual_hash == expected_hash
    if not hash_ok:
        errors.append(
            f"Hash mismatch: expected {expected_hash[:16]}..., "
            f"got {actual_hash[:16]}..."
        )

    # 2. Sample count
    actual_count = X.shape[0]
    count_ok = actual_count == expected_sample_count
    if not count_ok:
        errors.append(
            f"Sample count: expected {expected_sample_count}, got {actual_count}"
        )

    # 3. Feature dim
    actual_dim = X.shape[1] if X.ndim >= 2 else 1
    dim_ok = actual_dim == expected_feature_dim
    if not dim_ok:
        errors.append(
            f"Feature dim: expected {expected_feature_dim}, got {actual_dim}"
        )

    # 4. Label distribution
    label_dist = _compute_label_distribution(y)
    if expected_label_distribution is not None:
        dist_ok, dist_errs = _check_label_tolerance(
            label_dist, expected_label_distribution, label_tolerance
        )
        errors.extend(dist_errs)
    else:
        dist_ok = True  # No expected dist provided — skip

    # 5. Entropy
    entropy = _compute_shannon_entropy(label_dist)
    entropy_ok = entropy > entropy_threshold
    if not entropy_ok:
        errors.append(
            f"Entropy {entropy:.4f} <= threshold {entropy_threshold}"
        )

    valid = hash_ok and count_ok and dim_ok and dist_ok and entropy_ok

    result = DatasetValidationResult(
        valid=valid,
        dataset_hash=actual_hash,
        hash_match=hash_ok,
        sample_count=actual_count,
        sample_count_match=count_ok,
        feature_dim=actual_dim,
        feature_dim_match=dim_ok,
        label_distribution=label_dist,
        label_dist_within_tolerance=dist_ok,
        label_entropy=entropy,
        entropy_above_threshold=entropy_ok,
        errors=errors,
    )

    if valid:
        logger.info(
            f"[DATASET] Validation PASSED — "
            f"{actual_count} samples, dim={actual_dim}, "
            f"entropy={entropy:.4f}, hash={actual_hash[:16]}..."
        )
    else:
        logger.error(
            f"[DATASET] Validation FAILED — {len(errors)} error(s):"
        )
        for e in errors:
            logger.error(f"  • {e}")

    return result
