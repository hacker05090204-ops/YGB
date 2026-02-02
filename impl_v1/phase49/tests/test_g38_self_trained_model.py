# Test G38 Self-Trained Model
"""
Comprehensive tests for G38 Large Self-Trained Intelligence Model.

Tests cover:
- OS detection
- Backend selection
- Idle detection logic
- Training trigger conditions
- GPU fallback behavior
- All 10 guard enforcement
- Deterministic inference
- Cross-platform parity
"""

import pytest
from unittest.mock import patch, MagicMock

from impl_v1.phase49.governors.g38_self_trained_model import (
    # OS Detection
    OperatingSystem,
    detect_os,
    # Idle State
    IdleState,
    IdleConditions,
    IdleCheckResult,
    IDLE_THRESHOLD_SECONDS,
    check_idle_conditions,
    # GPU Backends
    GPUBackendInterface,
    LinuxGPUBackend,
    WindowsGPUBackend,
    UnsupportedOSError,
    get_gpu_backend,
    # Model Architecture
    ModelArchitecture,
    MultiHeadOutput,
    TrainingDataSourceEnum,
    TrainingSample,
    LocalModelStatus,
    create_model_architecture,
    run_inference,
    # Training Trigger
    TrainingTrigger,
    evaluate_training_trigger,
    # AUTO-MODE
    AutoModeDecision,
    PRECISION_THRESHOLD,
    make_auto_mode_decision,
    # Guards
    can_ai_execute,
    can_ai_submit,
    can_ai_override_governance,
    can_ai_verify_bug,
    can_ai_expand_scope,
    can_ai_train_while_active,
    can_ai_use_network,
    can_ai_leak_data,
    can_ai_enable_failover_without_error,
    can_ai_hide_external_usage,
    ALL_GUARDS,
    verify_all_guards,
)


# =============================================================================
# OS DETECTION TESTS
# =============================================================================

class TestOSDetection:
    """Tests for OS detection."""
    
    def test_operating_system_enum_has_linux(self):
        assert OperatingSystem.LINUX.value == "linux"
    
    def test_operating_system_enum_has_windows(self):
        assert OperatingSystem.WINDOWS.value == "windows"
    
    def test_operating_system_enum_has_unsupported(self):
        assert OperatingSystem.UNSUPPORTED.value == "unsupported"
    
    def test_detect_os_returns_operating_system(self):
        result = detect_os()
        assert isinstance(result, OperatingSystem)
    
    @patch("platform.system")
    def test_detect_os_linux(self, mock_system):
        mock_system.return_value = "Linux"
        assert detect_os() == OperatingSystem.LINUX
    
    @patch("platform.system")
    def test_detect_os_windows(self, mock_system):
        mock_system.return_value = "Windows"
        assert detect_os() == OperatingSystem.WINDOWS
    
    @patch("platform.system")
    def test_detect_os_unsupported(self, mock_system):
        mock_system.return_value = "FreeBSD"
        assert detect_os() == OperatingSystem.UNSUPPORTED


# =============================================================================
# BACKEND SELECTION TESTS
# =============================================================================

