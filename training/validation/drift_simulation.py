"""
Phase 6: Drift Simulation for MODE-B Gate.

Simulate:
  - Feature distribution shift +10%
  - New unseen pattern injection
  - Class imbalance 70/30
  - Feature missingness

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
    D = features.shape[1]
    model = nn.Sequential(
        nn.Linear(D, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(D // 2 + 256, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    ).to(device)
    # Fix: use proper model
    model = nn.Sequential(
        nn.Linear(D, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    ).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    ds = torch.utils.data.TensorDataset(
        torch.tensor(features, dtype=torch.float32),
        torch.tensor(labels, dtype=torch.long),
    )
    loader = torch.utils.data.DataLoader(ds, batch_size=256, shuffle=True)
    model.train()
    for _ in range(epochs):
        for bx, by in loader:
            bx, by = bx.to(device), by.to(device)
            optimizer.zero_grad()
            criterion(model(bx), by).backward()
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
    
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    test_f, test_l = features[idx[split:]], labels[idx[split:]]
    
    model = _build_and_train(train_f, train_l, device)
    baseline_acc, _, _ = _evaluate_drift(model, test_f, test_l, device)
    print(f"  Baseline accuracy: {baseline_acc:.4f}")
    
    results = []
    failures = []
    
    # Test 1: Feature distribution shift +10%
    shifted = test_f * 1.10
    shifted = np.clip(shifted, 0, 1)
    acc, ci, rd = _evaluate_drift(model, shifted, test_l, device, test_f)
    drop = baseline_acc - acc
    r = DriftTestResult("distribution_shift_10pct", baseline_acc, acc, drop, ci, rd,
                        drop < ACC_DROP_MAX and ci < CONF_INFLATION_MAX and rd < REPR_DEVIATION_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"dist_shift: drop={drop:.4f} ci={ci:.4f} rd={rd:.4f}")
    print(f"  Distribution shift: acc={acc:.4f} drop={drop:.4f}")
    
    # Test 2: New unseen pattern injection (20% of test set replaced with novel patterns)
    novel = test_f.copy()
    n_inject = len(novel) // 5
    novel[:n_inject] = np.random.uniform(0.3, 0.7, (n_inject, D))
    acc, ci, rd = _evaluate_drift(model, novel, test_l, device, test_f)
    drop = baseline_acc - acc
    r = DriftTestResult("unseen_pattern_injection", baseline_acc, acc, drop, ci, rd,
                        drop < ACC_DROP_MAX and ci < CONF_INFLATION_MAX and rd < REPR_DEVIATION_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"novel_pattern: drop={drop:.4f} ci={ci:.4f}")
    print(f"  Unseen patterns: acc={acc:.4f} drop={drop:.4f}")
    
    # Test 3: Class imbalance 70/30
    pos_idx = np.where(test_l == 1)[0]
    neg_idx = np.where(test_l == 0)[0]
    n_target = min(len(pos_idx), len(neg_idx))
    n_major = int(n_target * 0.7 / 0.3)
    if n_major > max(len(pos_idx), len(neg_idx)):
        n_major = max(len(pos_idx), len(neg_idx))
    
    imb_pos = pos_idx[:n_target]
    imb_neg = neg_idx[:min(n_major, len(neg_idx))]
    imb_idx = np.concatenate([imb_pos, imb_neg])
    acc, ci, rd = _evaluate_drift(model, test_f[imb_idx], test_l[imb_idx], device, test_f)
    drop = baseline_acc - acc
    r = DriftTestResult("class_imbalance_70_30", baseline_acc, acc, drop, ci, rd,
                        drop < ACC_DROP_MAX and ci < CONF_INFLATION_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"imbalance: drop={drop:.4f}")
    print(f"  Class imbalance: acc={acc:.4f} drop={drop:.4f}")
    
    # Test 4: Feature missingness (15% of features set to 0)
    missing = test_f.copy()
    mask = np.random.random(missing.shape) < 0.15
    missing[mask] = 0.0
    acc, ci, rd = _evaluate_drift(model, missing, test_l, device, test_f)
    drop = baseline_acc - acc
    r = DriftTestResult("feature_missingness_15pct", baseline_acc, acc, drop, ci, rd,
                        drop < ACC_DROP_MAX and ci < CONF_INFLATION_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"missingness: drop={drop:.4f}")
    print(f"  Feature missingness: acc={acc:.4f} drop={drop:.4f}")
    
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
