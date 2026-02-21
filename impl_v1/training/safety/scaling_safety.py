"""
scaling_safety.py — Post-Scaling Determinism Safety Check

After adaptive batch scaling:
  Run 3-run determinism validator.
  Compare weight hashes.

If mismatch:
  Disable adaptive scaling.
  Fallback to static batch_size (1024).
"""

import hashlib
import logging
import os
import json
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)


def verify_scaling_determinism(
    batch_size: int,
    input_dim: int = 256,
    num_runs: int = 3,
    epochs: int = 3,
) -> Tuple[bool, list]:
    """Run determinism check at the given batch_size.

    Args:
        batch_size: Batch size to validate.
        input_dim: Feature dimension.
        num_runs: Number of identical runs.
        epochs: Epochs per run.

    Returns:
        (all_match, list_of_hashes)
    """
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        return True, []

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

    hashes = []
    for run in range(num_runs):
        torch.manual_seed(42)
        np.random.seed(42)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        try:
            torch.use_deterministic_algorithms(True)
        except Exception:
            pass

        rng = np.random.RandomState(42)
        X = torch.from_numpy(rng.randn(4000, input_dim).astype(np.float32)).to(device)
        y = torch.from_numpy(rng.randint(0, 2, 4000).astype(np.int64)).to(device)

        model = nn.Sequential(
            nn.Linear(input_dim, 128), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, 2),
        ).to(device)

        optimizer = optim.Adam(model.parameters(), lr=0.001)
        criterion = nn.CrossEntropyLoss()

        model.train()
        for ep in range(epochs):
            for i in range(0, 4000, batch_size):
                bx = X[i:i+batch_size]
                by = y[i:i+batch_size]
                optimizer.zero_grad()
                loss = criterion(model(bx), by)
                loss.backward()
                optimizer.step()

        # Hash weights
        wb = b""
        for name, param in sorted(model.named_parameters()):
            wb += param.detach().cpu().numpy().tobytes()
        h = hashlib.sha256(wb).hexdigest()
        hashes.append(h)

        del model, optimizer, X, y
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    all_match = len(set(hashes)) == 1

    if all_match:
        logger.info(
            f"[SAFETY] Determinism PASS at batch_size={batch_size}: "
            f"{hashes[0][:16]}..."
        )
    else:
        logger.error(
            f"[SAFETY] Determinism FAIL at batch_size={batch_size} — "
            f"falling back to static batch"
        )
        for i, h in enumerate(hashes):
            logger.error(f"  Run {i+1}: {h[:16]}...")

    return all_match, hashes


def safe_adaptive_scale(
    starting_batch: int = 1024,
    input_dim: int = 256,
) -> int:
    """Run adaptive scaling with determinism safety.

    If scaling breaks determinism → fallback to static.

    Returns:
        Safe optimal batch_size.
    """
    from impl_v1.training.config.adaptive_batch import find_optimal_batch_size

    result = find_optimal_batch_size(starting_batch, input_dim)
    optimal = result.optimal_batch_size

    if optimal != starting_batch:
        # Verify determinism at new batch size
        match, _ = verify_scaling_determinism(optimal, input_dim)
        if not match:
            logger.warning(
                f"[SAFETY] Adaptive batch_size={optimal} breaks determinism — "
                f"falling back to {starting_batch}"
            )
            return starting_batch

    return optimal
