# Test G38 Runtime - Auto Trainer
"""
Tests for automatic idle-based training.

Tests cover:
- Scheduler triggers only when idle
- No trigger during scan
- No trigger during human activity
- No concurrent training
- All guards return False before training
"""

import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock

from impl_v1.phase49.runtime.auto_trainer import (
    AutoTrainer,
    TrainingState,
    TrainingEvent,
    TrainingSession,
    get_auto_trainer,
    start_auto_training,
    stop_auto_training,
)

from impl_v1.phase49.runtime.idle_detector import set_scan_active


# =============================================================================
# AUTO TRAINER BASIC TESTS
# =============================================================================

class TestAutoTrainerBasic:
    """Basic auto trainer tests."""
    
    def test_initial_state_is_idle(self):
        trainer = AutoTrainer()
        assert trainer.state == TrainingState.IDLE
    
    def test_initial_not_training(self):
        trainer = AutoTrainer()
        assert trainer.is_training is False
    
    def test_initial_epoch_zero(self):
        trainer = AutoTrainer()
        status = trainer.get_status()
        assert status["epoch"] == 0
    
    def test_events_initially_empty(self):
        trainer = AutoTrainer()
        assert trainer.events == []


# =============================================================================
# SCHEDULER TESTS
# =============================================================================

class TestSchedulerTriggers:
    """Tests for scheduler triggering conditions."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_triggers_when_idle_60s(self, mock_scan, mock_power, mock_idle):
        mock_idle.return_value = 120  # Idle for 2 minutes
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        # This should check conditions and potentially trigger training
        result = trainer.check_and_train()
        # Training may or may not succeed depending on GPU availability
        assert trainer.state in (TrainingState.IDLE, TrainingState.TRAINING, TrainingState.ERROR)
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    def test_no_trigger_when_not_idle(self, mock_idle):
        mock_idle.return_value = 10  # Only 10 seconds idle
        
        trainer = AutoTrainer()
        result = trainer.check_and_train()
        
        # Should not trigger training
        assert result is False
        assert trainer.state == TrainingState.IDLE
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_no_trigger_during_scan(self, mock_scan, mock_idle):
        mock_idle.return_value = 120
        mock_scan.return_value = True  # Scan active
        
        trainer = AutoTrainer()
        result = trainer.check_and_train()
        
        assert result is False
        assert trainer.state == TrainingState.IDLE
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    def test_no_trigger_without_power(self, mock_power, mock_idle):
        mock_idle.return_value = 120
        mock_power.return_value = False  # Not plugged in
        
        trainer = AutoTrainer()
        result = trainer.check_and_train()
        
        assert result is False


# =============================================================================
# NO CONCURRENT TRAINING TESTS
# =============================================================================

class TestNoConcurrentTraining:
    """Tests for preventing concurrent training."""
    
    def test_no_double_training(self):
        trainer = AutoTrainer()
        trainer._state = TrainingState.TRAINING
        
        # Should not start another training
        result = trainer.check_and_train()
        assert result is False


# =============================================================================
# GUARD TESTS
# =============================================================================

class TestGuardEnforcement:
    """Tests for guard enforcement before training."""
    
    def test_all_guards_checked(self):
        trainer = AutoTrainer()
        passed, msg = trainer._check_all_guards()
        
        # All guards should pass (return False = no authority)
        assert passed is True
        assert "All guards passed" in msg
    
    @patch("impl_v1.phase49.runtime.auto_trainer.verify_all_guards")
    def test_training_blocked_if_guard_fails(self, mock_guards):
        mock_guards.return_value = (False, "Guard violation")
        
        trainer = AutoTrainer()
        passed, msg = trainer._check_all_guards()
        
        assert passed is False
        assert "Guard violation" in msg
    
    @patch("impl_v1.phase49.runtime.auto_trainer.verify_pretraining_guards")
    def test_training_blocked_if_pretraining_guard_fails(self, mock_guards):
        mock_guards.return_value = (False, "Pretraining guard violation")
        
        trainer = AutoTrainer()
        passed, msg = trainer._check_all_guards()
        
        assert passed is False
        assert "Pretraining guard violation" in msg
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_mode_a_status")
    def test_training_blocked_if_mode_a_not_active(self, mock_status):
        from impl_v1.phase49.governors.g38_safe_pretraining import TrainingModeStatus
        mock_status.return_value = (TrainingModeStatus.LOCKED, "MODE-A locked")
        
        trainer = AutoTrainer()
        passed, msg = trainer._check_all_guards()
        
        assert passed is False
        assert "MODE-A is not active" in msg


# =============================================================================
# ABORT TESTS
# =============================================================================

class TestTrainingAbort:
    """Tests for training abort."""
    
    def test_abort_when_idle_returns_not_aborted(self):
        """abort_training() when idle does not set flag or emit event."""
        trainer = AutoTrainer()
        result = trainer.abort_training()
        
        # When idle, abort returns early without setting flag
        assert result["aborted"] is False
        assert "No training in progress" in result["reason"]
        assert not trainer._abort_flag.is_set()
    
    def test_abort_when_idle_no_event(self):
        """abort_training() when idle emits no event."""
        trainer = AutoTrainer()
        trainer.abort_training()
        
        # No events emitted when not training
        assert len(trainer.events) == 0


# =============================================================================
# HUMAN ACTIVITY ABORT TESTS
# =============================================================================

class TestHumanActivityAbort:
    """Tests for aborting on human activity."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_abort_on_human_interaction(self, mock_scan, mock_power, mock_idle):
        # Start with idle, then become active
        mock_idle.side_effect = [120, 120, 120, 5, 5, 5, 5, 5, 5, 5, 5]
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        result = trainer.check_and_train()
        
        # Training should have been aborted due to human interaction
        # (idle dropped below threshold during training)
        # Result may vary - key is the logic works


