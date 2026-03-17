"""
Test No Mock In Training Pipeline
====================================

Source-level and runtime inspection tests that ensure NO mock, synthetic,
or simulated code remains in any training-related file.

This test scans:
- g38_self_trained_model.py  (GPU backends)
- g37_gpu_training_backend.py (training adapter)
- g37_pytorch_backend.py (real PyTorch backend)
- g35_ai_accelerator.py (simulate_gpu_training blocked)
- gpu_thermal_monitor.py (no fake temperatures)
- representation_integrity.py (no fake layer profiles)
- auto_trainer.py (_init_gpu_resources, _gpu_train_step, _train_representation_only)
"""

import inspect
import os
import re
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


# =============================================================================
# G38 SELF-TRAINED MODEL — NO MOCK BACKENDS
# =============================================================================

class TestG38BackendsNoMock:
    """Ensure LinuxGPUBackend and WindowsGPUBackend have real OS calls."""

    def test_linux_check_idle_no_hardcoded_return(self):
        """LinuxGPUBackend.check_idle() must NOT return a hardcoded constant."""
        from impl_v1.phase49.governors.g38_self_trained_model import LinuxGPUBackend
        source = inspect.getsource(LinuxGPUBackend.check_idle)
        # Must not have hardcoded "return 120" or similar mock patterns
        assert "return 120" not in source, \
            "LinuxGPUBackend.check_idle() still returns hardcoded 120"
        assert "Mock" not in source and "mock" not in source, \
            "LinuxGPUBackend.check_idle() still contains mock references"

    def test_linux_check_idle_uses_real_detection(self):
        """LinuxGPUBackend.check_idle() must use real OS idle detection."""
        from impl_v1.phase49.governors.g38_self_trained_model import LinuxGPUBackend
        source = inspect.getsource(LinuxGPUBackend.check_idle)
        # Must contain real detection mechanisms
        has_xprintidle = "xprintidle" in source
        has_dev_input = "/dev/input" in source
        has_loginctl = "loginctl" in source
        assert any([has_xprintidle, has_dev_input, has_loginctl]), \
            "LinuxGPUBackend.check_idle() must use xprintidle, /dev/input, or loginctl"

    def test_linux_check_power_no_hardcoded_return(self):
        """LinuxGPUBackend.check_power() must NOT be a simple 'return True'."""
        from impl_v1.phase49.governors.g38_self_trained_model import LinuxGPUBackend
        source = inspect.getsource(LinuxGPUBackend.check_power)
        # Must not be just a mock
        assert "Mock" not in source and "mock" not in source, \
            "LinuxGPUBackend.check_power() still contains mock references"
        # Must call into the real power_supply filesystem
        assert "power_supply" in source, \
            "LinuxGPUBackend.check_power() must read /sys/class/power_supply"

    def test_windows_check_idle_no_hardcoded_return(self):
        """WindowsGPUBackend.check_idle() must NOT return a hardcoded constant."""
        from impl_v1.phase49.governors.g38_self_trained_model import WindowsGPUBackend
        source = inspect.getsource(WindowsGPUBackend.check_idle)
        assert "return 120" not in source, \
            "WindowsGPUBackend.check_idle() still returns hardcoded 120"
        assert "Mock" not in source and "mock" not in source, \
            "WindowsGPUBackend.check_idle() still contains mock references"

    def test_windows_check_idle_uses_real_detection(self):
        """WindowsGPUBackend.check_idle() must use real Win32 API."""
        from impl_v1.phase49.governors.g38_self_trained_model import WindowsGPUBackend
        source = inspect.getsource(WindowsGPUBackend.check_idle)
        assert "GetLastInputInfo" in source, \
            "WindowsGPUBackend.check_idle() must use GetLastInputInfo"

    def test_windows_check_power_no_mock(self):
        """WindowsGPUBackend.check_power() must NOT be a simple mock."""
        from impl_v1.phase49.governors.g38_self_trained_model import WindowsGPUBackend
        source = inspect.getsource(WindowsGPUBackend.check_power)
        assert "Mock" not in source and "mock" not in source, \
            "WindowsGPUBackend.check_power() still contains mock references"
        assert "GetSystemPowerStatus" in source, \
            "WindowsGPUBackend.check_power() must use GetSystemPowerStatus"

    def test_backends_return_correct_types(self):
        """Both backends must return correct types from real calls."""
        from impl_v1.phase49.governors.g38_self_trained_model import (
            LinuxGPUBackend, WindowsGPUBackend,
        )
        linux = LinuxGPUBackend()
        windows = WindowsGPUBackend()
        assert isinstance(linux.check_idle(), int)
        assert isinstance(linux.check_power(), bool)
        assert isinstance(windows.check_idle(), int)
        assert isinstance(windows.check_power(), bool)

    def test_no_mock_keyword_in_g38_backends(self):
        """Entire g38 file must have no mock references in backend methods."""
        from impl_v1.phase49.governors import g38_self_trained_model as mod
        backend_methods = [
            "LinuxGPUBackend.check_idle",
            "LinuxGPUBackend.check_power",
            "WindowsGPUBackend.check_idle",
            "WindowsGPUBackend.check_power",
        ]
        for method_name in backend_methods:
            cls_name, func_name = method_name.split(".")
            cls = getattr(mod, cls_name)
            func = getattr(cls, func_name)
            source = inspect.getsource(func).lower()
            assert "mock" not in source, \
                f"{method_name} still contains 'mock' reference"


