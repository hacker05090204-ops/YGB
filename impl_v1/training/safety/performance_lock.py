"""
P95 / P99 Performance Lock
===========================

Track latency percentiles:
- P50, P95, P99 latency
- Concurrency (10 parallel scans)

Lock thresholds:
- P95 < 200ms
- P99 < 300ms
"""

from dataclasses import dataclass
from typing import List, Tuple
from datetime import datetime
import statistics
import time


# =============================================================================
# THRESHOLDS
# =============================================================================

@dataclass
class PerformanceThresholds:
    """Performance latency thresholds."""
    p95_max_ms: float = 200.0
    p99_max_ms: float = 300.0
    max_concurrency: int = 10


# =============================================================================
# LATENCY METRICS
# =============================================================================

@dataclass
class LatencyMetrics:
    """Latency metrics."""
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    max_ms: float
    sample_count: int


# =============================================================================
# PERFORMANCE TRACKER
# =============================================================================

class PerformanceTracker:
    """Track P50/P95/P99 latency."""
    
    def __init__(self, thresholds: PerformanceThresholds = None):
        self.thresholds = thresholds or PerformanceThresholds()
        self.latencies: List[float] = []
        self.alerts: List[dict] = []
    
    def record_latency(self, latency_ms: float) -> None:
        """Record a latency measurement."""
        self.latencies.append(latency_ms)
        
        # Keep only last 10000 samples
        if len(self.latencies) > 10000:
            self.latencies = self.latencies[-10000:]
    
    def compute_metrics(self) -> LatencyMetrics:
        """Compute latency percentiles."""
        if len(self.latencies) < 2:
            return LatencyMetrics(0, 0, 0, 0, 0, len(self.latencies))
        
        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)
        
        p50_idx = int(n * 0.50)
        p95_idx = int(n * 0.95)
        p99_idx = int(n * 0.99)
        
        return LatencyMetrics(
            p50_ms=round(sorted_latencies[p50_idx], 2),
            p95_ms=round(sorted_latencies[p95_idx], 2),
            p99_ms=round(sorted_latencies[p99_idx], 2),
            mean_ms=round(statistics.mean(self.latencies), 2),
            max_ms=round(max(self.latencies), 2),
            sample_count=n,
        )
    
    def check_thresholds(self) -> Tuple[bool, dict]:
        """
        Check if latency thresholds are met.
        
        Returns:
            Tuple of (thresholds_met, details)
        """
        metrics = self.compute_metrics()
        
        p95_ok = metrics.p95_ms <= self.thresholds.p95_max_ms
        p99_ok = metrics.p99_ms <= self.thresholds.p99_max_ms
        
        thresholds_met = p95_ok and p99_ok
        
        details = {
            "p50_ms": metrics.p50_ms,
            "p95_ms": metrics.p95_ms,
            "p99_ms": metrics.p99_ms,
            "p95_ok": p95_ok,
            "p99_ok": p99_ok,
            "thresholds_met": thresholds_met,
        }
        
        if not thresholds_met:
            self._trigger_alert(details)
        
        return thresholds_met, details
    
    def _trigger_alert(self, details: dict) -> None:
        """Trigger performance drift alert."""
        alert = {
            "timestamp": datetime.now().isoformat(),
            "type": "performance_drift",
            "details": details,
        }
        self.alerts.append(alert)


# =============================================================================
# CONCURRENCY TESTER
# =============================================================================

class ConcurrencyTester:
    """Test performance under concurrent load."""
    
    def __init__(self, max_concurrency: int = 10):
        self.max_concurrency = max_concurrency
    
    def run_concurrent_test(self, scan_func, payloads: List[str]) -> dict:
        """Run concurrent scan test."""
        import concurrent.futures
        
        latencies = []
        errors = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_concurrency) as executor:
            start = time.time()
            
            futures = []
            for payload in payloads[:self.max_concurrency]:
                futures.append(executor.submit(self._timed_scan, scan_func, payload))
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    latency = future.result()
                    latencies.append(latency)
                except Exception as e:
                    errors.append(str(e))
            
            total_time = time.time() - start
        
        return {
            "concurrency": self.max_concurrency,
            "total_time_ms": round(total_time * 1000, 2),
            "latencies": latencies,
            "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "errors": len(errors),
        }
    
    def _timed_scan(self, scan_func, payload: str) -> float:
        """Run timed scan."""
        start = time.time()
        scan_func(payload)
        return (time.time() - start) * 1000