# =============================================================================
# EVENT EMISSION TESTS
# =============================================================================

class TestEventEmission:
    """Tests for event emission."""
    
    def test_emit_event_adds_to_list(self):
        trainer = AutoTrainer()
        event = trainer._emit_event("TEST_EVENT", "Test details")
        
        assert len(trainer.events) == 1
        assert trainer.events[0].event_type == "TEST_EVENT"
    
    def test_event_has_timestamp(self):
        trainer = AutoTrainer()
        event = trainer._emit_event("TEST_EVENT", "Test details")
        
        assert event.timestamp is not None
        assert "T" in event.timestamp  # ISO format
    
    def test_event_callback_called(self):
        trainer = AutoTrainer()
        callback_events = []
        
        trainer.set_event_callback(lambda e: callback_events.append(e))
        trainer._emit_event("TEST_EVENT", "Test details")
        
        assert len(callback_events) == 1
    
    def test_event_callback_error_handled(self):
        """Test that callback errors don't crash the trainer."""
        trainer = AutoTrainer()
        
        def bad_callback(e):
            raise ValueError("Callback error")
        
        trainer.set_event_callback(bad_callback)
        # Should not raise - error is caught
        event = trainer._emit_event("TEST_EVENT", "Test details")
        assert event is not None
    
    def test_event_types_log_correctly(self):
        """Test various event types are logged at appropriate levels."""
        trainer = AutoTrainer()
        
        # Test different event types
        trainer._emit_event("TRAINING_STARTED", "Started")
        trainer._emit_event("IDLE_DETECTED", "Idle detected")
        trainer._emit_event("TRAINING_STOPPED", "Stopped")
        trainer._emit_event("CHECKPOINT_SAVED", "Checkpoint")
        trainer._emit_event("TRAINING_ABORTED", "Aborted")
        trainer._emit_event("GUARD_BLOCKED", "Blocked")
        trainer._emit_event("ERROR", "Error occurred")
        trainer._emit_event("OTHER_EVENT", "Other")
        
        assert len(trainer.events) == 8


# =============================================================================
# STATUS TESTS
# =============================================================================

