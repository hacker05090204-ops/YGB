"""
sanity_gate.py — Pre-Training Sanity Gate (Phase 4)

Before real training begins:

1. Run label shuffle test
2. Persist result
3. Block launch if dataset is corrupted

Uses existing dataset_sanity.py for the actual shuffle test logic.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

SANITY_RESULT_PATH = os.path.join('secure_data', 'sanity_gate_result.json')


# =============================================================================
# TYPES
# =============================================================================

@dataclass
class SanityGateResult:
    """Persisted sanity gate result."""
    passed: bool
    shuffle_accuracy: float
    original_accuracy: float
    random_baseline: float
    threshold: float
    dataset_hash: str
    num_classes: int
    num_samples: int
    timestamp: str
    abort_reason: str = ""


# =============================================================================
# GATE
# =============================================================================

def run_sanity_gate(
    X_train: np.ndarray,
    y_train: np.ndarray,
    dataset_hash: str,
    num_classes: int = 2,
    input_dim: int = 256,
    batch_size: int = 512,
    tolerance: float = 0.10,
    result_path: str = SANITY_RESULT_PATH,
    X_test: Optional[np.ndarray] = None,
) -> SanityGateResult:
    """Run pre-training sanity gate.

    1. Label shuffle test
    2. Optional leakage test
    3. Persist result
    4. Return pass/fail

    Args:
        X_train: Training features.
        y_train: Training labels.
        dataset_hash: SHA-256 of the dataset.
        num_classes: Number of target classes.
        input_dim: Feature dimension.
        batch_size: Batch size for mini-training.
        tolerance: Max above random baseline.
        result_path: Where to save the result.
        X_test: Optional test features for leakage check.

    Returns:
        SanityGateResult.
    """
    from impl_v1.training.distributed.dataset_sanity import (
        run_label_shuffle_test,
        check_train_test_overlap,
    )

    random_baseline = 1.0 / num_classes
    threshold = random_baseline + tolerance

    # --- Shuffle test ---
    shuffle_result = run_label_shuffle_test(
        X_train, y_train,
        input_dim=input_dim,
        num_classes=num_classes,
        batch_size=batch_size,
        tolerance=tolerance,
    )

    abort_reason = ""
    passed = shuffle_result.passed

    if not passed:
        abort_reason = (
            f"Label shuffle test failed: shuffled_acc="
            f"{shuffle_result.shuffled_accuracy:.4f} >= "
            f"threshold {threshold:.4f}. Dataset may be corrupted."
        )
        logger.error(f"[SANITY_GATE] {abort_reason}")

    # --- Optional leakage test ---
    if X_test is not None and passed:
        leakage = check_train_test_overlap(X_train, X_test)
        if not leakage.passed:
            passed = False
            abort_reason = (
                f"Leakage detected: {leakage.overlap_count} samples "
                f"overlap between train and test"
            )
            logger.error(f"[SANITY_GATE] {abort_reason}")

    # --- Build result ---
    gate = SanityGateResult(
        passed=passed,
        shuffle_accuracy=round(shuffle_result.shuffled_accuracy, 6),
        original_accuracy=round(shuffle_result.original_accuracy, 6),
        random_baseline=round(random_baseline, 4),
        threshold=round(threshold, 4),
        dataset_hash=dataset_hash,
        num_classes=num_classes,
        num_samples=X_train.shape[0],
        timestamp=datetime.now().isoformat(),
        abort_reason=abort_reason,
    )

    # --- Persist ---
    _persist_result(gate, result_path)

    if passed:
        logger.info(
            f"[SANITY_GATE] PASSED: shuffle_acc={gate.shuffle_accuracy:.4f} "
            f"< threshold {gate.threshold:.4f}"
        )
    else:
        logger.error(f"[SANITY_GATE] BLOCKED: {abort_reason}")

    return gate


def _persist_result(result: SanityGateResult, path: str):
    """Persist sanity gate result atomically."""
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(asdict(result), f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def load_sanity_result(path: str = SANITY_RESULT_PATH) -> Optional[SanityGateResult]:
    """Load previous sanity gate result."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        return SanityGateResult(**data)
    except Exception as e:
        logger.error(f"[SANITY_GATE] Load failed: {e}")
        return None


def gate_allows_training(path: str = SANITY_RESULT_PATH) -> bool:
    """Quick check — does the saved sanity gate allow training?"""
    result = load_sanity_result(path)
    if result is None:
        logger.warning("[SANITY_GATE] No saved result — gate not run yet")
        return False
    return result.passed
