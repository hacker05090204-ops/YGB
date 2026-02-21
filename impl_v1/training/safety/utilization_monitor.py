"""
utilization_monitor.py — Continuous GPU Utilization & Safety Monitor

Monitors during training:
  - gpu_util_percent
  - vram_usage
  - samples_per_sec

If gpu_util < 85%: flag for batch increase.
If vram_usage < 70%: flag for batch increase until 80%.
Rollback on OOM.
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


TARGET_GPU_UTIL = 85.0
TARGET_VRAM_LOW = 70.0
TARGET_VRAM_HIGH = 80.0


@dataclass
class UtilizationSnapshot:
    """Single utilization measurement."""
    timestamp: float
    gpu_util_pct: float
    vram_used_mb: float
    vram_total_mb: float
    vram_used_pct: float
    samples_per_sec: float
    batch_size: int


@dataclass
class UtilizationAction:
    """Recommended action based on monitoring."""
    action: str           # "none", "increase_batch", "decrease_batch", "maintain"
    current_batch: int
    recommended_batch: int
    reason: str


class UtilizationMonitor:
    """Continuous GPU utilization monitor."""

    def __init__(self):
        self._snapshots = []
        self._max_batch_seen = 0
        self._oom_count = 0
        self._last_safe_batch = 1024

    def take_snapshot(
        self,
        batch_size: int,
        samples_per_sec: float = 0,
    ) -> UtilizationSnapshot:
        """Take a utilization snapshot."""
        gpu_util = 0.0
        vram_used = 0.0
        vram_total = 0.0

        try:
            import torch
            if torch.cuda.is_available():
                vram_used = torch.cuda.memory_allocated() / (1024**2)
                vram_total = torch.cuda.get_device_properties(0).total_memory / (1024**2)
                gpu_util = (vram_used / vram_total * 100) if vram_total > 0 else 0
        except Exception:
            pass

        vram_pct = (vram_used / vram_total * 100) if vram_total > 0 else 0

        snap = UtilizationSnapshot(
            timestamp=time.time(),
            gpu_util_pct=gpu_util,
            vram_used_mb=vram_used,
            vram_total_mb=vram_total,
            vram_used_pct=vram_pct,
            samples_per_sec=samples_per_sec,
            batch_size=batch_size,
        )

        self._snapshots.append(snap)
        if batch_size > self._max_batch_seen:
            self._max_batch_seen = batch_size

        return snap

    def recommend_action(self, current_batch: int) -> UtilizationAction:
        """Recommend batch size action based on recent snapshots."""
        if not self._snapshots:
            return UtilizationAction(
                action="none", current_batch=current_batch,
                recommended_batch=current_batch, reason="No data",
            )

        recent = self._snapshots[-1]

        # OOM guard
        if self._oom_count > 0:
            return UtilizationAction(
                action="maintain",
                current_batch=current_batch,
                recommended_batch=self._last_safe_batch,
                reason=f"OOM occurred ({self._oom_count}x), using last safe batch",
            )

        # Check if underutilized
        if recent.gpu_util_pct < TARGET_GPU_UTIL and recent.vram_used_pct < TARGET_VRAM_LOW:
            new_batch = min(current_batch * 2, 16384)
            return UtilizationAction(
                action="increase_batch",
                current_batch=current_batch,
                recommended_batch=new_batch,
                reason=f"GPU util {recent.gpu_util_pct:.0f}% < {TARGET_GPU_UTIL}%, "
                       f"VRAM {recent.vram_used_pct:.0f}% < {TARGET_VRAM_LOW}%",
            )

        # Check if over target
        if recent.vram_used_pct > 90:
            new_batch = max(current_batch // 2, 32)
            return UtilizationAction(
                action="decrease_batch",
                current_batch=current_batch,
                recommended_batch=new_batch,
                reason=f"VRAM usage {recent.vram_used_pct:.0f}% too high",
            )

        return UtilizationAction(
            action="maintain",
            current_batch=current_batch,
            recommended_batch=current_batch,
            reason=f"GPU util {recent.gpu_util_pct:.0f}%, "
                   f"VRAM {recent.vram_used_pct:.0f}% — within target",
        )

    def record_oom(self, batch_size: int):
        """Record an OOM event."""
        self._oom_count += 1
        self._last_safe_batch = max(batch_size // 2, 32)
        logger.warning(
            f"[MONITOR] OOM at batch={batch_size}, "
            f"rolling back to {self._last_safe_batch}"
        )

    def get_summary(self) -> dict:
        """Get monitoring summary."""
        if not self._snapshots:
            return {}

        return {
            'snapshots': len(self._snapshots),
            'latest_gpu_util': self._snapshots[-1].gpu_util_pct,
            'latest_vram_pct': self._snapshots[-1].vram_used_pct,
            'max_batch_seen': self._max_batch_seen,
            'oom_count': self._oom_count,
        }
