# Test G37 GPU Training Backend
"""
Tests for G37 GPU training backend.

100% coverage required.
"""

import pytest

from impl_v1.phase49.governors.g37_gpu_training_backend import (
    # Enums
    GPUBackend,
    TrainingObjective,
    # Dataclasses
    GPUDeviceInfo,
    FeatureVector,
    TrainingConfig,
    TrainingMetrics,
    ModelCheckpoint,
    InferenceResult,
    # Device functions
    detect_gpu_devices,
    select_best_device,
    # Feature extraction
    extract_bug_features,
    extract_duplicate_features,
    # Training
    create_training_config,
    gpu_train_epoch,
    gpu_train_full,
    save_checkpoint,
    # Inference
    gpu_infer,
    gpu_batch_infer,
    # Similarity
    compute_similarity,
    contrastive_loss,
    # Incremental
    prepare_incremental_batch,
    incremental_update,
    # Guards
    can_training_execute_payloads,
    can_training_access_network,
    can_training_modify_evidence,
    can_training_bypass_governance,
    can_inference_approve_bugs,
    can_inference_submit_reports,
)


class TestGPUBackendEnum:
    """Tests for GPUBackend enum."""
    
    def test_has_cuda(self):
        assert GPUBackend.CUDA.value == "CUDA"
    
    def test_has_rocm(self):
        assert GPUBackend.ROCM.value == "ROCM"
    
    def test_has_mock(self):
        assert GPUBackend.MOCK.value == "MOCK"


class TestTrainingObjectiveEnum:
    """Tests for TrainingObjective enum."""
    
    def test_has_bug_classifier(self):
        assert TrainingObjective.BUG_CLASSIFIER.value == "BUG_CLASSIFIER"
    
    def test_has_duplicate_detector(self):
        assert TrainingObjective.DUPLICATE_DETECTOR.value == "DUPLICATE_DETECTOR"
    
    def test_has_noise_filter(self):
        assert TrainingObjective.NOISE_FILTER.value == "NOISE_FILTER"


class TestDeviceDetection:
    """Tests for GPU device detection."""
    
    def test_detect_devices(self):
        devices = detect_gpu_devices()
        assert len(devices) >= 1
        assert devices[0].backend == GPUBackend.MOCK
    
    def test_select_best_device(self):
        devices = detect_gpu_devices()
        best = select_best_device(devices)
        assert isinstance(best, GPUDeviceInfo)


class TestFeatureExtraction:
    """Tests for feature extraction."""
    
    def test_extract_bug_features(self):
        feature = extract_bug_features(
            bug_text="SQL injection in login",
            bug_type="SQLi",
            endpoint="/login",
            response_delta=True,
            reproduction_count=3,
        )
        
        assert feature.vector_id.startswith("FV-")
        assert feature.dimensions == 256
        assert feature.label == "SQLi"
    
    def test_extract_duplicate_features(self):
        fa, fb = extract_duplicate_features("Report A", "Report B")
        
        assert fa.label == "REPORT_A"
        assert fb.label == "REPORT_B"


class TestTrainingConfig:
    """Tests for training configuration."""
    
    def test_create_config(self):
        config = create_training_config(
            TrainingObjective.BUG_CLASSIFIER,
            batch_size=64,
            learning_rate=0.001,
            epochs=50,
        )
        
        assert config.config_id.startswith("CFG-")
        assert config.objective == TrainingObjective.BUG_CLASSIFIER
        assert config.batch_size == 64
        assert config.epochs == 50


class TestGPUTraining:
    """Tests for GPU training."""
    
    def test_train_epoch(self):
        device = detect_gpu_devices()[0]
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER)
        features = (
            extract_bug_features("bug1", "XSS", "/page", True, 2),
            extract_bug_features("bug2", "SQLi", "/api", True, 3),
        )
        
        metrics = gpu_train_epoch(device, config, features, 1)
        
        assert metrics.epoch == 1
        assert 0 <= metrics.accuracy <= 1
        assert metrics.time_seconds >= 0
    
    def test_train_full(self):
        device = detect_gpu_devices()[0]
        config = create_training_config(
            TrainingObjective.BUG_CLASSIFIER,
            epochs=5,
        )
        features = (
            extract_bug_features("bug", "XSS", "/", True, 2),
        )
        
        all_metrics = gpu_train_full(device, config, features)
        
        assert len(all_metrics) >= 1
        # Should improve over epochs
        assert all_metrics[-1].accuracy >= all_metrics[0].accuracy
    
    def test_save_checkpoint(self):
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER)
        metrics = TrainingMetrics(
            epoch=10,
            loss=0.05,
            accuracy=0.97,
            precision=0.96,
            recall=0.95,
            f1_score=0.955,
            gpu_memory_used_mb=1024,
            time_seconds=60.0,
        )
        
        checkpoint = save_checkpoint(config, metrics, is_best=True)
        
        assert checkpoint.checkpoint_id.startswith("CKPT-")
        assert checkpoint.accuracy == 0.97
        assert checkpoint.is_best is True


