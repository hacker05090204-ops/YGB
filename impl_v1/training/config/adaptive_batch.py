"""
adaptive_batch.py — Deterministic Adaptive Batch Scaling

If:
  vram_used < 50% total AND gpu_util < 85%
Then:
  Increase batch_size by factor 2
  Re-run warmup epoch

Repeat until:
  vram_used reaches 70-80% OR OOM occurs

On OOM:
  Rollback to last safe batch_size.

Batch scaling is deterministic:
  Chosen batch_size stored in config.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Tuple

logger = logging.getLogger(__name__)

BATCH_CONFIG_PATH = os.path.join('secure_data', 'adaptive_batch_config.json')

# =============================================================================
# CONFIGURATION
# =============================================================================

MIN_BATCH_SIZE = 32
MAX_BATCH_SIZE = 8192
VRAM_TARGET_LOW = 50.0    # Below this % → scale up
VRAM_TARGET_HIGH = 80.0   # Target VRAM usage %
GPU_UTIL_THRESHOLD = 85.0  # Below this % → scale up
MAX_SCALE_ATTEMPTS = 5


@dataclass
class BatchScaleResult:
    """Result of adaptive batch scaling."""
    original_batch_size: int
    optimal_batch_size: int
    scale_factor: int
    vram_used_pct: float
    gpu_util_pct: float
    oom_occurred: bool
    attempts: int
    deterministic: bool    # True if same result reproducible


# =============================================================================
# VRAM QUERY
# =============================================================================

def _get_vram_usage() -> Tuple[float, float, float]:
    """Get VRAM usage: (used_mb, total_mb, used_percent)."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0, 0.0, 0.0

        used = torch.cuda.memory_allocated() / (1024 ** 2)
        total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        pct = (used / total * 100) if total > 0 else 0
        return used, total, pct
    except Exception:
        return 0.0, 0.0, 0.0


def _get_gpu_util() -> float:
    """Estimate GPU utilization %."""
    used, total, pct = _get_vram_usage()
    return pct  # Approximate via VRAM ratio


# =============================================================================
# WARMUP EPOCH
# =============================================================================

def _run_warmup(batch_size: int, input_dim: int = 256, num_samples: int = 4000) -> Tuple[bool, float, float]:
    """Run a warmup epoch to test a batch size.

    Returns:
        (success, vram_used_pct, samples_per_sec)
    """
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
        import numpy as np
    except ImportError:
        return False, 0.0, 0.0

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    try:
        torch.cuda.reset_peak_memory_stats()

        rng = np.random.RandomState(42)
        X = torch.from_numpy(rng.randn(num_samples, input_dim).astype(np.float32)).to(device)
        y = torch.from_numpy(rng.randint(0, 2, num_samples).astype(np.int64)).to(device)

        model = nn.Sequential(
            nn.Linear(input_dim, 512), nn.ReLU(),
            nn.Linear(512, 256), nn.ReLU(),
            nn.Linear(256, 2),
        ).to(device)

        optimizer = optim.Adam(model.parameters(), lr=0.001)
        criterion = nn.CrossEntropyLoss()

        model.train()
        start = time.perf_counter()
        processed = 0

        for i in range(0, num_samples, batch_size):
            bx = X[i:i+batch_size]
            by = y[i:i+batch_size]
            optimizer.zero_grad()
            loss = criterion(model(bx), by)
            loss.backward()
            optimizer.step()
            processed += bx.size(0)

        elapsed = time.perf_counter() - start
        sps = processed / max(elapsed, 0.001)

        _, total, vram_pct = _get_vram_usage()
        peak = torch.cuda.max_memory_allocated() / (1024 ** 2)
        vram_pct = (peak / total * 100) if total > 0 else 0

        # Cleanup
        del model, optimizer, X, y
        torch.cuda.empty_cache()

        return True, vram_pct, sps

    except RuntimeError as e:
        if "out of memory" in str(e).lower():
            logger.warning(f"[BATCH] OOM at batch_size={batch_size}")
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass
            return False, 100.0, 0.0
        raise


# =============================================================================
# ADAPTIVE SCALING
# =============================================================================

def find_optimal_batch_size(
    starting_batch: int = 1024,
    input_dim: int = 256,
) -> BatchScaleResult:
    """Find optimal batch size via warmup scaling.

    Doubles batch_size until VRAM target reached or OOM.

    Args:
        starting_batch: Initial batch size.
        input_dim: Feature dimension.

    Returns:
        BatchScaleResult with optimal batch size.
    """
    logger.info(f"[BATCH] Starting adaptive scaling from batch_size={starting_batch}")

    current_batch = starting_batch
    last_safe_batch = starting_batch
    oom = False
    attempts = 0

    # Initial warmup
    ok, vram_pct, sps = _run_warmup(current_batch, input_dim)
    if not ok:
        return BatchScaleResult(
            original_batch_size=starting_batch,
            optimal_batch_size=starting_batch,
            scale_factor=1,
            vram_used_pct=0, gpu_util_pct=0,
            oom_occurred=True, attempts=1, deterministic=True,
        )

    gpu_util = _get_gpu_util()

    while (vram_pct < VRAM_TARGET_LOW and gpu_util < GPU_UTIL_THRESHOLD
           and current_batch < MAX_BATCH_SIZE
           and attempts < MAX_SCALE_ATTEMPTS):

        last_safe_batch = current_batch
        current_batch *= 2
        attempts += 1

        logger.info(f"[BATCH] Attempt {attempts}: trying batch_size={current_batch}")

        ok, vram_pct, sps = _run_warmup(current_batch, input_dim)

        if not ok:
            # OOM — rollback
            oom = True
            current_batch = last_safe_batch
            logger.warning(f"[BATCH] OOM — rolling back to batch_size={last_safe_batch}")
            break

        gpu_util = _get_gpu_util()

        if vram_pct >= VRAM_TARGET_HIGH:
            logger.info(f"[BATCH] VRAM target reached ({vram_pct:.1f}%) at batch_size={current_batch}")
            break

    scale_factor = current_batch // starting_batch

    result = BatchScaleResult(
        original_batch_size=starting_batch,
        optimal_batch_size=current_batch,
        scale_factor=scale_factor,
        vram_used_pct=vram_pct,
        gpu_util_pct=gpu_util,
        oom_occurred=oom,
        attempts=attempts,
        deterministic=True,
    )

    logger.info(
        f"[BATCH] Optimal: batch_size={current_batch} "
        f"(scale={scale_factor}x, VRAM={vram_pct:.1f}%, attempts={attempts})"
    )

    # Save config
    save_batch_config(result)

    return result


def save_batch_config(result: BatchScaleResult, path: str = BATCH_CONFIG_PATH):
    """Save deterministic batch config."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(asdict(result), f, indent=2)


def load_batch_config(path: str = BATCH_CONFIG_PATH) -> int:
    """Load saved optimal batch size. Returns default if not found."""
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return data.get('optimal_batch_size', 1024)
        except Exception:
            pass
    return 1024
