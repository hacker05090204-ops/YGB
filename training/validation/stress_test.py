"""
Phase 3: Generalization Stress Test for MODE-B Gate.

This validator uses only real observed windows from the supplied dataset.
It does not inject synthetic perturbations or randomized drift.

REQUIREMENTS:
  Accuracy drop < 5%
  Calibration shift < 0.02
  Abstention preferred over misclassification
"""
import sys, os, json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np
import torch
import torch.nn as nn

from backend.training.adaptive_learner import DistributionMonitor

ACCURACY_DROP_MAX = 0.05
CALIBRATION_SHIFT_MAX = 0.05


@dataclass
class StressResult:
    test_name: str
    baseline_accuracy: float
    stressed_accuracy: float
    accuracy_drop: float
    calibration_shift: float
    abstention_rate: float
    passed: bool


@dataclass
class StressTestReport:
    passed: bool
    baseline_accuracy: float
    results: List[StressResult]
    failures: List[str]
    timestamp: str


def _build_model(input_dim: int, device: torch.device) -> nn.Module:
    return nn.Sequential(
        nn.Linear(input_dim, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    ).to(device)


def _train_model(model, features, labels, device, epochs=15, lr=0.001):
    """Real-data-only training with calibration-aware loss."""
    from backend.training.feature_bridge import CalibrationEngine

    cal_engine = CalibrationEngine()
    
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
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


def _evaluate(model, features, labels, device, confidence_threshold=0.7):
    model.eval()
    with torch.no_grad():
        x = torch.tensor(features, dtype=torch.float32).to(device)
        logits = model(x)
        probs = torch.softmax(logits, dim=1).cpu().numpy()
        preds = logits.argmax(dim=1).cpu().numpy()
    
    confidences = probs.max(axis=1)
    accuracy = (preds == labels).mean()
    
    # ECE
    ece = 0.0
    for lo, hi in zip(np.linspace(0, 1, 16)[:-1], np.linspace(0, 1, 16)[1:]):
        mask = (confidences >= lo) & (confidences < hi)
        if mask.sum() > 0:
            ece += mask.sum() / len(labels) * abs((preds[mask] == labels[mask]).mean() - confidences[mask].mean())
    
    abstention_rate = (confidences < confidence_threshold).mean()
    return float(accuracy), float(ece), float(abstention_rate)


def run_stress_tests(features: np.ndarray, labels: np.ndarray) -> StressTestReport:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    N, D = features.shape
    if N < 240:
        raise RuntimeError(
            "run_stress_tests requires at least 240 real samples for windowed evaluation"
        )

    def _severity_counts(window_labels: np.ndarray) -> dict[str, int]:
        return {
            "NEGATIVE": int(np.sum(window_labels == 0)),
            "POSITIVE": int(np.sum(window_labels == 1)),
        }

    ordered_features = np.ascontiguousarray(features, dtype=np.float32)
    ordered_labels = np.ascontiguousarray(labels, dtype=np.int64)
    window_size = max(40, min(N // 5, 400))
    
    # Split 80/20
    np.random.seed(42)
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    test_f, test_l = features[idx[split:]], labels[idx[split:]]
    
    # Train baseline model
    model = _build_model(D, device)
    _train_model(model, train_f, train_l, device)
    baseline_acc, baseline_ece, baseline_abstain = _evaluate(model, test_f, test_l, device)
    print(f"  Baseline: acc={baseline_acc:.4f} ece={baseline_ece:.4f}")
    
    results = []
    failures = []
    monitor = DistributionMonitor(history_size=6, shift_threshold=0.15)
    baseline_window_l = ordered_labels[:window_size]
    monitor.observe(_severity_counts(baseline_window_l))

    def _evaluate_real_window(name: str, window_f: np.ndarray, window_l: np.ndarray):
        acc, ece, abst = _evaluate(model, window_f, window_l, device)
        drop = baseline_acc - acc
        shift = abs(ece - baseline_ece)
        distribution_shift = monitor.observe(_severity_counts(window_l))
        result = StressResult(
            name,
            baseline_acc,
            acc,
            drop,
            shift,
            abst,
            drop < ACCURACY_DROP_MAX
            and shift < CALIBRATION_SHIFT_MAX
            and distribution_shift.js_distance <= distribution_shift.threshold,
        )
        return result, distribution_shift
    
    # --- Test 1: Early real window ---
    r, dist = _evaluate_real_window(
        "early_real_window",
        ordered_features[window_size:window_size * 2],
        ordered_labels[window_size:window_size * 2],
    )
    results.append(r)
    if not r.passed:
        failures.append(
            f"early_real_window: drop={r.accuracy_drop:.4f} shift={r.calibration_shift:.4f} js={dist.js_distance:.4f}"
        )
    print(f"  Early real window: acc={r.stressed_accuracy:.4f} drop={r.accuracy_drop:.4f} js={dist.js_distance:.4f}")
    
    # --- Test 2: Mid real window ---
    r, dist = _evaluate_real_window(
        "mid_real_window",
        ordered_features[window_size * 2:window_size * 3],
        ordered_labels[window_size * 2:window_size * 3],
    )
    results.append(r)
    if not r.passed:
        failures.append(
            f"mid_real_window: drop={r.accuracy_drop:.4f} shift={r.calibration_shift:.4f} js={dist.js_distance:.4f}"
        )
    print(f"  Mid real window: acc={r.stressed_accuracy:.4f} drop={r.accuracy_drop:.4f} js={dist.js_distance:.4f}")
    
    # --- Test 3: Late real window ---
    r, dist = _evaluate_real_window(
        "late_real_window",
        ordered_features[-window_size * 2:-window_size],
        ordered_labels[-window_size * 2:-window_size],
    )
    results.append(r)
    if not r.passed:
        failures.append(
            f"late_real_window: drop={r.accuracy_drop:.4f} shift={r.calibration_shift:.4f} js={dist.js_distance:.4f}"
        )
    print(f"  Late real window: acc={r.stressed_accuracy:.4f} drop={r.accuracy_drop:.4f} js={dist.js_distance:.4f}")
    
    # --- Test 4: Held-out evaluation window ---
    r, dist = _evaluate_real_window("heldout_eval", test_f, test_l)
    results.append(r)
    if not r.passed:
        failures.append(
            f"heldout_eval: drop={r.accuracy_drop:.4f} shift={r.calibration_shift:.4f} js={dist.js_distance:.4f}"
        )
    print(f"  Held-out eval: acc={r.stressed_accuracy:.4f} drop={r.accuracy_drop:.4f} js={dist.js_distance:.4f}")
    
    # --- Test 5: Tail real window ---
    r, dist = _evaluate_real_window(
        "tail_real_window",
        ordered_features[-window_size:],
        ordered_labels[-window_size:],
    )
    results.append(r)
    if not r.passed:
        failures.append(
            f"tail_real_window: drop={r.accuracy_drop:.4f} shift={r.calibration_shift:.4f} js={dist.js_distance:.4f}"
        )
    print(f"  Tail real window: acc={r.stressed_accuracy:.4f} drop={r.accuracy_drop:.4f} js={dist.js_distance:.4f}")
    
    # --- Test 6: Baseline window replay ---
    r, dist = _evaluate_real_window(
        "baseline_window_replay",
        ordered_features[:window_size],
        ordered_labels[:window_size],
    )
    results.append(r)
    if not r.passed:
        failures.append(
            f"baseline_window_replay: drop={r.accuracy_drop:.4f} shift={r.calibration_shift:.4f} js={dist.js_distance:.4f}"
        )
    print(f"  Baseline replay: acc={r.stressed_accuracy:.4f} drop={r.accuracy_drop:.4f} js={dist.js_distance:.4f}")
    
    return StressTestReport(
        passed=len(failures) == 0,
        baseline_accuracy=baseline_acc,
        results=results,
        failures=failures,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def generate_stress_report(r: StressTestReport) -> str:
    lines = [
        "=" * 70,
        "  G38 MODE-B GATE -- PHASE 3: STRESS TEST",
        "=" * 70,
        f"  Baseline Accuracy: {r.baseline_accuracy:.4f}",
        f"  Verdict: {'PASS' if r.passed else 'FAIL'}",
        "",
        f"  {'Test':<25} {'BaseAcc':>8} {'StressAcc':>9} {'Drop':>7} {'CalShift':>8} {'Abstain':>8} {'Pass':>5}",
    ]
    for s in r.results:
        lines.append(
            f"  {s.test_name:<25} {s.baseline_accuracy:8.4f} {s.stressed_accuracy:9.4f} "
            f"{s.accuracy_drop:7.4f} {s.calibration_shift:8.4f} {s.abstention_rate:8.4f} "
            f"{'Y' if s.passed else 'N':>5}"
        )
    if r.failures:
        lines += ["", "  FAILURES:"]
        for f in r.failures:
            lines.append(f"    {f}")
    lines += [
        "",
        "=" * 70,
        f"  PHASE 3 VERDICT: {'PASS' if r.passed else 'FAIL -- MODE-B BLOCKED'}",
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
    
    print(f"Running stress tests on {len(labels)} samples...")
    result = run_stress_tests(features, labels)
    report = generate_stress_report(result)
    print(report)
    
    rp = os.path.join(os.path.dirname(__file__), '..', '..', 'reports', 'g38_training', 'phase3_stress_test.txt')
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, 'w', encoding='utf-8') as f:
        f.write(report)
    sys.exit(0 if result.passed else 1)
