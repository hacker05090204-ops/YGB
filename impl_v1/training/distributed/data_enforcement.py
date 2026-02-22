"""
data_enforcement.py — Useful Data Enforcement (Phase 1)

Unified pre-training data gate. Chains all 6 checks:

  1. Signed dataset manifest (HMAC verification)
  2. Dataset integrity (hash, sample_count, feature_dim, entropy)
  3. Quality check (duplicates, imbalance, noise)
  4. Label shuffle test (must drop to random baseline)
  5. Baseline sanity model (small classifier > 40% accuracy)
  6. Train/test leakage check (hash intersection)

Blocks training if any fail.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

MANIFEST_PATH = os.path.join('secure_data', 'dataset_manifest.json')
ENFORCEMENT_RESULT_PATH = os.path.join('secure_data', 'data_enforcement_result.json')

# Thresholds
DUPLICATE_MAX = 0.20
IMBALANCE_MAX = 10.0
ENTROPY_MIN = 0.3
SANITY_ACC_MIN = 0.40
SHUFFLE_TOLERANCE = 0.10


# =============================================================================
# RESULT TYPES
# =============================================================================

@dataclass
class ManifestCheck:
    """Signed manifest verification result."""
    passed: bool
    manifest_exists: bool
    signature_valid: bool
    dataset_hash: str
    sample_count: int
    feature_dim: int
    error: str = ""


@dataclass
class QualityCheck:
    """Data quality gate result."""
    passed: bool
    duplicate_ratio: float
    imbalance_ratio: float
    entropy: float
    noise_score: float
    error: str = ""


@dataclass
class ShuffleCheck:
    """Label shuffle test result."""
    passed: bool
    original_accuracy: float
    shuffled_accuracy: float
    random_baseline: float
    accuracy_dropped: bool
    error: str = ""


@dataclass
class SanityCheck:
    """Baseline sanity model result."""
    passed: bool
    accuracy: float
    threshold: float
    error: str = ""


@dataclass
class LeakageCheck:
    """Train/test overlap result."""
    passed: bool
    overlap_count: int
    overlap_ratio: float
    error: str = ""


@dataclass
class DataEnforcementResult:
    """Combined enforcement result — all 6 checks."""
    passed: bool
    manifest: ManifestCheck
    quality: QualityCheck
    shuffle: ShuffleCheck
    sanity: SanityCheck
    leakage: LeakageCheck
    errors: List[str] = field(default_factory=list)
    timestamp: str = ""
    elapsed_sec: float = 0.0


# =============================================================================
# MANIFEST SIGNING
# =============================================================================

def sign_manifest(
    dataset_hash: str,
    sample_count: int,
    feature_dim: int,
    num_classes: int,
    secret_key: str = "cluster-authority-key",
    path: str = MANIFEST_PATH,
) -> str:
    """Create and sign a dataset manifest.

    Returns the HMAC signature.
    """
    manifest = {
        'dataset_hash': dataset_hash,
        'sample_count': sample_count,
        'feature_dim': feature_dim,
        'num_classes': num_classes,
        'created': datetime.now().isoformat(),
    }

    payload = json.dumps(manifest, sort_keys=True).encode()
    signature = hmac.new(
        secret_key.encode(), payload, hashlib.sha256
    ).hexdigest()

    manifest['signature'] = signature

    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w') as f:
        json.dump(manifest, f, indent=2)

    logger.info(f"[MANIFEST] Signed manifest created: {dataset_hash[:16]}...")
    return signature


def verify_manifest(
    dataset_hash: str,
    sample_count: int,
    feature_dim: int,
    secret_key: str = "cluster-authority-key",
    path: str = MANIFEST_PATH,
) -> ManifestCheck:
    """Verify a signed dataset manifest."""
    if not os.path.exists(path):
        return ManifestCheck(
            passed=False, manifest_exists=False, signature_valid=False,
            dataset_hash="", sample_count=0, feature_dim=0,
            error="Manifest file not found",
        )

    try:
        with open(path, 'r') as f:
            manifest = json.load(f)
    except Exception as e:
        return ManifestCheck(
            passed=False, manifest_exists=True, signature_valid=False,
            dataset_hash="", sample_count=0, feature_dim=0,
            error=f"Manifest parse error: {e}",
        )

    stored_sig = manifest.pop('signature', '')

    # Recompute signature
    payload = json.dumps(manifest, sort_keys=True).encode()
    expected_sig = hmac.new(
        secret_key.encode(), payload, hashlib.sha256
    ).hexdigest()

    sig_valid = hmac.compare_digest(stored_sig, expected_sig)

    # Check fields match
    errors = []
    if manifest.get('dataset_hash') != dataset_hash:
        errors.append("dataset_hash mismatch")
    if manifest.get('sample_count') != sample_count:
        errors.append("sample_count mismatch")
    if manifest.get('feature_dim') != feature_dim:
        errors.append("feature_dim mismatch")
    if not sig_valid:
        errors.append("HMAC signature invalid")

    passed = sig_valid and len(errors) == 0

    return ManifestCheck(
        passed=passed,
        manifest_exists=True,
        signature_valid=sig_valid,
        dataset_hash=manifest.get('dataset_hash', ''),
        sample_count=manifest.get('sample_count', 0),
        feature_dim=manifest.get('feature_dim', 0),
        error="; ".join(errors) if errors else "",
    )


# =============================================================================
# QUALITY CHECK
# =============================================================================

def check_quality(
    features: np.ndarray,
    labels: np.ndarray,
) -> QualityCheck:
    """Run data quality checks: duplicates, imbalance, entropy, noise."""
    N = features.shape[0]

    # Duplicates
    _, unique_counts = np.unique(features, axis=0, return_counts=True)
    duplicates = int(np.sum(unique_counts[unique_counts > 1] - 1))
    dup_ratio = duplicates / max(N, 1)

    # Class imbalance
    _, counts = np.unique(labels, return_counts=True)
    imbalance = float(counts.max()) / max(float(counts.min()), 1)

    # Entropy
    probs = counts.astype(float) / counts.sum()
    max_ent = np.log2(max(len(counts), 2))
    entropy = float(-np.sum(probs * np.log2(probs + 1e-10)))
    norm_entropy = entropy / max(max_ent, 1e-10)

    # Noise score
    feat_var = np.var(features, axis=0)
    var_cv = np.std(feat_var) / max(np.mean(feat_var), 1e-10)
    noise_score = max(0.0, 1.0 - var_cv)

    errors = []
    if dup_ratio > DUPLICATE_MAX:
        errors.append(f"duplicates {dup_ratio:.1%} > {DUPLICATE_MAX:.0%}")
    if imbalance > IMBALANCE_MAX:
        errors.append(f"imbalance {imbalance:.1f}x > {IMBALANCE_MAX:.0f}x")
    if norm_entropy < ENTROPY_MIN:
        errors.append(f"entropy {norm_entropy:.4f} < {ENTROPY_MIN}")

    return QualityCheck(
        passed=len(errors) == 0,
        duplicate_ratio=round(dup_ratio, 4),
        imbalance_ratio=round(imbalance, 4),
        entropy=round(norm_entropy, 4),
        noise_score=round(noise_score, 4),
        error="; ".join(errors),
    )


# =============================================================================
# SHUFFLE TEST
# =============================================================================

def run_shuffle_test(
    features: np.ndarray,
    labels: np.ndarray,
    input_dim: int = 256,
    num_classes: int = 2,
    tolerance: float = SHUFFLE_TOLERANCE,
) -> ShuffleCheck:
    """Label shuffle test — accuracy must drop to random baseline."""
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        return ShuffleCheck(
            passed=False, original_accuracy=0, shuffled_accuracy=0,
            random_baseline=0, accuracy_dropped=False,
            error="torch not available",
        )

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    random_baseline = 1.0 / max(num_classes, 2)
    threshold = random_baseline + tolerance

    def _train_eval(X, y):
        n = min(5000, len(y))
        idx = np.random.permutation(len(y))[:n]
        tx = torch.tensor(X[idx], dtype=torch.float32).to(device)
        ty = torch.tensor(y[idx], dtype=torch.long).to(device)

        model = nn.Sequential(
            nn.Linear(input_dim, 64), nn.ReLU(),
            nn.Linear(64, num_classes),
        ).to(device)
        opt = torch.optim.Adam(model.parameters(), lr=0.01)
        crit = nn.CrossEntropyLoss()

        model.train()
        for _ in range(3):
            opt.zero_grad()
            loss = crit(model(tx), ty)
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            acc = (model(tx).argmax(1) == ty).float().mean().item()
        return acc

    try:
        original_acc = _train_eval(features, labels)
        shuffled_labels = np.random.permutation(labels)
        shuffled_acc = _train_eval(features, shuffled_labels)
    except Exception as e:
        return ShuffleCheck(
            passed=False, original_accuracy=0, shuffled_accuracy=0,
            random_baseline=random_baseline, accuracy_dropped=False,
            error=str(e),
        )

    dropped = shuffled_acc < threshold
    passed = dropped  # Shuffled accuracy must be near random

    return ShuffleCheck(
        passed=passed,
        original_accuracy=round(original_acc, 6),
        shuffled_accuracy=round(shuffled_acc, 6),
        random_baseline=round(random_baseline, 4),
        accuracy_dropped=dropped,
        error="" if passed else f"shuffled_acc {shuffled_acc:.4f} >= threshold {threshold:.4f}",
    )


# =============================================================================
# SANITY MODEL
# =============================================================================

def run_sanity_model(
    features: np.ndarray,
    labels: np.ndarray,
    input_dim: int = 256,
    num_classes: int = 2,
    min_accuracy: float = SANITY_ACC_MIN,
) -> SanityCheck:
    """Train small classifier — must exceed minimum accuracy."""
    try:
        import torch
        import torch.nn as nn
    except ImportError:
        return SanityCheck(
            passed=False, accuracy=0, threshold=min_accuracy,
            error="torch not available",
        )

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    n = min(5000, len(labels))
    idx = np.random.permutation(len(labels))[:n]
    tx = torch.tensor(features[idx], dtype=torch.float32).to(device)
    ty = torch.tensor(labels[idx], dtype=torch.long).to(device)

    model = nn.Sequential(
        nn.Linear(input_dim, 64), nn.ReLU(),
        nn.Linear(64, num_classes),
    ).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=0.01)
    crit = nn.CrossEntropyLoss()

    model.train()
    for _ in range(5):
        opt.zero_grad()
        loss = crit(model(tx), ty)
        loss.backward()
        opt.step()

    model.eval()
    with torch.no_grad():
        acc = (model(tx).argmax(1) == ty).float().mean().item()

    passed = acc >= min_accuracy
    return SanityCheck(
        passed=passed,
        accuracy=round(acc, 6),
        threshold=min_accuracy,
        error="" if passed else f"accuracy {acc:.4f} < {min_accuracy}",
    )


# =============================================================================
# LEAKAGE CHECK
# =============================================================================

def check_leakage(
    X_train: np.ndarray,
    X_test: Optional[np.ndarray],
) -> LeakageCheck:
    """Check train/test overlap via row hash intersection."""
    if X_test is None:
        return LeakageCheck(passed=True, overlap_count=0, overlap_ratio=0.0)

    train_hashes = set()
    for row in X_train:
        train_hashes.add(hashlib.md5(row.tobytes()).hexdigest())

    overlap = 0
    for row in X_test:
        if hashlib.md5(row.tobytes()).hexdigest() in train_hashes:
            overlap += 1

    ratio = overlap / max(len(X_test), 1)
    passed = overlap == 0

    return LeakageCheck(
        passed=passed,
        overlap_count=overlap,
        overlap_ratio=round(ratio, 6),
        error="" if passed else f"{overlap} leaked samples ({ratio:.1%})",
    )


# =============================================================================
# UNIFIED ENFORCEMENT
# =============================================================================

def enforce_data_quality(
    features: np.ndarray,
    labels: np.ndarray,
    dataset_hash: str,
    sample_count: int,
    feature_dim: int,
    num_classes: int = 2,
    X_test: Optional[np.ndarray] = None,
    manifest_path: str = MANIFEST_PATH,
    secret_key: str = "cluster-authority-key",
    result_path: str = ENFORCEMENT_RESULT_PATH,
) -> DataEnforcementResult:
    """Run all 6 data enforcement checks.

    Blocks training if any fail.
    """
    t0 = time.perf_counter()
    errors = []

    # 1. Signed manifest
    manifest = verify_manifest(
        dataset_hash, sample_count, feature_dim,
        secret_key=secret_key, path=manifest_path,
    )
    if not manifest.passed:
        errors.append(f"Manifest: {manifest.error}")

    # 2+3. Quality check
    quality = check_quality(features, labels)
    if not quality.passed:
        errors.append(f"Quality: {quality.error}")

    # 4. Shuffle test
    shuffle = run_shuffle_test(
        features, labels, input_dim=feature_dim, num_classes=num_classes,
    )
    if not shuffle.passed:
        errors.append(f"Shuffle: {shuffle.error}")

    # 5. Sanity model
    sanity = run_sanity_model(
        features, labels, input_dim=feature_dim, num_classes=num_classes,
    )
    if not sanity.passed:
        errors.append(f"Sanity: {sanity.error}")

    # 6. Leakage
    leakage = check_leakage(features, X_test)
    if not leakage.passed:
        errors.append(f"Leakage: {leakage.error}")

    elapsed = time.perf_counter() - t0
    passed = len(errors) == 0

    result = DataEnforcementResult(
        passed=passed,
        manifest=manifest,
        quality=quality,
        shuffle=shuffle,
        sanity=sanity,
        leakage=leakage,
        errors=errors,
        timestamp=datetime.now().isoformat(),
        elapsed_sec=round(elapsed, 3),
    )

    # Persist
    os.makedirs(os.path.dirname(result_path) or '.', exist_ok=True)
    with open(result_path, 'w') as f:
        json.dump(asdict(result), f, indent=2)

    if passed:
        logger.info(
            f"[DATA_ENFORCEMENT] ALL PASSED in {elapsed:.1f}s — "
            f"quality=OK, shuffle=OK, sanity_acc={sanity.accuracy:.4f}, "
            f"leakage=0"
        )
    else:
        logger.error(
            f"[DATA_ENFORCEMENT] BLOCKED — {len(errors)} failure(s):"
        )
        for e in errors:
            logger.error(f"  • {e}")

    return result
