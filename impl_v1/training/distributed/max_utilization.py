"""
max_utilization.py — Per-Node Max GPU Utilization Strategy

For each node:
  1. Run adaptive batch scaling locally
  2. Store optimal_batch_size
  3. Use that per-node batch in DDP

Never forces same batch across heterogeneous GPUs.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

MAX_UTIL_PATH = os.path.join('secure_data', 'max_utilization.json')


@dataclass
class NodeUtilization:
    """Per-node max utilization config."""
    device_name: str
    gpu_count: int
    vram_total_mb: float
    optimal_batch: int
    samples_per_sec: float
    vram_peak_mb: float
    gpu_util_pct: float


def calibrate_local_node() -> NodeUtilization:
    """Run full calibration on the local node.

    Steps:
      1. Detect GPU
      2. Run adaptive batch scaling
      3. Run benchmark at optimal batch
      4. Store results

    Returns:
        NodeUtilization with optimal config.
    """
    try:
        import torch
    except ImportError:
        return NodeUtilization(
            device_name="CPU", gpu_count=0, vram_total_mb=0,
            optimal_batch=1024, samples_per_sec=0,
            vram_peak_mb=0, gpu_util_pct=0,
        )

    has_gpu = torch.cuda.is_available()
    device_name = torch.cuda.get_device_properties(0).name if has_gpu else "CPU"
    gpu_count = torch.cuda.device_count() if has_gpu else 0
    vram_total = torch.cuda.get_device_properties(0).total_memory / (1024**2) if has_gpu else 0

    # Step 1: Adaptive batch scaling
    optimal_batch = 1024
    try:
        from impl_v1.training.safety.scaling_safety import safe_adaptive_scale
        optimal_batch = safe_adaptive_scale(starting_batch=1024, input_dim=256)
        logger.info(f"[MAX_UTIL] Adaptive batch: {optimal_batch}")
    except Exception as e:
        logger.warning(f"[MAX_UTIL] Adaptive scaling failed: {e}")

    # Step 2: Benchmark at optimal batch
    sps = 0.0
    vram_peak = 0.0
    try:
        from impl_v1.training.validation.baseline_benchmark import run_benchmark
        bench = run_benchmark(epochs=1, batch_size=optimal_batch)
        sps = bench.samples_per_sec
        vram_peak = bench.vram_peak_mb
    except Exception as e:
        logger.warning(f"[MAX_UTIL] Benchmark failed: {e}")

    # Estimate GPU util from VRAM
    gpu_util = (vram_peak / vram_total * 100) if vram_total > 0 else 0

    result = NodeUtilization(
        device_name=device_name,
        gpu_count=gpu_count,
        vram_total_mb=vram_total,
        optimal_batch=optimal_batch,
        samples_per_sec=sps,
        vram_peak_mb=vram_peak,
        gpu_util_pct=gpu_util,
    )

    # Save
    os.makedirs(os.path.dirname(MAX_UTIL_PATH), exist_ok=True)
    with open(MAX_UTIL_PATH, 'w') as f:
        json.dump(asdict(result), f, indent=2)

    logger.info(
        f"[MAX_UTIL] {device_name}: batch={optimal_batch}, "
        f"sps={sps:.0f}, VRAM peak={vram_peak:.1f}MB"
    )

    return result


def load_node_utilization() -> Optional[NodeUtilization]:
    """Load saved node utilization config."""
    if os.path.exists(MAX_UTIL_PATH):
        try:
            with open(MAX_UTIL_PATH, 'r') as f:
                data = json.load(f)
            return NodeUtilization(**data)
        except Exception:
            pass
    return None
