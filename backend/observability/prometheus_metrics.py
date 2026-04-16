from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from typing import Dict


@dataclass
class PrometheusMetricsRegistry:
    """Lightweight in-process metrics registry with Prometheus-compatible names."""

    counters: Dict[str, float] = field(default_factory=dict)
    gauges: Dict[str, float] = field(default_factory=dict)
    histograms: Dict[str, list[float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def inc_counter(self, name: str, amount: float = 1.0) -> float:
        with self._lock:
            self.counters[name] = float(self.counters.get(name, 0.0)) + float(amount)
            return self.counters[name]

    def set_gauge(self, name: str, value: float) -> float:
        with self._lock:
            self.gauges[name] = float(value)
            return self.gauges[name]

    def observe_histogram(self, name: str, value: float) -> None:
        with self._lock:
            self.histograms.setdefault(name, []).append(float(value))

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "counters": dict(self.counters),
                "gauges": dict(self.gauges),
                "histograms": {key: list(values) for key, values in self.histograms.items()},
            }


_PROMETHEUS_REGISTRY = PrometheusMetricsRegistry()


def get_prometheus_metrics_registry() -> PrometheusMetricsRegistry:
    return _PROMETHEUS_REGISTRY


__all__ = ["PrometheusMetricsRegistry", "get_prometheus_metrics_registry"]
