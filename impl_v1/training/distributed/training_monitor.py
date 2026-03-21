from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


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
