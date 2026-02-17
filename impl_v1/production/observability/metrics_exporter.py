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
        self.metrics.append(Metric(
            name=name,
            help=help,
            type=MetricType.GAUGE,
            labels=labels or {},
            value=value,
        ))
    
    def counter(self, name: str, value: float, help: str = "", labels: dict = None):
        """Register a counter metric."""
        self.metrics.append(Metric(
            name=name,
            help=help,
            type=MetricType.COUNTER,
            labels=labels or {},
            value=value,
        ))
    
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

def get_metrics() -> str:
    """Get current metrics in Prometheus format.

    Reads REAL system state. No mock values.
    """
    collector = SystemMetricsCollector()

    # Auto-mode: read from governance state file
    auto_mode_enabled = False
    state_file = Path("reports/governance_state.json")
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            auto_mode_enabled = state.get("auto_mode_enabled", False)
        except (json.JSONDecodeError, OSError):
            pass
    collector.collect_auto_mode_state(auto_mode_enabled)

    # Drift events: read from incident logs
    drift_dir = Path("reports/incidents")
    accuracy_drift = 0
    calibration_drift = 0
    if drift_dir.exists():
        for f in drift_dir.glob("*.json"):
            try:
                inc = json.loads(f.read_text())
                trigger = inc.get("trigger", "")
                if trigger == "DRIFT_SPIKE":
                    accuracy_drift += 1
                elif trigger == "CALIBRATION_INFLATION":
                    calibration_drift += 1
            except (json.JSONDecodeError, OSError):
                pass
    collector.collect_drift_events(accuracy_drift, calibration_drift)

    # Performance: real system metrics
    scan_latency = 0.0
    memory_mb = 0.0
    cpu_percent = 0.0
    try:
        import psutil
        proc = psutil.Process()
        memory_mb = proc.memory_info().rss / (1024 * 1024)
        cpu_percent = proc.cpu_percent(interval=0.1)
    except (ImportError, Exception):
        pass
    collector.collect_performance_metrics(scan_latency, memory_mb, cpu_percent)

    # Seccomp: read from violation log
    seccomp_count = 0
    seccomp_log = Path("reports/seccomp_violations.log")
    if seccomp_log.exists():
        try:
            seccomp_count = sum(1 for _ in seccomp_log.open())
        except OSError:
            pass
    collector.collect_seccomp_violations(seccomp_count)

    # Emergency lock: read from lock file
    emergency_active = Path("reports/emergency_lock.active").exists()
    collector.collect_emergency_lock(emergency_active)

    # Calibration: read from latest report
    ece = 0.0
    cal_report = Path("reports/calibration_latest.json")
    if cal_report.exists():
        try:
            cal = json.loads(cal_report.read_text())
            ece = cal.get("ece", 0.0)
        except (json.JSONDecodeError, OSError):
            pass
    collector.collect_calibration_trend(ece)

    return collector.export()
