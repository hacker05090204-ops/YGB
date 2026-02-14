"""
Phase 2: 5-Fold Cross Validation Protocol for MODE-B Gate.

REQUIREMENTS:
  Accuracy >= 95%
  ECE <= 0.02
  Brier <= 0.03
  Rare class recall >= 90%
  Confidence inflation <= 3%
  Fold variance <= 3%
"""
import sys
import os
import json
import math
from typing import Dict, List, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


# Thresholds
ACCURACY_MIN = 0.95
ECE_MAX = 0.02
BRIER_MAX = 0.03
RARE_RECALL_MIN = 0.90
CONFIDENCE_INFLATION_MAX = 0.03
FOLD_VARIANCE_MAX = 0.03


@dataclass
class FoldResult:
    fold: int
    accuracy: float
    precision: float
    recall: float
    f1: float
    rare_class_recall: float
    ece: float
    brier: float
    confidence_gap: float
    roc_auc: float


@dataclass 
class CrossValidationResult:
    passed: bool
    fold_results: List[FoldResult]
    summary: Dict[str, float]
    failures: List[str]
    timestamp: str


def _compute_ece(confidences: np.ndarray, accuracies: np.ndarray, 
                 predictions: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> float:
    """Expected Calibration Error."""
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (confidences >= bin_boundaries[i]) & (confidences < bin_boundaries[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = (predictions[mask] == labels[mask]).mean()
        bin_conf = confidences[mask].mean()
        ece += mask.sum() / len(labels) * abs(bin_acc - bin_conf)
    return float(ece)


def _compute_brier(probs: np.ndarray, labels: np.ndarray) -> float:
    """Brier Score for binary classification."""
    return float(np.mean((probs - labels) ** 2))


def _compute_roc_auc(probs: np.ndarray, labels: np.ndarray) -> float:
    """ROC-AUC via trapezoidal rule."""
    thresholds = np.linspace(0, 1, 200)
    tpr_list, fpr_list = [], []
    for t in thresholds:
        preds = (probs >= t).astype(int)
        tp = ((preds == 1) & (labels == 1)).sum()
        fp = ((preds == 1) & (labels == 0)).sum()
        fn = ((preds == 0) & (labels == 1)).sum()
        tn = ((preds == 0) & (labels == 0)).sum()
        tpr = tp / max(tp + fn, 1)
        fpr = fp / max(fp + tn, 1)
        tpr_list.append(tpr)
        fpr_list.append(fpr)
    # Sort by FPR for AUC
    pairs = sorted(zip(fpr_list, tpr_list))
    fpr_sorted = [p[0] for p in pairs]
    tpr_sorted = [p[1] for p in pairs]
    auc = np.trapz(tpr_sorted, fpr_sorted)
    return float(abs(auc))


def train_fold(train_features: np.ndarray, train_labels: np.ndarray,
               val_features: np.ndarray, val_labels: np.ndarray,
               fold: int, epochs: int = 15, lr: float = 0.001) -> FoldResult:
    """Train and evaluate one fold with hardened augmentation."""
    from backend.training.feature_bridge import (
        FeatureDiversifier, FeatureConfig, CalibrationEngine, DriftAugmenter,
    )
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    # Create model
    input_dim = train_features.shape[1]
    model = nn.Sequential(
        nn.Linear(input_dim, 512),
        nn.ReLU(),
        nn.Dropout(0.3),
        nn.Linear(512, 256),
        nn.ReLU(),
        nn.Dropout(0.2),
        nn.Linear(256, 128),
        nn.ReLU(),
        nn.Dropout(0.1),
        nn.Linear(128, 2),
    ).to(device)
    
    feat_config = FeatureConfig(seed=42 + fold, training=True)
    diversifier = FeatureDiversifier(feat_config)
    drift_aug = DriftAugmenter()
    cal_engine = CalibrationEngine()
    
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)
    criterion = nn.CrossEntropyLoss()
    batch_size = 256
    
    # Train with hardened augmentation
    model.train()
    for epoch in range(epochs):
        perm = np.random.permutation(len(train_labels))
        epoch_f = train_features[perm].copy()
        epoch_l = train_labels[perm].copy()
        
        # Epoch-level augmentation
        aug_seed = (42 + fold) ^ (epoch * 11111)
        epoch_f = drift_aug.apply_domain_randomization(epoch_f, scale_pct=0.10, seed=aug_seed)
        epoch_f = drift_aug.inject_novel_patterns(epoch_f, inject_rate=0.10, seed=aug_seed + 1)
        epoch_f = drift_aug.apply_correlated_noise(epoch_f, sigma=0.03, seed=aug_seed + 2)
        
        total_loss = 0
        n_batches = (len(epoch_l) + batch_size - 1) // batch_size
        for b in range(n_batches):
            start = b * batch_size
            end = min(start + batch_size, len(epoch_l))
            batch_f = epoch_f[start:end].copy()
            batch_l = epoch_l[start:end]
            
            # Per-batch augmentation
            batch_f = diversifier.apply_interaction_dropout(batch_f, epoch, b)
            batch_f = diversifier.apply_adversarial_scramble(batch_f, epoch, b)
            batch_f = diversifier.apply_noise_augmentation(batch_f, epoch, b)
            
            batch_x = torch.tensor(batch_f, dtype=torch.float32).to(device)
            batch_y = torch.tensor(batch_l, dtype=torch.long).to(device)
            optimizer.zero_grad()
            out = model(batch_x)
            loss = criterion(out, batch_y)
            
            # Calibration penalty
            with torch.no_grad():
                probs = torch.softmax(out, dim=1)
                confs = probs.max(dim=1).values
                correct = (out.argmax(dim=1) == batch_y).float()
                cal_penalty = cal_engine.compute_calibration_penalty(
                    confs.cpu().numpy(), correct.cpu().numpy()
                )
            
            total = loss + 0.2 * cal_penalty
            total.backward()
            optimizer.step()
            total_loss += loss.item()
        scheduler.step(total_loss / n_batches)
    
    # Evaluate
    model.eval()
    with torch.no_grad():
        val_x = torch.tensor(val_features, dtype=torch.float32).to(device)
        val_y = torch.tensor(val_labels, dtype=torch.long).to(device)
        logits = model(val_x)
        probs = torch.softmax(logits, dim=1).cpu().numpy()
        preds = logits.argmax(dim=1).cpu().numpy()
        val_labels_np = val_y.cpu().numpy()
    
    # Metrics
    confidences = probs.max(axis=1)
    pos_probs = probs[:, 1]
    
    tp = ((preds == 1) & (val_labels_np == 1)).sum()
    fp = ((preds == 1) & (val_labels_np == 0)).sum()
    fn = ((preds == 0) & (val_labels_np == 1)).sum()
    tn = ((preds == 0) & (val_labels_np == 0)).sum()
    
    accuracy = (tp + tn) / len(val_labels_np)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-10)
    
    # Rare class = whichever class is minority in this fold
    n_pos = (val_labels_np == 1).sum()
    n_neg = (val_labels_np == 0).sum()
    if n_pos <= n_neg:
        rare_recall = recall  # positive is minority
    else:
        rare_recall = tn / max(tn + fp, 1)  # negative is minority
    
    ece = _compute_ece(confidences, None, preds, val_labels_np)
    brier = _compute_brier(pos_probs, val_labels_np)
    confidence_gap = float(confidences.mean()) - accuracy
    roc_auc = _compute_roc_auc(pos_probs, val_labels_np)
    
    return FoldResult(
        fold=fold,
        accuracy=round(float(accuracy), 4),
        precision=round(float(precision), 4),
        recall=round(float(recall), 4),
        f1=round(float(f1), 4),
        rare_class_recall=round(float(rare_recall), 4),
        ece=round(float(ece), 4),
        brier=round(float(brier), 4),
        confidence_gap=round(float(confidence_gap), 4),
        roc_auc=round(float(roc_auc), 4),
    )


def run_cross_validation(features: np.ndarray, labels: np.ndarray,
                         n_folds: int = 5, epochs: int = 15) -> CrossValidationResult:
    """Run 5-fold cross validation."""
    N = len(labels)
    indices = np.arange(N)
    np.random.seed(42)
    np.random.shuffle(indices)
    
    fold_size = N // n_folds
    fold_results = []
    
    for fold in range(n_folds):
        val_start = fold * fold_size
        val_end = val_start + fold_size
        val_idx = indices[val_start:val_end]
        train_idx = np.concatenate([indices[:val_start], indices[val_end:]])
        
        print(f"  Fold {fold + 1}/{n_folds}: train={len(train_idx)}, val={len(val_idx)}")
        
        result = train_fold(
            features[train_idx], labels[train_idx],
            features[val_idx], labels[val_idx],
            fold=fold + 1, epochs=epochs,
        )
        fold_results.append(result)
        print(f"    Acc={result.accuracy:.4f} P={result.precision:.4f} "
              f"R={result.recall:.4f} F1={result.f1:.4f} ECE={result.ece:.4f} "
              f"Brier={result.brier:.4f} AUC={result.roc_auc:.4f}")
    
    # Aggregate
    accs = [r.accuracy for r in fold_results]
    summary = {
        "mean_accuracy": round(float(np.mean(accs)), 4),
        "std_accuracy": round(float(np.std(accs)), 4),
        "mean_precision": round(float(np.mean([r.precision for r in fold_results])), 4),
        "mean_recall": round(float(np.mean([r.recall for r in fold_results])), 4),
        "mean_f1": round(float(np.mean([r.f1 for r in fold_results])), 4),
        "mean_rare_recall": round(float(np.mean([r.rare_class_recall for r in fold_results])), 4),
        "mean_ece": round(float(np.mean([r.ece for r in fold_results])), 4),
        "mean_brier": round(float(np.mean([r.brier for r in fold_results])), 4),
        "mean_confidence_gap": round(float(np.mean([r.confidence_gap for r in fold_results])), 4),
        "mean_roc_auc": round(float(np.mean([r.roc_auc for r in fold_results])), 4),
        "fold_variance": round(float(np.var(accs)), 6),
    }
    
    # Check gates
    failures = []
    if summary["mean_accuracy"] < ACCURACY_MIN:
        failures.append(f"Accuracy {summary['mean_accuracy']:.4f} < {ACCURACY_MIN}")
    if summary["mean_ece"] > ECE_MAX:
        failures.append(f"ECE {summary['mean_ece']:.4f} > {ECE_MAX}")
    if summary["mean_brier"] > BRIER_MAX:
        failures.append(f"Brier {summary['mean_brier']:.4f} > {BRIER_MAX}")
    if summary["mean_rare_recall"] < RARE_RECALL_MIN:
        failures.append(f"Rare recall {summary['mean_rare_recall']:.4f} < {RARE_RECALL_MIN}")
    if summary["mean_confidence_gap"] > CONFIDENCE_INFLATION_MAX:
        failures.append(f"Confidence inflation {summary['mean_confidence_gap']:.4f} > {CONFIDENCE_INFLATION_MAX}")
    if summary["fold_variance"] > FOLD_VARIANCE_MAX:
        failures.append(f"Fold variance {summary['fold_variance']:.6f} > {FOLD_VARIANCE_MAX}")
    
    return CrossValidationResult(
        passed=len(failures) == 0,
        fold_results=fold_results,
        summary=summary,
        failures=failures,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def generate_cv_report(result: CrossValidationResult) -> str:
    lines = [
        "=" * 70,
        "  G38 MODE-B GATE -- PHASE 2: CROSS VALIDATION",
        "=" * 70,
        f"  Timestamp: {result.timestamp}",
        f"  Verdict: {'PASS' if result.passed else 'FAIL'}",
        "",
        "-" * 70,
        "  Per-Fold Results",
        "-" * 70,
        f"  {'Fold':>4} {'Acc':>7} {'Prec':>7} {'Rec':>7} {'F1':>7} "
        f"{'RareR':>7} {'ECE':>7} {'Brier':>7} {'AUC':>7}",
    ]
    for r in result.fold_results:
        lines.append(
            f"  {r.fold:4d} {r.accuracy:7.4f} {r.precision:7.4f} {r.recall:7.4f} "
            f"{r.f1:7.4f} {r.rare_class_recall:7.4f} {r.ece:7.4f} {r.brier:7.4f} "
            f"{r.roc_auc:7.4f}"
        )
    
    s = result.summary
    lines += [
        "",
        "-" * 70,
        "  Aggregate Summary",
        "-" * 70,
        f"  Mean Accuracy:        {s['mean_accuracy']:.4f}  (>= {ACCURACY_MIN})",
        f"  Mean ECE:             {s['mean_ece']:.4f}  (<= {ECE_MAX})",
        f"  Mean Brier:           {s['mean_brier']:.4f}  (<= {BRIER_MAX})",
        f"  Mean Rare Recall:     {s['mean_rare_recall']:.4f}  (>= {RARE_RECALL_MIN})",
        f"  Mean Confidence Gap:  {s['mean_confidence_gap']:.4f}  (<= {CONFIDENCE_INFLATION_MAX})",
        f"  Fold Variance:        {s['fold_variance']:.6f}  (<= {FOLD_VARIANCE_MAX})",
        f"  Mean ROC-AUC:         {s['mean_roc_auc']:.4f}",
    ]
    
    if result.failures:
        lines += ["", "-" * 70, "  FAILURES", "-" * 70]
        for f in result.failures:
            lines.append(f"  FAIL: {f}")
    
    lines += [
        "",
        "=" * 70,
        f"  PHASE 2 VERDICT: {'PASS' if result.passed else 'FAIL -- MODE-B BLOCKED'}",
        "=" * 70,
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    from impl_v1.training.data.scaled_dataset import DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    
    print("Loading dataset for cross-validation...")
    config = DatasetConfig(total_samples=18000)
    dataset = RealTrainingDataset(config=config)
    features = dataset._features_tensor.numpy()
    labels = dataset._labels_tensor.numpy()
    
    print(f"Dataset: {len(labels)} samples, {features.shape[1]} dims")
    print("Running 5-fold cross validation...")
    
    result = run_cross_validation(features, labels, n_folds=5, epochs=15)
    report = generate_cv_report(result)
    print(report)
    
    report_path = os.path.join(os.path.dirname(__file__), '..', '..', 
                               'reports', 'g38_training', 'phase2_cross_validation.txt')
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\nSaved: {report_path}")
    
    sys.exit(0 if result.passed else 1)
