"""
Phase 3: Generalization Stress Test for MODE-B Gate.

Adversarial perturbation tests:
  1) Boundary noise (0.45-0.55 signal region)
  2) Feature scaling +/-15%
  3) Random feature masking
  4) Interaction scrambling
  5) Correlated noise injection
  6) Shuffled non-label features

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

ACCURACY_DROP_MAX = 0.05
CALIBRATION_SHIFT_MAX = 0.02


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
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
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
            loss = criterion(model(bx), by)
            loss.backward()
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
    
    # --- Test 1: Boundary noise (0.45-0.55 signal) ---
    stressed = test_f.copy()
    for i in range(len(stressed)):
        stressed[i, :64] = np.clip(stressed[i, :64] + np.random.uniform(-0.05, 0.05, 64), 0, 1)
        stressed[i, :64] = np.clip(stressed[i, :64], 0.35, 0.65)
    acc, ece, abst = _evaluate(model, stressed, test_l, device)
    drop = baseline_acc - acc
    shift = abs(ece - baseline_ece)
    r = StressResult("boundary_noise", baseline_acc, acc, drop, shift, abst, 
                     drop < ACCURACY_DROP_MAX and shift < CALIBRATION_SHIFT_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"boundary_noise: drop={drop:.4f} shift={shift:.4f}")
    print(f"  Boundary noise: acc={acc:.4f} drop={drop:.4f}")
    
    # --- Test 2: Feature scaling +/-15% ---
    stressed = test_f.copy() * np.random.uniform(0.85, 1.15, (1, D))
    stressed = np.clip(stressed, 0, 1)
    acc, ece, abst = _evaluate(model, stressed, test_l, device)
    drop = baseline_acc - acc
    shift = abs(ece - baseline_ece)
    r = StressResult("feature_scaling", baseline_acc, acc, drop, shift, abst,
                     drop < ACCURACY_DROP_MAX and shift < CALIBRATION_SHIFT_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"feature_scaling: drop={drop:.4f} shift={shift:.4f}")
    print(f"  Feature scaling: acc={acc:.4f} drop={drop:.4f}")
    
    # --- Test 3: Random feature masking (10% of dims) ---
    stressed = test_f.copy()
    mask_dims = np.random.choice(D, D // 10, replace=False)
    stressed[:, mask_dims] = 0.0
    acc, ece, abst = _evaluate(model, stressed, test_l, device)
    drop = baseline_acc - acc
    shift = abs(ece - baseline_ece)
    r = StressResult("feature_masking", baseline_acc, acc, drop, shift, abst,
                     drop < ACCURACY_DROP_MAX and shift < CALIBRATION_SHIFT_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"feature_masking: drop={drop:.4f} shift={shift:.4f}")
    print(f"  Feature masking: acc={acc:.4f} drop={drop:.4f}")
    
    # --- Test 4: Interaction scrambling ---
    stressed = test_f.copy()
    np.random.shuffle(stressed[:, 128:192])  # Shuffle interaction dims
    acc, ece, abst = _evaluate(model, stressed, test_l, device)
    drop = baseline_acc - acc
    shift = abs(ece - baseline_ece)
    r = StressResult("interaction_scramble", baseline_acc, acc, drop, shift, abst,
                     drop < ACCURACY_DROP_MAX and shift < CALIBRATION_SHIFT_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"interaction_scramble: drop={drop:.4f} shift={shift:.4f}")
    print(f"  Interaction scramble: acc={acc:.4f} drop={drop:.4f}")
    
    # --- Test 5: Correlated noise injection ---
    noise = np.random.randn(*test_f.shape) * 0.1
    noise[:, :64] *= (test_f[:, :64] + 0.1)  # Noise correlated with signal
    stressed = np.clip(test_f + noise, 0, 1)
    acc, ece, abst = _evaluate(model, stressed, test_l, device)
    drop = baseline_acc - acc
    shift = abs(ece - baseline_ece)
    r = StressResult("correlated_noise", baseline_acc, acc, drop, shift, abst,
                     drop < ACCURACY_DROP_MAX and shift < CALIBRATION_SHIFT_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"correlated_noise: drop={drop:.4f} shift={shift:.4f}")
    print(f"  Correlated noise: acc={acc:.4f} drop={drop:.4f}")
    
    # --- Test 6: Shuffle non-label features (noise dims) ---
    stressed = test_f.copy()
    for d in range(192, 256):
        np.random.shuffle(stressed[:, d])
    acc, ece, abst = _evaluate(model, stressed, test_l, device)
    drop = baseline_acc - acc
    shift = abs(ece - baseline_ece)
    r = StressResult("shuffle_noise_dims", baseline_acc, acc, drop, shift, abst,
                     drop < ACCURACY_DROP_MAX and shift < CALIBRATION_SHIFT_MAX)
    results.append(r)
    if not r.passed:
        failures.append(f"shuffle_noise_dims: drop={drop:.4f} shift={shift:.4f}")
    print(f"  Shuffle noise: acc={acc:.4f} drop={drop:.4f}")
    
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