class TestBackendSelection:
    """Tests for GPU backend selection."""
    
    def test_linux_backend_is_gpu_backend_interface(self):
        backend = LinuxGPUBackend()
        assert isinstance(backend, GPUBackendInterface)
    
    def test_windows_backend_is_gpu_backend_interface(self):
        backend = WindowsGPUBackend()
        assert isinstance(backend, GPUBackendInterface)
    
    def test_linux_backend_has_detect_gpu(self):
        backend = LinuxGPUBackend()
        assert hasattr(backend, "detect_gpu")
    
    def test_linux_backend_has_check_idle(self):
        backend = LinuxGPUBackend()
        assert hasattr(backend, "check_idle")
    
    def test_linux_backend_has_check_power(self):
        backend = LinuxGPUBackend()
        assert hasattr(backend, "check_power")
    
    def test_linux_backend_has_get_memory_mb(self):
        backend = LinuxGPUBackend()
        assert hasattr(backend, "get_memory_mb")
    
    def test_windows_backend_has_detect_gpu(self):
        backend = WindowsGPUBackend()
        assert hasattr(backend, "detect_gpu")
    
    def test_windows_backend_has_check_idle(self):
        backend = WindowsGPUBackend()
        assert hasattr(backend, "check_idle")
    
    def test_windows_backend_has_check_power(self):
        backend = WindowsGPUBackend()
        assert hasattr(backend, "check_power")
    
    def test_windows_backend_has_get_memory_mb(self):
        backend = WindowsGPUBackend()
        assert hasattr(backend, "get_memory_mb")
    
    @patch("impl_v1.phase49.governors.g38_self_trained_model.detect_os")
    def test_get_gpu_backend_linux(self, mock_detect):
        mock_detect.return_value = OperatingSystem.LINUX
        backend = get_gpu_backend()
        assert isinstance(backend, LinuxGPUBackend)
    
    @patch("impl_v1.phase49.governors.g38_self_trained_model.detect_os")
    def test_get_gpu_backend_windows(self, mock_detect):
        mock_detect.return_value = OperatingSystem.WINDOWS
        backend = get_gpu_backend()
        assert isinstance(backend, WindowsGPUBackend)
    
    @patch("impl_v1.phase49.governors.g38_self_trained_model.detect_os")
    def test_get_gpu_backend_unsupported_raises(self, mock_detect):
        mock_detect.return_value = OperatingSystem.UNSUPPORTED
        with pytest.raises(UnsupportedOSError):
            get_gpu_backend()


# =============================================================================
# IDLE DETECTION TESTS
# =============================================================================

class TestIdleDetection:
    """Tests for idle detection logic."""
    
    def test_idle_state_enum_has_active(self):
        assert IdleState.ACTIVE.value == "ACTIVE"
    
    def test_idle_state_enum_has_idle(self):
        assert IdleState.IDLE.value == "IDLE"
    
    def test_idle_state_enum_has_training_ready(self):
        assert IdleState.TRAINING_READY.value == "TRAINING_READY"
    
    def test_idle_threshold_is_60_seconds(self):
        assert IDLE_THRESHOLD_SECONDS == 60
    
    def test_check_idle_active_scan_blocks(self):
        conditions = IdleConditions(
            no_active_scan=False,
            no_human_interaction=True,
            power_connected=True,
            gpu_available=True,
            idle_seconds=120,
        )
        result = check_idle_conditions(conditions)
        assert result.can_train is False
        assert result.state == IdleState.ACTIVE
        assert "scan" in result.reason.lower()
    
    def test_check_idle_human_interaction_blocks(self):
        conditions = IdleConditions(
            no_active_scan=True,
            no_human_interaction=False,
            power_connected=True,
            gpu_available=True,
            idle_seconds=120,
        )
        result = check_idle_conditions(conditions)
        assert result.can_train is False
        assert result.state == IdleState.ACTIVE
    
    def test_check_idle_no_power_blocks(self):
        conditions = IdleConditions(
            no_active_scan=True,
            no_human_interaction=True,
            power_connected=False,
            gpu_available=True,
            idle_seconds=120,
        )
        result = check_idle_conditions(conditions)
        assert result.can_train is False
        assert "power" in result.reason.lower()
    
    def test_check_idle_below_threshold_blocks(self):
        conditions = IdleConditions(
            no_active_scan=True,
            no_human_interaction=True,
            power_connected=True,
            gpu_available=True,
            idle_seconds=30,  # Below 60s threshold
        )
        result = check_idle_conditions(conditions)
        assert result.can_train is False
        assert "60" in result.reason
    
    def test_check_idle_all_conditions_met_gpu_available(self):
        conditions = IdleConditions(
            no_active_scan=True,
            no_human_interaction=True,
            power_connected=True,
            gpu_available=True,
            idle_seconds=120,
        )
        result = check_idle_conditions(conditions)
        assert result.can_train is True
        assert result.state == IdleState.TRAINING_READY
        assert "GPU" in result.reason
    
    def test_check_idle_cpu_fallback_allowed(self):
        conditions = IdleConditions(
            no_active_scan=True,
            no_human_interaction=True,
            power_connected=True,
            gpu_available=False,
            idle_seconds=120,
        )
        result = check_idle_conditions(conditions)
        assert result.can_train is True
        assert result.state == IdleState.TRAINING_READY
        assert "CPU fallback" in result.reason


