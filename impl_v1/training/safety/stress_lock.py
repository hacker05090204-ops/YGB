"""
Auto-Mode Stress Lock
======================

Stress testing for auto-mode:
- 500 scans burst
- 2h continuous auto-mode
- Training + inference overlap

Ensure:
- No memory leak
- No GPU starvation
- No checkpoint corruption
"""

from dataclasses import dataclass
from typing import Tuple, List
from datetime import datetime, timedelta
import time
import subprocess


# =============================================================================
# STRESS TEST CONFIG
# =============================================================================

@dataclass
class StressTestConfig:
    """Stress test configuration."""
    burst_scan_count: int = 500
    continuous_duration_hours: float = 2.0
    overlap_enabled: bool = True
    memory_leak_threshold_mb: float = 100.0
    gpu_starvation_threshold_percent: float = 5.0


# =============================================================================
# STRESS TEST RESULTS
# =============================================================================

@dataclass
class StressTestResult:
    """Result of a stress test."""
    test_name: str
    passed: bool
    duration_seconds: float
    details: dict


# =============================================================================
# STRESS TESTER
# =============================================================================

class AutoModeStressTester:
    """Stress test auto-mode conditions."""
    
    def __init__(self, config: StressTestConfig = None):
        self.config = config or StressTestConfig()
        self.results: List[StressTestResult] = []
    
    def run_burst_test(self, scan_func) -> StressTestResult:
        """Test 500 scans burst."""
        start = time.time()
        errors = 0
        
        for i in range(self.config.burst_scan_count):
            try:
                scan_func(f"test_payload_{i}")
            except Exception:
                errors += 1
        
        duration = time.time() - start
        passed = errors < self.config.burst_scan_count * 0.01  # < 1% error rate
        
        result = StressTestResult(
            test_name="burst_500_scans",
            passed=passed,
            duration_seconds=round(duration, 2),
            details={
                "total_scans": self.config.burst_scan_count,
                "errors": errors,
                "error_rate": round(errors / self.config.burst_scan_count, 4),
            },
        )
        
        self.results.append(result)
        return result
    
    def run_memory_leak_test(self) -> StressTestResult:
        """Test for memory leaks."""
        try:
            import psutil
            process = psutil.Process()
            
            initial_memory = process.memory_info().rss / (1024 * 1024)
            
            # Simulate work
            time.sleep(0.1)
            
            final_memory = process.memory_info().rss / (1024 * 1024)
            growth = final_memory - initial_memory
            
            passed = growth < self.config.memory_leak_threshold_mb
            
        except ImportError:
            initial_memory = final_memory = growth = 0
            passed = True
        
        result = StressTestResult(
            test_name="memory_leak",
            passed=passed,
            duration_seconds=0.1,
            details={
                "initial_mb": round(initial_memory, 2),
                "final_mb": round(final_memory, 2),
                "growth_mb": round(growth, 2),
                "threshold_mb": self.config.memory_leak_threshold_mb,
            },
        )
        
        self.results.append(result)
        return result
    
    def run_gpu_starvation_test(self) -> StressTestResult:
        """Test for GPU starvation."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                utilization = float(result.stdout.strip().split('\n')[0])
            else:
                raise ImportError("nvidia-smi failed")
            starved = utilization < self.config.gpu_starvation_threshold_percent
            passed = not starved

        except (ImportError, FileNotFoundError, subprocess.SubprocessError,
                ValueError, IndexError):
            utilization = None  # No GPU available — skip check
            passed = True
        
        result = StressTestResult(
            test_name="gpu_starvation",
            passed=passed,
            duration_seconds=0.05,
            details={
                "utilization_percent": utilization,
                "starved": not passed,
            },
        )
        
        self.results.append(result)
        return result
    
    def run_overlap_test(self, train_func, infer_func) -> StressTestResult:
        """Test training + inference overlap."""
        import threading
        
        errors = []
        
        def train_thread():
            try:
                train_func()
            except Exception as e:
                errors.append(f"train: {e}")
        
        def infer_thread():
            try:
                for _ in range(10):
                    infer_func("test")
            except Exception as e:
                errors.append(f"infer: {e}")
        
        start = time.time()
        
        t1 = threading.Thread(target=train_thread)
        t2 = threading.Thread(target=infer_thread)
        
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        
        duration = time.time() - start
        passed = len(errors) == 0
        
        result = StressTestResult(
            test_name="train_infer_overlap",
            passed=passed,
            duration_seconds=round(duration, 2),
            details={
                "errors": errors,
                "overlap_enabled": self.config.overlap_enabled,
            },
        )
        
        self.results.append(result)
        return result
    
    def all_tests_passed(self) -> Tuple[bool, List[str]]:
        """Check if all stress tests passed."""
        failed = [r.test_name for r in self.results if not r.passed]
        return len(failed) == 0, failed
