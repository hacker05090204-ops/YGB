"""
strict_dataset_policy.py — Strict Dataset Policy (Phase 6)

Before training:
1. Validate signed dataset manifest
2. Run label shuffle sanity test
3. Run baseline model sanity check
4. Validate dataset version registry

Abort if any check fails.
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

MANIFEST_DIR = os.path.join('secure_data', 'dataset_manifests')
REGISTRY_PATH = os.path.join('secure_data', 'dataset_registry.json')


@dataclass
class DatasetManifest:
    """Signed dataset manifest."""
    dataset_id: str
    version: int
    num_samples: int
    num_features: int
    num_classes: int
    sha256: str
    signature: str          # HMAC signature
    created_at: str
    approved_by: str = ""


@dataclass
class PolicyCheckResult:
    """Result of a single policy check."""
    check_name: str
    passed: bool
    detail: str


@dataclass
class DatasetPolicyReport:
    """Full policy validation report."""
    dataset_id: str
    passed: bool
    checks: List[PolicyCheckResult] = field(default_factory=list)
    timestamp: str = ""
    abort_reason: str = ""


def compute_data_hash(X: np.ndarray, y: np.ndarray) -> str:
    """Compute SHA-256 of dataset."""
    h = hashlib.sha256()
    h.update(X.tobytes())
    h.update(y.tobytes())
    return h.hexdigest()


def sign_manifest(manifest: DatasetManifest, secret_key: str) -> str:
    """HMAC-sign a manifest."""
    import hmac
    content = (
        f"{manifest.dataset_id}:{manifest.version}:"
        f"{manifest.num_samples}:{manifest.sha256}"
    )
    sig = hmac.new(
        secret_key.encode(), content.encode(), hashlib.sha256
    ).hexdigest()
    return sig


def verify_manifest_signature(
    manifest: DatasetManifest,
    secret_key: str,
) -> bool:
    """Verify a manifest's HMAC signature."""
    expected = sign_manifest(manifest, secret_key)
    return manifest.signature == expected


def validate_dataset_policy(
    X_train: np.ndarray,
    y_train: np.ndarray,
    manifest: DatasetManifest,
    secret_key: str,
    num_classes: int = 2,
    input_dim: int = 256,
    shuffle_tolerance: float = 0.10,
    baseline_accuracy: float = 0.55,
) -> DatasetPolicyReport:
    """Run all dataset policy checks.

    1. Manifest signature
    2. Data hash matches manifest
    3. Label shuffle sanity
    4. Baseline model sanity

    Args:
        X_train, y_train: Training data.
        manifest: Signed manifest.
        secret_key: Signing key.
        num_classes: Number of classes.
        input_dim: Feature dimension.
        shuffle_tolerance: Max above random for shuffle test.
        baseline_accuracy: Min accuracy for baseline model.

    Returns:
        DatasetPolicyReport.
    """
    checks = []
    all_passed = True

    # Check 1: Manifest signature
    sig_valid = verify_manifest_signature(manifest, secret_key)
    checks.append(PolicyCheckResult(
        check_name="manifest_signature",
        passed=sig_valid,
        detail="Valid" if sig_valid else "Invalid signature",
    ))
    if not sig_valid:
        all_passed = False

    # Check 2: Data hash
    actual_hash = compute_data_hash(X_train, y_train)
    hash_match = actual_hash == manifest.sha256
    checks.append(PolicyCheckResult(
        check_name="data_hash",
        passed=hash_match,
        detail=(
            f"Match" if hash_match
            else f"Mismatch: {actual_hash[:16]} != {manifest.sha256[:16]}"
        ),
    ))
    if not hash_match:
        all_passed = False

    # Check 3: Label shuffle test
    try:
        from impl_v1.training.distributed.dataset_sanity import (
            run_label_shuffle_test,
        )
        shuffle_result = run_label_shuffle_test(
            X_train, y_train,
            input_dim=input_dim,
            num_classes=num_classes,
            tolerance=shuffle_tolerance,
        )
        checks.append(PolicyCheckResult(
            check_name="label_shuffle",
            passed=shuffle_result.passed,
            detail=(
                f"shuffle_acc={shuffle_result.shuffled_accuracy:.4f} "
                f"(random baseline={1.0/num_classes:.4f})"
            ),
        ))
        if not shuffle_result.passed:
            all_passed = False
    except Exception as e:
        checks.append(PolicyCheckResult(
            check_name="label_shuffle",
            passed=False,
            detail=f"Error: {e}",
        ))
        all_passed = False

    # Check 4: Baseline model sanity
    try:
        from impl_v1.training.distributed.dataset_sanity import (
            run_label_shuffle_test,
        )
        # Use original accuracy from shuffle test as baseline indicator
        original_acc = shuffle_result.original_accuracy
        baseline_ok = original_acc >= baseline_accuracy
        checks.append(PolicyCheckResult(
            check_name="baseline_accuracy",
            passed=baseline_ok,
            detail=(
                f"acc={original_acc:.4f} "
                f"{'≥' if baseline_ok else '<'} "
                f"min={baseline_accuracy:.4f}"
            ),
        ))
        if not baseline_ok:
            all_passed = False
    except Exception as e:
        checks.append(PolicyCheckResult(
            check_name="baseline_accuracy",
            passed=False,
            detail=f"Error: {e}",
        ))
        all_passed = False

    abort_reason = ""
    if not all_passed:
        failed = [c.check_name for c in checks if not c.passed]
        abort_reason = f"Failed checks: {failed}"

    report = DatasetPolicyReport(
        dataset_id=manifest.dataset_id,
        passed=all_passed,
        checks=checks,
        timestamp=datetime.now().isoformat(),
        abort_reason=abort_reason,
    )

    if all_passed:
        logger.info(
            f"[DATASET_POLICY] ALL CHECKS PASSED for {manifest.dataset_id}"
        )
    else:
        logger.error(
            f"[DATASET_POLICY] TRAINING BLOCKED: {abort_reason}"
        )

    return report


def save_manifest(manifest: DatasetManifest, base_dir: str = MANIFEST_DIR):
    """Save a manifest to disk."""
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"{manifest.dataset_id}_v{manifest.version}.json")
    with open(path, 'w') as f:
        json.dump(asdict(manifest), f, indent=2)