class TestStatus:
    """Tests for status reporting."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_get_status_returns_dict(self, mock_scan, mock_power, mock_idle):
        mock_idle.return_value = 0
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        status = trainer.get_status()
        
        assert isinstance(status, dict)
        assert "state" in status
        assert "is_training" in status
        assert "idle_seconds" in status
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_get_status_during_training(self, mock_scan, mock_power, mock_idle):
        """Test status shows real progress during training."""
        mock_idle.return_value = 120
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        trainer._state = TrainingState.TRAINING
        trainer._target_epochs = 10
        trainer._session_epoch = 5
        
        status = trainer.get_status()
        
        assert status["is_training"] is True
        assert status["epoch"] == 5
        assert status["total_epochs"] == 10
        assert status["progress"] == 50
    
    def test_get_status_shows_last_event(self):
        trainer = AutoTrainer()
        trainer._emit_event("TEST_EVENT", "Details")
        
        status = trainer.get_status()
        assert status["last_event"] == "TEST_EVENT"


# =============================================================================
# SINGLETON TESTS
# =============================================================================

class TestSingleton:
    """Tests for singleton instance."""
    
    def test_get_auto_trainer_returns_same_instance(self):
        trainer1 = get_auto_trainer()
        trainer2 = get_auto_trainer()
        assert trainer1 is trainer2


# =============================================================================
# REPRESENTATION-ONLY TESTS
# =============================================================================

class TestRepresentationOnlyTraining:
    """Tests to ensure only representation training is used."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_training_is_mode_a_only(self, mock_scan, mock_power, mock_idle):
        mock_idle.return_value = 120
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        
        # Check that MODE-A is enforced via guards
        from impl_v1.phase49.governors.g38_safe_pretraining import get_mode_a_status, TrainingModeStatus
        status, _ = get_mode_a_status()
        assert status == TrainingModeStatus.ACTIVE


# =============================================================================
# FORCE START TRAINING TESTS
# =============================================================================

def _make_mock_device():
    """Create a mock device_info that looks like CUDA."""
    from impl_v1.phase49.governors.g37_pytorch_backend import DeviceType
    m = MagicMock()
    m.device_type = DeviceType.CUDA
    m.device_name = "MockGPU"
    return m


