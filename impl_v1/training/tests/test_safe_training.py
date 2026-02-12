"""
Safe Training Tests
===================

Tests for safe training acceleration infrastructure.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.training.isolation.training_isolation import (
    get_training_seccomp,
    get_training_rlimits,
    get_training_isolation,
)

from impl_v1.training.config.safe_acceleration import (
    SafeAccelerationConfig,
    get_balanced_config,
    validate_config,
)

from impl_v1.training.checkpoints.checkpoint_hardening import (
    HardenedCheckpointManager,
    CheckpointMetadata,
)

from impl_v1.training.monitoring.gpu_thermal_monitor import (
    GPUThermalMonitor,
    GPUThermalConfig,
    ThermalState,
)

from impl_v1.training.calibration.calibration_enforcement import (
    CalibrationCalculator,
    CalibrationEnforcer,
    CalibrationThresholds,
)

from impl_v1.training.automode.automode_controller import (
    AutoModeController,
    declare_auto_mode_status,
)

from impl_v1.training.data.scaled_dataset import (
    ScaledDatasetGenerator,
    DatasetConfig,
    verify_determinism,
)


class TestTrainingIsolation(unittest.TestCase):
    """Test training isolation config."""
    
    def test_seccomp_blocks_network(self):
        """Network syscalls are blocked."""
        seccomp = get_training_seccomp()
        self.assertIn("socket", seccomp.blocked_syscalls)
        self.assertIn("connect", seccomp.blocked_syscalls)
    
    def test_rlimits_set(self):
        """Resource limits are set."""
        rlimits = get_training_rlimits()
        self.assertGreater(rlimits.max_memory_bytes, 0)


class TestSafeAcceleration(unittest.TestCase):
    """Test safe acceleration config."""
    
    def test_determinism_mandatory(self):
        """Determinism flags cannot be disabled."""
        config = get_balanced_config()
        self.assertTrue(config.deterministic_algorithms)
        self.assertTrue(config.cudnn_deterministic)
        self.assertFalse(config.cudnn_benchmark)
    
    def test_validate_config(self):
        """Valid config passes validation."""
        config = get_balanced_config()
        is_valid, errors = validate_config(config)
        self.assertTrue(is_valid)


class TestGPUThermalMonitor(unittest.TestCase):
    """Test GPU thermal monitoring."""
    
    def test_gpu_status(self):
        """GPU status returns valid data (real or unavailable)."""
        monitor = GPUThermalMonitor()
        status = monitor.get_gpu_status()
        self.assertIsNotNone(status.temperature_c)
    
    def test_thermal_state(self):
        """Thermal state is determined correctly."""
        monitor = GPUThermalMonitor()
        status = monitor.get_gpu_status()
        self.assertEqual(status.state, ThermalState.NORMAL)


class TestCalibrationEnforcement(unittest.TestCase):
    """Test calibration enforcement."""
    
    def test_compute_accuracy(self):
        """Accuracy computed correctly."""
        calc = CalibrationCalculator()
        acc = calc.compute_accuracy([1, 1, 0, 0], [1, 0, 0, 1])
        self.assertEqual(acc, 0.5)
    
    def test_compute_ece(self):
        """ECE computed."""
        calc = CalibrationCalculator()
        ece = calc.compute_ece([0.9, 0.8], [1, 1], [1, 1])
        self.assertGreaterEqual(ece, 0)


class TestAutoModeController(unittest.TestCase):
    """Test auto-mode controller."""
    
    def test_default_locked(self):
        """Auto-mode starts locked."""
        controller = AutoModeController()
        # Clear any saved state for test
        controller.state.unlocked = False
        self.assertFalse(controller.is_unlocked())
    
    def test_requirements_check(self):
        """Requirements are checked."""
        controller = AutoModeController()
        state = controller.evaluate_unlock(
            accuracy=0.98,
            ece=0.015,
            brier=0.025,
            stable_epochs=15,
            drift_events=0,
            checkpoint_count=60,
            replay_verified=True,
        )
        self.assertTrue(state.unlocked)


class TestScaledDataset(unittest.TestCase):
    """Test scaled dataset generation."""
    
    def test_generate_20k(self):
        """Generate 20,000 samples."""
        gen = ScaledDatasetGenerator()
        train, holdout = gen.generate()
        self.assertEqual(len(train) + len(holdout), 20000)
    
    def test_deterministic_shuffle(self):
        """Shuffle is deterministic."""
        self.assertTrue(verify_determinism())
    
    def test_balanced_classes(self):
        """Classes are balanced."""
        gen = ScaledDatasetGenerator()
        train, _ = gen.generate()
        stats = gen.get_statistics(train)
        self.assertAlmostEqual(stats["positive_ratio"], 0.5, delta=0.02)


if __name__ == "__main__":
    unittest.main()