class TestGPUInference:
    """Tests for GPU inference."""
    
    def test_infer_single(self):
        device = detect_gpu_devices()[0]
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER)
        metrics = TrainingMetrics(5, 0.1, 0.95, 0.94, 0.93, 0.935, 512, 30.0)
        checkpoint = save_checkpoint(config, metrics)
        
        feature = extract_bug_features("test", "XSS", "/", True, 2)
        result = gpu_infer(device, checkpoint, feature)
        
        assert result.result_id.startswith("INF-")
        assert result.prediction in ("REAL", "NOT_REAL")
        assert 0 <= result.confidence <= 1
    
    def test_batch_infer(self):
        device = detect_gpu_devices()[0]
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER)
        metrics = TrainingMetrics(5, 0.1, 0.95, 0.94, 0.93, 0.935, 512, 30.0)
        checkpoint = save_checkpoint(config, metrics)
        
        features = (
            extract_bug_features("b1", "XSS", "/a", True, 2),
            extract_bug_features("b2", "SQLi", "/b", True, 3),
        )
        
        results = gpu_batch_infer(device, checkpoint, features)
        
        assert len(results) == 2


class TestSimilarityAndLoss:
    """Tests for similarity and contrastive loss."""
    
    def test_compute_similarity(self):
        emb_a = (0.1, 0.2, 0.3)
        emb_b = (0.1, 0.2, 0.3)
        
        sim = compute_similarity(emb_a, emb_b)
        
        assert 0 <= sim <= 1
    
    def test_contrastive_loss(self):
        anchor = extract_bug_features("a", "XSS", "/", True, 2)
        positive = extract_bug_features("p", "XSS", "/", True, 2)
        negative = extract_bug_features("n", "INFO", "/", False, 0)
        
        loss = contrastive_loss(anchor, positive, negative)
        
        assert loss >= 0


class TestIncrementalTraining:
    """Tests for incremental training."""
    
    def test_prepare_batch(self):
        verified = (extract_bug_features("v", "XSS", "/", True, 2),)
        rejected = (extract_bug_features("r", "INFO", "/", False, 0),)
        duplicates = (extract_bug_features("d", "XSS", "/", True, 2),)
        
        batch = prepare_incremental_batch(verified, rejected, duplicates)
        
        assert len(batch) == 3
    
    def test_incremental_update(self):
        device = detect_gpu_devices()[0]
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER)
        metrics = TrainingMetrics(10, 0.05, 0.97, 0.96, 0.95, 0.955, 512, 60.0)
        checkpoint = save_checkpoint(config, metrics)
        
        new_features = (extract_bug_features("new", "SQLi", "/", True, 3),)
        
        update_metrics = incremental_update(device, checkpoint, new_features)
        
        assert update_metrics.epoch == 1


class TestGuards:
    """Tests for all guards."""
    
    def test_can_training_execute_payloads_returns_false(self):
        can_execute, reason = can_training_execute_payloads()
        assert can_execute is False
        assert "read-only" in reason.lower()
    
    def test_can_training_access_network_returns_false(self):
        can_access, reason = can_training_access_network()
        assert can_access is False
        assert "exploitation" in reason.lower()
    
    def test_can_training_modify_evidence_returns_false(self):
        can_modify, reason = can_training_modify_evidence()
        assert can_modify is False
        assert "read-only" in reason.lower()
    
    def test_can_training_bypass_governance_returns_false(self):
        can_bypass, reason = can_training_bypass_governance()
        assert can_bypass is False
        assert "absolute" in reason.lower()
    
    def test_can_inference_approve_bugs_returns_false(self):
        can_approve, reason = can_inference_approve_bugs()
        assert can_approve is False
        assert "advisory" in reason.lower()
    
    def test_can_inference_submit_reports_returns_false(self):
        can_submit, reason = can_inference_submit_reports()
        assert can_submit is False
        assert "human" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive guard test."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_training_execute_payloads,
            can_training_access_network,
            can_training_modify_evidence,
            can_training_bypass_governance,
            can_inference_approve_bugs,
            can_inference_submit_reports,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result is False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0


class TestFrozenDataclasses:
    """Test all dataclasses are frozen."""
    
    def test_feature_vector_frozen(self):
        feature = extract_bug_features("test", "XSS", "/", True, 2)
        with pytest.raises(AttributeError):
            feature.dimensions = 512
    
    def test_training_metrics_frozen(self):
        metrics = TrainingMetrics(1, 0.5, 0.8, 0.8, 0.8, 0.8, 512, 30.0)
        with pytest.raises(AttributeError):
            metrics.accuracy = 1.0


class TestNoForbiddenImports:
    """Test no forbidden imports."""
    
    def test_no_forbidden_imports(self):
        import impl_v1.phase49.governors.g37_gpu_training_backend as backend
        import inspect
        
        source = inspect.getsource(backend)
        
        forbidden = ["subprocess", "socket", "selenium", "playwright"]
        for name in forbidden:
            assert f"import {name}" not in source
