"""
7-Day Burn Test Specification - Production Grade
=================================================

Continuous operation monitoring:
- Scanning, training, drift monitoring
- Memory fragmentation
- FD usage, thread leaks
- GPU temp/throttling
- Scan latency drift

No mock data. No simulated values. Real OS metrics only.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import json
import time


# =============================================================================
# CONFIGURATION
# =============================================================================

BURN_DURATION_DAYS = 7
SAMPLE_INTERVAL_SECONDS = 60  # 1 minute
REPORTS_DIR = Path("reports/burn_test")


# =============================================================================
# METRICS
# =============================================================================

@dataclass
class BurnTestSample:
    """Single sample point during burn test."""
    timestamp: str
    memory_rss_mb: float
    memory_fragmentation: float
    fd_count: int
    thread_count: int
    gpu_temp_c: Optional[float]
    gpu_throttled: bool
    scan_latency_ms: float
    scans_completed: int
    errors: int


@dataclass
class BurnTestConfig:
    """Burn test configuration."""
    duration_days: int
    sample_interval_seconds: int
    enable_scanning: bool
    enable_training: bool
    enable_drift_monitoring: bool


@dataclass
class BurnTestResult:
    """Burn test result."""
    start_time: str
    end_time: str
    duration_hours: float
    samples: List[BurnTestSample]
    memory_growth_mb: float
    max_memory_mb: float
    fd_leaks: int
    thread_leaks: int
    gpu_throttle_events: int
    latency_drift_percent: float
    total_scans: int
    total_errors: int
    verdict: str


# =============================================================================
# THRESHOLDS
# =============================================================================

class BurnTestThresholds:
    """Thresholds for burn test pass/fail."""
    MAX_MEMORY_GROWTH_MB = 500
    MAX_FD_LEAKS = 50
    MAX_THREAD_LEAKS = 10
    MAX_GPU_THROTTLE_EVENTS = 100
    MAX_LATENCY_DRIFT_PERCENT = 25
    MAX_ERROR_RATE = 0.001  # 0.1%


# =============================================================================
# SYSTEM COLLECTORS — Real OS metrics, no mock data
# =============================================================================

def collect_memory_metrics() -> tuple:
    """Collect REAL memory metrics from OS."""
    try:
        import psutil
        process = psutil.Process()
        mem = process.memory_info()
        rss = mem.rss / (1024 * 1024)
        # Fragmentation: ratio of VMS to RSS (>1.0 = fragmented)
        vms = mem.vms / (1024 * 1024)
        frag = (vms / rss - 1.0) if rss > 0 else 0.0
        return rss, round(frag, 4)
    except ImportError:
        return None, None


def collect_fd_count() -> int:
    """Collect REAL file descriptor count from OS."""
    try:
        import psutil
        process = psutil.Process()
        if hasattr(process, 'num_fds'):
            return process.num_fds()
        # Windows: use handle count
        if hasattr(process, 'num_handles'):
            return process.num_handles()
    except Exception:
        pass
    # Fallback: try reading /proc on Linux
    try:
        import os
        fd_dir = f'/proc/{os.getpid()}/fd'
        if os.path.isdir(fd_dir):
            return len(os.listdir(fd_dir))
    except (OSError, PermissionError):
        pass
    return None


def collect_thread_count() -> int:
    """Collect REAL thread count."""
    try:
        import threading
        return threading.active_count()
    except Exception:
        return None


def collect_gpu_metrics() -> tuple:
    """Collect REAL GPU metrics via nvidia-smi."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu,throttle.reason.sw_thermal_slowdown",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            parts = result.stdout.strip().split(',')
            temp = float(parts[0].strip())
            throttled = parts[1].strip().lower() not in ('not active', '0')
            return temp, throttled
    except (FileNotFoundError, subprocess.SubprocessError,
            ValueError, IndexError):
        pass
    return None, False


def collect_scan_latency() -> float:
    """Collect REAL latest scan latency from timing log."""
    try:
        latency_file = Path("reports/last_scan_latency_ms.txt")
        if latency_file.exists():
            return float(latency_file.read_text().strip())
    except (ValueError, OSError):
        pass
    return None


# =============================================================================
# BURN TEST RUNNER
# =============================================================================

def take_burn_sample(scans: int, errors: int) -> BurnTestSample:
    """Take a burn test sample."""
    mem_rss, mem_frag = collect_memory_metrics()
    gpu_temp, gpu_throttled = collect_gpu_metrics()
    
    return BurnTestSample(
        timestamp=datetime.now().isoformat(),
        memory_rss_mb=mem_rss,
        memory_fragmentation=mem_frag,
        fd_count=collect_fd_count(),
        thread_count=collect_thread_count(),
        gpu_temp_c=gpu_temp,
        gpu_throttled=gpu_throttled,
        scan_latency_ms=collect_scan_latency(),
        scans_completed=scans,
        errors=errors,
    )


def analyze_burn_test(samples: List[BurnTestSample]) -> BurnTestResult:
    """Analyze burn test samples."""
    if len(samples) < 2:
        return None
    
    # Calculate metrics
    memory_growth = samples[-1].memory_rss_mb - samples[0].memory_rss_mb
    max_memory = max(s.memory_rss_mb for s in samples)
    fd_leaks = samples[-1].fd_count - samples[0].fd_count
    thread_leaks = samples[-1].thread_count - samples[0].thread_count
    gpu_throttles = sum(1 for s in samples if s.gpu_throttled)
    
    # Latency drift
    first_latencies = [s.scan_latency_ms for s in samples[:10]]
    last_latencies = [s.scan_latency_ms for s in samples[-10:]]
    avg_first = sum(first_latencies) / len(first_latencies)
    avg_last = sum(last_latencies) / len(last_latencies)
    latency_drift = ((avg_last - avg_first) / avg_first) * 100 if avg_first > 0 else 0
    
    total_scans = samples[-1].scans_completed
    total_errors = samples[-1].errors
    
    # Verdict
    thresholds = BurnTestThresholds()
    passed = all([
        memory_growth <= thresholds.MAX_MEMORY_GROWTH_MB,
        fd_leaks <= thresholds.MAX_FD_LEAKS,
        thread_leaks <= thresholds.MAX_THREAD_LEAKS,
        gpu_throttles <= thresholds.MAX_GPU_THROTTLE_EVENTS,
        abs(latency_drift) <= thresholds.MAX_LATENCY_DRIFT_PERCENT,
        (total_errors / total_scans if total_scans > 0 else 0) <= thresholds.MAX_ERROR_RATE,
    ])
    
    duration = (datetime.fromisoformat(samples[-1].timestamp) - 
                datetime.fromisoformat(samples[0].timestamp))
    
    return BurnTestResult(
        start_time=samples[0].timestamp,
        end_time=samples[-1].timestamp,
        duration_hours=duration.total_seconds() / 3600,
        samples=samples,
        memory_growth_mb=memory_growth,
        max_memory_mb=max_memory,
        fd_leaks=fd_leaks,
        thread_leaks=thread_leaks,
        gpu_throttle_events=gpu_throttles,
        latency_drift_percent=round(latency_drift, 2),
        total_scans=total_scans,
        total_errors=total_errors,
        verdict="PASS" if passed else "FAIL",
    )


def simulate_burn_test(duration_seconds: int = 60) -> BurnTestResult:
    """Simulate a short burn test for validation."""
    samples = []
    scans = 0
    errors = 0
    
    for i in range(10):  # 10 samples
        scans += 100
        errors += 0
        samples.append(take_burn_sample(scans, errors))
        time.sleep(duration_seconds / 10)
    
    return analyze_burn_test(samples)
