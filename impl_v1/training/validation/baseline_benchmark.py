"""
baseline_benchmark.py — Training Validation Benchmark Run

Runs controlled 1-epoch training and measures:
  - samples_per_sec
  - vram_peak_mb
  - batch_size
  - gpu_count

Stores baseline JSON for comparison across devices (RTX 2050/3050).
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

BASELINE_PATH = os.path.join('reports', 'baseline_benchmark.json')


@dataclass
class BenchmarkResult:
    """Single benchmark run result."""
    device_name: str
    gpu_count: int
    batch_size: int
    samples_per_sec: float
    vram_peak_mb: float
    vram_total_mb: float
    amp_enabled: bool
    epoch_time_sec: float
    total_samples: int
    timestamp: str


def run_benchmark(
    epochs: int = 1,
    batch_size: int = 1024,
    input_dim: int = 256,
    num_samples: int = 5000,
    seed: int = 42,
) -> BenchmarkResult:
    """Run controlled benchmark training.

    Args:
        epochs: Number of epochs (default 1).
        batch_size: Batch size.
        input_dim: Feature dimensionality.
        num_samples: Dataset size.
        seed: Random seed.

    Returns:
        BenchmarkResult with measured metrics.
    """
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        logger.error("[BENCH] PyTorch not available")
        return BenchmarkResult(
            device_name="N/A", gpu_count=0, batch_size=batch_size,
            samples_per_sec=0, vram_peak_mb=0, vram_total_mb=0,
            amp_enabled=False, epoch_time_sec=0, total_samples=0,
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        )

    # Setup
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.manual_seed(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

    has_gpu = torch.cuda.is_available()
    device = torch.device("cuda" if has_gpu else "cpu")
    device_name = torch.cuda.get_device_properties(0).name if has_gpu else "CPU"
    gpu_count = torch.cuda.device_count() if has_gpu else 0
    vram_total = torch.cuda.get_device_properties(0).total_memory / (1024**2) if has_gpu else 0

    if has_gpu:
        torch.cuda.reset_peak_memory_stats()

    # Generate data
    rng = np.random.RandomState(seed)
    X = torch.from_numpy(rng.randn(num_samples, input_dim).astype(np.float32)).to(device)
    y = torch.from_numpy(rng.randint(0, 2, num_samples).astype(np.int64)).to(device)

    # Model
    model = nn.Sequential(
        nn.Linear(input_dim, 128), nn.ReLU(), nn.Dropout(0.3),
        nn.Linear(128, 64), nn.ReLU(),
        nn.Linear(64, 2),
    ).to(device)

    optimizer = optim.Adam(model.parameters(), lr=0.001)
    criterion = nn.CrossEntropyLoss()

    # AMP setup
    amp_enabled = has_gpu
    scaler = None
    if amp_enabled:
        try:
            from torch.cuda.amp import GradScaler, autocast
            scaler = GradScaler()
        except ImportError:
            amp_enabled = False

    # Train
    total_processed = 0
    start = time.perf_counter()

    model.train()
    for epoch in range(epochs):
        for i in range(0, num_samples, batch_size):
            batch_x = X[i:i+batch_size]
            batch_y = y[i:i+batch_size]

            optimizer.zero_grad()

            if amp_enabled and scaler:
                with autocast(dtype=torch.float16):
                    out = model(batch_x)
                    loss = criterion(out, batch_y)
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                out = model(batch_x)
                loss = criterion(out, batch_y)
                loss.backward()
                optimizer.step()

            total_processed += batch_x.size(0)

    elapsed = time.perf_counter() - start
    vram_peak = torch.cuda.max_memory_allocated() / (1024**2) if has_gpu else 0
    sps = total_processed / max(elapsed, 0.001)

    result = BenchmarkResult(
        device_name=device_name,
        gpu_count=gpu_count,
        batch_size=batch_size,
        samples_per_sec=sps,
        vram_peak_mb=vram_peak,
        vram_total_mb=vram_total,
        amp_enabled=amp_enabled,
        epoch_time_sec=elapsed,
        total_samples=total_processed,
        timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    )

    logger.info(
        f"[BENCH] {device_name}: {sps:.0f} samples/sec, "
        f"VRAM peak={vram_peak:.0f}MB, batch={batch_size}, "
        f"AMP={amp_enabled}"
    )

    return result


def save_baseline(result: BenchmarkResult, path: str = BASELINE_PATH) -> str:
    """Save benchmark result as baseline JSON."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Append to existing baselines
    baselines = []
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                baselines = json.load(f)
        except Exception:
            baselines = []

    baselines.append(asdict(result))

    with open(path, 'w') as f:
        json.dump(baselines, f, indent=2)

    logger.info(f"[BENCH] Baseline saved to {path}")
    return path
