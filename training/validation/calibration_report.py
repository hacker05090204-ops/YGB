"""
Phase 4: Calibration Proof for MODE-B Gate.

Generate:
  - Reliability diagram data
  - Confidence histogram
  - Per-bin accuracy
  - ECE calculation
  - Temperature scaling test
  - Calibration drift across epochs

Reject MODE-B if:
  Confidence inflation > 3%
  Overconfidence spikes exist
  Confidence not monotonic with correctness
"""
import sys, os, json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np
import torch
import torch.nn as nn

CONFIDENCE_INFLATION_MAX = 0.03


@dataclass
class CalibrationBin:
    bin_lower: float
    bin_upper: float
    samples: int
    mean_confidence: float
    mean_accuracy: float
    gap: float


@dataclass
class CalibrationResult:
    passed: bool
    ece: float
    mce: float  # Max Calibration Error
    confidence_inflation: float
    bins: List[CalibrationBin]
    temperature: float
    ece_after_temp: float
    overconfidence_spikes: int
    monotonic: bool
    failures: List[str]
    timestamp: str


def _build_model(input_dim, device):
    return nn.Sequential(
        nn.Linear(input_dim, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    ).to(device)


def _train_and_get_logits(features, labels, device, epochs=15):
    N = len(labels)
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    val_f, val_l = features[idx[split:]], labels[idx[split:]]
    
    model = _build_model(features.shape[1], device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    ds = torch.utils.data.TensorDataset(
        torch.tensor(train_f, dtype=torch.float32),
        torch.tensor(train_l, dtype=torch.long),
    )
    loader = torch.utils.data.DataLoader(ds, batch_size=256, shuffle=True)
    
    model.train()
    for _ in range(epochs):
        for bx, by in loader:
            bx, by = bx.to(device), by.to(device)
            optimizer.zero_grad()
            criterion(model(bx), by).backward()
            optimizer.step()
    
    model.eval()
    with torch.no_grad():
        vx = torch.tensor(val_f, dtype=torch.float32).to(device)
        logits = model(vx).cpu()
    
    return logits.numpy(), val_l, model


def _find_temperature(logits, labels, lr=0.01, max_iter=100):
    """Find optimal temperature via NLL minimization."""
    temp = 1.0
    logits_t = torch.tensor(logits, dtype=torch.float32)
    labels_t = torch.tensor(labels, dtype=torch.long)
    
    for _ in range(max_iter):
        scaled = logits_t / temp
        probs = torch.softmax(scaled, dim=1)
        nll = -torch.log(probs[range(len(labels_t)), labels_t] + 1e-10).mean()
        
        # Gradient approximation
        temp_up = temp + 0.01
        scaled_up = logits_t / temp_up
        probs_up = torch.softmax(scaled_up, dim=1)
        nll_up = -torch.log(probs_up[range(len(labels_t)), labels_t] + 1e-10).mean()
        
        grad = (nll_up - nll) / 0.01
        temp -= lr * grad.item()
        temp = max(0.1, min(10.0, temp))
    
    return temp


def run_calibration(features: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> CalibrationResult:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    np.random.seed(42)
    
    logits, val_labels, model = _train_and_get_logits(features, labels, device)
    probs = np.exp(logits) / np.exp(logits).sum(axis=1, keepdims=True)
    confidences = probs.max(axis=1)
    preds = logits.argmax(axis=1)
    overall_acc = (preds == val_labels).mean()
    
    # Per-bin analysis
    bins = []
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    mce = 0.0
    overconfidence_spikes = 0
    
    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (confidences >= lo) & (confidences < hi)
        n = int(mask.sum())
        if n == 0:
            bins.append(CalibrationBin(lo, hi, 0, 0, 0, 0))
            continue
        
        mean_conf = float(confidences[mask].mean())
        mean_acc = float((preds[mask] == val_labels[mask]).mean())
        gap = mean_conf - mean_acc
        
        ece += (n / len(val_labels)) * abs(gap)
        mce = max(mce, abs(gap))
        
        if gap > 0.1:
            overconfidence_spikes += 1
        
        bins.append(CalibrationBin(
            round(lo, 3), round(hi, 3), n,
            round(mean_conf, 4), round(mean_acc, 4), round(gap, 4)
        ))
    
    # Confidence inflation
    confidence_inflation = float(confidences.mean()) - float(overall_acc)
    
    # Monotonicity check — accuracy should increase with confidence
    nonempty_bins = [b for b in bins if b.samples > 0]
    monotonic = all(
        nonempty_bins[i].mean_accuracy <= nonempty_bins[i+1].mean_accuracy
        for i in range(len(nonempty_bins) - 1)
    ) if len(nonempty_bins) > 1 else True
    
    # Temperature scaling
    temp = _find_temperature(logits, val_labels)
    scaled_logits = logits / temp
    scaled_probs = np.exp(scaled_logits) / np.exp(scaled_logits).sum(axis=1, keepdims=True)
    scaled_conf = scaled_probs.max(axis=1)
    scaled_preds = scaled_logits.argmax(axis=1)
    ece_after = 0.0
    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (scaled_conf >= lo) & (scaled_conf < hi)
        if mask.sum() > 0:
            ece_after += mask.sum() / len(val_labels) * abs(
                (scaled_preds[mask] == val_labels[mask]).mean() - scaled_conf[mask].mean()
            )
    
    # Failures
    failures = []
    if confidence_inflation > CONFIDENCE_INFLATION_MAX:
        failures.append(f"Confidence inflation {confidence_inflation:.4f} > {CONFIDENCE_INFLATION_MAX}")
    if overconfidence_spikes > 0:
        failures.append(f"Overconfidence spikes: {overconfidence_spikes} bins with gap > 0.1")
    if not monotonic:
        failures.append("Confidence not monotonic with correctness")
    
    return CalibrationResult(
        passed=len(failures) == 0,
        ece=round(float(ece), 4),
        mce=round(float(mce), 4),
        confidence_inflation=round(float(confidence_inflation), 4),
        bins=bins,
        temperature=round(temp, 4),
        ece_after_temp=round(float(ece_after), 4),
        overconfidence_spikes=overconfidence_spikes,
        monotonic=monotonic,
        failures=failures,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def generate_calibration_report(r: CalibrationResult) -> str:
    lines = [
        "=" * 70,
        "  G38 MODE-B GATE -- PHASE 4: CALIBRATION PROOF",
        "=" * 70,
        f"  Verdict: {'PASS' if r.passed else 'FAIL'}",
        f"  ECE: {r.ece:.4f}",
        f"  MCE (Max Cal Error): {r.mce:.4f}",
        f"  Confidence Inflation: {r.confidence_inflation:.4f}",
        f"  Overconfidence Spikes: {r.overconfidence_spikes}",
        f"  Monotonic: {'YES' if r.monotonic else 'NO'}",
        f"  Temperature (optimal): {r.temperature:.4f}",
        f"  ECE after temp scaling: {r.ece_after_temp:.4f}",
        "",
        "  Reliability Diagram:",
        f"  {'Bin':>12} {'Samples':>8} {'Conf':>7} {'Acc':>7} {'Gap':>7}",
    ]
    for b in r.bins:
        if b.samples > 0:
            lines.append(
                f"  [{b.bin_lower:.2f}-{b.bin_upper:.2f}] {b.samples:8d} "
                f"{b.mean_confidence:7.4f} {b.mean_accuracy:7.4f} {b.gap:+7.4f}"
            )
    if r.failures:
        lines += ["", "  FAILURES:"]
        for f in r.failures:
            lines.append(f"    {f}")
    lines += [
        "",
        "=" * 70,
        f"  PHASE 4 VERDICT: {'PASS' if r.passed else 'FAIL -- MODE-B BLOCKED'}",
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
    
    print(f"Calibration test: {len(labels)} samples")
    result = run_calibration(features, labels)
    report = generate_calibration_report(result)
    print(report)
    
    rp = os.path.join(os.path.dirname(__file__), '..', '..', 'reports', 'g38_training', 'phase4_calibration.txt')
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, 'w', encoding='utf-8') as f:
        f.write(report)
    sys.exit(0 if result.passed else 1)
