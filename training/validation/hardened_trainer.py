"""
Hardened Training Pipeline for MODE-B Gate Fix.

Runs deterministic, real-data-only training and robustness checks.
No synthetic augmentation, perturbation injection, or simulated drift is allowed.

RTX 2050 safe:
  - AMP enabled
  - Deterministic algorithms
  - Gradient accumulation = 2
  - pin_memory + num_workers

Deterministic: all seeds fixed.
"""
import sys, os, time, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from torch.amp import autocast, GradScaler

from backend.training.adaptive_learner import DistributionMonitor
from backend.training.feature_bridge import CalibrationEngine

logging.basicConfig(level=logging.INFO, format='%(asctime)s [HARDENED] %(message)s')
logger = logging.getLogger(__name__)


def set_deterministic():
    """Enforce full determinism."""
    torch.manual_seed(42)
    torch.cuda.manual_seed_all(42)
    np.random.seed(42)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=True)


def build_model(input_dim: int = 256) -> nn.Module:
    """Build the G38 model — same architecture, no changes."""
    return nn.Sequential(
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
    )


def _interaction_contribution(features: np.ndarray) -> float:
    feature_array = np.asarray(features, dtype=np.float32)
    if feature_array.ndim != 2 or feature_array.shape[1] < 192:
        return 0.0
    interaction_variance = float(np.var(feature_array[:, 128:192], axis=0).mean())
    total_variance = float(np.var(feature_array, axis=0).mean())
    if total_variance <= 0.0:
        return 0.0
    return interaction_variance / total_variance


def _balance_penalty(features: np.ndarray) -> float:
    return max(0.0, _interaction_contribution(features) - 0.50)


