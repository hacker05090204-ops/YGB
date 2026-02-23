"""
label_consistency_validator.py — Label Consistency Validator (Phase 6)

██████████████████████████████████████████████████████████████████████
LABEL CONSISTENCY GATE — REJECT CONTAMINATED DATASETS
██████████████████████████████████████████████████████████████████████

Checks:
  1. Historical label distribution delta
  2. KL divergence threshold
  3. Duplicate hash clusters
  4. Cross-field contamination
  5. Sudden imbalance spike

If violation → Reject dataset. No fallback.
"""

import hashlib
import json
import logging
import math
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# THRESHOLDS
# =============================================================================

KL_DIVERGENCE_MAX = 0.50           # Max KL divergence from baseline
DISTRIBUTION_DELTA_MAX = 0.15      # Max per-class count change (%)
DUPLICATE_CLUSTER_MAX = 0.05       # Max 5% duplicate hash clusters
CONTAMINATION_THRESHOLD = 0.01     # Max 1% cross-field leakage
IMBALANCE_SPIKE_THRESHOLD = 0.25   # Max 25% sudden shift


# =============================================================================
# FORBIDDEN FIELDS — Must never appear in features
# =============================================================================

FORBIDDEN_FIELDS = {
    "valid", "accepted", "rejected", "severity",
    "platform_decision", "bounty_amount", "payout",
}


# =============================================================================
# DATA TYPES
# =============================================================================

@dataclass
class LabelValidationReport:
    """Result of label consistency validation."""
    passed: bool
    kl_divergence: float = 0.0
    distribution_delta: float = 0.0
    duplicate_cluster_ratio: float = 0.0
    contamination_score: float = 0.0
    imbalance_spike: float = 0.0
    violations: List[str] = field(default_factory=list)
    checks_run: int = 0
    checks_passed: int = 0


# =============================================================================
# VALIDATION FUNCTIONS
# =============================================================================

def _kl_divergence(p: np.ndarray, q: np.ndarray) -> float:
    """Compute KL divergence D_KL(P || Q)."""
    # Add epsilon to avoid log(0)
    eps = 1e-12
    p = np.clip(p, eps, 1.0)
    q = np.clip(q, eps, 1.0)
    # Normalize
    p = p / p.sum()
    q = q / q.sum()
    return float(np.sum(p * np.log(p / q)))


def _compute_distribution(labels: np.ndarray, n_classes: int) -> np.ndarray:
    """Compute label probability distribution."""
    counts = np.zeros(n_classes)
    for l in labels:
        if 0 <= l < n_classes:
            counts[l] += 1
    total = counts.sum()
    if total > 0:
        return counts / total
    return counts


def check_kl_divergence(
    current_labels: np.ndarray,
    baseline_labels: np.ndarray,
    n_classes: int,
) -> Tuple[bool, float, str]:
    """Check KL divergence between current and baseline distributions."""
    p = _compute_distribution(current_labels, n_classes)
    q = _compute_distribution(baseline_labels, n_classes)
    kl = _kl_divergence(p, q)

    if kl > KL_DIVERGENCE_MAX:
        return False, kl, f"KL divergence {kl:.4f} > {KL_DIVERGENCE_MAX}"
    return True, kl, f"KL divergence {kl:.4f} OK"


def check_distribution_delta(
    current_labels: np.ndarray,
    baseline_labels: np.ndarray,
    n_classes: int,
) -> Tuple[bool, float, str]:
    """Check per-class distribution delta."""
    p = _compute_distribution(current_labels, n_classes)
    q = _compute_distribution(baseline_labels, n_classes)
    max_delta = float(np.max(np.abs(p - q)))

    if max_delta > DISTRIBUTION_DELTA_MAX:
        return False, max_delta, f"Distribution delta {max_delta:.4f} > {DISTRIBUTION_DELTA_MAX}"
    return True, max_delta, f"Distribution delta {max_delta:.4f} OK"


def check_duplicate_clusters(
    sample_hashes: List[str],
) -> Tuple[bool, float, str]:
    """Detect duplicate hash clusters."""
    if not sample_hashes:
        return True, 0.0, "No hashes to check"

    counter = Counter(sample_hashes)
    duplicates = sum(c - 1 for c in counter.values() if c > 1)
    ratio = duplicates / len(sample_hashes)

    if ratio > DUPLICATE_CLUSTER_MAX:
        return False, ratio, f"Duplicate cluster ratio {ratio:.4f} > {DUPLICATE_CLUSTER_MAX}"
    return True, ratio, f"Duplicate cluster ratio {ratio:.4f} OK"