# =============================================================================
# TRAINING TRIGGER TESTS
# =============================================================================

class TestTrainingTrigger:
    """Tests for training trigger logic."""
    
    def test_training_trigger_blocked_by_idle(self):
        conditions = IdleConditions(
            no_active_scan=False,
            no_human_interaction=True,
            power_connected=True,
            gpu_available=True,
            idle_seconds=120,
        )
        idle_check = check_idle_conditions(conditions)
        trigger = evaluate_training_trigger(idle_check, None, 100)
        assert trigger.should_train is False
    
    def test_training_trigger_blocked_no_samples(self):
        conditions = IdleConditions(
            no_active_scan=True,
            no_human_interaction=True,
            power_connected=True,
            gpu_available=True,
            idle_seconds=120,
        )
        idle_check = check_idle_conditions(conditions)
        trigger = evaluate_training_trigger(idle_check, None, 0)
        assert trigger.should_train is False
        assert "sample" in trigger.reason.lower()
    
    def test_training_trigger_ready(self):
        conditions = IdleConditions(
            no_active_scan=True,
            no_human_interaction=True,
            power_connected=True,
            gpu_available=True,
            idle_seconds=120,
        )
        idle_check = check_idle_conditions(conditions)
        trigger = evaluate_training_trigger(idle_check, None, 100)
        assert trigger.should_train is True


# =============================================================================
# MODEL ARCHITECTURE TESTS
# =============================================================================

class TestModelArchitecture:
    """Tests for model architecture."""
    
    def test_create_model_architecture(self):
        arch = create_model_architecture()
        assert isinstance(arch, ModelArchitecture)
        assert arch.input_dim == 512
        assert arch.encoder_heads == 8
        assert arch.output_heads == 4
    
    def test_create_model_with_custom_params(self):
        arch = create_model_architecture(
            input_dim=256,
            hidden_dims=(512, 256),
            seed=123,
        )
        assert arch.input_dim == 256
        assert arch.hidden_dims == (512, 256)
        assert arch.seed == 123


# =============================================================================
# INFERENCE TESTS
# =============================================================================

class TestInference:
    """Tests for model inference."""
    
    def test_run_inference_returns_multi_head_output(self):
        model_status = LocalModelStatus(
            status_id="TST-001",
            checkpoint_path="/tmp/model.pt",
            epoch=10,
            train_accuracy=0.95,
            val_accuracy=0.93,
            is_valid=True,
            integrity_hash="abc123",
            created_at="2026-01-01T00:00:00Z",
            last_trained_at="2026-01-01T00:00:00Z",
        )
        features = tuple([0.1] * 100)
        result = run_inference(features, model_status)
        assert isinstance(result, MultiHeadOutput)
    
    def test_inference_has_all_outputs(self):
        model_status = LocalModelStatus(
            status_id="TST-001",
            checkpoint_path="/tmp/model.pt",
            epoch=10,
            train_accuracy=0.95,
            val_accuracy=0.93,
            is_valid=True,
            integrity_hash="abc123",
            created_at="2026-01-01T00:00:00Z",
            last_trained_at="2026-01-01T00:00:00Z",
        )
        features = tuple([0.1] * 100)
        result = run_inference(features, model_status)
        assert hasattr(result, "real_probability")
        assert hasattr(result, "duplicate_probability")
        assert hasattr(result, "noise_probability")
        assert hasattr(result, "report_style_id")
    
    def test_inference_is_deterministic(self):
        model_status = LocalModelStatus(
            status_id="TST-001",
            checkpoint_path="/tmp/model.pt",
            epoch=10,
            train_accuracy=0.95,
            val_accuracy=0.93,
            is_valid=True,
            integrity_hash="abc123",
            created_at="2026-01-01T00:00:00Z",
            last_trained_at="2026-01-01T00:00:00Z",
        )
        features = tuple([0.5] * 100)
        result1 = run_inference(features, model_status)
        result2 = run_inference(features, model_status)
        assert result1.real_probability == result2.real_probability
        assert result1.duplicate_probability == result2.duplicate_probability
        assert result1.noise_probability == result2.noise_probability
        assert result1.report_style_id == result2.report_style_id