# =============================================================================
# G37 GPU TRAINING BACKEND — NO MOCK
# =============================================================================

class TestG37GpuBackendNoMock:
    """Ensure g37_gpu_training_backend.py has no mock training or detection."""

    def test_no_mock_keyword_in_module(self):
        """g37_gpu_training_backend.py must not contain 'mock' in any function."""
        import impl_v1.phase49.governors.g37_gpu_training_backend as mod
        source = open(mod.__file__, encoding="utf-8").read().lower()
        # Allow "mock" only in comments about what was removed
        lines_with_mock = [
            line.strip() for line in source.split("\n")
            if "mock" in line
            and not line.strip().startswith("#")
            and not line.strip().startswith('"""')
            and not line.strip().startswith("'''")
        ]
        assert len(lines_with_mock) == 0, \
            f"Found 'mock' in executable code: {lines_with_mock}"

    def test_detect_gpu_devices_uses_real_pytorch(self):
        """detect_gpu_devices() must use real PyTorch detection, not mock."""
        from impl_v1.phase49.governors.g37_gpu_training_backend import detect_gpu_devices
        source = inspect.getsource(detect_gpu_devices)
        assert "mock" not in source.lower(), \
            "detect_gpu_devices() contains mock reference"
        # Must reference real PyTorch device APIs
        assert "_pt_backend" in source or "torch" in source, \
            "detect_gpu_devices() must use PyTorch for device detection"

    def test_gpu_train_epoch_requires_pytorch(self):
        """gpu_train_epoch() must use real PyTorch training."""
        from impl_v1.phase49.governors.g37_gpu_training_backend import gpu_train_epoch
        source = inspect.getsource(gpu_train_epoch)
        assert "mock" not in source.lower()
        assert "_pt_backend" in source or "train_single_epoch" in source

    def test_gpu_train_full_requires_pytorch(self):
        """gpu_train_full() must use real PyTorch training."""
        from impl_v1.phase49.governors.g37_gpu_training_backend import gpu_train_full
        source = inspect.getsource(gpu_train_full)
        assert "mock" not in source.lower()

    def test_extract_bug_features_is_deterministic(self):
        """extract_bug_features() must be deterministic, not random mock."""
        from impl_v1.phase49.governors.g37_gpu_training_backend import extract_bug_features
        source = inspect.getsource(extract_bug_features)
        assert "mock" not in source.lower()
        assert "random" not in source.lower()
        # Must be deterministic — same input = same output
        v1 = extract_bug_features("test", "XSS", "/api", True, 3)
        v2 = extract_bug_features("test", "XSS", "/api", True, 3)
        assert v1.values == v2.values
        assert v1.data_hash == v2.data_hash


# =============================================================================
# G37 PYTORCH BACKEND — FAILS CLOSED WITHOUT PYTORCH
# =============================================================================

class TestG37PytorchBackendNoFallback:
    """Ensure g37_pytorch_backend.py fails closed, no mock fallback."""

    def test_train_single_epoch_requires_pytorch(self):
        """train_single_epoch must require PyTorch — no mock fallback."""
        from impl_v1.phase49.governors.g37_pytorch_backend import train_single_epoch
        source = inspect.getsource(train_single_epoch)
        assert "_require_pytorch_runtime" in source, \
            "train_single_epoch must call _require_pytorch_runtime"
        assert "mock" not in source.lower()

    def test_train_full_requires_pytorch(self):
        """train_full must require PyTorch — no mock fallback."""
        from impl_v1.phase49.governors.g37_pytorch_backend import train_full
        source = inspect.getsource(train_full)
        assert "_require_pytorch_runtime" in source
        assert "mock" not in source.lower()

    def test_infer_single_requires_pytorch(self):
        """infer_single must require PyTorch — no mock fallback."""
        from impl_v1.phase49.governors.g37_pytorch_backend import infer_single
        source = inspect.getsource(infer_single)
        assert "_require_pytorch_runtime" in source
        assert "mock" not in source.lower()

    def test_no_formula_based_metrics(self):
        """No formula-based fake metrics anywhere in the module."""
        import impl_v1.phase49.governors.g37_pytorch_backend as mod
        source = open(mod.__file__, encoding="utf-8").read().lower()
        # Check for formula-based patterns typical of mock metrics
        assert "0.95 -" not in source  # e.g., accuracy = 0.95 - epoch * 0.01
        assert "is_mock" not in source


# =============================================================================
# G35 AI ACCELERATOR — simulate_gpu_training BLOCKED
# =============================================================================

