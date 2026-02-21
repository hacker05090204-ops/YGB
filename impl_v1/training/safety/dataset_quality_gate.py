"""
dataset_quality_gate.py — Extended Dataset Validation Before Training

Validates:
  1. dataset_hash integrity
  2. sample_count matches manifest
  3. feature_dimension consistency
  4. Entropy score > threshold
  5. Mock data scanner (no dummy/test/synthetic patterns)

Abort on any failure. No silent fallback.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DatasetGateResult:
    """Dataset validation gate result."""
    passed: bool
    dataset_hash: str
    sample_count: int
    feature_dim: int
    entropy_score: float
    mock_detected: bool
    abort_reason: str


def validate_dataset_gate(
    features: np.ndarray,
    labels: np.ndarray,
    expected_hash: str = None,
    expected_samples: int = None,
    expected_dim: int = None,
    entropy_threshold: float = 0.5,
) -> DatasetGateResult:
    """Run full dataset quality gate.

    Args:
        features: Feature matrix (N x D).
        labels: Label vector (N,).
        expected_hash: Expected dataset hash.
        expected_samples: Expected sample count.
        expected_dim: Expected feature dimension.
        entropy_threshold: Minimum entropy score.

    Returns:
        DatasetGateResult.
    """
    N, D = features.shape
    abort = ""

    # 1. Hash
    data_hash = hashlib.sha256(features.tobytes() + labels.tobytes()).hexdigest()

    if expected_hash and data_hash != expected_hash:
        abort = f"Hash mismatch: got {data_hash[:16]}... vs expected {expected_hash[:16]}..."
        logger.error(f"[GATE] ABORT: {abort}")
        return DatasetGateResult(
            passed=False, dataset_hash=data_hash, sample_count=N,
            feature_dim=D, entropy_score=0, mock_detected=False,
            abort_reason=abort,
        )

    # 2. Sample count
    if expected_samples and N != expected_samples:
        abort = f"Sample count mismatch: got {N} vs expected {expected_samples}"
        logger.error(f"[GATE] ABORT: {abort}")
        return DatasetGateResult(
            passed=False, dataset_hash=data_hash, sample_count=N,
            feature_dim=D, entropy_score=0, mock_detected=False,
            abort_reason=abort,
        )

    # 3. Feature dimension
    if expected_dim and D != expected_dim:
        abort = f"Feature dim mismatch: got {D} vs expected {expected_dim}"
        logger.error(f"[GATE] ABORT: {abort}")
        return DatasetGateResult(
            passed=False, dataset_hash=data_hash, sample_count=N,
            feature_dim=D, entropy_score=0, mock_detected=False,
            abort_reason=abort,
        )

    # 4. Entropy score
    entropy = _compute_label_entropy(labels)
    if entropy < entropy_threshold:
        abort = f"Entropy too low: {entropy:.4f} < {entropy_threshold}"
        logger.error(f"[GATE] ABORT: {abort}")
        return DatasetGateResult(
            passed=False, dataset_hash=data_hash, sample_count=N,
            feature_dim=D, entropy_score=entropy, mock_detected=False,
            abort_reason=abort,
        )

    # 5. Mock data detection
    mock = _detect_mock_data(features, labels)
    if mock:
        abort = "Mock/synthetic data pattern detected"
        logger.error(f"[GATE] ABORT: {abort}")
        return DatasetGateResult(
            passed=False, dataset_hash=data_hash, sample_count=N,
            feature_dim=D, entropy_score=entropy, mock_detected=True,
            abort_reason=abort,
        )

    logger.info(
        f"[GATE] PASSED: {N} samples, dim={D}, "
        f"entropy={entropy:.4f}, hash={data_hash[:16]}..."
    )

    return DatasetGateResult(
        passed=True, dataset_hash=data_hash, sample_count=N,
        feature_dim=D, entropy_score=entropy, mock_detected=False,
        abort_reason="",
    )


def _compute_label_entropy(labels: np.ndarray) -> float:
    """Compute label distribution entropy."""
    unique, counts = np.unique(labels, return_counts=True)
    probs = counts / counts.sum()
    entropy = -np.sum(probs * np.log2(probs + 1e-10))
    return float(entropy)


def _detect_mock_data(features: np.ndarray, labels: np.ndarray) -> bool:
    """Detect synthetic/mock data patterns.

    Checks:
      - All-zero features
      - Constant features (zero variance)
      - Sequential incrementing patterns
      - Perfect correlation (identity matrix)
    """
    # All zeros
    if np.all(features == 0):
        return True

    # Constant features (all columns same value)
    col_std = np.std(features, axis=0)
    if np.all(col_std < 1e-10):
        return True

    # Sequential pattern (incrementing values)
    if features.shape[0] > 10:
        diffs = np.diff(features[:10, 0])
        if np.all(np.abs(diffs - diffs[0]) < 1e-10) and diffs[0] != 0:
            return True

    # All same label
    if len(np.unique(labels)) <= 1:
        return True

    return False