# =============================================================================
# AUTO-MODE TESTS
# =============================================================================

class TestAutoMode:
    """Tests for AUTO-MODE integration."""
    
    def test_precision_threshold_is_97_percent(self):
        assert PRECISION_THRESHOLD == 0.97
    
    def test_auto_mode_decision_requires_proof(self):
        inference = MultiHeadOutput(
            result_id="INF-001",
            real_probability=0.98,
            duplicate_probability=0.01,
            noise_probability=0.01,
            report_style_id=1,
            confidence=0.98,
            inference_time_ms=0.5,
        )
        decision = make_auto_mode_decision("CAND-001", inference)
        assert decision.requires_proof is True
    
    def test_auto_mode_high_real_recommends_verify(self):
        inference = MultiHeadOutput(
            result_id="INF-001",
            real_probability=0.98,
            duplicate_probability=0.01,
            noise_probability=0.01,
            report_style_id=1,
            confidence=0.98,
            inference_time_ms=0.5,
        )
        decision = make_auto_mode_decision("CAND-001", inference)
        assert decision.recommended_action == "VERIFY"
    
    def test_auto_mode_high_duplicate_recommends_duplicate(self):
        inference = MultiHeadOutput(
            result_id="INF-001",
            real_probability=0.1,
            duplicate_probability=0.85,
            noise_probability=0.05,
            report_style_id=1,
            confidence=0.85,
            inference_time_ms=0.5,
        )
        decision = make_auto_mode_decision("CAND-001", inference)
        assert decision.recommended_action == "DUPLICATE"
    
    def test_auto_mode_high_noise_recommends_discard(self):
        inference = MultiHeadOutput(
            result_id="INF-001",
            real_probability=0.05,
            duplicate_probability=0.04,
            noise_probability=0.91,
            report_style_id=1,
            confidence=0.91,
            inference_time_ms=0.5,
        )
        decision = make_auto_mode_decision("CAND-001", inference)
        assert decision.recommended_action == "DISCARD"


# =============================================================================
# GUARD TESTS (CRITICAL)
# =============================================================================

class TestGuardsReturnFalse:
    """Tests that ALL guards return (False, ...)."""
    
    def test_can_ai_execute_returns_false(self):
        result, msg = can_ai_execute()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_submit_returns_false(self):
        result, msg = can_ai_submit()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_override_governance_returns_false(self):
        result, msg = can_ai_override_governance()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_verify_bug_returns_false(self):
        result, msg = can_ai_verify_bug()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_expand_scope_returns_false(self):
        result, msg = can_ai_expand_scope()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_train_while_active_returns_false(self):
        result, msg = can_ai_train_while_active()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_use_network_returns_false(self):
        result, msg = can_ai_use_network()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_leak_data_returns_false(self):
        result, msg = can_ai_leak_data()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_enable_failover_without_error_returns_false(self):
        result, msg = can_ai_enable_failover_without_error()
        assert result is False
        assert isinstance(msg, str)
    
    def test_can_ai_hide_external_usage_returns_false(self):
        result, msg = can_ai_hide_external_usage()
        assert result is False
        assert isinstance(msg, str)


