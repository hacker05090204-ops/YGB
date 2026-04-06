"""
YGB Training State Manager — Production-Grade Telemetry

Reads REAL training state from the G38 AutoTrainer singleton.
Uses psutil for CPU metrics and torch.cuda for GPU metrics.

ZERO mock data. ZERO fallback values. ZERO random values.
If training is inactive, returns status="idle" with null metrics.
"""

import sys
import time
import logging
import subprocess
import threading
import numpy as np
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime, timezone
from scipy.special import kl_div
from sklearn.calibration import calibration_curve

# Add project root for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

GPU_DRIVER_INSTALL_COMMAND = "sudo apt install nvidia-driver-535 && sudo reboot"
GPU_METRIC_EMIT_INTERVAL_SECONDS = 60.0
GPU_WATCHDOG_POLL_INTERVAL_SECONDS = 30.0
GPU_WATCHDOG_ALERT_METRIC = "gpu_watchdog_alert_total"


class TrainingPausedException(RuntimeError):
    """Raised when drift checks require human review before training continues."""


def get_optimized_dataloader_kwargs() -> Dict[str, Any]:
    """Return the default DataLoader tuning for GPU-friendly training."""
    return {
        "num_workers": 4,
        "pin_memory": True,
        "persistent_workers": True,
    }


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
        self._last_gpu_emit_at = 0.0
        self._last_gpu_available: Optional[bool] = None
        self._watchdog_stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._init_g38()
        self._bootstrap_gpu_runtime()

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

    def _bootstrap_gpu_runtime(self) -> None:
        """Emit startup GPU status and configure PyTorch when CUDA is present."""
        gpu_metrics = self.get_gpu_metrics(force_emit=True)
        gpu_available = bool(gpu_metrics.get("gpu_available"))
        self._last_gpu_available = gpu_available
        self._configure_gpu_runtime(gpu_available)

        if not gpu_available:
            logger.warning(
                "CUDA unavailable; CPU fallback active. Install driver with: %s",
                GPU_DRIVER_INSTALL_COMMAND,
            )

    def _configure_gpu_runtime(self, gpu_available: bool) -> None:
        """Enable the preferred CUDA runtime flags when GPU training is available."""
        if not gpu_available:
            return

        try:
            import torch

            if hasattr(torch, "set_float32_matmul_precision"):
                torch.set_float32_matmul_precision("high")
            if hasattr(torch, "backends") and hasattr(torch.backends, "cudnn"):
                torch.backends.cudnn.benchmark = True
        except Exception:
            logger.debug("Failed to configure CUDA runtime flags", exc_info=True)

    def _emit_gpu_runtime_metrics(
        self,
        gpu_metrics: Dict[str, Optional[float]],
        *,
        force: bool = False,
    ) -> None:
        """Publish runtime GPU gauges on a throttled cadence."""
        now = time.monotonic()
        if not force and (now - self._last_gpu_emit_at) < GPU_METRIC_EMIT_INTERVAL_SECONDS:
            return

        try:
            from backend.observability.metrics import metrics_registry

            gpu_available = bool(gpu_metrics.get("gpu_available"))
            metrics_registry.set_gauge(
                "gpu_fallback_active",
                0.0 if gpu_available else 1.0,
            )

            gpu_memory_used_mb = gpu_metrics.get("gpu_memory_used_mb")
            if gpu_memory_used_mb is not None:
                metrics_registry.set_gauge("gpu_memory_used_mb", float(gpu_memory_used_mb))

            gpu_usage_percent = gpu_metrics.get("gpu_usage_percent")
            if gpu_usage_percent is not None:
                metrics_registry.set_gauge("gpu_utilization_pct", float(gpu_usage_percent))

            self._last_gpu_emit_at = now
        except Exception:
            logger.debug("Failed to emit GPU runtime metrics", exc_info=True)

    def get_gpu_metrics(self, *, force_emit: bool = False) -> Dict[str, Optional[float]]:
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
                self._emit_gpu_runtime_metrics(result, force=force_emit)
                return result

            result["gpu_available"] = True
            result["gpu_memory_used_mb"] = round(
                torch.cuda.memory_allocated() / 1024 / 1024, 2
            )
            props = torch.cuda.get_device_properties(0)
            result["gpu_memory_total_mb"] = round(
                props.total_memory / 1024 / 1024, 2
            )
        except Exception:
            self._emit_gpu_runtime_metrics(result, force=force_emit)
            return result

        # nvidia-smi for utilization and temperature
        try:
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
        except TrainingPausedException:
            raise
        except Exception as exc:
            logger.warning(
                "Non-critical failure while collecting GPU metrics: %s",
                exc,
                exc_info=True,
            )

        self._emit_gpu_runtime_metrics(result, force=force_emit)
        return result

    def _is_training_active(self) -> bool:
        """Return True when the upstream trainer reports an active training run."""
        if not self._g38_available or self._trainer is None:
            return False

        try:
            status = self._trainer.get_status()
        except Exception:
            return False

        return bool(status.get("is_training", False)) or str(
            status.get("state", "")
        ).upper() == "TRAINING"

    def run_gpu_watchdog_cycle(self) -> None:
        """Run one watchdog check and emit an alert if CUDA drops during training."""
        gpu_metrics = self.get_gpu_metrics(force_emit=True)
        gpu_available = bool(gpu_metrics.get("gpu_available"))

        if self._last_gpu_available is True and not gpu_available and self._is_training_active():
            try:
                from backend.observability.metrics import metrics_registry

                metrics_registry.increment(GPU_WATCHDOG_ALERT_METRIC)
            except Exception:
                logger.debug("Failed to increment GPU watchdog alert metric", exc_info=True)

            logger.critical("GPU watchdog detected CUDA drop mid-training")

        self._last_gpu_available = gpu_available

    def _gpu_watchdog_loop(self) -> None:
        """Background watchdog loop for CUDA runtime health."""
        while not self._watchdog_stop_event.wait(GPU_WATCHDOG_POLL_INTERVAL_SECONDS):
            self.run_gpu_watchdog_cycle()

    def start_gpu_watchdog(self) -> None:
        """Start the background GPU watchdog once for the singleton manager."""
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            return

        self._watchdog_stop_event.clear()
        self._watchdog_thread = threading.Thread(
            target=self._gpu_watchdog_loop,
            name="ygb-gpu-watchdog",
            daemon=True,
        )
        self._watchdog_thread.start()

    def stop_gpu_watchdog(self) -> None:
        """Stop the background GPU watchdog."""
        self._watchdog_stop_event.set()
        if self._watchdog_thread is not None and self._watchdog_thread.is_alive():
            self._watchdog_thread.join(timeout=0.5)

    def get_checkpoint_count(self) -> Optional[int]:
        """Count real checkpoint files on disk."""
        checkpoint_dirs = [
            PROJECT_ROOT / "reports" / "g38_training",
            PROJECT_ROOT / "training" / "checkpoints",
        ]
        count = 0
        for d in checkpoint_dirs:
            if d.exists():
                count += len(list(d.glob("*.safetensors")))
                count += len(list(d.glob("*.safetensor")))
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
            error_status = str(e).strip() or "trainer_error"
            return TrainingMetrics(
                status="error",
                automode_status=error_status,
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

    def emit_training_metrics(
        self,
        metrics: "TrainingMetrics",
        *,
        calibration_labels: Optional[list[int]] = None,
        calibration_probabilities: Optional[list[float]] = None,
        distribution: Optional[list[list[float]]] = None,
        epoch_number: Optional[int] = None,
    ) -> None:
        """Emit training domain metrics to the observability registry."""
        try:
            from backend.observability.metrics import metrics_registry
            if metrics.elapsed_seconds is not None:
                metrics_registry.record(
                    "training_latency_ms",
                    round(metrics.elapsed_seconds * 1000, 2),
                )
            if metrics.last_accuracy is not None:
                metrics_registry.set_gauge("model_accuracy", metrics.last_accuracy)
            if metrics.gpu_memory_used_mb is not None:
                metrics_registry.set_gauge("gpu_memory_used_mb", metrics.gpu_memory_used_mb)
            if metrics.gpu_usage_percent is not None:
                metrics_registry.set_gauge("gpu_utilization_pct", metrics.gpu_usage_percent)
            metrics_registry.set_gauge(
                "gpu_fallback_active",
                0.0 if (metrics.gpu_memory_used_mb is not None or metrics.gpu_usage_percent is not None) else 1.0,
            )

            if calibration_labels and calibration_probabilities:
                labels = np.asarray(calibration_labels, dtype=float)
                probabilities = np.clip(np.asarray(calibration_probabilities, dtype=float), 1e-6, 1.0 - 1e-6)
                calibration_curve(labels, probabilities, n_bins=10)
                bin_indices = np.minimum((probabilities * 10).astype(int), 9)
                ece = 0.0
                for bin_number in range(10):
                    mask = bin_indices == bin_number
                    if np.any(mask):
                        confidence = float(np.mean(probabilities[mask]))
                        accuracy = float(np.mean(labels[mask]))
                        ece += abs(confidence - accuracy) * (float(np.sum(mask)) / float(len(probabilities)))
                metrics_registry.set_gauge("ece", ece)
                if ece > 0.15:
                    logger.warning("ECE=%.4f exceeds threshold 0.15", ece)

            if distribution is not None and epoch_number is not None:
                dist_history_dir = PROJECT_ROOT / "checkpoints" / "dist_history"
                dist_history_dir.mkdir(parents=True, exist_ok=True)
                current_distribution = np.asarray(distribution, dtype=float)
                if current_distribution.ndim > 1:
                    current_distribution = np.mean(current_distribution, axis=0)
                current_distribution = np.clip(current_distribution, 1e-6, None)
                current_distribution = current_distribution / current_distribution.sum()
                np.save(dist_history_dir / f"epoch_{epoch_number}.npy", current_distribution)

                drift_value = 0.0
                historical_path = dist_history_dir / f"epoch_{epoch_number - 10}.npy"
                if epoch_number >= 10 and historical_path.exists():
                    prior_distribution = np.load(historical_path)
                    prior_distribution = np.clip(prior_distribution.astype(float), 1e-6, None)
                    prior_distribution = prior_distribution / prior_distribution.sum()
                    drift_value = float(np.sum(kl_div(current_distribution, prior_distribution)))
                    if drift_value > 0.15:
                        logger.critical("drift_kl=%.4f exceeds 0.15, pausing training", drift_value)
                        metrics_registry.set_gauge("training_paused", 1.0)
                        metrics_registry.set_gauge("drift_kl", drift_value)
                        raise TrainingPausedException("KL drift threshold exceeded")
                metrics_registry.set_gauge("drift_kl", drift_value)
        except TrainingPausedException:
            raise
        except Exception as exc:
            logger.debug("Failed to emit drift_kl gauge: %s", exc, exc_info=True)


# Singleton instance
_state_manager: Optional[TrainingStateManager] = None


def get_training_state_manager() -> TrainingStateManager:
    """Get or create the singleton TrainingStateManager."""
    global _state_manager
    if _state_manager is None:
        _state_manager = TrainingStateManager()
        _state_manager.start_gpu_watchdog()
    return _state_manager
