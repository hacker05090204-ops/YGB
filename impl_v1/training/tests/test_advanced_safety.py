"""
Advanced Safety Tests
=====================

Tests for advanced safety hardening.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.training.safety.rare_class_stability import (
    RareClassStabilityMonitor,
    RareClassThresholds,
    ClassMetrics,
)

from impl_v1.training.safety.representation_integrity import (
    RepresentationIntegrityMonitor,
    CheckpointProfile,
)

from impl_v1.training.safety.adversarial_drift import (
    AdversarialPayloadGenerator,
    AdversarialDriftTester,
)

from impl_v1.training.safety.performance_lock import (
    PerformanceTracker,
    PerformanceThresholds,
)

from impl_v1.training.safety.stress_lock import (
    AutoModeStressTester,
)

from impl_v1.training.safety.shadow_mode import (
    ShadowModeValidator,
    ShadowModeConfig,
)

from impl_v1.training.safety.final_gate import (
    FinalGateController,
)


class TestRareClassStability(unittest.TestCase):
    """Test rare class stability monitoring."""
    
    def test_record_prediction(self):
        """Record predictions correctly."""
        monitor = RareClassStabilityMonitor()
        monitor.record_prediction("sqli", True, True, 0.9)
        self.assertEqual(monitor.class_metrics["sqli"].true_positives, 1)
    
    def test_recall_calculation(self):
        """Recall calculated correctly."""
        metrics = ClassMetrics("test")
        metrics.true_positives = 9
        metrics.false_negatives = 1
        self.assertEqual(metrics.recall, 0.9)


class TestRepresentationIntegrity(unittest.TestCase):
    """Test representation integrity monitoring."""
    
    def test_mock_profile(self):
        """Mock profile is valid."""
        monitor = RepresentationIntegrityMonitor()
        profile = monitor._mock_profile("test_checkpoint")
        self.assertEqual(profile.checkpoint_id, "test_checkpoint")
    
    def test_check_integrity_no_baseline(self):
        """First check establishes baseline."""
        monitor = RepresentationIntegrityMonitor()
        profile = monitor._mock_profile("ckpt_1")
        is_valid, reason = monitor.check_integrity(profile)
        self.assertTrue(is_valid)


class TestAdversarialDrift(unittest.TestCase):
    """Test adversarial drift testing."""
    
    def test_generate_payloads(self):
        """Generate all payload types."""
        gen = AdversarialPayloadGenerator()
        payloads = gen.generate_all(per_type=10)
        self.assertEqual(len(payloads), 40)  # 4 types × 10
    
    def test_robustness_test(self):
        """Robustness test runs."""
        tester = AdversarialDriftTester()
        
        def mock_scanner(payload):
            return True, 0.9
        
        robustness, results = tester.run_robustness_test(mock_scanner)
        self.assertGreater(robustness, 0)


class TestPerformanceLock(unittest.TestCase):
    """Test P95/P99 performance tracking."""
    
    def test_record_latency(self):
        """Record latencies."""
        tracker = PerformanceTracker()
        for i in range(100):
            tracker.record_latency(100 + i)
        self.assertEqual(len(tracker.latencies), 100)
    
    def test_compute_percentiles(self):
        """Percentiles computed."""
        tracker = PerformanceTracker()
        for i in range(100):
            tracker.record_latency(i * 2)
        metrics = tracker.compute_metrics()
        self.assertGreater(metrics.p95_ms, metrics.p50_ms)


class TestStressLock(unittest.TestCase):
    """Test auto-mode stress testing."""
    
    def test_memory_leak_test(self):
        """Memory leak test runs."""
        tester = AutoModeStressTester()
        result = tester.run_memory_leak_test()
        self.assertIsNotNone(result.passed)


class TestShadowMode(unittest.TestCase):
    """Test shadow mode validation."""
    
    def test_record_comparison(self):
        """Record AI-human comparisons."""
        validator = ShadowModeValidator()
        validator.record_comparison("scan_1", True, True, 0.9)
        self.assertEqual(len(validator.comparisons), 1)
    
    def test_agreement_calculation(self):
        """Agreement calculated correctly."""
        validator = ShadowModeValidator()
        for i in range(100):
            validator.record_comparison(f"scan_{i}", True, True, 0.9)
        
        agreement, _ = validator.compute_agreement()
        self.assertEqual(agreement, 1.0)


class TestFinalGate(unittest.TestCase):
    """Test final gate controller."""
    
    def test_set_gate(self):
        """Set gate status."""
        controller = FinalGateController()
        controller.set_gate("calibration", True, {"accuracy": 0.98})
        self.assertTrue(controller.gates["calibration"].passed)
    
    def test_all_gates_required(self):
        """All gates must pass."""
        controller = FinalGateController()
        controller.gates = {}  # Reset
        is_safe, _ = controller.get_auto_mode_safe()
        self.assertFalse(is_safe)


if __name__ == "__main__":
    unittest.main()
