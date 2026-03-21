from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Tuple


@dataclass
class ComputeSnapshot:
    batch_size: int
    learning_rate: float
    gpu_utilization: float
    memory_utilization: float
    latency_ms: float
    cluster_sps: float
    scaling_efficiency: float
    gradient_accumulation: int = 1
    zero_stage: int = 0


@dataclass
class TuningDecision:
    batch_size: int
    learning_rate: float
    gradient_accumulation: int
    zero_stage: int
    compute_efficiency: float
    action: str
    reasons: Tuple[str, ...]


class PerformanceIntelligence:
    """Heuristic tuner for throughput, latency, and scaling health."""

    def __init__(self):
        self._history: List[TuningDecision] = []

    def analyze(self, snapshot: ComputeSnapshot) -> TuningDecision:
        batch_size = max(1, int(snapshot.batch_size))
        learning_rate = max(1e-6, float(snapshot.learning_rate))
        gradient_accumulation = max(1, int(snapshot.gradient_accumulation))
        zero_stage = max(0, int(snapshot.zero_stage))
        reasons: List[str] = []

        if (
            snapshot.gpu_utilization < 70.0
            and snapshot.memory_utilization < 75.0
            and snapshot.latency_ms < 250.0
        ):
            batch_size = max(batch_size + 1, int(math.ceil(batch_size * 1.25)))
            reasons.append("increase_batch_for_idle_gpu")

        if (
            snapshot.gpu_utilization > 95.0
            or snapshot.memory_utilization > 90.0
            or snapshot.latency_ms > 500.0
        ):
            batch_size = max(1, int(math.floor(batch_size * 0.8)))
            reasons.append("reduce_batch_for_latency_or_memory")

        if snapshot.scaling_efficiency < 0.70:
            gradient_accumulation = max(gradient_accumulation, 2)
            zero_stage = max(zero_stage, 2)
            reasons.append("increase_zero_and_accumulation_for_comm_pressure")
        elif snapshot.scaling_efficiency > 0.90 and snapshot.gpu_utilization < 85.0:
            gradient_accumulation = max(1, gradient_accumulation - 1)
            reasons.append("reduce_accumulation_to_raise_throughput")

        batch_scale = batch_size / max(1, snapshot.batch_size)
        learning_rate = learning_rate * math.sqrt(batch_scale)
        if snapshot.scaling_efficiency < 0.70:
            learning_rate *= 0.9

        compute_efficiency = self._compute_efficiency(snapshot)
        action = "hold" if not reasons else ("scale_up" if batch_size >= snapshot.batch_size else "throttle")
        decision = TuningDecision(
            batch_size=batch_size,
            learning_rate=round(learning_rate, 8),
            gradient_accumulation=gradient_accumulation,
            zero_stage=zero_stage,
            compute_efficiency=compute_efficiency,
            action=action,
            reasons=tuple(reasons),
        )
        self._history.append(decision)
        self._history = self._history[-256:]
        return decision

    def _compute_efficiency(self, snapshot: ComputeSnapshot) -> float:
        latency_factor = min(1.0, 1000.0 / max(snapshot.latency_ms, 1.0) / 10.0)
        throughput_factor = min(1.0, snapshot.cluster_sps / max(snapshot.batch_size, 1) / 100.0)
        resource_balance = min(
            1.0,
            ((snapshot.gpu_utilization / 100.0) + (snapshot.memory_utilization / 100.0)) / 2.0,
        )
        efficiency = (
            throughput_factor * 0.35
            + latency_factor * 0.25
            + max(0.0, min(1.0, snapshot.scaling_efficiency)) * 0.30
            + resource_balance * 0.10
        )
        return round(min(1.0, efficiency), 4)

    def latest(self) -> Dict[str, Any]:
        if not self._history:
            return {}
        return asdict(self._history[-1])

    def history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return [asdict(item) for item in self._history[-max(1, limit) :]]
