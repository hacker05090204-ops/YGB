"""
Lifecycle Monitoring Tests - Phase 50
======================================

Tests for continuous proof infrastructure.
"""

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase50.monitoring.model_drift_monitor import (
    ModelDriftMonitor,
    DriftType,
    ACCURACY_THRESHOLD,
)

from impl_v1.phase50.monitoring.dependency_monitor import (
    take_environment_snapshot,
    compare_environments,
    EnvironmentSnapshot,
)

from impl_v1.phase50.monitoring.incident_simulation import (
    simulate_key_compromise,
    simulate_build_server_compromise,
    simulate_baseline_tamper,
    run_all_incident_simulations,
)

from impl_v1.phase50.monitoring.performance_drift import (
    calculate_deviation,
    PerformanceMetrics,
    check_performance_drift,
)


class TestModelDriftMonitor(unittest.TestCase):
    """Test model drift monitoring."""
    
    def test_record_scan(self):
        """Record scan results."""
        monitor = ModelDriftMonitor(window_size=10)
        monitor.record_scan(True, True, 0.9)
        self.assertEqual(len(monitor.results), 1)
    
    def test_rolling_accuracy(self):
        """Calculate rolling accuracy."""
        monitor = ModelDriftMonitor(window_size=10)
        for _ in range(5):
            monitor.record_scan(True, True, 0.9)
        for _ in range(5):
            monitor.record_scan(True, False, 0.9)
        
        accuracy = monitor.get_rolling_accuracy()
        self.assertAlmostEqual(accuracy, 0.5, places=1)
    
    def test_empty_monitor_accuracy(self):
        """Empty monitor returns 1.0 accuracy."""
        monitor = ModelDriftMonitor()
        self.assertEqual(monitor.get_rolling_accuracy(), 1.0)


class TestDependencyMonitor(unittest.TestCase):
    """Test dependency monitoring."""
    
    def test_take_snapshot(self):
        """Take environment snapshot."""
        snapshot = take_environment_snapshot()
        self.assertIsNotNone(snapshot.kernel_version)
        self.assertIsNotNone(snapshot.python_version)
    
    def test_compare_identical(self):
        """Identical environments match."""
        snapshot = take_environment_snapshot()
        match, changes = compare_environments(snapshot, snapshot)
        self.assertTrue(match)
        self.assertEqual(len(changes), 0)
    
    def test_compare_different_kernel(self):
        """Different kernel detected."""
        s1 = EnvironmentSnapshot(
            kernel_version="5.0",
            cuda_version=None,
            compiler_version="gcc",
            openssl_version="3.0",
            glibc_version=None,
            python_version="3.11",
            timestamp="now",
        )
        s2 = EnvironmentSnapshot(
            kernel_version="6.0",
            cuda_version=None,
            compiler_version="gcc",
            openssl_version="3.0",
            glibc_version=None,
            python_version="3.11",
            timestamp="now",
        )
        match, changes = compare_environments(s1, s2)
        self.assertFalse(match)


class TestIncidentSimulation(unittest.TestCase):
    """Test incident simulations."""
    
    def test_key_compromise_simulation(self):
        """Key compromise simulation runs."""
        result = simulate_key_compromise()
        self.assertTrue(result.failed_closed)
    
    def test_build_server_compromise(self):
        """Build server compromise detected."""
        result = simulate_build_server_compromise()
        self.assertTrue(result.passed)
    
    def test_baseline_tamper(self):
        """Baseline tamper detected."""
        result = simulate_baseline_tamper()
        self.assertTrue(result.passed)
    
    def test_all_simulations_run(self):
        """All simulations complete."""
        results = run_all_incident_simulations()
        self.assertGreater(len(results), 0)


class TestPerformanceDrift(unittest.TestCase):
    """Test performance drift detection."""
    
    def test_calculate_deviation_zero(self):
        """Zero baseline returns zero deviation."""
        deviation = calculate_deviation(0, 100)
        self.assertEqual(deviation, 0.0)
    
    def test_calculate_deviation_50_percent(self):
        """50% deviation calculated correctly."""
        deviation = calculate_deviation(100, 150)
        self.assertAlmostEqual(deviation, 0.5, places=2)
    
    def test_check_drift_no_baseline(self):
        """No drift without baseline."""
        with patch('impl_v1.phase50.monitoring.performance_drift.load_performance_baseline', return_value=None):
            metrics = PerformanceMetrics(100, 256, 25, 60)
            drifts = check_performance_drift(metrics)
            self.assertEqual(len(drifts), 0)


if __name__ == "__main__":
    unittest.main()
