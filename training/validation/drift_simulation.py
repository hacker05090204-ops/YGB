"""
Phase 6: Real distribution drift validation for MODE-B Gate.

This module evaluates drift using only real observed samples.
It does NOT synthesize perturbations or inject simulated patterns.

Reject if:
  Accuracy drop > 5%
  Confidence inflation > 5%
  Representation deviation > 20%
"""
import sys, os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np
import torch
import torch.nn as nn

from backend.training.adaptive_learner import DistributionMonitor

ACC_DROP_MAX = 0.05
CONF_INFLATION_MAX = 0.05
REPR_DEVIATION_MAX = 0.20


@dataclass
class DriftTestResult:
    name: str
    baseline_acc: float
    drifted_acc: float
    acc_drop: float
    conf_inflation: float
    repr_deviation: float
    passed: bool


@dataclass
class DriftSimulationReport:
    passed: bool
    results: List[DriftTestResult]
    failures: List[str]
    timestamp: str


def _build_and_train(features, labels, device, epochs=15):
    """Train only on real observed features without synthetic augmentation."""
    from backend.training.feature_bridge import CalibrationEngine
    
    D = features.shape[1]
    model = nn.Sequential(
        nn.Linear(D, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    ).to(device)
    
    cal_engine = CalibrationEngine()
    
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)
    criterion = nn.CrossEntropyLoss()
    batch_size = 256
    
    model.train()
    for epoch in range(epochs):
        perm = np.random.permutation(len(labels))
        epoch_f = features[perm].copy()
        epoch_l = labels[perm].copy()

        n_batches = (len(epoch_l) + batch_size - 1) // batch_size
        for b in range(n_batches):
            start = b * batch_size
            end = min(start + batch_size, len(epoch_l))
            batch_f = epoch_f[start:end].copy()
            batch_l = epoch_l[start:end]

            bx = torch.tensor(batch_f, dtype=torch.float32).to(device)
            by = torch.tensor(batch_l, dtype=torch.long).to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(bx)
            ce_loss = criterion(logits, by)
            
            # Calibration penalty
            with torch.no_grad():
                probs = torch.softmax(logits, dim=1)
                confs = probs.max(dim=1).values
                correct = (logits.argmax(dim=1) == by).float()
                cal_penalty = cal_engine.compute_calibration_penalty(
                    confs.cpu().numpy(), correct.cpu().numpy()
                )
            
            total_loss = ce_loss + 0.2 * cal_penalty
            total_loss.backward()
            optimizer.step()
    
    return model


def _evaluate_drift(model, features, labels, device, baseline_features=None):
    model.eval()
    with torch.no_grad():
        x = torch.tensor(features, dtype=torch.float32).to(device)
        logits = model(x)
        probs = torch.softmax(logits, dim=1).cpu().numpy()
        preds = logits.argmax(dim=1).cpu().numpy()
    
    acc = float((preds == labels).mean())
    conf = float(probs.max(axis=1).mean())
    conf_inflation = conf - acc
    
    # Representation deviation
    repr_dev = 0.0
    if baseline_features is not None:
        baseline_mean = baseline_features.mean(axis=0)
        drifted_mean = features.mean(axis=0)
        repr_dev = float(np.linalg.norm(drifted_mean - baseline_mean) / 
                         (np.linalg.norm(baseline_mean) + 1e-10))
    
    return acc, conf_inflation, repr_dev


