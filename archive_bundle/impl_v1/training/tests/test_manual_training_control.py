"""
Test Manual Training Control
=============================

Validates:
- Training starts ONLY via explicit API call
- No idle auto-trigger
- Start/Stop endpoints functional
- Training state persists correctly
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


class TestManualTrainingControl:
    """Tests for manual training control (no auto-trigger)."""
    
    def test_no_auto_trigger_in_scheduler(self):
        """run_scheduler must NOT call check_and_train automatically."""
        import inspect
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer.run_scheduler)
        
        # run_scheduler should NOT contain check_and_train call
        assert "check_and_train" not in source, \
            "run_scheduler still contains auto-trigger (check_and_train)"
    
    def test_training_mode_is_manual(self):
        """Training mode must be MANUAL."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        trainer = AutoTrainer()
        status = trainer.get_status()
        
        assert status["training_mode"] == "MANUAL", \
            f"Expected MANUAL mode, got {status['training_mode']}"
    
    def test_force_start_requires_gpu(self):
        """force_start_training must enforce GPU-only mode."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        import torch
        
        trainer = AutoTrainer()
        
        if not torch.cuda.is_available():
            result = trainer.force_start_training(epochs=1)
            assert result["started"] is False
            assert "CUDA" in result.get("reason", "") or "GPU" in result.get("reason", "")
    
    def test_abort_training_when_not_training(self):
        """abort_training must return status when not training."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        trainer = AutoTrainer()
        result = trainer.abort_training()
        
        assert result["aborted"] is False
        assert "No training" in result.get("reason", "")
    
    def test_trainer_starts_in_idle_state(self):
        """Trainer must start in IDLE state, not TRAINING."""
        from impl_v1.phase49.runtime.auto_trainer import (
            AutoTrainer,
            TrainingState,
        )
        
        trainer = AutoTrainer()
        assert trainer.state == TrainingState.IDLE
        assert trainer.is_training is False
    
    def test_status_includes_gpu_metrics(self):
        """get_status must include GPU metrics."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        trainer = AutoTrainer()
        status = trainer.get_status()
        
        assert "gpu_mem_allocated_mb" in status
        assert "gpu_mem_reserved_mb" in status
        assert "last_loss" in status
        assert "last_accuracy" in status
        assert "samples_per_sec" in status
        assert "dataset_size" in status
    
    def test_status_includes_dataset_size(self):
        """get_status must report dataset size (0 before init)."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        trainer = AutoTrainer()
        status = trainer.get_status()
        
        # Before GPU init, dataset_size should be 0
        assert status["dataset_size"] == 0
    
    def test_start_auto_training_is_manual_mode(self):
        """start_auto_training must NOT auto-trigger training."""
        import inspect
        from impl_v1.phase49.runtime.auto_trainer import start_auto_training
        
        source = inspect.getsource(start_auto_training)
        assert "MANUAL" in source or "manual" in source.lower(), \
            "start_auto_training should document MANUAL mode"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
