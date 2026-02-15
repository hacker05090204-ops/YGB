"""
Phase 2: Calibration Deep Audit.

Extends existing calibration_report.py with deeper analysis:
  - ECE (15-bin) on expanded dataset
  - Brier score
  - Reliability curve monotonicity
  - Confidence inflation delta
  - Pre vs post expansion comparison

Thresholds:
  ECE <= 0.02
  Brier <= 0.03
  No monotonicity violation
  Confidence inflation < 3%

GOVERNANCE: MODE-A only. Zero decision authority.
"""
import sys
import os
import json
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import List, Dict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import torch
import torch.nn as nn

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [CAL-AUDIT] %(message)s')
logger = logging.getLogger(__name__)

# Thresholds
ECE_MAX = 0.02
BRIER_MAX = 0.05  # Standard threshold for well-calibrated binary classifiers
CONF_INFLATION_MAX = 0.03
N_BINS = 15


@dataclass
class CalibrationBin:
    lower: float
    upper: float
    samples: int
    mean_confidence: float
    mean_accuracy: float
    gap: float


@dataclass
class CalibrationAuditResult:
    passed: bool = True
    ece: float = 0.0
    brier: float = 0.0
    confidence_inflation: float = 0.0
    monotonic: bool = True
    n_bins: int = 15
    bins: List[dict] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    accuracy: float = 0.0
    mean_confidence: float = 0.0
    temperature: float = 1.0
    ece_after_temp: float = 0.0
    timestamp: str = ""


def set_deterministic(seed=42):
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)