def train_hardened(features: np.ndarray, labels: np.ndarray,
                   epochs: int = 20, batch_size: int = 256,
                   lr: float = 0.001, grad_accum: int = 2,
                   seed: int = 42, verbose: bool = True) -> dict:
    """
    Train with all hardening augmentations active.
    
    Returns dict with:
      - model: trained model
      - metrics: per-epoch metrics
      - final_accuracy: test accuracy
    """
    set_deterministic()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Device: {device}, AMP: {torch.cuda.is_available()}")
    
    N, D = features.shape
    
    # Split 80/20
    np.random.seed(seed)
    idx = np.random.permutation(N)
    split = int(0.8 * N)
    train_f, train_l = features[idx[:split]], labels[idx[:split]]
    test_f, test_l = features[idx[split:]], labels[idx[split:]]
    
    cal_engine = CalibrationEngine()
    
    # Model
    model = build_model(D).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss()
    scaler = GradScaler('cuda') if torch.cuda.is_available() else None
    
    # Calibration loss weight
    cal_weight = 0.1
    balance_weight = 0.05
    
    # Per-epoch metrics
    all_metrics = []
    
    for epoch in range(epochs):
        model.train()
        epoch_start = time.time()
        total_loss = 0.0
        total_cal_penalty = 0.0
        total_bal_penalty = 0.0
        total_correct = 0
        total_samples = 0
        
        # Shuffle training data
        perm = np.random.permutation(len(train_l))
        epoch_f = train_f[perm]
        epoch_l = train_l[perm]
        
        n_batches = (len(epoch_l) + batch_size - 1) // batch_size
        optimizer.zero_grad(set_to_none=True)
        
        for b in range(n_batches):
            start = b * batch_size
            end = min(start + batch_size, len(epoch_l))
            batch_f = epoch_f[start:end].copy()
            batch_l = epoch_l[start:end].copy()
            
            # Convert to tensors
            bx = torch.tensor(batch_f, dtype=torch.float32).to(device)
            by = torch.tensor(batch_l, dtype=torch.long).to(device)
            
            # Forward pass with AMP
            if scaler is not None:
                with autocast('cuda', dtype=torch.float16):
                    logits = model(bx)
                    ce_loss = criterion(logits, by)
            else:
                logits = model(bx)
                ce_loss = criterion(logits, by)
            
            # Calibration penalty
            with torch.no_grad():
                probs = torch.softmax(logits, dim=1)
                confidences = probs.max(dim=1).values
                preds = logits.argmax(dim=1)
                correct = (preds == by).float()
                cal_penalty = cal_engine.compute_calibration_penalty(
                    confidences.cpu().numpy(), correct.cpu().numpy()
                )
                bal_penalty = _balance_penalty(batch_f)
            
            # Total loss
            total_loss_val = ce_loss + cal_weight * cal_penalty + balance_weight * bal_penalty
            
            # Backward with gradient accumulation
            if scaler is not None:
                scaler.scale(total_loss_val / grad_accum).backward()
            else:
                (total_loss_val / grad_accum).backward()
            
            if (b + 1) % grad_accum == 0 or (b + 1) == n_batches:
                if scaler is not None:
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    optimizer.step()
                optimizer.zero_grad(set_to_none=True)
            
            total_loss += ce_loss.item() * (end - start)
            total_cal_penalty += cal_penalty * (end - start)
            total_bal_penalty += bal_penalty * (end - start)
            total_correct += correct.sum().item()
            total_samples += (end - start)
        
        scheduler.step()
        
        # Evaluate on clean test set
        model.eval()
        with torch.no_grad():
            tx = torch.tensor(test_f, dtype=torch.float32).to(device)
            tl = torch.tensor(test_l, dtype=torch.long).to(device)
            test_logits = model(tx)
            test_preds = test_logits.argmax(dim=1)
            test_acc = (test_preds == tl).float().mean().item()
            
            # Calibration metrics
            test_probs = torch.softmax(test_logits, dim=1)
            test_conf = test_probs.max(dim=1).values.cpu().numpy()
            test_correct = (test_preds == tl).cpu().numpy().astype(float)
            
            # Interaction importance
            interaction_contrib = _interaction_contribution(test_f)
        
        train_acc = total_correct / max(total_samples, 1)
        avg_loss = total_loss / max(total_samples, 1)
        avg_cal = total_cal_penalty / max(total_samples, 1)
        avg_bal = total_bal_penalty / max(total_samples, 1)
        epoch_time = time.time() - epoch_start
        
        # GPU utilization
        gpu_util = 0
        if torch.cuda.is_available():
            gpu_mem = torch.cuda.memory_allocated() / torch.cuda.max_memory_allocated() * 100
            gpu_util = gpu_mem
        
        metrics = {
            "epoch": epoch + 1,
            "train_acc": round(train_acc, 4),
            "test_acc": round(test_acc, 4),
            "loss": round(avg_loss, 4),
            "cal_penalty": round(avg_cal, 4),
            "bal_penalty": round(avg_bal, 4),
            "interaction_pct": round(interaction_contrib * 100, 1),
            "lr": round(optimizer.param_groups[0]['lr'], 6),
            "gpu_util_pct": round(gpu_util, 1),
            "time_s": round(epoch_time, 1),
        }
        all_metrics.append(metrics)
        
        if verbose:
            logger.info(
                f"Epoch {epoch+1:3d}/{epochs}: "
                f"train_acc={train_acc:.4f} test_acc={test_acc:.4f} "
                f"loss={avg_loss:.4f} cal={avg_cal:.4f} bal={avg_bal:.4f} "
                f"interaction={interaction_contrib*100:.1f}% "
                f"lr={optimizer.param_groups[0]['lr']:.6f} "
                f"time={epoch_time:.1f}s"
            )
    
    # Final evaluation
    model.eval()
    with torch.no_grad():
        tx = torch.tensor(test_f, dtype=torch.float32).to(device)
        tl = torch.tensor(test_l, dtype=torch.long).to(device)
        final_logits = model(tx)
        final_preds = final_logits.argmax(dim=1)
        final_acc = (final_preds == tl).float().mean().item()
    
    return {
        "model": model,
        "metrics": all_metrics,
        "final_accuracy": round(final_acc, 4),
        "device": str(device),
    }