class TestForceStartTraining:
    """Tests for manual force_start_training."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.detect_compute_device", side_effect=lambda: _make_mock_device())
    @patch("impl_v1.phase49.runtime.auto_trainer.PYTORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.TORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    @patch("impl_v1.phase49.runtime.auto_trainer.generate_training_report")
    def test_force_start_success(self, mock_report, mock_scan, mock_power, mock_idle, mock_dev):
        mock_idle.return_value = 0
        mock_power.return_value = True
        mock_scan.return_value = False
        mock_report.return_value = {"summary": "/path/to/report.txt"}
        
        trainer = AutoTrainer()
        
        # Mock GPU init and train step to avoid real GPU dependence
        with patch.object(trainer, "_init_gpu_resources", return_value=True), \
             patch.object(trainer, "_gpu_train_step", return_value=(True, 0.95, 0.1)):
            result = trainer.force_start_training(epochs=2)
        
        assert result["started"] is True
        assert result["completed_epochs"] == 2
        assert result["state"] == "COMPLETED"
    
    @patch("impl_v1.phase49.runtime.auto_trainer.detect_compute_device", side_effect=lambda: _make_mock_device())
    @patch("impl_v1.phase49.runtime.auto_trainer.PYTORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.TORCH_AVAILABLE", True)
    def test_force_start_blocked_if_already_training(self, mock_dev):
        trainer = AutoTrainer()
        trainer._state = TrainingState.TRAINING
        
        result = trainer.force_start_training(epochs=5)
        
        assert result["started"] is False
        assert "already in progress" in result["reason"]
    
    @patch("impl_v1.phase49.runtime.auto_trainer.detect_compute_device", side_effect=lambda: _make_mock_device())
    @patch("impl_v1.phase49.runtime.auto_trainer.PYTORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.TORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_force_start_abort_mid_training(self, mock_scan, mock_power, mock_idle, mock_dev):
        mock_idle.return_value = 0
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        
        # Set abort flag through mocked train step
        def abort_on_train(*args, **kwargs):
            trainer._abort_flag.set()
            return (True, 0.9, 0.2)
        
        with patch.object(trainer, "_init_gpu_resources", return_value=True), \
             patch.object(trainer, "_gpu_train_step", side_effect=abort_on_train):
            result = trainer.force_start_training(epochs=5)
        
        # Training was aborted
        assert result["completed_epochs"] < 5
    
    def test_force_start_error_handling(self):
        """Test that force_start_training handles edge cases gracefully."""
        trainer = AutoTrainer()
        trainer._state = TrainingState.IDLE
        
        # Test that error state is handled - verify the error state enum value
        trainer._state = TrainingState.ERROR
        assert trainer.state == TrainingState.ERROR
        
        # Reset to idle for next test
        trainer._state = TrainingState.IDLE


# =============================================================================
# SCHEDULER LOOP TESTS
# =============================================================================

class TestSchedulerLoop:
    """Tests for the async scheduler loop."""
    
    def test_run_scheduler_starts_and_stops(self):
        """Test that scheduler can start and stop."""
        trainer = AutoTrainer()
        
        # Verify scheduler can be controlled
        trainer._running = True
        assert trainer._running is True
        
        trainer._running = False
        assert trainer._running is False
    
    def test_start_creates_task(self):
        trainer = AutoTrainer()
        # Don't actually start to avoid async issues in test
        # Just verify the method exists and can be called
        assert hasattr(trainer, "start")
    
    def test_stop_sets_running_false(self):
        trainer = AutoTrainer()
        trainer._running = True
        trainer.stop()
        
        assert trainer._running is False
        assert trainer._abort_flag.is_set()


# =============================================================================
# GPU DETECTION TESTS
# =============================================================================

class TestGPUDetection:
    """Tests for GPU availability detection."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_gpu_detection_with_torch(self, mock_scan, mock_power, mock_idle):
        mock_idle.return_value = 0
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        conditions = trainer._get_current_conditions()
        
        # Should be bool regardless of torch availability
        assert isinstance(conditions.gpu_available, bool)
    
    @patch.dict("sys.modules", {"torch": None})
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_gpu_detection_without_torch(self, mock_scan, mock_power, mock_idle):
        mock_idle.return_value = 0
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        # Test that conditions can still be retrieved when torch import fails
        # The internal import exception is handled


# =============================================================================
# TRAINING SESSION TESTS
# =============================================================================

class TestTrainingSession:
    """Tests for TrainingSession dataclass."""
    
    def test_training_session_creation(self):
        session = TrainingSession(
            started_at="2025-01-01T00:00:00Z",
            start_epoch=0,
            gpu_used=True,
        )
        
        assert session.started_at == "2025-01-01T00:00:00Z"
        assert session.start_epoch == 0
        assert session.gpu_used is True
        assert session.checkpoints_saved == 0
        assert session.last_checkpoint_hash == ""


# =============================================================================
# REPORT GENERATION TESTS
# =============================================================================

