"""
occupancy_validator.py — GPU Occupancy & Bottleneck Detection

Target: GPU utilization >= 85%

If below:
  Identify bottleneck:
  - DataLoader (CPU-bound data loading)
  - Model size (too small for GPU)
  - CPU bottleneck (preprocessing)

Log bottleneck reason.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

TARGET_GPU_UTIL = 85.0  # Minimum target %


@dataclass
class OccupancyReport:
    """GPU occupancy analysis."""
    gpu_util_pct: float
    vram_used_pct: float
    meets_target: bool
    bottleneck: str           # "none", "dataloader", "model_size", "cpu", "unknown"
    bottleneck_detail: str
    recommendation: str


def analyze_occupancy(
    gpu_util_pct: float = None,
    vram_used_pct: float = None,
    dataloader_time_pct: float = None,
    compute_time_pct: float = None,
    batch_size: int = 1024,
    model_params: int = 0,
) -> OccupancyReport:
    """Analyze GPU occupancy and identify bottlenecks.

    Args:
        gpu_util_pct: Current GPU utilization %.
        vram_used_pct: Current VRAM usage %.
        dataloader_time_pct: % of time spent in data loading (~0-100).
        compute_time_pct: % of time spent in GPU compute.
        batch_size: Current batch size.
        model_params: Number of model parameters.

    Returns:
        OccupancyReport with bottleneck analysis.
    """
    # Default: query from pytorch
    if gpu_util_pct is None or vram_used_pct is None:
        gpu_util_pct, vram_used_pct = _query_gpu_stats()

    meets_target = gpu_util_pct >= TARGET_GPU_UTIL

    if meets_target:
        return OccupancyReport(
            gpu_util_pct=gpu_util_pct,
            vram_used_pct=vram_used_pct,
            meets_target=True,
            bottleneck="none",
            bottleneck_detail="GPU utilization meets target",
            recommendation="No changes needed",
        )

    # Identify bottleneck
    bottleneck = "unknown"
    detail = ""
    recommendation = ""

    if dataloader_time_pct is not None and dataloader_time_pct > 50:
        bottleneck = "dataloader"
        detail = f"DataLoader consuming {dataloader_time_pct:.0f}% of epoch time"
        recommendation = "Increase num_workers, enable pin_memory, use persistent_workers"

    elif vram_used_pct < 20:
        bottleneck = "model_size"
        detail = f"VRAM usage only {vram_used_pct:.1f}% — model too small for GPU"
        recommendation = "Increase batch_size or model capacity"

    elif vram_used_pct < 50 and gpu_util_pct < 50:
        bottleneck = "cpu"
        detail = f"Low GPU util ({gpu_util_pct:.1f}%) with low VRAM ({vram_used_pct:.1f}%) — CPU bottleneck likely"
        recommendation = "Profile CPU preprocessing, increase batch_size, reduce data transforms"

    elif vram_used_pct >= 50 and gpu_util_pct < TARGET_GPU_UTIL:
        bottleneck = "model_size"
        detail = f"Good VRAM usage ({vram_used_pct:.1f}%) but low GPU util ({gpu_util_pct:.1f}%)"
        recommendation = "Increase batch_size for better kernel occupancy"

    else:
        detail = f"GPU util={gpu_util_pct:.1f}%, VRAM={vram_used_pct:.1f}%"
        recommendation = "Run profiler for detailed analysis"

    report = OccupancyReport(
        gpu_util_pct=gpu_util_pct,
        vram_used_pct=vram_used_pct,
        meets_target=False,
        bottleneck=bottleneck,
        bottleneck_detail=detail,
        recommendation=recommendation,
    )

    logger.warning(
        f"[OCCUPANCY] Below target ({gpu_util_pct:.1f}% < {TARGET_GPU_UTIL}%): "
        f"bottleneck={bottleneck} — {detail}"
    )

    return report


def _query_gpu_stats():
    """Query GPU stats from PyTorch."""
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0, 0.0

        used = torch.cuda.memory_allocated() / (1024 ** 2)
        total = torch.cuda.get_device_properties(0).total_memory / (1024 ** 2)
        vram_pct = (used / total * 100) if total > 0 else 0
        gpu_pct = vram_pct  # Approximate
        return gpu_pct, vram_pct
    except Exception:
        return 0.0, 0.0