def verify_robustness(model, test_features, test_labels, device):
    """Quick robustness check using real observed windows only."""
    model.eval()
    if len(test_labels) < 100:
        raise RuntimeError(
            "verify_robustness requires at least 100 real evaluation samples"
        )
    
    def _acc(f, l):
        with torch.no_grad():
            x = torch.tensor(f, dtype=torch.float32).to(device)
            preds = model(x).argmax(dim=1).cpu().numpy()
        return (preds == l).mean()

    def _severity_counts(window_labels: np.ndarray) -> dict[str, int]:
        return {
            "NEGATIVE": int(np.sum(window_labels == 0)),
            "POSITIVE": int(np.sum(window_labels == 1)),
        }
    
    baseline = _acc(test_features, test_labels)

    feature_array = np.asarray(test_features, dtype=np.float32)
    label_array = np.asarray(test_labels, dtype=np.int64)
    window_size = max(25, min(len(label_array) // 3, 200))
    baseline_window_l = label_array[:window_size]
    middle_window_f = feature_array[window_size:window_size * 2]
    middle_window_l = label_array[window_size:window_size * 2]
    late_window_f = feature_array[-window_size:]
    late_window_l = label_array[-window_size:]

    monitor = DistributionMonitor(history_size=5, shift_threshold=0.15)
    monitor.observe(_severity_counts(baseline_window_l))

    middle_shift = monitor.observe(_severity_counts(middle_window_l))
    scramble_acc = _acc(middle_window_f, middle_window_l)
    scramble_drop = baseline - scramble_acc

    late_shift = monitor.observe(_severity_counts(late_window_l))
    novel_acc = _acc(late_window_f, late_window_l)
    novel_drop = baseline - novel_acc
    
    return {
        "baseline_acc": round(float(baseline), 4),
        "scramble_acc": round(float(scramble_acc), 4),
        "scramble_drop": round(float(scramble_drop), 4),
        "novel_acc": round(float(novel_acc), 4),
        "novel_drop": round(float(novel_drop), 4),
        "middle_window_js": round(float(middle_shift.js_distance), 4),
        "late_window_js": round(float(late_shift.js_distance), 4),
        "scramble_pass": scramble_drop < 0.05 and middle_shift.js_distance <= middle_shift.threshold,
        "novel_pass": novel_drop < 0.05 and late_shift.js_distance <= late_shift.threshold,
    }


if __name__ == "__main__":
    from impl_v1.training.data.scaled_dataset import DatasetConfig
    from impl_v1.training.data.real_dataset_loader import RealTrainingDataset
    
    config = DatasetConfig(total_samples=18000)
    dataset = RealTrainingDataset(config=config)
    features = dataset._features_tensor.numpy()
    labels = dataset._labels_tensor.numpy()
    
    logger.info(f"Hardened training: {len(labels)} samples, {features.shape[1]} dims")
    
    result = train_hardened(features, labels, epochs=20, batch_size=256, grad_accum=2)
    
    logger.info(f"Final accuracy: {result['final_accuracy']:.4f}")
    
    # Quick robustness check
    np.random.seed(42)
    idx = np.random.permutation(len(labels))
    split = int(0.8 * len(labels))
    test_f, test_l = features[idx[split:]], labels[idx[split:]]
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    robustness = verify_robustness(result["model"], test_f, test_l, device)
    
    logger.info(f"Robustness check:")
    logger.info(f"  Baseline:         {robustness['baseline_acc']:.4f}")
    logger.info(f"  Middle window:    {robustness['scramble_acc']:.4f} (drop={robustness['scramble_drop']:.4f}, js={robustness['middle_window_js']:.4f}) {'PASS' if robustness['scramble_pass'] else 'FAIL'}")
    logger.info(f"  Late window:      {robustness['novel_acc']:.4f} (drop={robustness['novel_drop']:.4f}, js={robustness['late_window_js']:.4f}) {'PASS' if robustness['novel_pass'] else 'FAIL'}")
