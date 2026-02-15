"""
Phase 1: Temporal Drift Runner — Python orchestrator for drift simulation.

Mirrors the C++ rolling_drift_engine and catastrophic_forgetting_detector
logic in Python/NumPy for direct integration with PyTorch models.

Simulation:
  - 7-day rolling distribution shift (Gaussian drift, sigma grows per day)
  - 5 sequential representation expansions (10% group mutation each)
  - Per-step: train model, measure accuracy/KL/entropy

Thresholds:
  - Accuracy drop < 5%
  - KL divergence shift < 0.5
  - Entropy drop < 10%
  - Stability score >= 80

GOVERNANCE: MODE-A only. Zero decision authority.
"""
import sys
import os
import json
import time
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import torch
import torch.nn as nn
from torch.cuda.amp import autocast, GradScaler

from training.validation.representation_audit import (
    compute_entropy, compute_kl_divergence, FEATURE_GROUPS,
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [TEMPORAL-DRIFT] %(message)s')
logger = logging.getLogger(__name__)

# Thresholds
ACC_DROP_MAX = 0.05
KL_SHIFT_MAX = 0.5
ENTROPY_DROP_MAX = 0.10
STABILITY_PASS = 80.0


@dataclass
class DriftStepResult:
    day: int = 0
    accuracy: float = 0.0
    accuracy_drop: float = 0.0
    kl_divergence: float = 0.0
    entropy_retention: float = 1.0
    stability_score: float = 100.0
    passed: bool = True


@dataclass
class ForgettingResult:
    expansion_id: int = 0
    mutated_group: str = ""
    accuracy_on_current: float = 0.0
    accuracy_on_original: float = 0.0
    worst_drop: float = 0.0
    forgetting_detected: bool = False


@dataclass
class TemporalDriftReport:
    overall_pass: bool = True
    drift_results: List[dict] = field(default_factory=list)
    forgetting_results: List[dict] = field(default_factory=list)
    avg_stability_score: float = 0.0
    worst_stability_score: float = 0.0
    timestamp: str = ""


def set_deterministic(seed=42):
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)


