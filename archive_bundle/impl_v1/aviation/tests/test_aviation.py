"""
Aviation Safety Tests
======================

Tests for aviation-grade safety systems.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.aviation.decision_trace import (
    DecisionTraceEngine,
    DecisionTrace,
)

from impl_v1.aviation.decision_validator import (
    DecisionValidator,
    ValidationThresholds,
    DualModelConsensus,
)

from impl_v1.aviation.fmea_generator import (
    FMEAGenerator,
)

from impl_v1.aviation.safety_case import (
    SafetyCaseGenerator,
)

from impl_v1.aviation.no_silent_failure import (
    NoSilentFailureController,
    FailureType,
    AviationSafetyController,
)


class TestDecisionTrace(unittest.TestCase):
    """Test decision trace engine."""
    
    def test_create_trace(self):
        """Create and store trace."""
        engine = DecisionTraceEngine()
        trace = engine.create_trace(
            scan_id="SCAN_TEST_001",
            input_data="test input",
            feature_vector={"f1": 1.0},
            model_version="1.0.0",
            checkpoint_hash="abc123",
            calibration={"ece": 0.02},
            confidence=0.95,
            boundary_distance=0.3,
            entropy=0.15,
            decision="VULNERABLE",
        )
        self.assertIsNotNone(trace.trace_hash)
    
    def test_hash_chain(self):
        """Verify hash chain."""
        engine = DecisionTraceEngine()
        # Reset to ensure clean state for testing
        engine.reset_chain()
        # Create a fresh trace
        engine.create_trace(
            scan_id="TEST_CHAIN_001",
            input_data="test",
            feature_vector={"x": 1},
            model_version="1.0",
            checkpoint_hash="hash",
            calibration={"ece": 0.01},
            confidence=0.9,
            boundary_distance=0.2,
            entropy=0.1,
            decision="CLEAN",
        )
        valid, _ = engine.verify_chain()
        self.assertTrue(valid)
        # Clean up
        engine.reset_chain()


class TestDecisionValidator(unittest.TestCase):
    """Test decision validator."""
    
    def test_valid_decision(self):
        """Valid decision passes."""
        validator = DecisionValidator()
        valid, response, reason = validator.validate(
            confidence=0.9,
            entropy=0.2,
            calibration_variance=0.01,
            representation_deviation=0.05,
            rare_class_uncertainty=0.1,
        )
        self.assertTrue(valid)
    
    def test_low_confidence_rejected(self):
        """Low confidence rejected."""
        validator = DecisionValidator()
        valid, response, reason = validator.validate(
            confidence=0.5,
            entropy=0.2,
            calibration_variance=0.01,
            representation_deviation=0.05,
            rare_class_uncertainty=0.1,
        )
        self.assertFalse(valid)
        self.assertIn("HUMAN REVIEW", response)
    
    def test_abstention_preferred(self):
        """System prefers abstention over error."""
        validator = DecisionValidator()
        # High entropy
        valid, _, _ = validator.validate(0.9, 0.8, 0.01, 0.05, 0.1)
        self.assertFalse(valid)


class TestDualConsensus(unittest.TestCase):
    """Test dual model consensus."""
    
    def test_consensus_reached(self):
        """Consensus when models agree."""
        consensus = DualModelConsensus()
        result = consensus.check_consensus(
            "VULNERABLE", 0.95,
            "VULNERABLE", 0.94,
        )
        self.assertTrue(result.consensus_reached)
    
    def test_consensus_failed_decision(self):
        """Consensus fails on disagreement."""
        consensus = DualModelConsensus()
        result = consensus.check_consensus(
            "VULNERABLE", 0.95,
            "CLEAN", 0.90,
        )
        self.assertFalse(result.consensus_reached)


class TestFMEA(unittest.TestCase):
    """Test FMEA generation."""
    
    def test_generate_fmea(self):
        """Generate FMEA.json."""
        generator = FMEAGenerator()
        path = generator.generate_fmea()
        self.assertTrue(path.exists())
    
    def test_critical_modes(self):
        """Get critical failure modes."""
        generator = FMEAGenerator()
        critical = generator.get_critical_modes()
        self.assertGreater(len(critical), 0)


class TestNoSilentFailure(unittest.TestCase):
    """Test no-silent-failure guarantee."""
    
    def test_drift_disables_auto_mode(self):
        """Drift detection disables auto-mode."""
        controller = NoSilentFailureController()
        controller.on_drift_detected("accuracy", 0.10)
        safe, _ = controller.is_auto_mode_safe()
        self.assertFalse(safe)
    
    def test_failure_logged(self):
        """Failures are logged."""
        controller = NoSilentFailureController()
        controller.on_calibration_break(0.10, 0.02)
        self.assertEqual(controller.get_failure_count(), 1)


if __name__ == "__main__":
    unittest.main()
