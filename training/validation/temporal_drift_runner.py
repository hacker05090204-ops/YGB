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
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import torch
import torch.nn as nn

from backend.training.adaptive_learner import DistributionMonitor
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
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()

    model.eval()
    with torch.no_grad():
        tx = torch.tensor(test_f, dtype=torch.float32).to(device)
        tl = torch.tensor(test_l, dtype=torch.long).to(device)
        acc = (model(tx).argmax(1) == tl).float().mean().item()

    return acc, model


def _evaluate_model(model, features, labels) -> float:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.eval()
    with torch.no_grad():
        x = torch.tensor(features, dtype=torch.float32).to(device)
        y = torch.tensor(labels, dtype=torch.long).to(device)
        logits = model(x)
        preds = logits.argmax(1)
        return float((preds == y).float().mean().item())


def _severity_counts(window_labels: np.ndarray) -> dict[str, int]:
    return {
        "NEGATIVE": int(np.sum(window_labels == 0)),
        "POSITIVE": int(np.sum(window_labels == 1)),
    }


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
    """Run temporal drift and forgetting checks using real sequential windows."""
    report = TemporalDriftReport(
        timestamp=datetime.now(timezone.utc).isoformat())

    logger.info("=" * 60)
    logger.info("TEMPORAL DRIFT SIMULATION")
    logger.info("=" * 60)

    N, D = features.shape
    total_windows = 13
    minimum_window_size = 32
    if N < total_windows * minimum_window_size:
        raise RuntimeError(
            "Temporal drift validation requires at least "
            f"{total_windows * minimum_window_size} real samples"
        )
    logger.info(f"Dataset: {N} samples, {D}D")

    ordered_features = np.ascontiguousarray(features, dtype=np.float32)
    ordered_labels = np.ascontiguousarray(labels, dtype=np.int64)
    window_size = N // total_windows
    windows = [
        (
            ordered_features[index * window_size:(index + 1) * window_size],
            ordered_labels[index * window_size:(index + 1) * window_size],
        )
        for index in range(total_windows)
    ]

    # Baseline
    baseline_features, baseline_labels = windows[0]
    baseline_acc, baseline_model = quick_train(baseline_features, baseline_labels, epochs=5)
    logger.info(f"Baseline accuracy: {baseline_acc:.4f}")

    # Baseline entropy
    baseline_entropy = {}
    for gn, (s, e) in FEATURE_GROUPS.items():
        baseline_entropy[gn] = compute_entropy(baseline_features[:, s:e].flatten())

    # ---------------------------------------------------------------
    # Part 1: 7-day rolling drift
    # ---------------------------------------------------------------
    logger.info("\n--- 7 Sequential Real Windows ---")
    stability_scores = []
    monitor = DistributionMonitor(history_size=7, shift_threshold=0.15)
    monitor.observe(_severity_counts(baseline_labels))

    for day in range(7):
        current_features, current_labels = windows[day + 1]
        acc = _evaluate_model(baseline_model, current_features, current_labels)
        acc_drop = baseline_acc - acc
        shift = monitor.observe(_severity_counts(current_labels))

        # KL divergence (avg across groups)
        kl_avg = 0.0
        for gn, (s, e) in FEATURE_GROUPS.items():
            kl = compute_kl_divergence(
                baseline_features[:, s:e].flatten(), current_features[:, s:e].flatten())
            kl_avg += kl
        kl_avg /= 4.0

        # Entropy retention
        ent_retention = 0.0
        for gn, (s, e) in FEATURE_GROUPS.items():
            current_ent = compute_entropy(current_features[:, s:e].flatten())
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
                    and ent_retention > (1.0 - ENTROPY_DROP_MAX)
                    and shift.js_distance <= shift.threshold))

        report.drift_results.append(asdict(result))

        status = "PASS" if result.passed else "FAIL"
        logger.info(
            f"  Day {day+1}: acc={acc:.4f} drop={acc_drop:.4f} "
            f"KL={kl_avg:.4f} ent_ret={ent_retention:.4f} js={shift.js_distance:.4f} "
            f"score={score:.1f} [{status}]")

        if not result.passed:
            report.overall_pass = False

    # ---------------------------------------------------------------
    # Part 2: 5 sequential expansions (catastrophic forgetting)
    # ---------------------------------------------------------------
    logger.info("\n--- 5 Sequential Real Windows (Forgetting Check) ---")
    snapshots = []
    snapshots.append(("baseline", baseline_features.copy(), baseline_labels.copy(), baseline_acc))

    for exp in range(5):
        current_features, current_labels = windows[8 + exp]
        exp_acc, exp_model = quick_train(current_features, current_labels, epochs=5, seed=42 + exp)
        baseline_eval = _evaluate_model(exp_model, baseline_features, baseline_labels)
        worst_drop = 0.0
        for _snapshot_name, snapshot_features, snapshot_labels, snapshot_acc in snapshots:
            replay_acc = _evaluate_model(exp_model, snapshot_features, snapshot_labels)
            worst_drop = max(worst_drop, snapshot_acc - replay_acc)

        fr = ForgettingResult(
            expansion_id=exp + 1, mutated_group=f"real_window_{exp + 1}",
            accuracy_on_current=round(exp_acc, 4),
            accuracy_on_original=round(baseline_eval, 4),
            worst_drop=round(worst_drop, 4),
            forgetting_detected=worst_drop > ACC_DROP_MAX)

        report.forgetting_results.append(asdict(fr))

        status = "PASS" if not fr.forgetting_detected else "FORGETTING"
        logger.info(
            f"  Window {exp+1}: "
            f"current_acc={exp_acc:.4f} baseline_eval={baseline_eval:.4f} "
            f"drop={worst_drop:.4f} [{status}]")

        if fr.forgetting_detected:
            report.overall_pass = False

        snapshots.append((f"window_{exp+1}", current_features.copy(), current_labels.copy(), exp_acc))

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
    config = DatasetConfig(total_samples=6000)
    dataset = RealTrainingDataset(config=config, seed=42)
    features = dataset._features_tensor.numpy()
    labels = dataset._labels_tensor.numpy()

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