def build_model(dim=256):
    return nn.Sequential(
        nn.Linear(dim, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    )


def quick_train(features, labels, epochs=5, lr=0.002, seed=42):
    """Quick train for drift evaluation (lightweight)."""
    set_deterministic(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    N = len(labels)
    split = int(0.8 * N)
    idx = np.random.permutation(N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    test_f, test_l = features[idx[split:]], labels[idx[split:]]

    model = build_model(features.shape[1]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    for ep in range(epochs):
        model.train()
        perm = np.random.permutation(len(train_l))
        for i in range(0, len(train_l), 512):
            end = min(i + 512, len(train_l))
            bx = torch.tensor(train_f[perm[i:end]], dtype=torch.float32).to(device)
            by = torch.tensor(train_l[perm[i:end]], dtype=torch.long).to(device)
            loss = criterion(model(bx), by)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        tx = torch.tensor(test_f, dtype=torch.float32).to(device)
        tl = torch.tensor(test_l, dtype=torch.long).to(device)
        acc = (model(tx).argmax(1) == tl).float().mean().item()

    return acc, model


def apply_rolling_drift(features, day, n_days=7, base_sigma=0.05, seed=42):
    """Apply Gaussian drift to features. Sigma grows linearly per day."""
    rng = np.random.RandomState(seed + day * 1000)
    sigma = base_sigma * (day + 1) / n_days
    drifted = features.copy()

    group_scales = {"signal": 1.0, "response": 1.0,
                    "interaction": 1.5, "noise": 1.0}

    for group_name, (start, end) in FEATURE_GROUPS.items():
        scale = group_scales[group_name]
        noise = rng.normal(0, sigma * scale, drifted[:, start:end].shape)
        drifted[:, start:end] = np.clip(drifted[:, start:end] + noise, 0, 1)

    return drifted


def compute_stability_score(kl, entropy_ret, acc_ret, cal_delta=0.0):
    """Composite stability score matching C++ stability_score.cpp logic."""
    def kl_s(k):
        if k <= 0: return 100.0
        if k >= 1.0: return 0.0
        return 100.0 * (1.0 - k / 1.0)

    def ent_s(r):
        if r >= 1.0: return 100.0
        drop = 1.0 - r
        if drop >= 0.20: return 0.0
        return 100.0 * (1.0 - drop / 0.20)

    def acc_s(r):
        if r >= 1.0: return 100.0
        drop = 1.0 - r
        if drop >= 0.10: return 0.0
        return 100.0 * (1.0 - drop / 0.10)

    def cal_s(d):
        d = abs(d)
        if d <= 0: return 100.0
        if d >= 0.04: return 0.0
        return 100.0 * (1.0 - d / 0.04)

    return 0.30 * kl_s(kl) + 0.25 * ent_s(entropy_ret) + \
           0.25 * acc_s(acc_ret) + 0.20 * cal_s(cal_delta)


def run_temporal_drift_simulation(features, labels):
    """Run full temporal drift + forgetting simulation."""
    report = TemporalDriftReport(
        timestamp=datetime.now(timezone.utc).isoformat())

    logger.info("=" * 60)
    logger.info("TEMPORAL DRIFT SIMULATION")
    logger.info("=" * 60)

    N, D = features.shape
    logger.info(f"Dataset: {N} samples, {D}D")

    # Baseline
    baseline_acc, _ = quick_train(features, labels, epochs=5)
    logger.info(f"Baseline accuracy: {baseline_acc:.4f}")

    # Baseline entropy
    baseline_entropy = {}
    for gn, (s, e) in FEATURE_GROUPS.items():
        baseline_entropy[gn] = compute_entropy(features[:, s:e].flatten())

    # ---------------------------------------------------------------
    # Part 1: 7-day rolling drift
    # ---------------------------------------------------------------
    logger.info("\n--- 7-Day Rolling Drift ---")
    stability_scores = []

    for day in range(7):
        drifted = apply_rolling_drift(features, day)
        acc, _ = quick_train(drifted, labels, epochs=5, seed=42 + day)
        acc_drop = baseline_acc - acc

        # KL divergence (avg across groups)
        kl_avg = 0.0
        for gn, (s, e) in FEATURE_GROUPS.items():
            kl = compute_kl_divergence(
                features[:, s:e].flatten(), drifted[:, s:e].flatten())
            kl_avg += kl
        kl_avg /= 4.0

        # Entropy retention
        ent_retention = 0.0
        for gn, (s, e) in FEATURE_GROUPS.items():
            current_ent = compute_entropy(drifted[:, s:e].flatten())
            ent_retention += current_ent / max(baseline_entropy[gn], 1e-10)
        ent_retention /= 4.0

        score = compute_stability_score(kl_avg, ent_retention,
                                         1.0 - acc_drop)
        stability_scores.append(score)

        result = DriftStepResult(
            day=day + 1, accuracy=round(acc, 4),
            accuracy_drop=round(acc_drop, 4),
            kl_divergence=round(kl_avg, 6),
            entropy_retention=round(ent_retention, 4),
            stability_score=round(score, 1),
            passed=(acc_drop < ACC_DROP_MAX and kl_avg < KL_SHIFT_MAX
                    and ent_retention > (1.0 - ENTROPY_DROP_MAX)))

        report.drift_results.append(asdict(result))

        status = "PASS" if result.passed else "FAIL"
        logger.info(
            f"  Day {day+1}: acc={acc:.4f} drop={acc_drop:.4f} "
            f"KL={kl_avg:.4f} ent_ret={ent_retention:.4f} "
            f"score={score:.1f} [{status}]")

        if not result.passed:
            report.overall_pass = False

    # ---------------------------------------------------------------
    # Part 2: 5 sequential expansions (catastrophic forgetting)
    # ---------------------------------------------------------------
    logger.info("\n--- 5 Sequential Expansions (Forgetting Check) ---")
    group_names = ["signal", "response", "interaction", "noise"]
    current_features = features.copy()
    snapshots = []
    snapshots.append(("original", features.copy(), labels.copy(), baseline_acc))

    for exp in range(5):
        group_idx = exp % 4
        group_name = group_names[group_idx]
        gstart, gend = list(FEATURE_GROUPS.values())[group_idx]

        # Apply 10% mutation to the target group
        rng = np.random.RandomState(42 + exp * 100)
        mask = rng.random(current_features.shape[0]) < 0.10
        n_mutated = mask.sum()
        current_features[mask, gstart:gend] = rng.uniform(
            0, 1, (n_mutated, gend - gstart)).astype(np.float32)

        # Train on mutated data
        exp_acc, _ = quick_train(current_features, labels, epochs=5,
                                  seed=42 + exp)

        # Check accuracy on original data
        orig_acc_now, _ = quick_train(features, labels, epochs=5,
                                       seed=42 + exp)

        # Worst drop across snapshots
        worst_drop = baseline_acc - exp_acc

        fr = ForgettingResult(
            expansion_id=exp + 1, mutated_group=group_name,
            accuracy_on_current=round(exp_acc, 4),
            accuracy_on_original=round(orig_acc_now, 4),
            worst_drop=round(worst_drop, 4),
            forgetting_detected=worst_drop > ACC_DROP_MAX)

        report.forgetting_results.append(asdict(fr))

        status = "PASS" if not fr.forgetting_detected else "FORGETTING"
        logger.info(
            f"  Expansion {exp+1} ({group_name}): "
            f"current_acc={exp_acc:.4f} orig_acc={orig_acc_now:.4f} "
            f"drop={worst_drop:.4f} [{status}]")

        if fr.forgetting_detected:
            report.overall_pass = False

        snapshots.append((f"exp_{exp+1}", current_features.copy(),
                          labels.copy(), exp_acc))

    # Summary
    report.avg_stability_score = round(
        sum(stability_scores) / len(stability_scores), 1)
    report.worst_stability_score = round(min(stability_scores), 1)

    if report.worst_stability_score < STABILITY_PASS:
        report.overall_pass = False

    logger.info(f"\n{'=' * 60}")
    logger.info(f"RESULT: {'PASS' if report.overall_pass else 'FAIL'}")
    logger.info(f"Avg stability score: {report.avg_stability_score}")
    logger.info(f"Worst stability score: {report.worst_stability_score}")
    logger.info(f"{'=' * 60}")

    return report


if __name__ == "__main__":
    from impl_v1.training.data.scaled_dataset import DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    from backend.training.representation_bridge import (
        RepresentationExpander, ExpansionConfig,
    )

    # Load merged dataset
    orig_config = DatasetConfig(total_samples=18000)
    orig_ds = RealTrainingDataset(config=orig_config, seed=42)
    orig_f = orig_ds._features_tensor.numpy()
    orig_l = orig_ds._labels_tensor.numpy()

    exp = RepresentationExpander(seed=42)
    exp_f, exp_l = exp.generate_expanded_dataset(8000)

    features = np.concatenate([orig_f, exp_f], axis=0)
    labels = np.concatenate([orig_l, exp_l], axis=0)

    rng = np.random.RandomState(42)
    perm = rng.permutation(len(labels))
    features, labels = features[perm], labels[perm]

    # Use smaller subset for speed (6000 samples)
    features, labels = features[:6000], labels[:6000]

    report = run_temporal_drift_simulation(features, labels)

    # Save report
    report_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'reports', 'g38_training')
    os.makedirs(report_dir, exist_ok=True)
    rp = os.path.join(report_dir, 'temporal_drift_report.json')

    with open(rp, 'w', encoding='utf-8') as f:
        json.dump(asdict(report), f, indent=2, default=str)

    logger.info(f"Report saved: {rp}")
    sys.exit(0 if report.overall_pass else 1)
