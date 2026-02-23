"""
dataset_balance_controller.py — Dataset Balance Controller (Phase 1)

██████████████████████████████████████████████████████████████████████
BOUNTY-READY — CLASS BALANCE AND DISTRIBUTION CONTROL
██████████████████████████████████████████████████████████████████████

Governance layer enforcing:
  - Class distribution within acceptable bounds
  - Under-represented class upweighting
  - Over-represented class downsampling
  - No class may exceed 3x the minimum class count
  - Target: uniform ± configurable tolerance
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Balance thresholds
MAX_IMBALANCE_RATIO = 3.0   # No class can be > 3x smallest class
TARGET_UNIFORM_TOLERANCE = 0.20  # ±20% from uniform
MIN_CLASS_SAMPLES = 20      # Minimum samples per class


@dataclass
class BalanceReport:
    """Dataset balance analysis."""
    balanced: bool
    n_classes: int
    total_samples: int
    class_counts: Dict[int, int] = field(default_factory=dict)
    class_weights: Dict[int, float] = field(default_factory=dict)
    imbalance_ratio: float = 0.0
    max_deviation: float = 0.0
    undersampled_classes: List[int] = field(default_factory=list)
    oversampled_classes: List[int] = field(default_factory=list)
    action: str = ""  # "PASS", "REWEIGHT", "DOWNSAMPLE", "REJECT"


def analyze_balance(labels: np.ndarray, n_classes: int) -> BalanceReport:
    """
    Analyze class distribution and compute balance metrics.

    Args:
        labels: Array of integer class labels
        n_classes: Expected number of classes

    Returns:
        BalanceReport with analysis and recommended action.
    """
    report = BalanceReport(balanced=False, n_classes=n_classes, total_samples=len(labels))

    # Count per class
    for c in range(n_classes):
        report.class_counts[c] = int(np.sum(labels == c))

    counts = list(report.class_counts.values())
    min_count = min(counts) if counts else 0
    max_count = max(counts) if counts else 0

    # Imbalance ratio
    report.imbalance_ratio = max_count / max(min_count, 1)

    # Deviation from uniform
    expected = len(labels) / max(n_classes, 1)
    deviations = [abs(c - expected) / max(expected, 1) for c in counts]
    report.max_deviation = max(deviations) if deviations else 0

    # Identify under/over sampled
    for c in range(n_classes):
        if report.class_counts[c] < MIN_CLASS_SAMPLES:
            report.undersampled_classes.append(c)
        elif report.class_counts[c] > expected * (1 + TARGET_UNIFORM_TOLERANCE):
            report.oversampled_classes.append(c)

    # Compute class weights (inverse frequency)
    total = sum(counts)
    for c in range(n_classes):
        if report.class_counts[c] > 0:
            report.class_weights[c] = total / (n_classes * report.class_counts[c])
        else:
            report.class_weights[c] = 0.0

    # Determine action
    if report.undersampled_classes and any(
        report.class_counts[c] == 0 for c in report.undersampled_classes
    ):
        report.action = "REJECT"
        report.balanced = False
    elif report.imbalance_ratio > MAX_IMBALANCE_RATIO:
        report.action = "DOWNSAMPLE"
        report.balanced = False
    elif report.max_deviation > TARGET_UNIFORM_TOLERANCE:
        report.action = "REWEIGHT"
        report.balanced = False
    else:
        report.action = "PASS"
        report.balanced = True

    logger.info(
        f"[BALANCE] Classes={n_classes}, ratio={report.imbalance_ratio:.2f}, "
        f"deviation={report.max_deviation:.2f}, action={report.action}"
    )
    return report


def apply_balance(
    data: np.ndarray, labels: np.ndarray, report: BalanceReport
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Apply balancing action to dataset.

    Returns:
        (balanced_data, balanced_labels, sample_weights)
    """
    n = len(labels)
    weights = np.ones(n, dtype=np.float32)

    if report.action == "PASS":
        return data, labels, weights

    if report.action == "REJECT":
        raise ValueError(
            f"Dataset rejected: missing classes {report.undersampled_classes}"
        )

    if report.action == "REWEIGHT":
        # Apply inverse frequency weights
        for c, w in report.class_weights.items():
            mask = labels == c
            weights[mask] = w
        weights /= weights.mean()  # Normalize
        logger.info(f"[BALANCE] Applied reweighting: {len(report.class_weights)} classes")
        return data, labels, weights

    if report.action == "DOWNSAMPLE":
        # Downsample over-represented classes to match min viable count
        target_per_class = max(
            MIN_CLASS_SAMPLES,
            min(report.class_counts[c] for c in range(report.n_classes) if report.class_counts[c] > 0)
        )
        indices = []
        for c in range(report.n_classes):
            c_idx = np.where(labels == c)[0]
            if len(c_idx) > target_per_class:
                chosen = np.random.choice(c_idx, target_per_class, replace=False)
                indices.extend(chosen.tolist())
            else:
                indices.extend(c_idx.tolist())

        indices = sorted(indices)
        balanced_data = data[indices]
        balanced_labels = labels[indices]
        balanced_weights = np.ones(len(indices), dtype=np.float32)
        logger.info(
            f"[BALANCE] Downsampled: {n} → {len(indices)} "
            f"(target_per_class={target_per_class})"
        )
        return balanced_data, balanced_labels, balanced_weights

    return data, labels, weights