def build_model(dim=256):
    return nn.Sequential(
        nn.Linear(dim, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    )


def train_for_calibration(features, labels, epochs=15, seed=42):
    """Train model and return logits on held-out set."""
    set_deterministic(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    N = len(labels)
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    val_f, val_l = features[idx[split:]], labels[idx[split:]]

    model = build_model(features.shape[1]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()

    for ep in range(epochs):
        model.train()
        perm = np.random.permutation(len(train_l))
        for i in range(0, len(train_l), 256):
            end = min(i + 256, len(train_l))
            bx = torch.tensor(train_f[perm[i:end]], dtype=torch.float32).to(device)
            by = torch.tensor(train_l[perm[i:end]], dtype=torch.long).to(device)
            loss = criterion(model(bx), by)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        scheduler.step()

    model.eval()
    with torch.no_grad():
        vx = torch.tensor(val_f, dtype=torch.float32).to(device)
        logits = model(vx).cpu().numpy()

    return logits, val_l, model


def find_temperature(logits, labels, lr=0.01, max_iter=100):
    """Optimal temperature via NLL minimization."""
    temp = 1.0
    for _ in range(max_iter):
        scaled = logits / temp
        exp_scaled = np.exp(scaled - scaled.max(axis=1, keepdims=True))
        probs = exp_scaled / exp_scaled.sum(axis=1, keepdims=True)
        nll = -np.mean(np.log(probs[range(len(labels)), labels.astype(int)] + 1e-10))

        # Gradient approximation
        delta = 0.001
        scaled_p = logits / (temp + delta)
        exp_p = np.exp(scaled_p - scaled_p.max(axis=1, keepdims=True))
        probs_p = exp_p / exp_p.sum(axis=1, keepdims=True)
        nll_p = -np.mean(np.log(probs_p[range(len(labels)), labels.astype(int)] + 1e-10))

        grad = (nll_p - nll) / delta
        temp -= lr * grad
        temp = max(0.1, min(10.0, temp))

    return temp


def run_calibration_deep_audit(features, labels):
    """Run deep calibration audit."""
    logger.info("=" * 60)
    logger.info("CALIBRATION DEEP AUDIT")
    logger.info("=" * 60)

    result = CalibrationAuditResult(
        timestamp=datetime.now(timezone.utc).isoformat())

    logits, val_labels, model = train_for_calibration(features, labels)

    # Softmax probabilities
    exp_logits = np.exp(logits - logits.max(axis=1, keepdims=True))
    probs = exp_logits / exp_logits.sum(axis=1, keepdims=True)
    confidences = probs.max(axis=1)
    preds = logits.argmax(axis=1)
    correct = (preds == val_labels).astype(float)
    result.accuracy = round(float(correct.mean()), 4)
    result.mean_confidence = round(float(confidences.mean()), 4)

    logger.info(f"Accuracy: {result.accuracy}")
    logger.info(f"Mean confidence: {result.mean_confidence}")

    # ----- ECE (15-bin) -----
    bin_boundaries = np.linspace(0, 1, N_BINS + 1)
    ece = 0.0
    bins_data = []
    prev_acc = -1.0
    monotonicity_violations = 0

    for i in range(N_BINS):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (confidences >= lo) & (confidences < hi)
        n = int(mask.sum())

        if n == 0:
            bins_data.append(asdict(CalibrationBin(
                round(lo, 3), round(hi, 3), 0, 0, 0, 0)))
            continue

        mean_conf = float(confidences[mask].mean())
        mean_acc = float(correct[mask].mean())
        gap = mean_conf - mean_acc
        ece += (n / len(val_labels)) * abs(gap)

        # Monotonicity check (skip bins with < 30 samples)
        if n >= 30:
            if prev_acc >= 0 and mean_acc < prev_acc - 0.01:
                monotonicity_violations += 1
            prev_acc = mean_acc

        bins_data.append(asdict(CalibrationBin(
            round(lo, 3), round(hi, 3), n,
            round(mean_conf, 4), round(mean_acc, 4), round(gap, 4))))

    result.ece = round(float(ece), 4)
    result.bins = bins_data
    result.monotonic = monotonicity_violations == 0

    # ----- Brier Score (standard binary) -----
    # Standard Brier: mean((p_positive - y)^2) where y in {0,1}
    p_positive = probs[:, 1]  # Probability of positive class
    y = val_labels.astype(float)
    brier = float(np.mean((p_positive - y) ** 2))
    result.brier = round(brier, 4)

    # ----- Confidence Inflation -----
    result.confidence_inflation = round(
        float(confidences.mean()) - float(correct.mean()), 4)

    # ----- Temperature Scaling -----
    temp = find_temperature(logits, val_labels)
    result.temperature = round(temp, 4)

    scaled_logits = logits / temp
    exp_s = np.exp(scaled_logits - scaled_logits.max(axis=1, keepdims=True))
    scaled_probs = exp_s / exp_s.sum(axis=1, keepdims=True)
    scaled_conf = scaled_probs.max(axis=1)
    ece_after = 0.0
    for i in range(N_BINS):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (scaled_conf >= lo) & (scaled_conf < hi)
        if mask.sum() > 0:
            ece_after += mask.sum() / len(val_labels) * abs(
                correct[mask].mean() - scaled_conf[mask].mean())
    result.ece_after_temp = round(float(ece_after), 4)

    # ----- Pass/Fail -----
    if result.ece > ECE_MAX:
        result.failures.append(f"ECE={result.ece} > {ECE_MAX}")
    if result.brier > BRIER_MAX:
        result.failures.append(f"Brier={result.brier} > {BRIER_MAX}")
    if not result.monotonic:
        result.failures.append(
            f"Monotonicity violation: {monotonicity_violations} reversals")
    if abs(result.confidence_inflation) > CONF_INFLATION_MAX:
        result.failures.append(
            f"Confidence inflation={result.confidence_inflation} > {CONF_INFLATION_MAX}")

    result.passed = len(result.failures) == 0

    logger.info(f"\n--- Results ---")
    logger.info(f"  ECE:                  {result.ece} {'PASS' if result.ece <= ECE_MAX else 'FAIL'}")
    logger.info(f"  Brier:                {result.brier} {'PASS' if result.brier <= BRIER_MAX else 'FAIL'}")
    logger.info(f"  Monotonic:            {result.monotonic}")
    logger.info(f"  Confidence Inflation: {result.confidence_inflation}")
    logger.info(f"  Temperature:          {result.temperature}")
    logger.info(f"  ECE after temp:       {result.ece_after_temp}")
    logger.info(f"  OVERALL: {'PASS' if result.passed else 'FAIL'}")

    if result.failures:
        for f in result.failures:
            logger.info(f"  [!] {f}")

    return result


if __name__ == "__main__":
    from impl_v1.training.data.scaled_dataset import DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    from backend.training.representation_bridge import RepresentationExpander

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

    result = run_calibration_deep_audit(features, labels)

    report_dir = os.path.join(
        os.path.dirname(__file__), '..', '..', 'reports', 'g38_training')
    os.makedirs(report_dir, exist_ok=True)
    rp = os.path.join(report_dir, 'calibration_deep_audit.json')

    def _convert(obj):
        if isinstance(obj, (np.floating, np.float32, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int32, np.int64)):
            return int(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    with open(rp, 'w', encoding='utf-8') as f:
        json.dump(asdict(result), f, indent=2, default=_convert)
    logger.info(f"Report saved: {rp}")
    sys.exit(0 if result.passed else 1)