def run_drift_simulation(features: np.ndarray, labels: np.ndarray) -> DriftSimulationReport:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    N, D = features.shape
    np.random.seed(42)

    if N < 200:
        raise RuntimeError(
            "Real drift validation requires at least 200 real samples to compare "
            "baseline and later observed windows."
        )
    
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    test_f, test_l = features[idx[split:]], labels[idx[split:]]
    
    model = _build_and_train(train_f, train_l, device)
    baseline_acc, _, _ = _evaluate_drift(model, test_f, test_l, device)
    print(f"  Baseline accuracy: {baseline_acc:.4f}")
    
    results = []
    failures = []
    
    def _severity_counts(window_labels: np.ndarray) -> dict[str, int]:
        positives = int(np.sum(window_labels == 1))
        negatives = int(np.sum(window_labels == 0))
        return {
            "POSITIVE": positives,
            "NEGATIVE": negatives,
        }

    def _window_metrics(
        name: str,
        observed_f: np.ndarray,
        observed_l: np.ndarray,
        baseline_features: np.ndarray,
        *,
        monitor: DistributionMonitor,
    ) -> DriftTestResult:
        acc, ci, rd = _evaluate_drift(model, observed_f, observed_l, device, baseline_features)
        drop = baseline_acc - acc
        shift = monitor.observe(_severity_counts(observed_l))
        passed = (
            drop < ACC_DROP_MAX
            and ci < CONF_INFLATION_MAX
            and rd < REPR_DEVIATION_MAX
            and shift.js_distance <= shift.threshold
        )
        return DriftTestResult(
            name,
            baseline_acc,
            acc,
            drop,
            ci,
            rd,
            passed,
        )

    ordered_features = np.ascontiguousarray(features, dtype=np.float32)
    ordered_labels = np.ascontiguousarray(labels, dtype=np.int64)
    window_size = max(50, min(len(ordered_labels) // 4, 500))
    baseline_window_f = ordered_features[:window_size]
    baseline_window_l = ordered_labels[:window_size]
    later_window_f = ordered_features[window_size:window_size * 2]
    later_window_l = ordered_labels[window_size:window_size * 2]
    latest_window_f = ordered_features[-window_size:]
    latest_window_l = ordered_labels[-window_size:]

    monitor = DistributionMonitor(history_size=5, shift_threshold=0.15)
    monitor.observe(_severity_counts(baseline_window_l))

    # Test 1: adjacent real-time window drift
    r = _window_metrics(
        "adjacent_real_window",
        later_window_f,
        later_window_l,
        baseline_window_f,
        monitor=monitor,
    )
    results.append(r)
    if not r.passed:
        failures.append(
            f"adjacent_real_window: drop={r.acc_drop:.4f} ci={r.conf_inflation:.4f} rd={r.repr_deviation:.4f}"
        )
    print(f"  Adjacent real window: acc={r.drifted_acc:.4f} drop={r.acc_drop:.4f}")
    
    # Test 2: late real window drift
    r = _window_metrics(
        "late_real_window",
        latest_window_f,
        latest_window_l,
        baseline_window_f,
        monitor=monitor,
    )
    results.append(r)
    if not r.passed:
        failures.append(
            f"late_real_window: drop={r.acc_drop:.4f} ci={r.conf_inflation:.4f} rd={r.repr_deviation:.4f}"
        )
    print(f"  Late real window: acc={r.drifted_acc:.4f} drop={r.acc_drop:.4f}")
    
    # Test 3: evaluation split against real held-out baseline
    r = _window_metrics(
        "heldout_real_eval",
        test_f,
        test_l,
        baseline_window_f,
        monitor=monitor,
    )
    results.append(r)
    if not r.passed:
        failures.append(
            f"heldout_real_eval: drop={r.acc_drop:.4f} ci={r.conf_inflation:.4f} rd={r.repr_deviation:.4f}"
        )
    print(f"  Held-out real eval: acc={r.drifted_acc:.4f} drop={r.acc_drop:.4f}")
    
    return DriftSimulationReport(
        passed=len(failures) == 0, results=results,
        failures=failures, timestamp=datetime.now(timezone.utc).isoformat(),
    )


def generate_drift_report(r: DriftSimulationReport) -> str:
    lines = [
        "=" * 70,
        "  G38 MODE-B GATE -- PHASE 6: DRIFT SIMULATION",
        "=" * 70,
        f"  Verdict: {'PASS' if r.passed else 'FAIL'}",
        "",
        f"  {'Test':<30} {'Base':>6} {'Drift':>6} {'Drop':>6} {'ConfInf':>7} {'ReprDev':>7} {'Pass':>5}",
    ]
    for t in r.results:
        lines.append(
            f"  {t.name:<30} {t.baseline_acc:6.4f} {t.drifted_acc:6.4f} "
            f"{t.acc_drop:6.4f} {t.conf_inflation:7.4f} {t.repr_deviation:7.4f} "
            f"{'Y' if t.passed else 'N':>5}"
        )
    if r.failures:
        lines += ["", "  FAILURES:"]
        for f in r.failures:
            lines.append(f"    {f}")
    lines += [
        "", "=" * 70,
        f"  PHASE 6 VERDICT: {'PASS' if r.passed else 'FAIL -- MODE-B BLOCKED'}",
        "=" * 70,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    from impl_v1.training.data.scaled_dataset import DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    config = DatasetConfig(total_samples=18000)
    dataset = RealTrainingDataset(config=config)
    features = dataset._features_tensor.numpy()
    labels = dataset._labels_tensor.numpy()
    print(f"Drift simulation: {len(labels)} samples")
    result = run_drift_simulation(features, labels)
    report = generate_drift_report(result)
    print(report)
    rp = os.path.join(os.path.dirname(__file__), '..', '..', 'reports', 'g38_training', 'phase6_drift.txt')
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, 'w', encoding='utf-8') as f:
        f.write(report)
    sys.exit(0 if result.passed else 1)