class TestAllGuardsCollection:
    """Tests for ALL_GUARDS collection."""
    
    def test_all_guards_has_10_guards(self):
        assert len(ALL_GUARDS) == 10
    
    def test_all_guards_are_callable(self):
        for guard in ALL_GUARDS:
            assert callable(guard)
    
    def test_verify_all_guards_passes(self):
        result, msg = verify_all_guards()
        assert result is True
        assert "verified" in msg.lower()


# =============================================================================
# CROSS-PLATFORM PARITY TESTS
# =============================================================================

class TestCrossPlatformParity:
    """Tests for cross-platform behavior parity."""
    
    def test_linux_backend_interface_matches_windows(self):
        linux = LinuxGPUBackend()
        windows = WindowsGPUBackend()
        
        linux_methods = set(dir(linux)) - set(dir(object))
        windows_methods = set(dir(windows)) - set(dir(object))
        
        # Both should have same public methods
        linux_public = {m for m in linux_methods if not m.startswith("_")}
        windows_public = {m for m in windows_methods if not m.startswith("_")}
        
        assert linux_public == windows_public
    
    def test_backend_detect_gpu_returns_tuple(self):
        linux = LinuxGPUBackend()
        windows = WindowsGPUBackend()
        
        linux_result = linux.detect_gpu()
        windows_result = windows.detect_gpu()
        
        assert isinstance(linux_result, tuple)
        assert isinstance(windows_result, tuple)
        assert len(linux_result) == 2
        assert len(windows_result) == 2
    
    def test_backend_check_idle_returns_int(self):
        linux = LinuxGPUBackend()
        windows = WindowsGPUBackend()
        
        assert isinstance(linux.check_idle(), int)
        assert isinstance(windows.check_idle(), int)
    
    def test_backend_check_power_returns_bool(self):
        linux = LinuxGPUBackend()
        windows = WindowsGPUBackend()
        
        assert isinstance(linux.check_power(), bool)
        assert isinstance(windows.check_power(), bool)
    
    def test_backend_get_memory_mb_returns_int(self):
        linux = LinuxGPUBackend()
        windows = WindowsGPUBackend()
        
        assert isinstance(linux.get_memory_mb(), int)
        assert isinstance(windows.get_memory_mb(), int)


# =============================================================================
# DATA SOURCE TESTS
# =============================================================================

class TestTrainingDataSources:
    """Tests for training data sources."""
    
    def test_has_g33_verified_real(self):
        assert TrainingDataSourceEnum.G33_VERIFIED_REAL.value == "G33_VERIFIED_REAL"
    
    def test_has_g36_auto_verified(self):
        assert TrainingDataSourceEnum.G36_AUTO_VERIFIED.value == "G36_AUTO_VERIFIED"
    
    def test_has_rejected_findings(self):
        assert TrainingDataSourceEnum.REJECTED_FINDINGS.value == "REJECTED_FINDINGS"
    
    def test_has_duplicate_clusters(self):
        assert TrainingDataSourceEnum.DUPLICATE_CLUSTERS.value == "DUPLICATE_CLUSTERS"
    
    def test_has_human_corrections(self):
        assert TrainingDataSourceEnum.HUMAN_CORRECTIONS.value == "HUMAN_CORRECTIONS"
    
    def test_has_accepted_reports(self):
        assert TrainingDataSourceEnum.ACCEPTED_REPORTS.value == "ACCEPTED_REPORTS"


# =============================================================================
# EXTERNAL AI USAGE DETECTION TESTS
# =============================================================================

class TestExternalAIDetection:
    """Tests for external AI usage detection."""
    
    def test_no_huggingface_import(self):
        import impl_v1.phase49.governors.g38_self_trained_model as module
        source = open(module.__file__).read()
        assert "hugging" not in source.lower()
        assert "transformers" not in source.lower()
    
    def test_no_openai_import(self):
        import impl_v1.phase49.governors.g38_self_trained_model as module
        source = open(module.__file__).read()
        assert "openai" not in source.lower()
    
    def test_no_anthropic_import(self):
        import impl_v1.phase49.governors.g38_self_trained_model as module
        source = open(module.__file__).read()
        assert "anthropic" not in source.lower()
