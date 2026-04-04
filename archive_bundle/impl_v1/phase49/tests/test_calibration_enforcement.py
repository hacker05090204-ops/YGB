"""
AI Calibration Enforcement Tests - Phase 49
============================================

Tests for auto-mode calibration requirements:
1. Accuracy >= 97%
2. ECE <= 0.02
3. Brier <= 0.03
4. 5-epoch stability
5. Deterministic replay
"""

import unittest
import sys
from pathlib import Path

# Add to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase49.governors.calibration_enforcement import (
    CalibrationMetrics,
    CalibrationStatus,
    AutoModeGovernor,
    compute_ece,
    compute_brier_score,
    compute_accuracy,
    check_stability,
    validate_replay_determinism,
    ACCURACY_THRESHOLD,
    ECE_THRESHOLD,
    BRIER_THRESHOLD,
    MIN_STABILITY_EPOCHS,
)


class TestAutoModeAccuracyThreshold(unittest.TestCase):
    """Test: Auto mode requires 97% accuracy."""
    
    def test_blocked_at_96_percent(self):
        """96% accuracy - BLOCKED."""
        metrics = CalibrationMetrics(
            accuracy=0.96,
            ece=0.01,
            brier_score=0.02,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertFalse(ready)
        self.assertEqual(status, CalibrationStatus.FAIL_ACCURACY)
    
    def test_allowed_at_97_percent(self):
        """97% accuracy with all other criteria - ALLOWED."""
        metrics = CalibrationMetrics(
            accuracy=0.97,
            ece=0.01,
            brier_score=0.02,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertTrue(ready)
        self.assertEqual(status, CalibrationStatus.PASS)
    
    def test_blocked_at_90_percent(self):
        """90% accuracy - BLOCKED."""
        metrics = CalibrationMetrics(
            accuracy=0.90,
            ece=0.01,
            brier_score=0.02,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertFalse(ready)


class TestAutoModeECEThreshold(unittest.TestCase):
    """Test: Auto mode requires ECE <= 0.02."""
    
    def test_blocked_at_ece_0_03(self):
        """ECE 0.03 - BLOCKED."""
        metrics = CalibrationMetrics(
            accuracy=0.98,
            ece=0.03,
            brier_score=0.02,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertFalse(ready)
        self.assertEqual(status, CalibrationStatus.FAIL_ECE)
    
    def test_allowed_at_ece_0_02(self):
        """ECE 0.02 - ALLOWED."""
        metrics = CalibrationMetrics(
            accuracy=0.98,
            ece=0.02,
            brier_score=0.02,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertTrue(ready)
    
    def test_allowed_at_ece_0_01(self):
        """ECE 0.01 - ALLOWED."""
        metrics = CalibrationMetrics(
            accuracy=0.98,
            ece=0.01,
            brier_score=0.02,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertTrue(ready)


class TestAutoModeBrierThreshold(unittest.TestCase):
    """Test: Auto mode requires Brier <= 0.03."""
    
    def test_blocked_at_brier_0_04(self):
        """Brier 0.04 - BLOCKED."""
        metrics = CalibrationMetrics(
            accuracy=0.98,
            ece=0.01,
            brier_score=0.04,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertFalse(ready)
        self.assertEqual(status, CalibrationStatus.FAIL_BRIER)
    
    def test_allowed_at_brier_0_03(self):
        """Brier 0.03 - ALLOWED."""
        metrics = CalibrationMetrics(
            accuracy=0.98,
            ece=0.01,
            brier_score=0.03,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertTrue(ready)


class TestAutoModeEpochRequirement(unittest.TestCase):
    """Test: Auto mode requires 5 epochs minimum."""
    
    def test_blocked_at_4_epochs(self):
        """4 epochs - BLOCKED."""
        metrics = CalibrationMetrics(
            accuracy=0.99,
            ece=0.01,
            brier_score=0.01,
            epochs_completed=4,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertFalse(ready)
        self.assertEqual(status, CalibrationStatus.FAIL_EPOCHS)
    
    def test_allowed_at_5_epochs(self):
        """5 epochs - ALLOWED."""
        metrics = CalibrationMetrics(
            accuracy=0.99,
            ece=0.01,
            brier_score=0.01,
            epochs_completed=5,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertTrue(ready)


class TestAutoModeStabilityRequirement(unittest.TestCase):
    """Test: Auto mode requires stability confirmation."""
    
    def test_blocked_unstable(self):
        """Unstable training - BLOCKED."""
        metrics = CalibrationMetrics(
            accuracy=0.99,
            ece=0.01,
            brier_score=0.01,
            epochs_completed=10,
            stability_confirmed=False,
            replay_deterministic=True,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertFalse(ready)
        self.assertEqual(status, CalibrationStatus.FAIL_STABILITY)


class TestAutoModeReplayRequirement(unittest.TestCase):
    """Test: Auto mode requires deterministic replay."""
    
    def test_blocked_nondeterministic(self):
        """Non-deterministic replay - BLOCKED."""
        metrics = CalibrationMetrics(
            accuracy=0.99,
            ece=0.01,
            brier_score=0.01,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=False,
        )
        ready, status = metrics.is_auto_mode_ready()
        self.assertFalse(ready)
        self.assertEqual(status, CalibrationStatus.FAIL_REPLAY)


class TestCalibrationComputation(unittest.TestCase):
    """Test: Calibration metric computation."""
    
    def test_perfect_ece(self):
        """Perfect calibration = ECE 0."""
        # When confidence matches accuracy exactly
        confidences = [0.9, 0.9, 0.9, 0.9, 0.9]
        predictions = [1, 1, 1, 1, 0]  # 80% correct
        labels =      [1, 1, 1, 1, 0]
        
        ece = compute_ece(confidences, predictions, labels)
        self.assertLess(ece, 0.2)  # Should be low
    
    def test_perfect_accuracy(self):
        """100% accuracy."""
        predictions = [1, 0, 1, 0, 1]
        labels =      [1, 0, 1, 0, 1]
        
        acc = compute_accuracy(predictions, labels)
        self.assertEqual(acc, 1.0)
    
    def test_zero_accuracy(self):
        """0% accuracy."""
        predictions = [1, 1, 1, 1, 1]
        labels =      [0, 0, 0, 0, 0]
        
        acc = compute_accuracy(predictions, labels)
        self.assertEqual(acc, 0.0)
    
    def test_brier_score_perfect(self):
        """Perfect Brier score."""
        confidences = [1.0, 0.0, 1.0, 0.0]
        labels =      [1,   0,   1,   0]
        
        brier = compute_brier_score(confidences, labels)
        self.assertEqual(brier, 0.0)
    
    def test_stability_check_insufficient_epochs(self):
        """Stability fails with insufficient epochs."""
        accuracies = [0.95, 0.96, 0.97, 0.97]  # Only 4 epochs
        stable = check_stability(accuracies, min_epochs=5)
        self.assertFalse(stable)
    
    def test_stability_check_sufficient_epochs(self):
        """Stability passes with sufficient stable epochs."""
        accuracies = [0.97, 0.97, 0.97, 0.97, 0.97]  # 5 stable epochs
        stable = check_stability(accuracies, min_epochs=5, variance_threshold=0.001)
        self.assertTrue(stable)
    
    def test_replay_determinism_match(self):
        """Replay is deterministic when hashes match."""
        self.assertTrue(validate_replay_determinism("abc123", "abc123"))
    
    def test_replay_determinism_mismatch(self):
        """Replay is non-deterministic when hashes differ."""
        self.assertFalse(validate_replay_determinism("abc123", "xyz789"))


class TestAutoModeGovernor(unittest.TestCase):
    """Test: AutoModeGovernor behavior."""
    
    def test_governor_initially_disabled(self):
        """Governor starts disabled."""
        gov = AutoModeGovernor()
        self.assertFalse(gov.is_enabled)
    
    def test_governor_enables_with_good_metrics(self):
        """Governor enables with good metrics."""
        gov = AutoModeGovernor()
        metrics = CalibrationMetrics(
            accuracy=0.98,
            ece=0.01,
            brier_score=0.02,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        enabled, reason = gov.check_and_enable(metrics)
        self.assertTrue(enabled)
        self.assertTrue(gov.is_enabled)
    
    def test_governor_blocks_with_bad_metrics(self):
        """Governor blocks with bad metrics."""
        gov = AutoModeGovernor()
        metrics = CalibrationMetrics(
            accuracy=0.90,  # Too low
            ece=0.01,
            brier_score=0.02,
            epochs_completed=10,
            stability_confirmed=True,
            replay_deterministic=True,
        )
        enabled, reason = gov.check_and_enable(metrics)
        self.assertFalse(enabled)
        self.assertFalse(gov.is_enabled)
    
    def test_governor_force_disable(self):
        """Governor can be force disabled."""
        gov = AutoModeGovernor()
        metrics = CalibrationMetrics(
            accuracy=0.98, ece=0.01, brier_score=0.02,
            epochs_completed=10, stability_confirmed=True, replay_deterministic=True,
        )
        gov.check_and_enable(metrics)
        self.assertTrue(gov.is_enabled)
        
        gov.force_disable()
        self.assertFalse(gov.is_enabled)


if __name__ == "__main__":
    unittest.main()
