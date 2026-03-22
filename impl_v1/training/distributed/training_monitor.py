from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional


class DriftType(Enum):
    LOSS_SPIKE = "LOSS_SPIKE"
    GRAD_EXPLOSION = "GRAD_EXPLOSION"
    ACCURACY_DROP = "ACCURACY_DROP"


class DriftSeverity(Enum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class EnergyMetric:
    epoch: int
    avg_power_watts: float
    epoch_duration_sec: float
    energy_joules: float
    energy_kwh: float
    timestamp: str


@dataclass
class DriftAnomaly:
    epoch: int
    drift_type: DriftType
    severity: DriftSeverity
    message: str


@dataclass
class DriftCheckResult:
    epoch: int
    anomalies: List[DriftAnomaly] = field(default_factory=list)
    should_pause: bool = False


class EnergyTracker:
    def __init__(self):
        self.metrics: List[EnergyMetric] = []

    def record_epoch(self, epoch: int, avg_power_watts: float, epoch_duration_sec: float) -> EnergyMetric:
        energy_joules = float(avg_power_watts) * float(epoch_duration_sec)
        metric = EnergyMetric(
            epoch=int(epoch),
            avg_power_watts=float(avg_power_watts),
            epoch_duration_sec=float(epoch_duration_sec),
            energy_joules=energy_joules,
            energy_kwh=energy_joules / 3_600_000.0,
            timestamp=datetime.now().isoformat(),
        )
        self.metrics.append(metric)
        return metric

    def get_average_energy(self) -> float:
        if not self.metrics:
            return 0.0
        return sum(metric.energy_joules for metric in self.metrics) / len(self.metrics)

    def get_summary(self) -> Dict[str, float]:
        total_energy = sum(metric.energy_joules for metric in self.metrics)
        return {
            "total_epochs": len(self.metrics),
            "total_energy_joules": total_energy,
            "average_energy_joules": self.get_average_energy(),
        }


class DriftDetector:
    def __init__(self):
        self._previous_loss: Optional[float] = None
        self._previous_grad_norm: Optional[float] = None
        self._previous_accuracy: Optional[float] = None
        self._results: List[DriftCheckResult] = []

    def check_epoch(self, epoch: int, val_loss: float, grad_norm: float, accuracy: float) -> DriftCheckResult:
        anomalies: List[DriftAnomaly] = []

        if self._previous_loss and self._previous_loss > 0:
            loss_ratio = float(val_loss) / self._previous_loss
            if loss_ratio >= 5.0:
                anomalies.append(
                    DriftAnomaly(
                        epoch=int(epoch),
                        drift_type=DriftType.LOSS_SPIKE,
                        severity=DriftSeverity.CRITICAL,
                        message=f"Validation loss spiked {loss_ratio:.2f}x",
                    )
                )
            elif loss_ratio >= 2.0:
                anomalies.append(
                    DriftAnomaly(
                        epoch=int(epoch),
                        drift_type=DriftType.LOSS_SPIKE,
                        severity=DriftSeverity.WARNING,
                        message=f"Validation loss spiked {loss_ratio:.2f}x",
                    )
                )

        if self._previous_grad_norm and self._previous_grad_norm > 0:
            grad_ratio = float(grad_norm) / self._previous_grad_norm
            if grad_ratio >= 25.0:
                anomalies.append(
                    DriftAnomaly(
                        epoch=int(epoch),
                        drift_type=DriftType.GRAD_EXPLOSION,
                        severity=DriftSeverity.CRITICAL,
                        message=f"Gradient norm spiked {grad_ratio:.2f}x",
                    )
                )
            elif grad_ratio >= 10.0:
                anomalies.append(
                    DriftAnomaly(
                        epoch=int(epoch),
                        drift_type=DriftType.GRAD_EXPLOSION,
                        severity=DriftSeverity.WARNING,
                        message=f"Gradient norm spiked {grad_ratio:.2f}x",
                    )
                )

        if self._previous_accuracy is not None:
            accuracy_drop = self._previous_accuracy - float(accuracy)
            if accuracy_drop >= 0.15:
                anomalies.append(
                    DriftAnomaly(
                        epoch=int(epoch),
                        drift_type=DriftType.ACCURACY_DROP,
                        severity=DriftSeverity.CRITICAL,
                        message=f"Accuracy dropped by {accuracy_drop:.4f}",
                    )
                )
            elif accuracy_drop >= 0.05:
                anomalies.append(
                    DriftAnomaly(
                        epoch=int(epoch),
                        drift_type=DriftType.ACCURACY_DROP,
                        severity=DriftSeverity.WARNING,
                        message=f"Accuracy dropped by {accuracy_drop:.4f}",
                    )
                )

        result = DriftCheckResult(
            epoch=int(epoch),
            anomalies=anomalies,
            should_pause=any(anomaly.severity == DriftSeverity.CRITICAL for anomaly in anomalies),
        )
        self._results.append(result)

        self._previous_loss = float(val_loss)
        self._previous_grad_norm = float(grad_norm)
        self._previous_accuracy = float(accuracy)
        return result

    def get_summary(self) -> Dict[str, float]:
        total_anomalies = sum(len(result.anomalies) for result in self._results)
        total_critical = sum(
            1
            for result in self._results
            for anomaly in result.anomalies
            if anomaly.severity == DriftSeverity.CRITICAL
        )
        return {
            "epochs_monitored": len(self._results),
            "total_anomalies": total_anomalies,
            "critical_anomalies": total_critical,
        }


@dataclass
class ThroughputSample:
    step: int
    epoch: int
    samples_per_second: float
    batch_size: int
    timestamp: str


@dataclass
class GPUSnapshot:
    device_index: int
    utilization_percent: Optional[float]
    memory_used_mb: Optional[float]
    memory_total_mb: Optional[float]
    timestamp: str


@dataclass
class TrainingDashboardState:
    run_id: str
    started_at: str
    throughput: List[ThroughputSample] = field(default_factory=list)
    gpu: List[GPUSnapshot] = field(default_factory=list)
    runtime: List[Dict[str, float | int | str]] = field(default_factory=list)
    latest_metrics: Dict[str, float] = field(default_factory=dict)


class TrainingMonitor:
    def __init__(self, dashboard_path: str, flush_interval_seconds: float = 1.5):
        self.dashboard_path = dashboard_path
        self.flush_interval_seconds = max(0.1, float(flush_interval_seconds))
        self.state = TrainingDashboardState(
            run_id=datetime.now().strftime("run_%Y%m%d_%H%M%S"),
            started_at=datetime.now().isoformat(),
        )
        self._last_flush = 0.0
        os.makedirs(os.path.dirname(dashboard_path) or ".", exist_ok=True)

    def _write(self) -> None:
        tmp = f"{self.dashboard_path}.tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    **asdict(self.state),
                    "updated_at": datetime.now().isoformat(),
                },
                handle,
                indent=2,
            )
        os.replace(tmp, self.dashboard_path)
        self._last_flush = time.time()

    def _maybe_flush(self, force: bool = False) -> None:
        now = time.time()
        if force or (now - self._last_flush) >= self.flush_interval_seconds:
            self._write()

    def flush(self) -> None:
        self._maybe_flush(force=True)

    def record_throughput(self, *, step: int, epoch: int, samples_per_second: float, batch_size: int) -> None:
        self.state.throughput.append(
            ThroughputSample(
                step=step,
                epoch=epoch,
                samples_per_second=round(samples_per_second, 4),
                batch_size=batch_size,
                timestamp=datetime.now().isoformat(),
            )
        )
        self.state.throughput = self.state.throughput[-500:]
        self.state.latest_metrics["samples_per_second"] = round(samples_per_second, 4)
        self._maybe_flush()

    def record_runtime(
        self,
        *,
        step: int,
        epoch: int,
        batch_size: int,
        learning_rate: float,
        gradient_accumulation: int,
        samples_per_second: float,
        step_time_ms: float,
        data_time_ms: float,
    ) -> None:
        runtime_sample: Dict[str, float | int | str] = {
            "step": step,
            "epoch": epoch,
            "batch_size": int(batch_size),
            "learning_rate": round(float(learning_rate), 8),
            "gradient_accumulation": int(gradient_accumulation),
            "samples_per_second": round(float(samples_per_second), 4),
            "step_time_ms": round(float(step_time_ms), 4),
            "data_time_ms": round(float(data_time_ms), 4),
            "timestamp": datetime.now().isoformat(),
        }
        self.state.runtime.append(runtime_sample)
        self.state.runtime = self.state.runtime[-500:]
        self.state.latest_metrics["batch_size"] = float(batch_size)
        self.state.latest_metrics["learning_rate"] = round(float(learning_rate), 8)
        self.state.latest_metrics["gradient_accumulation"] = float(gradient_accumulation)
        self.state.latest_metrics["step_time_ms"] = round(float(step_time_ms), 4)
        self.state.latest_metrics["data_time_ms"] = round(float(data_time_ms), 4)
        self._maybe_flush()

    def record_gpu(self) -> None:
        snapshot = GPUSnapshot(
            device_index=0,
            utilization_percent=None,
            memory_used_mb=None,
            memory_total_mb=None,
            timestamp=datetime.now().isoformat(),
        )
        try:
            import torch

            if torch.cuda.is_available():
                snapshot.memory_used_mb = round(torch.cuda.memory_allocated(0) / (1024 * 1024), 2)
                snapshot.memory_total_mb = round(torch.cuda.get_device_properties(0).total_memory / (1024 * 1024), 2)
        except Exception:
            pass

        try:
            import pynvml  # type: ignore

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
            snapshot.utilization_percent = float(util.gpu)
            snapshot.memory_used_mb = round(mem.used / (1024 * 1024), 2)
            snapshot.memory_total_mb = round(mem.total / (1024 * 1024), 2)
        except Exception:
            pass

        self.state.gpu.append(snapshot)
        self.state.gpu = self.state.gpu[-200:]
        if snapshot.utilization_percent is not None:
            self.state.latest_metrics["gpu_utilization_percent"] = snapshot.utilization_percent
        if snapshot.memory_total_mb:
            self.state.latest_metrics["memory_utilization_percent"] = round(
                (snapshot.memory_used_mb or 0.0) / max(snapshot.memory_total_mb, 1e-6) * 100.0,
                4,
            )
        self._maybe_flush()

    def latest_snapshot(self) -> Dict[str, float]:
        snapshot = dict(self.state.latest_metrics)
        if self.state.gpu:
            latest_gpu = self.state.gpu[-1]
            if latest_gpu.utilization_percent is not None:
                snapshot["gpu_utilization_percent"] = float(latest_gpu.utilization_percent)
            if latest_gpu.memory_total_mb:
                snapshot["memory_utilization_percent"] = round(
                    (latest_gpu.memory_used_mb or 0.0) / max(latest_gpu.memory_total_mb, 1e-6) * 100.0,
                    4,
                )
        return snapshot
