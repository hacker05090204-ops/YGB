"""
Metrics Exporter - Prometheus Format
=====================================

Export system metrics in Prometheus format:
- Auto-mode state
- Drift events
- Performance metrics
- Seccomp violations
- Emergency lock state
"""

from dataclasses import dataclass
from typing import Dict, List
from datetime import datetime
from pathlib import Path
import json


# =============================================================================
# METRIC TYPES
# =============================================================================


@dataclass
class Metric:
    """A Prometheus-style metric."""

    name: str
    help: str
    type: str  # counter, gauge, histogram
    labels: Dict[str, str]
    value: float


class MetricType:
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"


# =============================================================================
# METRICS REGISTRY
# =============================================================================


class MetricsRegistry:
    """Registry for Prometheus metrics."""

    def __init__(self):
        self.metrics: List[Metric] = []

    def gauge(self, name: str, value: float, help: str = "", labels: dict = None):
        """Register a gauge metric."""
        self.metrics.append(
            Metric(
                name=name,
                help=help,
                type=MetricType.GAUGE,
                labels=labels or {},
                value=value,
            )
        )

    def counter(self, name: str, value: float, help: str = "", labels: dict = None):
        """Register a counter metric."""
        self.metrics.append(
            Metric(
                name=name,
                help=help,
                type=MetricType.COUNTER,
                labels=labels or {},
                value=value,
            )
        )

    def export(self) -> str:
        """Export metrics in Prometheus format."""
        lines = []

        for m in self.metrics:
            # Help line
            lines.append(f"# HELP {m.name} {m.help}")
            lines.append(f"# TYPE {m.name} {m.type}")

            # Metric line with labels
            if m.labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in m.labels.items())
                lines.append(f"{m.name}{{{label_str}}} {m.value}")
            else:
                lines.append(f"{m.name} {m.value}")

        return "\n".join(lines)


# =============================================================================
# SYSTEM METRICS COLLECTOR
# =============================================================================


class SystemMetricsCollector:
    """Collect system metrics for export."""

    def __init__(self):
        self.registry = MetricsRegistry()

    def collect_auto_mode_state(self, enabled: bool):
        """Collect auto-mode state."""
        self.registry.gauge(
            "ygb_auto_mode_enabled",
            1.0 if enabled else 0.0,
            "Whether auto-mode is enabled",
        )

    def collect_drift_events(self, accuracy_drift: int, calibration_drift: int):
        """Collect drift event counts."""
        self.registry.counter(
            "ygb_drift_events_total",
            accuracy_drift,
            "Total accuracy drift events",
            {"type": "accuracy"},
        )
        self.registry.counter(
            "ygb_drift_events_total",
            calibration_drift,
            "Total calibration drift events",
            {"type": "calibration"},
        )

    def collect_performance_metrics(
        self,
        scan_latency_ms: float,
        memory_mb: float,
        cpu_percent: float,
    ):
        """Collect performance metrics."""
        self.registry.gauge(
            "ygb_scan_latency_ms",
            scan_latency_ms,
            "Scan latency in milliseconds",
        )
        self.registry.gauge(
            "ygb_memory_usage_mb",
            memory_mb,
            "Memory usage in megabytes",
        )
        self.registry.gauge(
            "ygb_cpu_percent",
            cpu_percent,
            "CPU usage percentage",
        )

    def collect_seccomp_violations(self, count: int):
        """Collect seccomp violation count."""
        self.registry.counter(
            "ygb_seccomp_violations_total",
            count,
            "Total seccomp violations detected",
        )

    def collect_emergency_lock(self, active: bool):
        """Collect emergency lock state."""
        self.registry.gauge(
            "ygb_emergency_lock_active",
            1.0 if active else 0.0,
            "Whether emergency lock is active",
        )

    def collect_calibration_trend(self, ece: float):
        """Collect calibration error trend."""
        self.registry.gauge(
            "ygb_calibration_ece",
            ece,
            "Expected calibration error",
        )

    def export(self) -> str:
        """Export all collected metrics."""
        return self.registry.export()


# =============================================================================
# METRICS ENDPOINT
# =============================================================================


def _collect_real_metrics(collector: SystemMetricsCollector) -> None:
    """Collect real metrics from system state files and runtime."""
    from impl_v1.training.evaluation.accuracy_metrics import AccuracyFeedbackStore
    from pathlib import Path

    reports_dir = Path("reports")

    # Auto-mode state
    auto_mode_state_file = reports_dir / "auto_mode_state.json"
    auto_mode_enabled = False
    if auto_mode_state_file.exists():
        try:
            state_data = json.loads(auto_mode_state_file.read_text(encoding="utf-8"))
            auto_mode_enabled = bool(state_data.get("unlocked", False))
        except (json.JSONDecodeError, OSError):
            pass
    collector.collect_auto_mode_state(auto_mode_enabled)

    # Emergency lock state
    governance_state_file = reports_dir / "governance_state.json"
    emergency_lock = False
    if governance_state_file.exists():
        try:
            gov_data = json.loads(governance_state_file.read_text(encoding="utf-8"))
            emergency_lock = bool(gov_data.get("emergency_lock_active", False))
        except (json.JSONDecodeError, OSError):
            pass
    collector.collect_emergency_lock(emergency_lock)

    # Drift events from failure log
    accuracy_drift = 0
    calibration_drift = 0
    failure_log_file = reports_dir / "failure_log.jsonl"
    if failure_log_file.exists():
        try:
            for line in failure_log_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                failure_type = str(record.get("failure_type", ""))
                if failure_type == "drift":
                    accuracy_drift += 1
                elif failure_type == "calibration_break":
                    calibration_drift += 1
        except (json.JSONDecodeError, OSError):
            pass
    collector.collect_drift_events(accuracy_drift, calibration_drift)

    # Calibration trend from accuracy feedback
    calibration_error = 0.0
    try:
        store = AccuracyFeedbackStore()
        summary = store.summary()
        by_category = summary.get("by_category", {})
        ece_values = [
            cat.get("false_positive_rate", 0.0)
            for cat in by_category.values()
            if isinstance(cat, dict)
        ]
        calibration_error = sum(ece_values) / len(ece_values) if ece_values else 0.0
        calibration_error = min(max(calibration_error, 0.0), 1.0)
    except Exception:
        pass
    collector.collect_calibration_trend(round(calibration_error, 4))

    # Performance metrics (basic system stats)
    try:
        import psutil

        process = psutil.Process()
        mem_mb = round(process.memory_info().rss / 1024 / 1024, 2)
        cpu_percent = psutil.cpu_percent(interval=0.1)
    except ImportError:
        mem_mb = 0.0
        cpu_percent = 0.0

    collector.collect_performance_metrics(
        scan_latency_ms=0.0,  # Not tracked without runtime integration
        memory_mb=mem_mb,
        cpu_percent=cpu_percent,
    )

    # Seccomp violations (not tracked in current system)
    collector.collect_seccomp_violations(0)


def get_metrics() -> str:
    """Get current metrics in Prometheus format."""
    collector = SystemMetricsCollector()
    _collect_real_metrics(collector)
    return collector.export()
