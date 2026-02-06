"""
Operational Validation Tests - Phase 49
========================================

Tests for operational validation framework.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase49.validation.effectiveness_validation import (
    generate_vulnerable_cases,
    generate_clean_cases,
    calculate_metrics,
    EffectivenessMetrics,
    mock_scan,
)

from impl_v1.phase49.validation.chaos_tests import (
    test_corrupted_har,
    test_malformed_dom,
    test_large_payload,
    test_interrupted_training,
    run_all_chaos_tests,
    ChaosScenario,
)

from impl_v1.phase49.validation.stability_tests import (
    take_stability_snapshot,
    create_performance_baseline,
    test_generalization,
)


class TestEffectivenessValidation(unittest.TestCase):
    """Test effectiveness validation."""
    
    def test_generate_vulnerable_cases(self):
        """Generate 100 vulnerable cases."""
        cases = generate_vulnerable_cases(100)
        self.assertEqual(len(cases), 100)
        self.assertTrue(all(c.is_vulnerable for c in cases))
    
    def test_generate_clean_cases(self):
        """Generate 100 clean cases."""
        cases = generate_clean_cases(100)
        self.assertEqual(len(cases), 100)
        self.assertTrue(all(not c.is_vulnerable for c in cases))
    
    def test_mock_scan_returns_result(self):
        """Mock scan returns result."""
        cases = generate_vulnerable_cases(1)
        result = mock_scan(cases[0])
        self.assertIsNotNone(result)
        self.assertEqual(result.test_id, cases[0].id)
    
    def test_metrics_calculation(self):
        """Metrics calculated correctly."""
        metrics = EffectivenessMetrics(
            true_positives=90,
            true_negatives=95,
            false_positives=5,
            false_negatives=10,
        )
        self.assertAlmostEqual(metrics.tpr, 0.9, places=2)
        self.assertAlmostEqual(metrics.fpr, 0.05, places=2)


class TestChaosEngineering(unittest.TestCase):
    """Test chaos engineering framework."""
    
    def test_corrupted_har(self):
        """Corrupted HAR handled gracefully."""
        result = test_corrupted_har()
        self.assertTrue(result.passed)
        self.assertFalse(result.crashed)
    
    def test_malformed_dom(self):
        """Malformed DOM handled gracefully."""
        result = test_malformed_dom()
        self.assertTrue(result.passed)
        self.assertFalse(result.crashed)
    
    def test_large_payload(self):
        """Large payload rejected."""
        result = test_large_payload()
        self.assertTrue(result.passed)
        self.assertTrue(result.failed_closed)
    
    def test_interrupted_training(self):
        """Interrupted training saves checkpoint."""
        result = test_interrupted_training()
        self.assertTrue(result.passed)
    
    def test_all_chaos_tests_run(self):
        """All chaos tests run without crashing."""
        results = run_all_chaos_tests()
        self.assertGreater(len(results), 0)
        self.assertTrue(all(not r.crashed for r in results))


class TestStabilityMonitoring(unittest.TestCase):
    """Test stability monitoring."""
    
    def test_take_snapshot(self):
        """Take stability snapshot."""
        snapshot = take_stability_snapshot()
        self.assertIsNotNone(snapshot.timestamp)
        self.assertGreaterEqual(snapshot.memory_mb, 0)
    
    def test_create_performance_baseline(self):
        """Create performance baseline."""
        baseline = create_performance_baseline()
        self.assertIsNotNone(baseline.timestamp)
        self.assertGreater(baseline.scan_time_ms, 0)


class TestGeneralization(unittest.TestCase):
    """Test generalization testing."""
    
    def test_generalization_result(self):
        """Generalization test returns result."""
        result = test_generalization()
        self.assertGreater(result.robustness_score, 0.5)
        self.assertLess(result.calibration_shift, 0.1)


if __name__ == "__main__":
    unittest.main()