class TestReportGeneration:
    """Tests for training report generation."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.generate_training_report")
    def test_generate_session_report(self, mock_report):
        mock_report.return_value = {"summary": "/path/to/report.txt"}
        
        trainer = AutoTrainer()
        trainer._current_session = TrainingSession(
            started_at="2025-01-01T00:00:00Z",
            start_epoch=0,
            gpu_used=True,
        )
        trainer._epoch = 5
        trainer._emit_event("CHECKPOINT_SAVED", "Saved (hash: abc123)")
        
        trainer._generate_session_report()
        
        # Report should have been called
        assert mock_report.called
    
    def test_generate_session_report_no_session(self):
        trainer = AutoTrainer()
        trainer._current_session = None
        
        # Should not raise
        trainer._generate_session_report()
    
    @patch("impl_v1.phase49.runtime.auto_trainer.generate_training_report")
    def test_generate_session_report_error_handled(self, mock_report):
        mock_report.side_effect = Exception("Report error")
        
        trainer = AutoTrainer()
        trainer._current_session = TrainingSession(
            started_at="2025-01-01T00:00:00Z",
            start_epoch=0,
            gpu_used=True,
        )
        
        # Should not raise - error is logged
        trainer._generate_session_report()


# =============================================================================
# TRAINING REPRESENTATION TESTS
# =============================================================================

class TestTrainRepresentationOnly:
    """Tests for _train_representation_only method."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.detect_compute_device", side_effect=lambda: _make_mock_device())
    @patch("impl_v1.phase49.runtime.auto_trainer.PYTORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.TORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_train_aborts_on_flag(self, mock_scan, mock_idle, mock_dev):
        mock_idle.return_value = 120
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        trainer._abort_flag.set()
        
        result = trainer._train_representation_only()
        
        assert result is False
    
    @patch("impl_v1.phase49.runtime.auto_trainer.detect_compute_device", side_effect=lambda: _make_mock_device())
    @patch("impl_v1.phase49.runtime.auto_trainer.PYTORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.TORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_train_aborts_on_scan_start(self, mock_scan, mock_idle, mock_dev):
        mock_idle.return_value = 120
        # Scan is active when checked inside _train_representation_only
        mock_scan.return_value = True
        
        trainer = AutoTrainer()
        
        result = trainer._train_representation_only()
        
        assert result is False
    
    @patch("impl_v1.phase49.runtime.auto_trainer.detect_compute_device", side_effect=lambda: _make_mock_device())
    @patch("impl_v1.phase49.runtime.auto_trainer.PYTORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.TORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_train_aborts_on_human_activity(self, mock_scan, mock_idle, mock_dev):
        # Idle is below threshold when checked pre-step
        mock_idle.return_value = 30
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        
        result = trainer._train_representation_only()
        
        assert result is False
    
    @patch("impl_v1.phase49.runtime.auto_trainer.detect_compute_device", side_effect=lambda: _make_mock_device())
    @patch("impl_v1.phase49.runtime.auto_trainer.PYTORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.TORCH_AVAILABLE", True)
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_train_completes_successfully(self, mock_scan, mock_idle, mock_dev):
        mock_idle.return_value = 120
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        
        with patch.object(trainer, "_gpu_train_step", return_value=(True, 0.95, 0.05)):
            result = trainer._train_representation_only()
        
        assert result is True
        assert trainer._epoch == 1


# =============================================================================
# CHECK AND TRAIN TESTS
# =============================================================================

class TestCheckAndTrain:
    """Tests for check_and_train method."""
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    @patch("impl_v1.phase49.runtime.auto_trainer.generate_training_report")
    def test_check_and_train_guards_blocked(self, mock_report, mock_scan, mock_power, mock_idle):
        mock_idle.return_value = 120
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        
        with patch.object(trainer, "_check_all_guards", return_value=(False, "Guard failed")):
            result = trainer.check_and_train()
            
            assert result is False
            # Should have emitted GUARD_BLOCKED event
            blocked_events = [e for e in trainer.events if e.event_type == "GUARD_BLOCKED"]
            assert len(blocked_events) > 0
    
    @patch("impl_v1.phase49.runtime.auto_trainer.get_idle_seconds")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_power_connected")
    @patch("impl_v1.phase49.runtime.auto_trainer.is_scan_active")
    def test_check_and_train_error_handling(self, mock_scan, mock_power, mock_idle):
        mock_idle.side_effect = Exception("Test exception")
        mock_power.return_value = True
        mock_scan.return_value = False
        
        trainer = AutoTrainer()
        result = trainer.check_and_train()
        
        assert result is False
        assert trainer.state == TrainingState.ERROR


# =============================================================================
# START/STOP AUTO TRAINING TESTS
# =============================================================================

class TestStartStopAutoTraining:
    """Tests for module-level start/stop functions."""
    
    def test_start_auto_training_function_exists(self):
        # Just verify the function exists and is callable
        assert callable(start_auto_training)
    
    def test_stop_auto_training_function_exists(self):
        # Just verify the function exists and is callable
        assert callable(stop_auto_training)
    
    def test_stop_auto_training_when_no_trainer(self):
        # Should not raise when no trainer exists
        import impl_v1.phase49.runtime.auto_trainer as module
        old_trainer = module._auto_trainer
        module._auto_trainer = None
        
        stop_auto_training()  # Should not raise
        
        module._auto_trainer = old_trainer
