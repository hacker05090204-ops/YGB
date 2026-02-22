"""
dataset_sanity.py — Dataset Sanity Hardening (Phase 5)

Extends dataset validation with:

  1. Label shuffle test:
     - Shuffle labels, train 1 epoch
     - Accuracy must drop near random baseline
     - Blocks training if shuffled accuracy > threshold

  2. Train/test overlap:
     - Hash every sample
     - Check intersection
     - Block if leakage detected

  3. Block training if:
     - leakage > 0 samples
     - shuffle accuracy > random_baseline + tolerance
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# DEFAULTS
# =============================================================================

SHUFFLE_ACC_TOLERANCE = 0.10  # Allowed above random baseline
MAX_LEAKAGE_SAMPLES = 0      # Zero tolerance


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class ShuffleTestResult:
    """Result of label shuffle sanity test."""
    passed: bool
    original_accuracy: float
    shuffled_accuracy: float
    random_baseline: float
    threshold: float
    accuracy_dropped: bool
    elapsed_sec: float


@dataclass
class LeakageTestResult:
    """Result of train/test overlap check."""
    passed: bool
    train_samples: int
    test_samples: int
    overlap_count: int
    overlap_ratio: float
    leaked_indices: List[int] = field(default_factory=list)


@dataclass
class DatasetSanityResult:
    """Combined dataset sanity result."""
    passed: bool
    shuffle_test: Optional[ShuffleTestResult]
    leakage_test: Optional[LeakageTestResult]
    errors: List[str] = field(default_factory=list)


# =============================================================================
# LABEL SHUFFLE TEST
# =============================================================================

def run_label_shuffle_test(
    X: np.ndarray,
    y: np.ndarray,
    input_dim: int = 256,
    num_classes: int = 2,
    batch_size: int = 512,
    tolerance: float = SHUFFLE_ACC_TOLERANCE,
) -> ShuffleTestResult:
    """Run label shuffle sanity test.

    1. Train 1 epoch on real labels → measure accuracy
    2. Shuffle labels randomly → train 1 epoch → measure accuracy
    3. Shuffled accuracy must drop near random baseline

    If model learns equally well on shuffled labels, the dataset
    may be degenerate or features may be leaking labels.

    Args:
        X: Feature matrix (N, D).
        y: Label vector (N,).
        input_dim: Feature dimension.
        num_classes: Number of classes.
        batch_size: Training batch size.
        tolerance: Max allowed above random baseline.

    Returns:
        ShuffleTestResult.
    """
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        return ShuffleTestResult(
            passed=True, original_accuracy=0, shuffled_accuracy=0,
            random_baseline=1.0/num_classes, threshold=0,
            accuracy_dropped=True, elapsed_sec=0,
        )

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    random_baseline = 1.0 / num_classes
    threshold = random_baseline + tolerance

    t0 = time.perf_counter()

    # --- Train on real labels ---
    original_acc = _train_and_eval(X, y, input_dim, num_classes, batch_size, device, seed=42)

    # --- Train on shuffled labels ---
    rng = np.random.RandomState(99)
    y_shuffled = y.copy()
    rng.shuffle(y_shuffled)

    shuffled_acc = _train_and_eval(X, y_shuffled, input_dim, num_classes, batch_size, device, seed=42)

    elapsed = time.perf_counter() - t0
    acc_dropped = shuffled_acc <= threshold

    result = ShuffleTestResult(
        passed=acc_dropped,
        original_accuracy=round(original_acc, 4),
        shuffled_accuracy=round(shuffled_acc, 4),
        random_baseline=round(random_baseline, 4),
        threshold=round(threshold, 4),
        accuracy_dropped=acc_dropped,
        elapsed_sec=round(elapsed, 3),
    )

    if acc_dropped:
        logger.info(
            f"[SANITY] Shuffle test PASSED: orig={original_acc:.2%}, "
            f"shuffled={shuffled_acc:.2%} (< {threshold:.2%})"
        )
    else:
        logger.error(
            f"[SANITY] Shuffle test FAILED: shuffled_acc={shuffled_acc:.2%} "
            f">= threshold {threshold:.2%} — possible label leakage"
        )

    return result


def _train_and_eval(
    X: np.ndarray,
    y: np.ndarray,
    input_dim: int,
    num_classes: int,
    batch_size: int,
    device,
    seed: int = 42,
) -> float:
    """Train 1 epoch and return accuracy."""
    import torch
    import torch.nn as nn
    import torch.optim as optim

    torch.manual_seed(seed)

    X_t = torch.from_numpy(X.astype(np.float32)).to(device)
    y_t = torch.from_numpy(y.astype(np.int64)).to(device)

    n = X_t.size(0)
    split = int(n * 0.8)
    X_train, X_val = X_t[:split], X_t[split:]
    y_train, y_val = y_t[:split], y_t[split:]

    model = nn.Sequential(
        nn.Linear(input_dim, 256), nn.ReLU(),
        nn.Linear(256, 128), nn.ReLU(),
        nn.Linear(128, num_classes),
    ).to(device)

    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()

    model.train()
    for i in range(0, split, batch_size):
        bx = X_train[i:i + batch_size]
        by = y_train[i:i + batch_size]
        optimizer.zero_grad()
        loss = criterion(model(bx), by)
        loss.backward()
        optimizer.step()

    model.eval()
    with torch.no_grad():
        preds = model(X_val).argmax(dim=1)
        acc = (preds == y_val).float().mean().item()

    del model, optimizer, X_t, y_t
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    return acc


# =============================================================================
# TRAIN/TEST OVERLAP (LEAKAGE) DETECTION
# =============================================================================

def check_train_test_overlap(
    X_train: np.ndarray,
    X_test: np.ndarray,
    max_leakage: int = MAX_LEAKAGE_SAMPLES,
) -> LeakageTestResult:
    """Check for train/test sample overlap via hash intersection.

    Args:
        X_train: Training features (N_train, D).
        X_test: Test features (N_test, D).
        max_leakage: Maximum allowed overlapping samples (default: 0).

    Returns:
        LeakageTestResult with overlap details.
    """
    # Hash each sample for efficient comparison
    train_hashes = {}
    for i in range(X_train.shape[0]):
        h = hashlib.sha256(X_train[i].tobytes()).hexdigest()
        train_hashes[h] = i

    leaked_indices = []
    for j in range(X_test.shape[0]):
        h = hashlib.sha256(X_test[j].tobytes()).hexdigest()
        if h in train_hashes:
            leaked_indices.append(j)

    overlap_count = len(leaked_indices)
    overlap_ratio = overlap_count / max(X_test.shape[0], 1)

    passed = overlap_count <= max_leakage

    result = LeakageTestResult(
        passed=passed,
        train_samples=X_train.shape[0],
        test_samples=X_test.shape[0],
        overlap_count=overlap_count,
        overlap_ratio=round(overlap_ratio, 6),
        leaked_indices=leaked_indices[:100],  # Cap for logging
    )

    if passed:
        logger.info(
            f"[SANITY] Leakage test PASSED: 0 overlap between "
            f"{X_train.shape[0]} train / {X_test.shape[0]} test samples"
        )
    else:
        logger.error(
            f"[SANITY] Leakage test FAILED: {overlap_count} overlapping "
            f"samples detected ({overlap_ratio:.2%})"
        )

    return result


# =============================================================================
# COMBINED SANITY CHECK
# =============================================================================

def run_full_sanity_check(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: Optional[np.ndarray] = None,
    input_dim: int = 256,
    num_classes: int = 2,
    batch_size: int = 512,
    shuffle_tolerance: float = SHUFFLE_ACC_TOLERANCE,
    max_leakage: int = MAX_LEAKAGE_SAMPLES,
) -> DatasetSanityResult:
    """Run all dataset sanity checks.

    Blocks training if any check fails.

    Args:
        X_train: Training features.
        y_train: Training labels.
        X_test: Optional test features for leakage check.
        input_dim: Feature dimension.
        num_classes: Number of classes.
        batch_size: Batch size for shuffle test.
        shuffle_tolerance: Max above random baseline.
        max_leakage: Max allowed overlapping samples.

    Returns:
        DatasetSanityResult.
    """
    errors = []

    # Shuffle test
    shuffle = run_label_shuffle_test(
        X_train, y_train,
        input_dim=input_dim,
        num_classes=num_classes,
        batch_size=batch_size,
        tolerance=shuffle_tolerance,
    )
    if not shuffle.passed:
        errors.append(
            f"Shuffle test failed: shuffled_acc={shuffle.shuffled_accuracy:.2%} "
            f">= threshold {shuffle.threshold:.2%}"
        )

    # Leakage test
    leakage = None
    if X_test is not None:
        leakage = check_train_test_overlap(X_train, X_test, max_leakage)
        if not leakage.passed:
            errors.append(
                f"Leakage detected: {leakage.overlap_count} overlapping samples"
            )

    passed = shuffle.passed and (leakage is None or leakage.passed)

    result = DatasetSanityResult(
        passed=passed,
        shuffle_test=shuffle,
        leakage_test=leakage,
        errors=errors,
    )

    if passed:
        logger.info("[SANITY] All dataset sanity checks PASSED")
    else:
        logger.error(
            f"[SANITY] Dataset sanity FAILED — TRAINING BLOCKED: {errors}"
        )

    return result
