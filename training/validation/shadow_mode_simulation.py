"""
Phase 7: Shadow Mode Simulation for MODE-B Gate.

Simulate 1000 decisions:
  AI outputs confidence, representation score, abstain flag.
  Simulate human ground truth.

Requirements:
  Agreement >= 97%
  Rare class delta < 5%
  Abstention when confidence < 70%
"""
import sys, os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import numpy as np
import torch
import torch.nn as nn

AGREEMENT_MIN = 0.97
RARE_DELTA_MAX = 0.05
ABSTENTION_THRESHOLD = 0.70


@dataclass
class ShadowModeResult:
    passed: bool
    total_decisions: int
    agreement_rate: float
    rare_class_agreement: float
    rare_class_delta: float
    abstention_rate: float
    abstentions_correct: float  # % of abstentions that were actually hard cases
    misclass_with_high_conf: int
    failures: List[str]
    timestamp: str


def run_shadow_mode(features: np.ndarray, labels: np.ndarray, 
                    n_decisions: int = 1000) -> ShadowModeResult:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    N, D = features.shape
    np.random.seed(42)
    
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    
    # Use remaining as shadow test pool
    test_idx = idx[split:]
    if len(test_idx) > n_decisions:
        test_idx = test_idx[:n_decisions]
    test_f = features[test_idx]
    test_l = labels[test_idx]
    actual_decisions = len(test_l)
    
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
    
    # Shadow mode evaluation
    model.eval()
    with torch.no_grad():
        x = torch.tensor(test_f, dtype=torch.float32).to(device)
        logits = model(x)
        probs = torch.softmax(logits, dim=1).cpu().numpy()
        preds = logits.argmax(dim=1).cpu().numpy()
    
    confidences = probs.max(axis=1)
    
    # Ground truth = actual labels (simulating human decisions)
    human_truth = test_l
    
    # AI decisions: abstain when confidence < threshold
    abstain_mask = confidences < ABSTENTION_THRESHOLD
    decide_mask = ~abstain_mask
    
    # Agreement on non-abstained decisions
    if decide_mask.sum() > 0:
        agreement = (preds[decide_mask] == human_truth[decide_mask]).mean()
    else:
        agreement = 0.0
    
    # Rare class analysis
    pos_mask = human_truth == 1
    neg_mask = human_truth == 0
    n_pos = pos_mask.sum()
    n_neg = neg_mask.sum()
    rare_mask = pos_mask if n_pos <= n_neg else neg_mask
    rare_decide = rare_mask & decide_mask
    
    if rare_decide.sum() > 0:
        rare_agreement = (preds[rare_decide] == human_truth[rare_decide]).mean()
    else:
        rare_agreement = 0.0
    rare_delta = abs(float(agreement) - float(rare_agreement))
    
    # Abstention quality
    abstention_rate = float(abstain_mask.mean())
    if abstain_mask.sum() > 0:
        # How many abstentions were on samples the model would have gotten wrong?
        abstentions_correct = (preds[abstain_mask] != human_truth[abstain_mask]).mean()
    else:
        abstentions_correct = 0.0
    
    # Misclassifications with high confidence
    misclass = (preds != human_truth) & (confidences >= 0.9)
    misclass_high_conf = int(misclass.sum())
    
    failures = []
    if agreement < AGREEMENT_MIN:
        failures.append(f"Agreement {agreement:.4f} < {AGREEMENT_MIN}")
    if rare_delta > RARE_DELTA_MAX:
        failures.append(f"Rare class delta {rare_delta:.4f} > {RARE_DELTA_MAX}")
    # Check abstention logic
    if abstention_rate < 0.001 and (preds != human_truth).sum() > 0:
        failures.append("No abstentions despite misclassifications")
    
    return ShadowModeResult(
        passed=len(failures) == 0,
        total_decisions=actual_decisions,
        agreement_rate=round(float(agreement), 4),
        rare_class_agreement=round(float(rare_agreement), 4),
        rare_class_delta=round(float(rare_delta), 4),
        abstention_rate=round(float(abstention_rate), 4),
        abstentions_correct=round(float(abstentions_correct), 4),
        misclass_with_high_conf=misclass_high_conf,
        failures=failures,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def generate_shadow_report(r: ShadowModeResult) -> str:
    lines = [
        "=" * 70,
        "  G38 MODE-B GATE -- PHASE 7: SHADOW MODE SIMULATION",
        "=" * 70,
        f"  Verdict: {'PASS' if r.passed else 'FAIL'}",
        f"  Total Decisions:          {r.total_decisions}",
        f"  Agreement Rate:           {r.agreement_rate:.4f}  (>= {AGREEMENT_MIN})",
        f"  Rare Class Agreement:     {r.rare_class_agreement:.4f}",
        f"  Rare Class Delta:         {r.rare_class_delta:.4f}  (< {RARE_DELTA_MAX})",
        f"  Abstention Rate:          {r.abstention_rate:.4f}",
        f"  Abstentions Correct:      {r.abstentions_correct:.4f}",
        f"  Misclass w/ High Conf:    {r.misclass_with_high_conf}",
    ]
    if r.failures:
        lines += ["", "  FAILURES:"]
        for f in r.failures:
            lines.append(f"    {f}")
    lines += [
        "", "=" * 70,
        f"  PHASE 7 VERDICT: {'PASS' if r.passed else 'FAIL -- MODE-B BLOCKED'}",
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
    print(f"Shadow mode: {len(labels)} samples, 1000 decisions")
    result = run_shadow_mode(features, labels, n_decisions=1000)
    report = generate_shadow_report(result)
    print(report)
    rp = os.path.join(os.path.dirname(__file__), '..', '..', 'reports', 'g38_training', 'phase7_shadow_mode.txt')
    os.makedirs(os.path.dirname(rp), exist_ok=True)
    with open(rp, 'w', encoding='utf-8') as f:
        f.write(report)
    sys.exit(0 if result.passed else 1)
