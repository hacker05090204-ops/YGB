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

from backend.training.representation_bridge import SyntheticDataBlockedError
from impl_v1.training.distributed.hash_utils import hash_model_weights

logger = logging.getLogger(__name__)


def verify_scaling_determinism(
    batch_size: int,
    input_dim: int = 256,
    num_runs: int = 3,
    epochs: int = 3,
    X=None,
    y=None,
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

    if X is None or y is None:
        raise SyntheticDataBlockedError(
            "scaling_safety.verify_scaling_determinism requires caller-supplied real tensors; "
            "synthetic determinism data is blocked"
        )

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

    X_np = np.asarray(X, dtype=np.float32)
    y_np = np.asarray(y, dtype=np.int64)
    if X_np.shape[0] == 0 or y_np.shape[0] == 0:
        raise ValueError("scaling_safety.verify_scaling_determinism requires non-empty real tensors")

    hashes = []
    for run in range(num_runs):
        torch.manual_seed(42)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        try:
            torch.use_deterministic_algorithms(True)
        except Exception:
            logger.warning(
                "[SAFETY] Could not enable deterministic algorithms for scaling validation; continuing with best-effort determinism",
                exc_info=True,
            )

        X = torch.from_numpy(X_np).to(device)
        y = torch.from_numpy(y_np).to(device)

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
                optimizer.zero_grad(set_to_none=True)
                loss = criterion(model(bx), by)
                loss.backward()
                optimizer.step()

        # Hash weights
        h = hash_model_weights(model, mode="sampled")
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
    X=None,
    y=None,
) -> int:
    """Run adaptive scaling with determinism safety.

    If scaling breaks determinism → fallback to static.

    Returns:
        Safe optimal batch_size.
    """
    from impl_v1.training.config.adaptive_batch import find_optimal_batch_size

    result = find_optimal_batch_size(starting_batch, input_dim, X=X, y=y)
    optimal = result.optimal_batch_size

    if optimal != starting_batch:
        # Verify determinism at new batch size
        match, _ = verify_scaling_determinism(optimal, input_dim, X=X, y=y)
        if not match:
            logger.warning(
                f"[SAFETY] Adaptive batch_size={optimal} breaks determinism — "
                f"falling back to {starting_batch}"
            )
            return starting_batch

    return optimal
