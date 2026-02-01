# Test G37 PyTorch Backend
"""
Tests for G37 PyTorch training backend.

100% coverage required.
"""

import pytest

from impl_v1.phase49.governors.g37_pytorch_backend import (
    # Enums
    DeviceType,
    # Dataclasses
    DeviceInfo,
    ModelConfig,
    TrainingSample,
    TrainingBatch,
    EpochMetrics,
    ModelCheckpoint,
    InferenceResult,
    # Device functions
    detect_compute_device,
    get_torch_device,
    # Training
    create_model_config,
    prepare_training_batch,
    train_single_epoch,
    train_full,
    save_model_checkpoint,
    # Inference
    infer_single,
    infer_batch,
    # Guards
    can_train_without_idle,
    can_infer_without_model,
    can_override_gpu_errors,
    can_training_modify_governance,
    can_training_execute_code,
    can_inference_approve_bugs,
    # Constants
    PYTORCH_AVAILABLE,
)


class TestDeviceType:
    """Tests for DeviceType enum."""
    
    def test_has_cuda(self):
        assert DeviceType.CUDA.value == "CUDA"
    
    def test_has_cpu(self):
        assert DeviceType.CPU.value == "CPU"


class TestDeviceDetection:
    """Tests for device detection."""
    
    def test_detect_device(self):
        device_info = detect_compute_device()
        assert isinstance(device_info, DeviceInfo)
        assert device_info.device_type in (DeviceType.CUDA, DeviceType.CPU, DeviceType.UNAVAILABLE)
    
    def test_get_torch_device(self):
        device = get_torch_device()
        # Can be None if PyTorch unavailable
        if PYTORCH_AVAILABLE:
            assert device is not None


class TestModelConfig:
    """Tests for model configuration."""
    
    def test_create_config(self):
        config = create_model_config(
            input_dim=128,
            output_dim=3,
            learning_rate=0.01,
        )
        
        assert config.input_dim == 128
        assert config.output_dim == 3
        assert config.learning_rate == 0.01


class TestTrainingBatch:
    """Tests for training batch preparation."""
    
    def test_prepare_batch(self):
        samples = (
            TrainingSample("S001", (0.1, 0.2, 0.3), 0, "G33"),
            TrainingSample("S002", (0.4, 0.5, 0.6), 1, "G33"),
        )
        
        batch = prepare_training_batch(samples)
        
        assert batch.batch_id.startswith("BTH-")
        assert len(batch.samples) == 2
        assert len(batch.batch_hash) == 32


class TestTraining:
    """Tests for training functions."""
    
    def test_train_full(self):
        config = create_model_config(
            input_dim=3,
            output_dim=2,
            epochs=5,
        )
        
        samples = (
            TrainingSample("S001", (0.1, 0.2, 0.3), 0, "G33"),
            TrainingSample("S002", (0.4, 0.5, 0.6), 1, "G33"),
        )
        
        model, metrics = train_full(config, samples)
        
        assert len(metrics) >= 1
        assert all(m.epoch > 0 for m in metrics)
        # Accuracy should improve
        assert metrics[-1].train_accuracy >= metrics[0].train_accuracy
    
    def test_early_stopping(self):
        config = create_model_config(
            input_dim=3,
            output_dim=2,
            epochs=100,
        )
        
        samples = (
            TrainingSample("S001", (0.1, 0.2, 0.3), 0, "G33"),
        )
        
        model, metrics = train_full(config, samples, early_stop_accuracy=0.8)
        
        # Should stop before 100 epochs if accuracy reached
        assert len(metrics) < 100


class TestInference:
    """Tests for inference functions."""
    
    def test_infer_single(self):
        config = create_model_config(input_dim=3, output_dim=2, epochs=3)
        samples = (TrainingSample("S001", (0.1, 0.2, 0.3), 0, "G33"),)
        model, _ = train_full(config, samples)
        
        result = infer_single(model, samples[0])
        
        assert result.result_id.startswith("INF-")
        assert result.prediction in (0, 1)
        assert 0 <= result.confidence <= 1
    
    def test_infer_batch(self):
        config = create_model_config(input_dim=3, output_dim=2, epochs=3)
        samples = (
            TrainingSample("S001", (0.1, 0.2, 0.3), 0, "G33"),
            TrainingSample("S002", (0.4, 0.5, 0.6), 1, "G33"),
        )
        model, _ = train_full(config, samples)
        
        results = infer_batch(model, samples)
        
        assert len(results) == 2


class TestGuards:
    """Tests for all guards."""
    
    def test_can_train_without_idle_returns_false(self):
        can_train, reason = can_train_without_idle()
        assert can_train is False
        assert "idle" in reason.lower()
    
    def test_can_infer_without_model_returns_false(self):
        can_infer, reason = can_infer_without_model()
        assert can_infer is False
        assert "model" in reason.lower()
    
    def test_can_override_gpu_errors_returns_false(self):
        can_override, reason = can_override_gpu_errors()
        assert can_override is False
        assert "explicit" in reason.lower()
    
    def test_can_training_modify_governance_returns_false(self):
        can_modify, reason = can_training_modify_governance()
        assert can_modify is False
        assert "governance" in reason.lower()
    
    def test_can_training_execute_code_returns_false(self):
        can_execute, reason = can_training_execute_code()
        assert can_execute is False
        assert "execute" in reason.lower()
    
    def test_can_inference_approve_bugs_returns_false(self):
        can_approve, reason = can_inference_approve_bugs()
        assert can_approve is False
        assert "advisory" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive guard test."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_train_without_idle,
            can_infer_without_model,
            can_override_gpu_errors,
            can_training_modify_governance,
            can_training_execute_code,
            can_inference_approve_bugs,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result is False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0


class TestFrozenDataclasses:
    """Test dataclasses are frozen."""
    
    def test_training_sample_frozen(self):
        sample = TrainingSample("S001", (0.1,), 0, "src")
        with pytest.raises(AttributeError):
            sample.label = 1
    
    def test_model_config_frozen(self):
        config = create_model_config()
        with pytest.raises(AttributeError):
            config.epochs = 1000