class TestG35SimulateBlocked:
    """Ensure simulate_gpu_training raises RuntimeError."""

    def test_simulate_gpu_training_raises_runtime_error(self):
        """simulate_gpu_training() must raise RuntimeError."""
        from impl_v1.phase49.governors.g35_ai_accelerator import (
            simulate_gpu_training,
            prepare_training_batch,
            _create_training_config,
            TrainingMode,
        )
        batch = prepare_training_batch(
            verified_bugs=(("id1", "hash1", "REAL"),),
            rejected_findings=(("id2", "hash2"),),
        )
        config = _create_training_config()
        with pytest.raises(RuntimeError, match="BLOCKED"):
            simulate_gpu_training(batch, config, TrainingMode.IDLE)

    def test_simulate_function_source_is_blocked(self):
        """simulate_gpu_training source must contain BLOCKED/retired."""
        from impl_v1.phase49.governors.g35_ai_accelerator import simulate_gpu_training
        source = inspect.getsource(simulate_gpu_training)
        assert "BLOCKED" in source or "retired" in source.lower()
        assert "is_mock" not in source


# =============================================================================
# GPU THERMAL MONITOR — NO FAKE TEMPERATURES
# =============================================================================

class TestThermalMonitorNoFake:
    """Ensure GPU thermal monitor returns real data only."""

    def test_no_fake_temperature_value(self):
        """No hardcoded fake temperature like 65°C."""
        import impl_v1.training.monitoring.gpu_thermal_monitor as mod
        source = open(mod.__file__, encoding="utf-8").read()
        # Should not have "default mock value" or hardcoded 65.0
        assert "Default mock value" not in source
        assert "mock_status" not in source
        assert "_mock_status" not in source

    def test_unavailable_returns_zero_not_fake(self):
        """When GPU is unavailable, return 0 values, not fake data."""
        from impl_v1.training.monitoring.gpu_thermal_monitor import (
            GPUThermalMonitor, ThermalState,
        )
        monitor = GPUThermalMonitor()
        status = monitor._unavailable_status(0)
        # Must be zero, not fake 65°C
        assert status.temperature_c == 0.0
        assert status.vram_used_mb == 0.0
        assert status.vram_total_mb == 0.0
        assert status.state == ThermalState.NORMAL


# =============================================================================
# REPRESENTATION INTEGRITY — NO FAKE PROFILES
# =============================================================================

class TestRepresentationIntegrityNoFake:
    """Ensure representation integrity has no fake layer profiles."""

    def test_no_mock_profile_function(self):
        """Must not have _mock_profile function."""
        import impl_v1.training.safety.representation_integrity as mod
        source = open(mod.__file__, encoding="utf-8").read()
        assert "_mock_profile" not in source

    def test_unavailable_profile_is_empty_not_fake(self):
        """When torch unavailable, profile has empty layers, not fake ones."""
        from impl_v1.training.safety.representation_integrity import (
            RepresentationIntegrityMonitor,
        )
        monitor = RepresentationIntegrityMonitor()
        profile = monitor._unavailable_profile("test-ckpt")
        assert len(profile.layer_profiles) == 0, \
            "Unavailable profile must have empty layers, not fake ones"
        assert profile.is_suspicious is True
        assert "unavailable" in profile.suspicious_reason


# =============================================================================
# AUTO TRAINER — TRAINING PATHS USE REAL DATA ONLY
# =============================================================================

class TestAutoTrainerNoSyntheticTraining:
    """Ensure auto_trainer training methods use real data only."""

    def test_gpu_train_step_no_synthetic(self):
        """_gpu_train_step must NOT generate synthetic training samples."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        source = inspect.getsource(AutoTrainer._gpu_train_step)
        assert "synthetic" not in source.lower(), \
            "_gpu_train_step contains synthetic data reference"
        assert "source=\"synthetic" not in source.lower()

    def test_gpu_train_step_uses_dataloader(self):
        """_gpu_train_step must iterate over the real DataLoader."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        source = inspect.getsource(AutoTrainer._gpu_train_step)
        assert "_gpu_dataloader" in source, \
            "_gpu_train_step must use the real DataLoader"

    def test_train_representation_only_no_synthetic(self):
        """_train_representation_only must NOT generate synthetic data."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        source = inspect.getsource(AutoTrainer._train_representation_only)
        assert "synthetic" not in source.lower()
        assert "source=\"synthetic" not in source.lower()

    def test_init_gpu_resources_uses_real_dataset(self):
        """_init_gpu_resources must use real_dataset_loader, not synthetic."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        assert "real_dataset_loader" in source
        assert "validate_dataset_integrity" in source
        # DataLoader creation is in _build_training_dataloaders (which
        # imports create_training_dataloader from real_dataset_loader)
        assert "_build_training_dataloaders" in source

    def test_no_mock_in_init_gpu_resources(self):
        """No mock references in _init_gpu_resources."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        source = inspect.getsource(AutoTrainer._init_gpu_resources).lower()
        assert "mock" not in source

    def test_force_start_training_no_synthetic(self):
        """force_start_training must not use synthetic data."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        source = inspect.getsource(AutoTrainer.force_start_training)
        assert "synthetic" not in source.lower()
        assert "mock" not in source.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
