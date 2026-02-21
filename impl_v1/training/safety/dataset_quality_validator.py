"""
dataset_quality_validator.py — Deep Data Quality Enforcement

Checks:
  1. Label distribution (class balance)
  2. Class imbalance ratio
  3. Entropy score
  4. Duplicate ratio
  5. Random noise detection (feature variance analysis)

Blocks training if quality score < threshold.
"""

import logging
import os
from dataclasses import dataclass
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)

QUALITY_THRESHOLD = 0.6  # Minimum acceptable quality score


@dataclass
class DataQualityReport:
    """Dataset quality analysis report."""
    label_entropy: float
    class_imbalance_ratio: float    # max_class / min_class
    duplicate_ratio: float           # Fraction of duplicate rows
    noise_score: float               # 0=clean, 1=pure noise
    feature_variance_mean: float
    feature_variance_std: float
    quality_score: float             # 0-1 composite score
    passed: bool
    block_reason: str


def validate_data_quality(
    features: np.ndarray,
    labels: np.ndarray,
    threshold: float = QUALITY_THRESHOLD,
) -> DataQualityReport:
    """Run full data quality validation.

    Args:
        features: Feature matrix (N x D).
        labels: Label vector (N,).
        threshold: Minimum quality score to pass.

    Returns:
        DataQualityReport.
    """
    N, D = features.shape

    # 1. Label entropy
    unique, counts = np.unique(labels, return_counts=True)
    probs = counts / counts.sum()
    max_entropy = np.log2(max(len(unique), 2))
    entropy = -np.sum(probs * np.log2(probs + 1e-10))
    norm_entropy = entropy / max(max_entropy, 1e-10)

    # 2. Class imbalance
    imbalance = counts.max() / max(counts.min(), 1)

    # 3. Duplicate ratio
    _, unique_counts = np.unique(features, axis=0, return_counts=True)
    duplicates = np.sum(unique_counts[unique_counts > 1] - 1)
    dup_ratio = duplicates / max(N, 1)

    # 4. Noise score (high variance across features = potentially structured,
    #    very uniform variance across features with no structure = noise)
    feat_variances = np.var(features, axis=0)
    var_mean = np.mean(feat_variances)
    var_std = np.std(feat_variances)

    # If all features have identical variance → likely random noise
    var_cv = var_std / max(var_mean, 1e-10)  # Coefficient of variation
    noise_score = max(0, 1.0 - var_cv)  # Low CV → high noise

    # Check if values look like standard normal (common synthetic pattern)
    overall_mean = np.abs(np.mean(features))
    overall_std = np.std(features)
    looks_standard_normal = (overall_mean < 0.05 and abs(overall_std - 1.0) < 0.1)
    if looks_standard_normal:
        noise_score = max(noise_score, 0.7)

    # 5. Composite quality score
    entropy_score = min(norm_entropy, 1.0) * 0.3
    balance_score = min(1.0 / max(imbalance, 1), 1.0) * 0.2
    dup_score = (1.0 - dup_ratio) * 0.2
    noise_penalty = (1.0 - noise_score) * 0.3

    quality = entropy_score + balance_score + dup_score + noise_penalty

    # Block decision
    passed = quality >= threshold
    block_reason = ""
    if not passed:
        reasons = []
        if norm_entropy < 0.5:
            reasons.append(f"low entropy ({norm_entropy:.3f})")
        if imbalance > 10:
            reasons.append(f"class imbalance ({imbalance:.1f}x)")
        if dup_ratio > 0.1:
            reasons.append(f"high duplicates ({dup_ratio:.1%})")
        if noise_score > 0.7:
            reasons.append(f"noise detected ({noise_score:.3f})")
        block_reason = "; ".join(reasons) if reasons else f"quality={quality:.3f} < {threshold}"

        logger.error(f"[QUALITY] BLOCKED: {block_reason}")
    else:
        logger.info(
            f"[QUALITY] PASSED: score={quality:.3f}, "
            f"entropy={norm_entropy:.3f}, imbalance={imbalance:.1f}x, "
            f"dups={dup_ratio:.1%}, noise={noise_score:.3f}"
        )

    return DataQualityReport(
        label_entropy=float(entropy),
        class_imbalance_ratio=float(imbalance),
        duplicate_ratio=float(dup_ratio),
        noise_score=float(noise_score),
        feature_variance_mean=float(var_mean),
        feature_variance_std=float(var_std),
        quality_score=float(quality),
        passed=passed,
        block_reason=block_reason,
    )
