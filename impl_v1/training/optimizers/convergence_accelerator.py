"""
convergence_accelerator.py — Faster Convergence via LR Scheduling & Gradient Clipping

1. Cosine warm restarts (CosineAnnealingWarmRestarts)
2. OneCycleLR scheduler
3. LR finder (short sweep to find optimal initial LR)
4. Gradient clipping (max_norm=1.0)
5. Per-epoch convergence curve logging

Goal: Reach target accuracy in fewer epochs.
"""

import json
import logging
import math
import os
import time
from dataclasses import dataclass, asdict, field
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class EpochLog:
    """Per-epoch convergence metrics."""
    epoch: int
    lr: float
    train_loss: float
    val_loss: float
    accuracy: float
    grad_norm: float
    elapsed_sec: float


@dataclass
class ConvergenceReport:
    """Full convergence report."""
    scheduler_type: str
    initial_lr: float
    final_lr: float
    grad_clip_norm: float
    total_epochs: int
    converged_at_epoch: int
    target_accuracy: float
    final_accuracy: float
    epoch_logs: List[EpochLog] = field(default_factory=list)


# =============================================================================
# LR FINDER
# =============================================================================

def find_optimal_lr(
    model,
    train_loader,
    criterion,
    device,
    min_lr: float = 1e-7,
    max_lr: float = 1.0,
    steps: int = 100,
) -> float:
    """Quick LR sweep to find optimal initial learning rate.

    Runs a short training with exponentially increasing LR.
    Optimal LR = point where loss decreases fastest.

    Args:
        model: PyTorch model.
        train_loader: Training data loader.
        criterion: Loss function.
        device: torch.device.
        min_lr: Starting LR.
        max_lr: Ending LR.
        steps: Number of LR steps.

    Returns:
        Optimal initial learning rate.
    """
    import torch
    import torch.optim as optim

    # Save initial weights
    initial_state = {k: v.clone() for k, v in model.state_dict().items()}

    optimizer = optim.SGD(model.parameters(), lr=min_lr)
    lr_lambda = lambda step: math.exp(step * math.log(max_lr / min_lr) / steps)
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    losses = []
    lrs = []
    best_loss = float('inf')
    model.train()

    step = 0
    for batch_x, batch_y in train_loader:
        if step >= steps:
            break

        batch_x = batch_x.to(device, non_blocking=True)
        batch_y = batch_y.to(device, non_blocking=True)

        optimizer.zero_grad()
        output = model(batch_x)
        loss = criterion(output, batch_y)
        loss.backward()
        optimizer.step()
        scheduler.step()

        current_lr = optimizer.param_groups[0]['lr']
        current_loss = loss.item()

        lrs.append(current_lr)
        losses.append(current_loss)

        if current_loss < best_loss:
            best_loss = current_loss

        # Stop if loss diverges
        if current_loss > best_loss * 4:
            break

        step += 1

    # Restore initial weights
    model.load_state_dict(initial_state)

    # Find LR with steepest loss decrease
    if len(losses) < 10:
        return 1e-3  # Default

    # Smooth losses
    smoothed = []
    window = max(len(losses) // 10, 3)
    for i in range(len(losses)):
        start = max(0, i - window)
        smoothed.append(np.mean(losses[start:i+1]))

    # Find steepest descent
    min_grad_idx = 0
    min_grad = 0
    for i in range(1, len(smoothed) - 1):
        grad = smoothed[i+1] - smoothed[i-1]
        if grad < min_grad:
            min_grad = grad
            min_grad_idx = i

    optimal_lr = lrs[min_grad_idx] / 10  # Use 1/10 of the steepest point
    optimal_lr = max(min_lr, min(optimal_lr, 0.01))

    logger.info(f"[LR_FIND] Optimal LR: {optimal_lr:.6f} (from {len(lrs)} steps)")
    return optimal_lr


# =============================================================================
# SCHEDULER FACTORY
# =============================================================================

def create_scheduler(
    optimizer,
    scheduler_type: str = "cosine_warm_restarts",
    total_epochs: int = 30,
    steps_per_epoch: int = 20,
    initial_lr: float = None,
):
    """Create LR scheduler.

    Args:
        optimizer: PyTorch optimizer.
        scheduler_type: "cosine_warm_restarts" or "one_cycle".
        total_epochs: Total training epochs.
        steps_per_epoch: Steps per epoch.
        initial_lr: Initial LR (for OneCycleLR).

    Returns:
        LR scheduler.
    """
    import torch.optim.lr_scheduler as sched

    if scheduler_type == "cosine_warm_restarts":
        # Restart every T_0 epochs with T_mult scaling
        return sched.CosineAnnealingWarmRestarts(
            optimizer,
            T_0=max(total_epochs // 3, 5),
            T_mult=2,
            eta_min=1e-6,
        )
    elif scheduler_type == "one_cycle":
        max_lr = initial_lr or optimizer.param_groups[0]['lr']
        return sched.OneCycleLR(
            optimizer,
            max_lr=max_lr * 10,
            total_steps=total_epochs * steps_per_epoch,
            pct_start=0.3,
            anneal_strategy='cos',
        )
    else:
        return sched.StepLR(optimizer, step_size=10, gamma=0.1)


# =============================================================================
# GRADIENT CLIPPING
# =============================================================================

def clip_gradients(model, max_norm: float = 1.0) -> float:
    """Clip gradients by norm and return the total norm.

    Args:
        model: PyTorch model.
        max_norm: Maximum gradient norm.

    Returns:
        Total gradient norm before clipping.
    """
    import torch.nn.utils as nn_utils
    return nn_utils.clip_grad_norm_(model.parameters(), max_norm).item()


# =============================================================================
# CONVERGENCE LOGGING
# =============================================================================

def save_convergence_report(report: ConvergenceReport, path: str = None):
    """Save convergence report to JSON."""
    if path is None:
        path = os.path.join('reports', 'convergence_report.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)

    data = asdict(report)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

    logger.info(f"[CONVERGE] Report saved: {path}")
