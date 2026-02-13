"""
Phase 5: Rare Class Protection for MODE-B Gate.

For minority class:
  - Recall >= 90%
  - False Positive Rate
  - Calibration gap <= 0.03
  - Confidence entropy
"""
import sys, os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np
import torch
import torch.nn as nn

RARE_RECALL_MIN = 0.90
CALIBRATION_GAP_MAX = 0.03


@dataclass
class RareClassResult:
    passed: bool
    rare_class_label: int
    rare_class_count: int
    majority_class_count: int
    recall: float
    fpr: float
    calibration_gap: float
    confidence_entropy: float
    failures: List[str]
    timestamp: str


def run_rare_class_test(features: np.ndarray, labels: np.ndarray) -> RareClassResult:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    N, D = features.shape
    np.random.seed(42)
    
    # Create imbalanced split — make minority class 20% of test set
    pos_idx = np.where(labels == 1)[0]
    neg_idx = np.where(labels == 0)[0]
    
    # Train on balanced, test with imbalance
    n_train = int(0.8 * N)
    idx = np.random.permutation(N)
    train_f, train_l = features[idx[:n_train]], labels[idx[:n_train]]
    test_f, test_l = features[idx[n_train:]], labels[idx[n_train:]]
    
    # Identify rare class in test set
    test_pos = (test_l == 1).sum()
    test_neg = (test_l == 0).sum()
    rare_label = 1 if test_pos <= test_neg else 0
    rare_count = min(test_pos, test_neg)
    majority_count = max(test_pos, test_neg)
    
    # Train model
    model = nn.Sequential(
        nn.Linear(D, 512), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(256, 128), nn.ReLU(), nn.Dropout(0.1),
        nn.Linear(128, 2),
    ).to(device)
    
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()
    ds = torch.utils.data.TensorDataset(
        torch.tensor(train_f, dtype=torch.float32),
        torch.tensor(train_l, dtype=torch.long),
    )
    loader = torch.utils.data.DataLoader(ds, batch_size=256, shuffle=True)
    model.train()
    for _ in range(15):
        for bx, by in loader:
            bx, by = bx.to(device), by.to(device)
            optimizer.zero_grad()
            criterion(model(bx), by).backward()
            optimizer.step()
    
    # Evaluate
    model.eval()
    with torch.no_grad():
        x = torch.tensor(test_f, dtype=torch.float32).to(device)
        logits = model(x)
        probs = torch.softmax(logits, dim=1).cpu().numpy()
        preds = logits.argmax(dim=1).cpu().numpy()
    
    # Rare class metrics
    rare_mask = test_l == rare_label
    rare_preds = preds[rare_mask]
    rare_true = test_l[rare_mask]
    recall = (rare_preds == rare_true).mean()
    
    # FPR: predicted as rare but actually majority
    majority_mask = test_l != rare_label
    fpr = (preds[majority_mask] == rare_label).mean()
    
    # Calibration gap for rare class
    rare_confidences = probs[rare_mask].max(axis=1)
    rare_accuracy = (rare_preds == rare_true).mean()
    calibration_gap = abs(float(rare_confidences.mean()) - float(rare_accuracy))
    
    # Confidence entropy
    rare_probs_pos = probs[rare_mask, rare_label]
    entropy = -np.mean(rare_probs_pos * np.log(rare_probs_pos + 1e-10) + 
                       (1 - rare_probs_pos) * np.log(1 - rare_probs_pos + 1e-10))
    
    failures = []
    if recall < RARE_RECALL_MIN:
        failures.append(f"Rare recall {recall:.4f} < {RARE_RECALL_MIN}")
    if calibration_gap > CALIBRATION_GAP_MAX:
        failures.append(f"Calibration gap {calibration_gap:.4f} > {CALIBRATION_GAP_MAX}")
    
    return RareClassResult(
        passed=len(failures) == 0,
        rare_class_label=int(rare_label),
        rare_class_count=int(rare_count),
        majority_class_count=int(majority_count),
        recall=round(float(recall), 4),
        fpr=round(float(fpr), 4),
        calibration_gap=round(float(calibration_gap), 4),
        confidence_entropy=round(float(entropy), 4),
        failures=failures,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def generate_rare_report(r: RareClassResult) -> str:
    lines = [
        "=" * 70,
        "  G38 MODE-B GATE -- PHASE 5: RARE CLASS PROTECTION",
        "=" * 70,
        f"  Verdict: {'PASS' if r.passed else 'FAIL'}",
        f"  Rare Class Label:      {r.rare_class_label}",
        f"  Rare Class Count:      {r.rare_class_count}",
        f"  Majority Class Count:  {r.majority_class_count}",
        f"  Recall:                {r.recall:.4f}  (>= {RARE_RECALL_MIN})",
        f"  False Positive Rate:   {r.fpr:.4f}",
        f"  Calibration Gap:       {r.calibration_gap:.4f}  (<= {CALIBRATION_GAP_MAX})",
        f"  Confidence Entropy:    {r.confidence_entropy:.4f}",
    ]
    if r.failures:
        lines += ["", "  FAILURES:"]
        for f in r.failures:
            lines.append(f"    {f}")
    lines += [
        "",
        "=" * 70,
        f"  PHASE 5 VERDICT: {'PASS' if r.passed else 'FAIL -- MODE-B BLOCKED'}",
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
    print(f"Rare class test: {len(labels)} samples")
    result = run_rare_class_test(features, labels)
    report = generate_rare_report(result)
    print(report)
    rp = os.path.join(os.path.dirname(__file__), '..', '..', 'reports', 'g38_training', 'phase5_rare_class.txt')
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, 'w', encoding='utf-8') as f:
        f.write(report)
    sys.exit(0 if result.passed else 1)
