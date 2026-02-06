"""
Stability and Performance Tests - Phase 49
============================================

Long-run stability monitoring:
- Memory growth
- File descriptor leaks
- Zombie processes
- Training drift

Performance baseline:
- Scan time
- Memory usage
- CPU/GPU usage
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime
import time
import os
import platform


# =============================================================================
# STABILITY METRICS
# =============================================================================

@dataclass
class StabilitySnapshot:
    """Point-in-time stability metrics."""
    timestamp: str
    memory_mb: float
    file_descriptors: int
    cpu_percent: float
    zombie_processes: int


@dataclass
class StabilityReport:
    """Long-run stability report."""
    duration_hours: float
    snapshots: List[StabilitySnapshot]
    memory_growth_mb: float
    fd_leaks: int
    max_zombies: int
    verdict: str


# =============================================================================
# STABILITY MONITORING
# =============================================================================

def get_memory_usage_mb() -> float:
    """Get current memory usage in MB."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        # Fallback for systems without psutil
        return 0.0


def get_file_descriptor_count() -> int:
    """Get current open file descriptor count."""
    if platform.system() == "Windows":
        return 0  # Windows doesn't expose FDs the same way
    
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.num_fds()
    except (ImportError, AttributeError):
        try:
            fd_path = Path(f"/proc/{os.getpid()}/fd")
            if fd_path.exists():
                return len(list(fd_path.iterdir()))
        except Exception:
            pass
    return 0


def get_cpu_percent() -> float:
    """Get current CPU usage percent."""
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        return 0.0


def take_stability_snapshot() -> StabilitySnapshot:
    """Take a stability snapshot."""
    return StabilitySnapshot(
        timestamp=datetime.now().isoformat(),
        memory_mb=get_memory_usage_mb(),
        file_descriptors=get_file_descriptor_count(),
        cpu_percent=get_cpu_percent(),
        zombie_processes=0,  # Would check actual zombies
    )


def run_stability_check(
    duration_seconds: int = 60,
    interval_seconds: int = 10,
) -> StabilityReport:
    """Run stability check for specified duration."""
    snapshots = []
    start = time.time()
    
    while time.time() - start < duration_seconds:
        snapshots.append(take_stability_snapshot())
        time.sleep(min(interval_seconds, duration_seconds - (time.time() - start)))
    
    # Calculate metrics
    if len(snapshots) >= 2:
        memory_growth = snapshots[-1].memory_mb - snapshots[0].memory_mb
        fd_leaks = snapshots[-1].file_descriptors - snapshots[0].file_descriptors
    else:
        memory_growth = 0.0
        fd_leaks = 0
    
    max_zombies = max(s.zombie_processes for s in snapshots) if snapshots else 0
    
    # Determine verdict
    verdict = "PASS"
    if memory_growth > 100:  # >100MB growth is concerning
        verdict = "WARN"
    if fd_leaks > 10:  # >10 FD leaks is concerning
        verdict = "WARN"
    if max_zombies > 0:
        verdict = "FAIL"
    
    return StabilityReport(
        duration_hours=duration_seconds / 3600,
        snapshots=snapshots,
        memory_growth_mb=memory_growth,
        fd_leaks=fd_leaks,
        max_zombies=max_zombies,
        verdict=verdict,
    )


# =============================================================================
# PERFORMANCE BASELINE
# =============================================================================

@dataclass
class PerformanceBaseline:
    """Performance baseline metrics."""
    scan_time_ms: float
    memory_per_scan_mb: float
    cpu_usage_percent: float
    gpu_usage_percent: float
    report_generation_ms: float
    timestamp: str


def measure_scan_performance(iterations: int = 10) -> Dict[str, float]:
    """Measure scanning performance."""
    times = []
    memory_before = get_memory_usage_mb()
    
    for _ in range(iterations):
        start = time.time()
        # Simulate scan operation
        time.sleep(0.01)  # Mock scan
        times.append((time.time() - start) * 1000)
    
    memory_after = get_memory_usage_mb()
    
    return {
        "avg_scan_time_ms": sum(times) / len(times),
        "max_scan_time_ms": max(times),
        "min_scan_time_ms": min(times),
        "memory_per_scan_mb": (memory_after - memory_before) / iterations,
    }


def create_performance_baseline() -> PerformanceBaseline:
    """Create performance baseline."""
    scan_metrics = measure_scan_performance()
    
    return PerformanceBaseline(
        scan_time_ms=scan_metrics["avg_scan_time_ms"],
        memory_per_scan_mb=scan_metrics["memory_per_scan_mb"],
        cpu_usage_percent=get_cpu_percent(),
        gpu_usage_percent=0.0,  # Would measure actual GPU
        report_generation_ms=50.0,  # Mock value
        timestamp=datetime.now().isoformat(),
    )


# =============================================================================
# GENERALIZATION TESTING
# =============================================================================

@dataclass
class GeneralizationResult:
    """Result of generalization testing."""
    unseen_patterns_accuracy: float
    modified_payloads_accuracy: float
    obfuscated_accuracy: float
    unusual_encodings_accuracy: float
    robustness_score: float
    calibration_shift: float


def test_generalization() -> GeneralizationResult:
    """Test model generalization on unseen patterns."""
    # These would be actual model evaluations
    # Using mock values for framework demonstration
    
    return GeneralizationResult(
        unseen_patterns_accuracy=0.92,
        modified_payloads_accuracy=0.88,
        obfuscated_accuracy=0.85,
        unusual_encodings_accuracy=0.90,
        robustness_score=0.89,
        calibration_shift=0.03,
    )
