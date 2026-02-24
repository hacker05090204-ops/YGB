"""
YGB Training State Manager — Production-Grade Telemetry

Reads REAL training state from the G38 AutoTrainer singleton.
Uses psutil for CPU metrics and torch.cuda for GPU metrics.

ZERO mock data. ZERO fallback values. ZERO random values.
If training is inactive, returns status="idle" with null metrics.
"""

import os
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timezone

# Add project root for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class TrainingMetrics:
    """Real training metrics — no defaults, no mocks."""
    status: str  # "idle", "training", "completed", "error"
    current_epoch: Optional[int] = None
    total_epochs: Optional[int] = None
    loss: Optional[float] = None
    throughput: Optional[float] = None  # samples/sec
    gpu_usage_percent: Optional[float] = None
    gpu_memory_used_mb: Optional[float] = None
    gpu_memory_total_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    dataset_size: Optional[int] = None
    checkpoints_count: Optional[int] = None
    automode_status: Optional[str] = None
    last_accuracy: Optional[float] = None
    training_mode: Optional[str] = None
    started_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TrainingStateManager:
    """
    Production training state reader.

    Reads from:
    1. G38 AutoTrainer singleton (epoch, loss, accuracy, state)
    2. psutil (CPU usage)
    3. torch.cuda (GPU memory, availability)
    4. nvidia-smi subprocess (GPU utilization %, temperature)

    NEVER generates fake data.
    """

    def __init__(self):
        self._trainer = None
        self._g38_available = False
        self._init_g38()

    def _init_g38(self):
        """Try loading G38 AutoTrainer. No fallback if unavailable."""
        try:
            from impl_v1.phase49.runtime import get_auto_trainer
            self._trainer = get_auto_trainer()
            self._g38_available = True
        except ImportError:
            self._g38_available = False
            self._trainer = None

    def get_cpu_usage(self) -> Optional[float]:
        """Get real CPU usage via psutil. Returns None if unavailable."""
        try:
            import psutil
            return psutil.cpu_percent(interval=0.1)
        except ImportError:
            return None
        except Exception:
            return None

    def get_gpu_metrics(self) -> Dict[str, Optional[float]]:
        """Get real GPU metrics via torch.cuda. Real data only."""
        result: Dict[str, Optional[float]] = {
            "gpu_available": False,
            "gpu_usage_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
            "temperature": None,
        }

        try:
            import torch
            if not torch.cuda.is_available():
                return result

            result["gpu_available"] = True
            result["gpu_memory_used_mb"] = round(
                torch.cuda.memory_allocated() / 1024 / 1024, 2
            )
            props = torch.cuda.get_device_properties(0)
            result["gpu_memory_total_mb"] = round(
                props.total_mem / 1024 / 1024, 2
            )
        except Exception:
            pass

        # nvidia-smi for utilization and temperature
        try:
            import subprocess
            smi_output = subprocess.check_output(
                ["nvidia-smi",
                 "--query-gpu=utilization.gpu,temperature.gpu",
                 "--format=csv,noheader,nounits"],
                timeout=5,
                text=True
            ).strip()
            parts = smi_output.split(",")
            if len(parts) >= 2:
                result["gpu_usage_percent"] = float(parts[0].strip())
                result["temperature"] = float(parts[1].strip())
        except Exception:
            pass

        return result

    def get_checkpoint_count(self) -> Optional[int]:
        """Count real checkpoint files on disk."""
        checkpoint_dirs = [
            PROJECT_ROOT / "reports" / "g38_training",
            PROJECT_ROOT / "training" / "checkpoints",
        ]
        count = 0
        for d in checkpoint_dirs:
            if d.exists():
                count += len(list(d.glob("*.pt"))) + len(list(d.glob("*.pth")))
                count += len(list(d.glob("checkpoint_*")))
        return count if count > 0 else None

    def get_training_progress(self) -> TrainingMetrics:
        """
        Get real training progress.

        If training is inactive → status="idle", all metrics null.
        If G38 unavailable → status="idle", automode_status="g38_unavailable".
        NEVER returns mock/hardcoded metrics.
        """
        if not self._g38_available or self._trainer is None:
            return TrainingMetrics(
                status="idle",
                automode_status="g38_unavailable",
            )

        try:
            trainer_status = self._trainer.get_status()
        except Exception as e:
            import logging
            logging.getLogger(__name__).exception("Failed to get trainer status")
            return TrainingMetrics(
                status="error",
                automode_status="trainer_error",
            )

        is_training = trainer_status.get("is_training", False)
        state = trainer_status.get("state", "IDLE")

        if not is_training and state.upper() in ("IDLE", "STOPPED"):
            return TrainingMetrics(
                status="idle",
                automode_status=state,
                checkpoints_count=self.get_checkpoint_count(),
                total_epochs=trainer_status.get("total_completed") or None,
            )

        # Training is active — return REAL metrics only
        gpu = self.get_gpu_metrics()
        cpu = self.get_cpu_usage()

        # Extract real values; use None (not 0) if unavailable
        loss_val = trainer_status.get("last_loss")
        if loss_val == 0 or loss_val == 0.0:
            loss_val = None  # 0 is likely uninitialized, not real

        accuracy_val = trainer_status.get("last_accuracy")
        if accuracy_val == 0 or accuracy_val == 0.0:
            accuracy_val = None

        throughput_val = trainer_status.get("samples_per_sec")
        if throughput_val == 0 or throughput_val == 0.0:
            throughput_val = None

        dataset_val = trainer_status.get("dataset_size")
        if dataset_val == 0:
            dataset_val = None

        return TrainingMetrics(
            status="training" if is_training else state.lower(),
            current_epoch=trainer_status.get("epoch") or None,
            total_epochs=trainer_status.get("total_epochs") or None,
            loss=loss_val,
            throughput=throughput_val,
            gpu_usage_percent=gpu.get("gpu_usage_percent"),
            gpu_memory_used_mb=gpu.get("gpu_memory_used_mb"),
            gpu_memory_total_mb=gpu.get("gpu_memory_total_mb"),
            cpu_usage_percent=cpu,
            dataset_size=dataset_val,
            checkpoints_count=self.get_checkpoint_count(),
            automode_status=state,
            last_accuracy=accuracy_val,
            training_mode=trainer_status.get("training_mode"),
        )


# Singleton instance
_state_manager: Optional[TrainingStateManager] = None


def get_training_state_manager() -> TrainingStateManager:
    """Get or create the singleton TrainingStateManager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = TrainingStateManager()
    return _state_manager
