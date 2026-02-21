"""
device_baselines.py — Cross-GPU Performance Normalization

Stores per-device baselines:
{
  "device_name": "...",
  "optimal_batch_size": N,
  "samples_per_sec": float,
  "vram_peak_mb": float,
  "compute_capability": "..."
}

Never assumes same batch_size across devices.
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from typing import Dict, Optional

logger = logging.getLogger(__name__)

BASELINES_PATH = os.path.join('secure_data', 'device_baselines.json')


@dataclass
class DeviceBaseline:
    """Per-device performance baseline."""
    device_name: str
    compute_capability: str
    vram_total_mb: float
    optimal_batch_size: int
    samples_per_sec: float
    vram_peak_mb: float
    amp_enabled: bool
    measured_at: str = ""


class DeviceBaselineStore:
    """Store and retrieve per-device baselines."""

    def __init__(self, path: str = BASELINES_PATH):
        self._path = path
        self._baselines: Dict[str, DeviceBaseline] = {}
        self._load()

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path, 'r') as f:
                    data = json.load(f)
                for key, val in data.items():
                    self._baselines[key] = DeviceBaseline(**val)
            except Exception as e:
                logger.warning(f"[BASELINES] Failed to load: {e}")

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, 'w') as f:
            json.dump(
                {k: asdict(v) for k, v in self._baselines.items()},
                f, indent=2,
            )

    def store_baseline(self, baseline: DeviceBaseline):
        """Store or update a device baseline."""
        key = f"{baseline.device_name}_{baseline.compute_capability}"
        self._baselines[key] = baseline
        self._save()
        logger.info(
            f"[BASELINES] Stored: {baseline.device_name} — "
            f"batch={baseline.optimal_batch_size}, "
            f"sps={baseline.samples_per_sec:.0f}"
        )

    def get_baseline(self, device_name: str, cc: str = "") -> Optional[DeviceBaseline]:
        """Retrieve baseline for a device."""
        key = f"{device_name}_{cc}"
        return self._baselines.get(key)

    def get_optimal_batch(self, device_name: str, cc: str = "", default: int = 1024) -> int:
        """Get optimal batch_size for a device."""
        baseline = self.get_baseline(device_name, cc)
        return baseline.optimal_batch_size if baseline else default

    def list_all(self) -> Dict[str, dict]:
        """List all stored baselines."""
        return {k: asdict(v) for k, v in self._baselines.items()}

    def calibrate_current_device(self) -> Optional[DeviceBaseline]:
        """Auto-calibrate the current device.

        Runs adaptive batch scaling and stores baseline.

        Returns:
            DeviceBaseline or None if no GPU.
        """
        try:
            import torch
            import time
        except ImportError:
            return None

        if not torch.cuda.is_available():
            logger.info("[BASELINES] No GPU — skipping calibration")
            return None

        props = torch.cuda.get_device_properties(0)
        device_name = props.name
        cc = f"{props.major}.{props.minor}"
        vram_total = props.total_memory / (1024 ** 2)

        # Run adaptive batch scaling
        try:
            from impl_v1.training.config.adaptive_batch import find_optimal_batch_size
            result = find_optimal_batch_size(starting_batch=1024)
            optimal_batch = result.optimal_batch_size
        except Exception:
            optimal_batch = 1024

        # Run quick benchmark
        sps = 0.0
        vram_peak = 0.0
        try:
            from impl_v1.training.validation.baseline_benchmark import run_benchmark
            bench = run_benchmark(epochs=1, batch_size=optimal_batch)
            sps = bench.samples_per_sec
            vram_peak = bench.vram_peak_mb
        except Exception:
            pass

        baseline = DeviceBaseline(
            device_name=device_name,
            compute_capability=cc,
            vram_total_mb=vram_total,
            optimal_batch_size=optimal_batch,
            samples_per_sec=sps,
            vram_peak_mb=vram_peak,
            amp_enabled=True,
            measured_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        )

        self.store_baseline(baseline)
        return baseline
