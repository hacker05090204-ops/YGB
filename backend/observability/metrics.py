"""
Structured Telemetry Metrics Registry

Thread-safe in-process metrics for request latency, dependency latency,
timeout rate, error rate, measurement completeness, and missing-metric
detection.

Metrics:
    - Counters:    request_count, error_count, timeout_count, metric_missing_counter
    - Gauges:      measurement_completeness_ratio, null_metric_ratio
    - Histograms:  request_latency_ms, dependency_latency_ms, readiness_latency_ms

If a critical metric is missing when checked, a structured warning is
logged and metric_missing_counter is incremented.
"""

import collections
import logging
import threading
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ygb.observability.metrics")

# Infrastructure metrics — must always be present after server boot
INFRASTRUCTURE_METRICS = frozenset({
    "request_count",
    "error_count",
    "timeout_count",
    "measurement_completeness_ratio",
    "null_metric_ratio",
    "request_latency_ms",
    "dependency_latency_ms",
    "readiness_latency_ms",
    # Domain-specific pipeline metrics (emitted per-request / per-event)
    "training_latency_ms",
    "voice_inference_latency_ms",
    "report_generation_latency_ms",
})

# Training-only metrics — populated only when a training run completes.
# These are NOT flagged as missing during normal API operation.
TRAINING_ONLY_METRICS = frozenset({
    "model_accuracy",
    "ece",          # expected calibration error
    "drift_kl",     # KL divergence drift
    "duplicate_rate",
})

# Combined set for snapshot completeness
CRITICAL_METRICS = INFRASTRUCTURE_METRICS | TRAINING_ONLY_METRICS


class MetricsRegistry:
    """Thread-safe in-process metrics registry.

    Supports counters (monotonic increments), gauges (last-value),
    and histogram-style values (list of observations for percentile
    computation).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[str, float] = collections.defaultdict(float)
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = collections.defaultdict(list)
        self._last_updated: Dict[str, float] = {}

        # Pre-register critical metrics so they always appear in snapshots
        for name in CRITICAL_METRICS:
            self._counters.setdefault(name, 0.0)

    # ----- Recording API -----

    def increment(self, name: str, value: float = 1.0) -> None:
        """Increment a counter by value."""
        with self._lock:
            self._counters[name] += value
            self._last_updated[name] = time.monotonic()

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge to a specific value."""
        with self._lock:
            self._gauges[name] = value
            self._last_updated[name] = time.monotonic()

    def record(self, name: str, value: float) -> None:
        """Record a histogram observation (e.g. latency)."""
        with self._lock:
            self._histograms[name].append(value)
            # Keep only last 1000 observations to bound memory
            if len(self._histograms[name]) > 1000:
                self._histograms[name] = self._histograms[name][-500:]
            self._last_updated[name] = time.monotonic()

    # ----- Query API -----

    def get_counter(self, name: str) -> float:
        with self._lock:
            return self._counters.get(name, 0.0)

    def get_gauge(self, name: str) -> Optional[float]:
        with self._lock:
            return self._gauges.get(name)

    def get_histogram_stats(self, name: str) -> Dict[str, Any]:
        """Return count, min, max, mean, p50, p95, p99 for a histogram."""
        with self._lock:
            values = list(self._histograms.get(name, []))

        if not values:
            return {"count": 0}

        values.sort()
        count = len(values)
        return {
            "count": count,
            "min": round(values[0], 2),
            "max": round(values[-1], 2),
            "mean": round(sum(values) / count, 2),
            "p50": round(values[int(count * 0.5)], 2),
            "p95": round(values[min(int(count * 0.95), count - 1)], 2),
            "p99": round(values[min(int(count * 0.99), count - 1)], 2),
        }

    def get_snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot of all metrics."""
        with self._lock:
            snapshot: Dict[str, Any] = {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {},
            }
            histogram_names = list(self._histograms.keys())

        # Compute histogram stats outside the lock
        for name in histogram_names:
            snapshot["histograms"][name] = self.get_histogram_stats(name)

        return snapshot

    def check_critical_metrics(self) -> List[str]:
        """Verify all critical metrics have been recorded at least once.

        Returns list of missing metric names. For each missing metric,
        emits a structured warning log and increments metric_missing_counter.
        """
        missing: List[str] = []
        with self._lock:
            # Only flag infrastructure metrics as missing; training-only
            # metrics are expected to be absent outside training runs.
            for name in INFRASTRUCTURE_METRICS:
                if name not in self._last_updated:
                    missing.append(name)

        if missing:
            for name in missing:
                logger.warning(
                    "Critical metric never recorded: %s",
                    name,
                    extra={"metric_name": name, "event": "metric_missing"},
                )
            self.increment("metric_missing_counter", len(missing))

        return missing

    def reset(self) -> None:
        """Clear all metrics. For testing only."""
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._last_updated.clear()
            for name in CRITICAL_METRICS:
                self._counters[name] = 0.0


# Module-level singleton
metrics_registry = MetricsRegistry()


def get_measurement_completeness(data: Dict[str, Any], expected_fields: List[str]) -> float:
    """Calculate measurement completeness ratio for an API response.

    Returns float between 0.0 and 1.0 representing the fraction of
    expected fields that have non-null values.
    """
    if not expected_fields:
        return 1.0
    non_null = sum(1 for f in expected_fields if data.get(f) is not None)
    ratio = non_null / len(expected_fields)
    metrics_registry.set_gauge("measurement_completeness_ratio", ratio)
    return ratio


def get_null_metric_ratio(data: Dict[str, Any], metric_fields: List[str]) -> float:
    """Calculate the ratio of null/missing metric fields.

    Returns float between 0.0 and 1.0.
    """
    if not metric_fields:
        return 0.0
    null_count = sum(1 for f in metric_fields if data.get(f) is None)
    ratio = null_count / len(metric_fields)
    metrics_registry.set_gauge("null_metric_ratio", ratio)
    return ratio
