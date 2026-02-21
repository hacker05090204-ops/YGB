"""
encoder_freezer.py — Freeze Base Encoder for Compute Reduction

If model has a feature encoder:
  1. Train encoder once (representation learning)
  2. Freeze encoder weights
  3. Train only classifier head per field

Reduces compute by 50-70%:
  - No backward pass through encoder
  - Only classifier gradients computed
"""

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def freeze_encoder(model, encoder_layer_names: List[str] = None) -> Tuple[int, int]:
    """Freeze encoder layers, keeping classifier trainable.

    Args:
        model: PyTorch model (nn.Sequential or named modules).
        encoder_layer_names: Names of layers to freeze.
            If None, freezes all but the last 2 layers.

    Returns:
        Tuple of (frozen_params, trainable_params).
    """
    import torch.nn as nn

    all_params = list(model.named_parameters())
    total = len(all_params)

    if encoder_layer_names:
        # Freeze specific named layers
        for name, param in all_params:
            for enc_name in encoder_layer_names:
                if enc_name in name:
                    param.requires_grad = False
                    break
    else:
        # Auto-detect: freeze all but last 2 layers
        # For Sequential models, freeze first N-2 modules
        if isinstance(model, nn.Sequential):
            modules = list(model.children())
            # Freeze all modules except last 2
            freeze_count = max(len(modules) - 2, 0)
            for i, module in enumerate(modules):
                if i < freeze_count:
                    for param in module.parameters():
                        param.requires_grad = False
        else:
            # For non-sequential: freeze first 75% of params
            freeze_until = int(total * 0.75)
            for i, (name, param) in enumerate(all_params):
                if i < freeze_until:
                    param.requires_grad = False

    frozen = sum(1 for _, p in model.named_parameters() if not p.requires_grad)
    trainable = sum(1 for _, p in model.named_parameters() if p.requires_grad)

    frozen_params = sum(p.numel() for p in model.parameters() if not p.requires_grad)
    trainable_params = sum(p.numel() for p in model.parameters() if p.requires_grad)

    logger.info(
        f"[FREEZE] Frozen {frozen} layers ({frozen_params:,} params), "
        f"trainable {trainable} layers ({trainable_params:,} params)"
    )

    return frozen_params, trainable_params


def unfreeze_all(model) -> int:
    """Unfreeze all model parameters.

    Args:
        model: PyTorch model.

    Returns:
        Total number of parameters.
    """
    total = 0
    for param in model.parameters():
        param.requires_grad = True
        total += param.numel()

    logger.info(f"[FREEZE] Unfrozen all {total:,} parameters")
    return total


def get_trainable_params(model) -> List[dict]:
    """Get only trainable parameters for optimizer.

    Args:
        model: PyTorch model.

    Returns:
        List of parameter dicts for optimizer.
    """
    return [
        {'params': p, 'name': n}
        for n, p in model.named_parameters()
        if p.requires_grad
    ]


def compute_savings(model) -> dict:
    """Compute compute savings from freezing.

    Returns:
        Dict with total, frozen, trainable counts and savings %.
    """
    total = sum(p.numel() for p in model.parameters())
    frozen = sum(p.numel() for p in model.parameters() if not p.requires_grad)
    trainable = total - frozen

    savings = (frozen / total * 100) if total > 0 else 0

    return {
        'total_params': total,
        'frozen_params': frozen,
        'trainable_params': trainable,
        'compute_savings_pct': round(savings, 1),
    }
