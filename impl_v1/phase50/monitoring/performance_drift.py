"""
Performance Drift Tracking - Phase 50
=======================================

Compare current performance to baseline:
- Scan time
- Memory usage
- GPU utilization

Flag if deviation > 20%.
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime
from pathlib import Path
import json


# =============================================================================
# CONFIGURATION
# =============================================================================

DRIFT_THRESHOLD = 0.20  # 20% deviation
BASELINE_FILE = Path(__file__).parent.parent.parent / "phase49" / "PERFORMANCE_BASELINE.json"
ALERTS_DIR = Path("reports/performance")


# =============================================================================
# PERFORMANCE METRICS
# =============================================================================

@dataclass
class PerformanceMetrics:
    """Current performance metrics."""
    scan_time_ms: float
    memory_mb: float
    cpu_percent: float
    gpu_percent: float


@dataclass
class PerformanceDrift:
    """Detected performance drift."""
    metric: str
    baseline: float
    current: float
    deviation_percent: float
    threshold_exceeded: bool


# =============================================================================
# BASELINE LOADING
# =============================================================================

def load_performance_baseline() -> Optional[dict]:
    """Load performance baseline."""
    if not BASELINE_FILE.exists():
        return None
    
    try:
        with open(BASELINE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return None


# =============================================================================
# DRIFT DETECTION
# =============================================================================

def calculate_deviation(baseline: float, current: float) -> float:
    """Calculate percentage deviation."""
    if baseline == 0:
        return 0.0
    return abs(current - baseline) / baseline


def check_performance_drift(current: PerformanceMetrics) -> list:
    """Check for performance drift against baseline."""
    baseline = load_performance_baseline()
    
    if baseline is None:
        return []
    
    drifts = []
    
    # Check scan time
    baseline_scan = baseline.get("scan_performance", {}).get("avg_scan_time_ms", 0)
    if baseline_scan > 0:
        deviation = calculate_deviation(baseline_scan, current.scan_time_ms)
        drifts.append(PerformanceDrift(
            metric="scan_time_ms",
            baseline=baseline_scan,
            current=current.scan_time_ms,
            deviation_percent=deviation * 100,
            threshold_exceeded=deviation > DRIFT_THRESHOLD,
        ))
    
    # Check memory
    baseline_mem = baseline.get("memory_usage", {}).get("baseline_mb", 0)
    if baseline_mem > 0:
        deviation = calculate_deviation(baseline_mem, current.memory_mb)
        drifts.append(PerformanceDrift(
            metric="memory_mb",
            baseline=baseline_mem,
            current=current.memory_mb,
            deviation_percent=deviation * 100,
            threshold_exceeded=deviation > DRIFT_THRESHOLD,
        ))
    
    # Check CPU
    baseline_cpu = baseline.get("cpu_usage", {}).get("avg_percent", 0)
    if baseline_cpu > 0:
        deviation = calculate_deviation(baseline_cpu, current.cpu_percent)
        drifts.append(PerformanceDrift(
            metric="cpu_percent",
            baseline=baseline_cpu,
            current=current.cpu_percent,
            deviation_percent=deviation * 100,
            threshold_exceeded=deviation > DRIFT_THRESHOLD,
        ))
    
    # Check GPU
    baseline_gpu = baseline.get("gpu_usage", {}).get("avg_percent", 0)
    if baseline_gpu > 0:
        deviation = calculate_deviation(baseline_gpu, current.gpu_percent)
        drifts.append(PerformanceDrift(
            metric="gpu_percent",
            baseline=baseline_gpu,
            current=current.gpu_percent,
            deviation_percent=deviation * 100,
            threshold_exceeded=deviation > DRIFT_THRESHOLD,
        ))
    
    return drifts


def generate_drift_alert(drifts: list) -> Optional[str]:
    """Generate drift alert if thresholds exceeded."""
    exceeded = [d for d in drifts if d.threshold_exceeded]
    
    if not exceeded:
        return None
    
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    
    alert_file = ALERTS_DIR / f"PERFORMANCE_DRIFT_ALERT_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    content = f"""# Performance Drift Alert

**Generated**: {datetime.now().isoformat()}
**Threshold**: {DRIFT_THRESHOLD * 100}%

## Drifts Detected

| Metric | Baseline | Current | Deviation |
|--------|----------|---------|-----------|
"""
    for d in exceeded:
        content += f"| {d.metric} | {d.baseline} | {d.current} | {d.deviation_percent:.1f}% |\n"
    
    content += "\n## Action Required\n\nInvestigate performance regression.\n"
    
    with open(alert_file, "w") as f:
        f.write(content)
    
    return str(alert_file)
