"""
speed_telemetry.py — Training Speed & GPU Utilization Metrics

Tracks:
  - samples_per_sec: Training throughput
  - gpu_util_avg: Average GPU utilization (%)
  - mode_a_time: Seconds spent in MODE_A training
  - mode_b_time: Seconds spent in MODE_B training
  - epoch_time: Time per epoch

Output: JSON telemetry appended to training report.
"""

import json
import os
import time
import logging
from dataclasses import dataclass, asdict, field
from typing import Optional, List

logger = logging.getLogger(__name__)


# =============================================================================
# TELEMETRY DATA
# =============================================================================

@dataclass
class EpochMetrics:
    """Metrics for a single training epoch."""
    epoch: int
    samples_per_sec: float
    epoch_time_sec: float
    loss: float
    accuracy: float
    gpu_memory_used_mb: float = 0.0
    gpu_memory_total_mb: float = 0.0


@dataclass
class SpeedTelemetry:
    """Aggregate training speed telemetry."""
    samples_per_sec: float = 0.0
    gpu_util_avg: float = 0.0
    mode_a_time: float = 0.0
    mode_b_time: float = 0.0
    amp_enabled: bool = False
    total_epochs: int = 0
    total_samples: int = 0
    avg_epoch_time: float = 0.0
    peak_samples_per_sec: float = 0.0
    epoch_metrics: List[EpochMetrics] = field(default_factory=list)


# =============================================================================
# GPU UTILIZATION
# =============================================================================

def get_gpu_utilization() -> dict:
    """Get GPU utilization and memory stats.
    
    Returns:
        Dict with gpu_util_pct, memory_used_mb, memory_total_mb.
    """
    result = {
        'gpu_util_pct': 0.0,
        'memory_used_mb': 0.0,
        'memory_total_mb': 0.0,
        'available': False,
    }
    
    try:
        import torch
        if not torch.cuda.is_available():
            return result
        
        result['available'] = True
        result['memory_used_mb'] = torch.cuda.memory_allocated() / (1024 * 1024)
        result['memory_total_mb'] = torch.cuda.get_device_properties(0).total_mem / (1024 * 1024)
        
        # GPU utilization from memory ratio (approximate)
        if result['memory_total_mb'] > 0:
            result['gpu_util_pct'] = (result['memory_used_mb'] / result['memory_total_mb']) * 100
        
    except Exception:
        pass
    
    return result


# =============================================================================
# TELEMETRY TRACKER
# =============================================================================

class SpeedTracker:
    """Track training speed metrics across epochs."""
    
    def __init__(self):
        self._telemetry = SpeedTelemetry()
        self._epoch_start: float = 0.0
        self._mode_start: float = 0.0
        self._current_mode: str = ''
        self._gpu_util_samples: List[float] = []
    
    def start_epoch(self):
        """Mark start of an epoch."""
        self._epoch_start = time.perf_counter()
        
        # Sample GPU utilization
        gpu_info = get_gpu_utilization()
        if gpu_info['available']:
            self._gpu_util_samples.append(gpu_info['gpu_util_pct'])
    
    def end_epoch(self, epoch: int, total_samples: int,
                  loss: float, accuracy: float):
        """Mark end of an epoch and record metrics.
        
        Args:
            epoch: Epoch number.
            total_samples: Samples processed in this epoch.
            loss: Training loss.
            accuracy: Training accuracy.
        """
        elapsed = time.perf_counter() - self._epoch_start
        sps = total_samples / max(elapsed, 0.001)
        
        gpu_info = get_gpu_utilization()
        
        metrics = EpochMetrics(
            epoch=epoch,
            samples_per_sec=sps,
            epoch_time_sec=elapsed,
            loss=loss,
            accuracy=accuracy,
            gpu_memory_used_mb=gpu_info['memory_used_mb'],
            gpu_memory_total_mb=gpu_info['memory_total_mb'],
        )
        
        self._telemetry.epoch_metrics.append(metrics)
        self._telemetry.total_epochs += 1
        self._telemetry.total_samples += total_samples
        self._telemetry.peak_samples_per_sec = max(
            self._telemetry.peak_samples_per_sec, sps
        )
        
        # Update averages
        if self._telemetry.total_epochs > 0:
            total_time = sum(m.epoch_time_sec for m in self._telemetry.epoch_metrics)
            self._telemetry.avg_epoch_time = total_time / self._telemetry.total_epochs
            self._telemetry.samples_per_sec = (
                self._telemetry.total_samples / max(total_time, 0.001)
            )
        
        if self._gpu_util_samples:
            self._telemetry.gpu_util_avg = sum(self._gpu_util_samples) / len(self._gpu_util_samples)
        
        logger.info(
            f"[TELEMETRY] Epoch {epoch}: "
            f"{sps:.0f} samples/sec, {elapsed:.2f}s, "
            f"GPU util={self._telemetry.gpu_util_avg:.1f}%"
        )
    
    def start_mode(self, mode: str):
        """Start timing a training mode (MODE_A, MODE_B)."""
        self._mode_start = time.perf_counter()
        self._current_mode = mode
    
    def end_mode(self):
        """End timing current training mode."""
        elapsed = time.perf_counter() - self._mode_start
        if self._current_mode == 'MODE_A':
            self._telemetry.mode_a_time += elapsed
        elif self._current_mode == 'MODE_B':
            self._telemetry.mode_b_time += elapsed
        self._current_mode = ''
    
    def get_telemetry(self) -> dict:
        """Get current telemetry as JSON-serializable dict."""
        data = asdict(self._telemetry)
        # Flatten epoch_metrics for JSON output
        data['epoch_count'] = len(data.pop('epoch_metrics', []))
        return data
    
    def save_telemetry(self, path: str = None) -> str:
        """Save telemetry to JSON file.
        
        Args:
            path: Optional custom path. Default: reports/speed_telemetry.json
        
        Returns:
            Path to saved file.
        """
        if path is None:
            path = os.path.join('reports', 'speed_telemetry.json')
        
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, 'w') as f:
            json.dump(self.get_telemetry(), f, indent=2)
        
        logger.info(f"[TELEMETRY] Saved to {path}")
        return path


# =============================================================================
# MODULE-LEVEL TRACKER
# =============================================================================

_global_tracker: Optional[SpeedTracker] = None


def get_speed_tracker() -> SpeedTracker:
    """Get the global speed tracker (create if needed)."""
    global _global_tracker
    if _global_tracker is None:
        _global_tracker = SpeedTracker()
    return _global_tracker
