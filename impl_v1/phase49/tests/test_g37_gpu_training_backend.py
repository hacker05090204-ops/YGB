# Test G37 GPU Training Backend
"""Tests for the real G37 training adapter."""

import inspect

import pytest

import impl_v1.phase49.governors.g37_gpu_training_backend as backend

from impl_v1.phase49.governors.g37_gpu_training_backend import (
    FeatureVector,
    GPUBackend,
    GPUDeviceInfo,
    InferenceResult,
    ModelCheckpoint,
    TrainingConfig,
    TrainingMetrics,
    TrainingObjective,
    can_inference_approve_bugs,
    can_inference_submit_reports,
    can_training_access_network,
    can_training_bypass_governance,
    can_training_execute_payloads,
    can_training_modify_evidence,
    compute_similarity,
    contrastive_loss,
    create_training_config,
    detect_gpu_devices,
    extract_bug_features,
    extract_duplicate_features,
    gpu_batch_infer,
    gpu_infer,
    gpu_train_epoch,
    gpu_train_full,
    incremental_update,
    prepare_incremental_batch,
    save_checkpoint,
    select_best_device,
)


def _training_features():
    return (
        extract_bug_features("SQL injection in login", "SQLI", "/login", True, 3),
        extract_bug_features("Cross-site scripting in search", "XSS", "/search", True, 2),
        extract_bug_features("Informational banner mismatch", "INFO", "/health", False, 0),
    )


class TestGPUBackendEnum:
    def test_has_cuda(self):
        assert GPUBackend.CUDA.value == "CUDA"

    def test_has_cpu(self):
        assert GPUBackend.CPU.value == "CPU"

    def test_has_unavailable(self):
        assert GPUBackend.UNAVAILABLE.value == "UNAVAILABLE"


class TestTrainingObjectiveEnum:
    def test_has_bug_classifier(self):
        assert TrainingObjective.BUG_CLASSIFIER.value == "BUG_CLASSIFIER"

    def test_has_duplicate_detector(self):
        assert TrainingObjective.DUPLICATE_DETECTOR.value == "DUPLICATE_DETECTOR"

    def test_has_noise_filter(self):
        assert TrainingObjective.NOISE_FILTER.value == "NOISE_FILTER"


class TestDeviceDetection:
    def test_detect_devices(self):
        devices = detect_gpu_devices()
        assert len(devices) >= 1
        assert devices[0].backend in {
            GPUBackend.CUDA,
            GPUBackend.ROCM,
            GPUBackend.CPU,
            GPUBackend.UNAVAILABLE,
        }

    def test_select_best_device(self):
        best = select_best_device(detect_gpu_devices())
        assert isinstance(best, GPUDeviceInfo)


class TestFeatureExtraction:
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
        assert len(feature.values) == 256

    def test_extract_duplicate_features(self):
        fa, fb = extract_duplicate_features("Report A", "Report B")
        assert fa.label == "REPORT_A"
        assert fb.label == "REPORT_B"
        assert len(fa.values) == 256


class TestTrainingConfig:
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


@pytest.mark.skipif(not backend._pt_backend.PYTORCH_AVAILABLE, reason="PyTorch unavailable")
class TestGPUTraining:
    def test_train_epoch(self):
        device = select_best_device(detect_gpu_devices())
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER, epochs=1)
        metrics = gpu_train_epoch(device, config, _training_features(), 1)
        assert metrics.epoch == 1
        assert 0 <= metrics.accuracy <= 1
        assert metrics.time_seconds >= 0

    def test_train_full(self):
        device = select_best_device(detect_gpu_devices())
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER, epochs=3)
        all_metrics = gpu_train_full(device, config, _training_features())
        assert len(all_metrics) >= 1
        assert all(metric.epoch > 0 for metric in all_metrics)

    def test_save_checkpoint(self):
        device = select_best_device(detect_gpu_devices())
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER, epochs=2)
        metrics = gpu_train_full(device, config, _training_features())[-1]
        checkpoint = save_checkpoint(config, metrics, is_best=True)
        assert checkpoint.checkpoint_id.startswith("CKPT-")
        assert checkpoint.accuracy == metrics.accuracy
        assert checkpoint.is_best is True
        assert checkpoint.path

    def test_save_checkpoint_requires_trained_model(self):
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER, epochs=1)
        metrics = TrainingMetrics(1, 0.5, 0.5, 0.5, 0.5, 0.5, 0, 0.1)
        with pytest.raises(RuntimeError, match="No trained model"):
            save_checkpoint(config, metrics)


@pytest.mark.skipif(not backend._pt_backend.PYTORCH_AVAILABLE, reason="PyTorch unavailable")
class TestGPUInference:
    def test_infer_single(self):
        device = select_best_device(detect_gpu_devices())
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER, epochs=2)
        metrics = gpu_train_full(device, config, _training_features())[-1]
        checkpoint = save_checkpoint(config, metrics)
        feature = extract_bug_features("test", "XSS", "/", True, 2)
        result = gpu_infer(device, checkpoint, feature)
        assert result.result_id.startswith("INF-")
        assert result.prediction in ("REAL", "NOT_REAL")
        assert 0 <= result.confidence <= 1

    def test_batch_infer(self):
        device = select_best_device(detect_gpu_devices())
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER, epochs=2)
        metrics = gpu_train_full(device, config, _training_features())[-1]
        checkpoint = save_checkpoint(config, metrics)
        features = (
            extract_bug_features("b1", "XSS", "/a", True, 2),
            extract_bug_features("b2", "INFO", "/b", False, 0),
        )
        results = gpu_batch_infer(device, checkpoint, features)
        assert len(results) == 2


class TestSimilarityAndLoss:
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
    def test_prepare_batch(self):
        verified = (extract_bug_features("v", "XSS", "/", True, 2),)
        rejected = (extract_bug_features("r", "INFO", "/", False, 0),)
        duplicates = (extract_bug_features("d", "XSS", "/", True, 2),)
        batch = prepare_incremental_batch(verified, rejected, duplicates)
        assert len(batch) == 3

    @pytest.mark.skipif(not backend._pt_backend.PYTORCH_AVAILABLE, reason="PyTorch unavailable")
    def test_incremental_update(self):
        device = select_best_device(detect_gpu_devices())
        config = create_training_config(TrainingObjective.BUG_CLASSIFIER, epochs=2)
        metrics = gpu_train_full(device, config, _training_features())[-1]
        checkpoint = save_checkpoint(config, metrics)
        new_features = (extract_bug_features("new", "SQLi", "/", True, 3),)
        update_metrics = incremental_update(device, checkpoint, new_features)
        assert update_metrics.epoch == 1
        assert update_metrics.time_seconds >= 0


class TestGuards:
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
            assert result is False
            assert len(reason) > 0


class TestFrozenDataclasses:
    def test_feature_vector_frozen(self):
        feature = extract_bug_features("test", "XSS", "/", True, 2)
        with pytest.raises(AttributeError):
            feature.dimensions = 512

    def test_training_metrics_frozen(self):
        metrics = TrainingMetrics(1, 0.5, 0.8, 0.8, 0.8, 0.8, 0, 30.0)
        with pytest.raises(AttributeError):
            metrics.accuracy = 1.0


class TestNoForbiddenImports:
    def test_no_forbidden_imports(self):
        source = inspect.getsource(backend)
        forbidden = ["subprocess", "socket", "selenium", "playwright"]
        for name in forbidden:
            assert f"import {name}" not in source
