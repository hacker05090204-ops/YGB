"""
Enterprise Control Plane Tests
================================

Tests for enterprise 24/7 control plane.
"""

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.enterprise.training_controller import (
    TrainingController,
    TrainingMode,
)

from impl_v1.enterprise.process_isolation import (
    ProcessIsolator,
    ProcessState,
    HashVerifiedTransfer,
)

from impl_v1.enterprise.resource_partition import (
    GPUScheduler,
    PerformanceGuard,
    ResourceLimits,
)

from impl_v1.enterprise.checkpoint_sync import (
    CheckpointExchangeProtocol,
    CheckpointMetadata,
    TrainingSandbox,
)

from impl_v1.enterprise.control_plane import (
    EnterpriseControlPlane,
)


class TestTrainingController(unittest.TestCase):
    """Test training controller."""
    
    def test_start_stop(self):
        """Start and stop training."""
        controller = TrainingController()
        controller.is_running = False  # Reset
        
        success, _ = controller.start()
        self.assertTrue(success)
        
        success, _ = controller.stop()
        self.assertTrue(success)
    
    def test_status(self):
        """Get training status."""
        controller = TrainingController()
        status = controller.get_status()
        self.assertIsNotNone(status.mode)


class TestProcessIsolation(unittest.TestCase):
    """Test process isolation."""
    
    def test_isolation_status(self):
        """Get isolation status."""
        isolator = ProcessIsolator()
        status = isolator.get_isolation_status()
        self.assertFalse(status["shared_memory"])
    
    def test_training_crash_no_affect_inference(self):
        """Training crash doesn't affect inference."""
        isolator = ProcessIsolator()
        isolator.start_inference()
        isolator.start_training()
        
        # Simulate crash
        isolator.on_training_crash()
        
        self.assertEqual(isolator.training_process.state, ProcessState.CRASHED)
        self.assertEqual(isolator.inference_process.state, ProcessState.RUNNING)


class TestResourcePartition(unittest.TestCase):
    """Test resource partitioning."""
    
    def test_gpu_throttle(self):
        """Throttle on high utilization."""
        scheduler = GPUScheduler()
        batch, accum = scheduler.throttle_training(0.90)  # High
        self.assertLess(batch, scheduler.limits.max_batch_size)
    
    def test_performance_guard(self):
        """Performance guard triggers throttle."""
        guard = PerformanceGuard()
        throttle, _ = guard.check_and_throttle(
            current_latency_ms=150,  # Above 120ms (20% of 100)
            current_memory_mb=5000,
            current_temp_c=75,
        )
        self.assertTrue(throttle)


class TestCheckpointSync(unittest.TestCase):
    """Test checkpoint sync."""
    
    def test_version_mismatch_rejected(self):
        """Reject mismatched versions."""
        protocol = CheckpointExchangeProtocol()
        
        local = CheckpointMetadata("ckpt1", "1.0.0", "hash1", 10, {}, "", "d0")
        remote = CheckpointMetadata("ckpt2", "2.0.0", "hash2", 10, {}, "", "d1")
        
        valid, _ = protocol.validate_for_merge(local, remote)
        self.assertFalse(valid)
    
    def test_valid_merge(self):
        """Valid merge succeeds."""
        protocol = CheckpointExchangeProtocol()
        
        local = CheckpointMetadata("ckpt1", "1.0.0", "hash1", 10, {}, "", "d0")
        remote = CheckpointMetadata("ckpt2", "1.0.0", "hash2", 10, {}, "", "d1")
        
        merge_id, _ = protocol.merge_checkpoints(local, remote)
        self.assertIsNotNone(merge_id)


class TestSandbox(unittest.TestCase):
    """Test training sandbox."""
    
    def test_sandbox_status(self):
        """Sandbox enforced."""
        sandbox = TrainingSandbox()
        status = sandbox.get_sandbox_status()
        self.assertTrue(status["seccomp_enabled"])
        self.assertTrue(status["network_blocked"])


class TestControlPlane(unittest.TestCase):
    """Test enterprise control plane."""
    
    def test_check_all(self):
        """Check all enterprise requirements."""
        plane = EnterpriseControlPlane()
        status = plane.check_all()
        self.assertIsNotNone(status.auto_mode_safe)


if __name__ == "__main__":
    unittest.main()