def check_cross_field_contamination(
    feature_names: List[str],
) -> Tuple[bool, float, str]:
    """Check for forbidden field names in features."""
    if not feature_names:
        return True, 0.0, "No feature names to check"

    contaminated = [f for f in feature_names if f.lower() in FORBIDDEN_FIELDS]
    score = len(contaminated) / max(len(feature_names), 1)

    if contaminated:
        return False, score, f"Forbidden fields detected: {contaminated[:5]}"
    return True, 0.0, "No cross-field contamination"


def check_imbalance_spike(
    current_labels: np.ndarray,
    n_classes: int,
) -> Tuple[bool, float, str]:
    """Detect sudden class imbalance spike."""
    dist = _compute_distribution(current_labels, n_classes)
    uniform = 1.0 / n_classes

    max_deviation = float(np.max(np.abs(dist - uniform)))

    if max_deviation > IMBALANCE_SPIKE_THRESHOLD:
        return False, max_deviation, f"Imbalance spike {max_deviation:.4f} > {IMBALANCE_SPIKE_THRESHOLD}"
    return True, max_deviation, f"Imbalance within bounds: {max_deviation:.4f}"


# =============================================================================
# MAIN VALIDATOR
# =============================================================================

def validate_label_consistency(
    current_labels: np.ndarray,
    baseline_labels: Optional[np.ndarray],
    n_classes: int,
    sample_hashes: Optional[List[str]] = None,
    feature_names: Optional[List[str]] = None,
) -> LabelValidationReport:
    """
    Run all label consistency checks.

    Args:
        current_labels: Current dataset labels
        baseline_labels: Previous/baseline labels (None for first run)
        n_classes: Number of label classes
        sample_hashes: SHA-256 hashes of samples for duplicate detection
        feature_names: Feature column names for contamination check

    Returns:
        LabelValidationReport with pass/fail and details.
    """
    report = LabelValidationReport(passed=True)
    violations = []

    # Check 1: KL divergence (requires baseline)
    if baseline_labels is not None and len(baseline_labels) > 0:
        ok, kl, msg = check_kl_divergence(current_labels, baseline_labels, n_classes)
        report.kl_divergence = kl
        report.checks_run += 1
        if ok:
            report.checks_passed += 1
        else:
            violations.append(msg)
        logger.info(f"[LABEL_VALIDATOR] {msg}")

        # Check 2: Distribution delta
        ok, delta, msg = check_distribution_delta(current_labels, baseline_labels, n_classes)
        report.distribution_delta = delta
        report.checks_run += 1
        if ok:
            report.checks_passed += 1
        else:
            violations.append(msg)
        logger.info(f"[LABEL_VALIDATOR] {msg}")

    # Check 3: Duplicate hash clusters
    if sample_hashes:
        ok, ratio, msg = check_duplicate_clusters(sample_hashes)
        report.duplicate_cluster_ratio = ratio
        report.checks_run += 1
        if ok:
            report.checks_passed += 1
        else:
            violations.append(msg)
        logger.info(f"[LABEL_VALIDATOR] {msg}")

    # Check 4: Cross-field contamination
    if feature_names:
        ok, score, msg = check_cross_field_contamination(feature_names)
        report.contamination_score = score
        report.checks_run += 1
        if ok:
            report.checks_passed += 1
        else:
            violations.append(msg)
        logger.info(f"[LABEL_VALIDATOR] {msg}")

    # Check 5: Imbalance spike
    ok, spike, msg = check_imbalance_spike(current_labels, n_classes)
    report.imbalance_spike = spike
    report.checks_run += 1
    if ok:
        report.checks_passed += 1
    else:
        violations.append(msg)
    logger.info(f"[LABEL_VALIDATOR] {msg}")

    report.violations = violations
    report.passed = len(violations) == 0

    icon = "✓" if report.passed else "✗"
    logger.info(
        f"[LABEL_VALIDATOR] {icon} Result: "
        f"{report.checks_passed}/{report.checks_run} checks passed, "
        f"{len(violations)} violations"
    )

    return report
