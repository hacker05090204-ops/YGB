"""
data_enforcement.py — Strict Useful Data Enforcement (Phase 2)

7-check pre-training gate:
1. Signed dataset manifest required
2. Manual owner approval flag
3. Label shuffle test must degrade accuracy
4. Baseline model must exceed minimum
5. Train/test hash overlap must be zero
6. Entropy threshold enforced
7. Duplicate ratio < threshold

If ANY check fails → ABORT TRAINING.
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class EnforcementCheck:
    """Single enforcement check result."""
    check_id: int
    name: str
    passed: bool
    detail: str
    severity: str = "BLOCK"


@dataclass
class EnforcementReport:
    """Full 7-check enforcement report."""
    passed: bool
    checks: List[EnforcementCheck]
    dataset_hash: str
    timestamp: str
    abort_reason: str = ""


def compute_dataset_hash(X: np.ndarray, y: np.ndarray) -> str:
    h = hashlib.sha256()
    h.update(X.tobytes())
    h.update(y.tobytes())
    return h.hexdigest()


def compute_entropy(y: np.ndarray) -> float:
    _, counts = np.unique(y, return_counts=True)
    probs = counts / counts.sum()
    return float(-np.sum(probs * np.log2(probs + 1e-12)))


def compute_duplicate_ratio(X: np.ndarray) -> float:
    """Fraction of duplicate rows."""
    hashes = set()
    dupes = 0
    for i in range(len(X)):
        h = hashlib.md5(X[i].tobytes()).hexdigest()
        if h in hashes:
            dupes += 1
        hashes.add(h)
    return dupes / max(len(X), 1)


def enforce_data_policy(
    X_train: np.ndarray,
    y_train: np.ndarray,
    manifest_signature: str = "",
    manifest_valid: bool = False,
    owner_approved: bool = False,
    X_test: Optional[np.ndarray] = None,
    num_classes: int = 2,
    input_dim: int = 256,
    min_baseline_accuracy: float = 0.55,
    min_entropy: float = 0.5,
    max_duplicate_ratio: float = 0.10,
    shuffle_tolerance: float = 0.10,
) -> EnforcementReport:
    """Run all 7 enforcement checks.

    Returns EnforcementReport. Training BLOCKED if any check fails.
    """
    checks = []
    dataset_hash = compute_dataset_hash(X_train, y_train)

    # CHECK 1: Signed manifest
    checks.append(EnforcementCheck(
        check_id=1, name="signed_manifest",
        passed=manifest_valid,
        detail="Valid" if manifest_valid else "Missing or invalid signature",
    ))

    # CHECK 2: Owner approval
    checks.append(EnforcementCheck(
        check_id=2, name="owner_approval",
        passed=owner_approved,
        detail="Approved" if owner_approved else "NOT approved by owner",
    ))

    # CHECK 3: Label shuffle test
    shuffle_passed = False
    shuffle_detail = ""
    original_acc = 0.0
    try:
        from impl_v1.training.distributed.dataset_sanity import (
            run_label_shuffle_test,
        )
        result = run_label_shuffle_test(
            X_train, y_train,
            input_dim=input_dim, num_classes=num_classes,
            batch_size=min(512, len(X_train)),
            tolerance=shuffle_tolerance,
        )
        shuffle_passed = result.passed
        original_acc = result.original_accuracy
        shuffle_detail = (
            f"orig_acc={result.original_accuracy:.4f} "
            f"shuffle_acc={result.shuffled_accuracy:.4f}"
        )
    except Exception as e:
        shuffle_detail = f"Error: {e}"

    checks.append(EnforcementCheck(
        check_id=3, name="label_shuffle_test",
        passed=shuffle_passed,
        detail=shuffle_detail,
    ))

    # CHECK 4: Baseline accuracy
    baseline_ok = original_acc >= min_baseline_accuracy
    checks.append(EnforcementCheck(
        check_id=4, name="baseline_accuracy",
        passed=baseline_ok,
        detail=(
            f"acc={original_acc:.4f} "
            f"{'≥' if baseline_ok else '<'} "
            f"min={min_baseline_accuracy:.4f}"
        ),
    ))

    # CHECK 5: Zero train/test overlap
    overlap_ok = True
    overlap_detail = "No test set provided"
    if X_test is not None:
        try:
            from impl_v1.training.distributed.dataset_sanity import (
                check_train_test_overlap,
            )
            overlap_result = check_train_test_overlap(X_train, X_test)
            overlap_ok = overlap_result.passed
            overlap_detail = (
                f"overlap={overlap_result.overlap_count} "
                f"(ratio={overlap_result.overlap_ratio:.4f})"
            )
        except Exception as e:
            overlap_detail = f"Error: {e}"
            overlap_ok = False

    checks.append(EnforcementCheck(
        check_id=5, name="zero_overlap",
        passed=overlap_ok,
        detail=overlap_detail,
    ))

    # CHECK 6: Entropy threshold
    entropy = compute_entropy(y_train)
    entropy_ok = entropy >= min_entropy
    checks.append(EnforcementCheck(
        check_id=6, name="entropy_threshold",
        passed=entropy_ok,
        detail=(
            f"entropy={entropy:.4f} "
            f"{'≥' if entropy_ok else '<'} "
            f"min={min_entropy:.4f}"
        ),
    ))

    # CHECK 7: Duplicate ratio
    dup_ratio = compute_duplicate_ratio(X_train)
    dup_ok = dup_ratio <= max_duplicate_ratio
    checks.append(EnforcementCheck(
        check_id=7, name="duplicate_ratio",
        passed=dup_ok,
        detail=(
            f"ratio={dup_ratio:.4f} "
            f"{'≤' if dup_ok else '>'} "
            f"max={max_duplicate_ratio:.4f}"
        ),
    ))

    # Final verdict
    all_passed = all(c.passed for c in checks)
    abort_reason = ""
    if not all_passed:
        failed = [c.name for c in checks if not c.passed]
        abort_reason = f"TRAINING BLOCKED: failed checks = {failed}"

    report = EnforcementReport(
        passed=all_passed,
        checks=checks,
        dataset_hash=dataset_hash,
        timestamp=datetime.now().isoformat(),
        abort_reason=abort_reason,
    )

    if all_passed:
        logger.info("[DATA_ENFORCEMENT] ✓ All 7 checks passed")
    else:
        logger.error(f"[DATA_ENFORCEMENT] ✗ {abort_reason}")

    return report
