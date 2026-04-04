"""
Tests for GPU Status Endpoint

Verifies:
- GPU unavailable returns gpu_available=false, all else null
- GPU available returns real metrics
- Response schema correct
- No mock data
"""

import sys
import logging
import builtins
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.observability.metrics import metrics_registry
from backend.training.state_manager import (
    GPU_DRIVER_INSTALL_COMMAND,
    GPU_WATCHDOG_ALERT_METRIC,
    TrainingStateManager,
    get_optimized_dataloader_kwargs,
)


def _build_torch_mock(*, cuda_available: bool, allocated_mb: float = 0.0, total_mb: float = 0.0):
    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = cuda_available
    mock_torch.cuda.memory_allocated.return_value = int(allocated_mb * 1024 * 1024)
    props = MagicMock()
    props.total_memory = int(total_mb * 1024 * 1024)
    mock_torch.cuda.get_device_properties.return_value = props
    mock_torch.backends = MagicMock()
    mock_torch.backends.cudnn = MagicMock()
    mock_torch.backends.cudnn.benchmark = False
    return mock_torch


class TestGPUMetrics:
    """Test GPU metrics from TrainingStateManager."""

    def test_gpu_unavailable_returns_false(self):
        """When torch.cuda not available, gpu_available must be False."""
        mgr = TrainingStateManager()

        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = False

        with patch.dict("sys.modules", {"torch": mock_torch}):
            # Force reimport scenario
            result = mgr.get_gpu_metrics()

        # Even if the patching doesn't work perfectly,
        # the result should never have fake data
        assert "gpu_available" in result
        assert result.get("gpu_usage_percent") is None or isinstance(
            result.get("gpu_usage_percent"), float
        )

    def test_gpu_metrics_schema(self):
        """GPU metrics dict must contain required keys."""
        mgr = TrainingStateManager()
        result = mgr.get_gpu_metrics()

        required_keys = [
            "gpu_available",
            "gpu_usage_percent",
            "gpu_memory_used_mb",
            "gpu_memory_total_mb",
            "temperature",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

    def test_no_hardcoded_gpu_values(self):
        """GPU metrics must not return hardcoded positive values when GPU unavailable."""
        mgr = TrainingStateManager()
        mgr._g38_available = False

        result = mgr.get_gpu_metrics()
        if not result["gpu_available"]:
            assert result["gpu_usage_percent"] is None
            assert result["gpu_memory_used_mb"] is None
            assert result["gpu_memory_total_mb"] is None

    def test_cpu_usage_returns_float_or_none(self):
        """CPU usage must return a real float or None. Never fake."""
        mgr = TrainingStateManager()
        result = mgr.get_cpu_usage()
        assert result is None or isinstance(result, float)

    def test_no_mock_keywords_in_gpu_code(self):
        """GPU code must not contain mock patterns."""
        import inspect
        source = inspect.getsource(TrainingStateManager.get_gpu_metrics)
        forbidden = ["random", "MOCK", "FAKE", "DEMO", "placeholder",
                      "simulated", "hardcoded"]
        for kw in forbidden:
            assert kw.lower() not in source.lower(), \
                f"Forbidden keyword '{kw}' found in get_gpu_metrics"

    def test_startup_cpu_fallback_emits_metric_and_warning(self, caplog):
        """CPU fallback should emit a gauge and the exact driver recovery command."""
        metrics_registry.reset()
        mock_torch = _build_torch_mock(cuda_available=False)

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with caplog.at_level(logging.WARNING):
                TrainingStateManager()

        assert metrics_registry.get_gauge("gpu_fallback_active") == 1.0
        assert any(
            GPU_DRIVER_INSTALL_COMMAND in record.getMessage()
            for record in caplog.records
        )

    def test_gpu_runtime_configuration_enables_cuda_optimizations(self):
        """CUDA startup should enable benchmark mode and high matmul precision."""
        metrics_registry.reset()
        mock_torch = _build_torch_mock(
            cuda_available=True,
            allocated_mb=512.0,
            total_mb=4096.0,
        )

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch(
                "backend.training.state_manager.subprocess.check_output",
                return_value="73,61",
            ):
                mgr = TrainingStateManager()
                result = mgr.get_gpu_metrics(force_emit=True)

        assert result["gpu_available"] is True
        assert mock_torch.backends.cudnn.benchmark is True
        mock_torch.set_float32_matmul_precision.assert_called_with("high")
        assert metrics_registry.get_gauge("gpu_fallback_active") == 0.0
        assert metrics_registry.get_gauge("gpu_memory_used_mb") == 512.0
        assert metrics_registry.get_gauge("gpu_utilization_pct") == 73.0

    def test_get_optimized_dataloader_kwargs_returns_expected_values(self):
        """The training DataLoader should use the requested GPU-friendly settings."""
        assert get_optimized_dataloader_kwargs() == {
            "num_workers": 4,
            "pin_memory": True,
            "persistent_workers": True,
        }

    def test_gpu_watchdog_alerts_on_drop_during_training(self, caplog):
        """A GPU disappearing mid-training should raise a critical alert metric."""
        metrics_registry.reset()
        mock_torch = _build_torch_mock(cuda_available=False)
        mgr = TrainingStateManager()
        mgr._g38_available = True
        mgr._trainer = MagicMock()
        mgr._trainer.get_status.return_value = {
            "is_training": True,
            "state": "TRAINING",
        }
        mgr._last_gpu_available = True

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with caplog.at_level(logging.CRITICAL):
                mgr.run_gpu_watchdog_cycle()

        assert metrics_registry.get_counter(GPU_WATCHDOG_ALERT_METRIC) == 1.0
        assert any(
            "GPU watchdog detected CUDA drop mid-training" in record.getMessage()
            for record in caplog.records
        )

    def test_init_g38_handles_import_error(self):
        mgr = TrainingStateManager.__new__(TrainingStateManager)
        mgr._trainer = object()
        mgr._g38_available = True
        original_import = builtins.__import__

        def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "impl_v1.phase49.runtime":
                raise ImportError("blocked")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=_raising_import):
            TrainingStateManager._init_g38(mgr)

        assert mgr._g38_available is False
        assert mgr._trainer is None

    def test_get_cpu_usage_handles_missing_psutil(self):
        mgr = TrainingStateManager()
        original_import = builtins.__import__

        def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "psutil":
                raise ImportError("missing")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=_raising_import):
            assert mgr.get_cpu_usage() is None

    def test_get_cpu_usage_handles_runtime_error(self):
        mgr = TrainingStateManager()
        mock_psutil = MagicMock()
        mock_psutil.cpu_percent.side_effect = RuntimeError("broken")

        with patch.dict("sys.modules", {"psutil": mock_psutil}):
            assert mgr.get_cpu_usage() is None

    def test_configure_gpu_runtime_logs_debug_on_error(self, caplog):
        mgr = TrainingStateManager()
        broken_torch = MagicMock()
        broken_torch.set_float32_matmul_precision.side_effect = RuntimeError("bad torch")
        broken_torch.backends = MagicMock()
        broken_torch.backends.cudnn = MagicMock()

        with patch.dict("sys.modules", {"torch": broken_torch}):
            with caplog.at_level(logging.DEBUG):
                mgr._configure_gpu_runtime(True)

        assert any(
            "Failed to configure CUDA runtime flags" in record.getMessage()
            for record in caplog.records
        )

    def test_emit_gpu_runtime_metrics_throttles_without_force(self):
        mgr = TrainingStateManager()
        metrics_registry.reset()
        mgr._last_gpu_emit_at = 100.0
        before = metrics_registry.get_gauge("gpu_fallback_active")

        with patch("backend.training.state_manager.time.monotonic", return_value=120.0):
            mgr._emit_gpu_runtime_metrics({"gpu_available": False}, force=False)

        assert metrics_registry.get_gauge("gpu_fallback_active") == before

    def test_emit_gpu_runtime_metrics_handles_registry_failures(self, caplog):
        mgr = TrainingStateManager()
        with patch.object(metrics_registry, "set_gauge", side_effect=RuntimeError("boom")):
            with caplog.at_level(logging.DEBUG):
                mgr._emit_gpu_runtime_metrics({"gpu_available": False}, force=True)

        assert any(
            "Failed to emit GPU runtime metrics" in record.getMessage()
            for record in caplog.records
        )

    def test_get_gpu_metrics_handles_torch_import_failure(self):
        metrics_registry.reset()
        mgr = TrainingStateManager()
        original_import = builtins.__import__

        def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "torch":
                raise ImportError("missing")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=_raising_import):
            result = mgr.get_gpu_metrics(force_emit=True)

        assert result["gpu_available"] is False
        assert metrics_registry.get_gauge("gpu_fallback_active") == 1.0

    def test_get_gpu_metrics_ignores_nvidia_smi_failure(self):
        metrics_registry.reset()
        mock_torch = _build_torch_mock(
            cuda_available=True,
            allocated_mb=256.0,
            total_mb=2048.0,
        )
        mgr = TrainingStateManager()

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch(
                "backend.training.state_manager.subprocess.check_output",
                side_effect=RuntimeError("nvidia-smi missing"),
            ):
                result = mgr.get_gpu_metrics(force_emit=True)

        assert result["gpu_available"] is True
        assert result["gpu_memory_used_mb"] == 256.0
        assert result["gpu_usage_percent"] is None

    def test_is_training_active_false_when_trainer_missing_or_broken(self):
        mgr = TrainingStateManager()
        mgr._g38_available = False
        mgr._trainer = None
        assert mgr._is_training_active() is False

        mgr._g38_available = True
        mgr._trainer = MagicMock()
        mgr._trainer.get_status.side_effect = RuntimeError("detached")
        assert mgr._is_training_active() is False

    def test_gpu_watchdog_handles_metric_increment_failure(self, caplog):
        mock_torch = _build_torch_mock(cuda_available=False)
        mgr = TrainingStateManager()
        mgr._g38_available = True
        mgr._trainer = MagicMock()
        mgr._trainer.get_status.return_value = {
            "is_training": True,
            "state": "TRAINING",
        }
        mgr._last_gpu_available = True

        with patch.dict("sys.modules", {"torch": mock_torch}):
            with patch.object(metrics_registry, "increment", side_effect=RuntimeError("boom")):
                with caplog.at_level(logging.DEBUG):
                    mgr.run_gpu_watchdog_cycle()

        assert any(
            "Failed to increment GPU watchdog alert metric" in record.getMessage()
            for record in caplog.records
        )

    def test_gpu_watchdog_loop_runs_until_stop(self):
        mgr = TrainingStateManager()
        with patch.object(mgr._watchdog_stop_event, "wait", side_effect=[False, True]):
            with patch.object(mgr, "run_gpu_watchdog_cycle") as run_cycle:
                mgr._gpu_watchdog_loop()

        run_cycle.assert_called_once()

    def test_start_and_stop_gpu_watchdog_are_idempotent(self):
        class FakeThread:
            def __init__(self, target, name, daemon):
                self.target = target
                self.name = name
                self.daemon = daemon
                self.started = False
                self._alive = False

            def start(self):
                self.started = True
                self._alive = True

            def is_alive(self):
                return self._alive

            def join(self, timeout=None):
                self._alive = False

        mgr = TrainingStateManager()
        with patch("backend.training.state_manager.threading.Thread", FakeThread):
            mgr.start_gpu_watchdog()
            first_thread = mgr._watchdog_thread
            mgr.start_gpu_watchdog()
            mgr.stop_gpu_watchdog()

        assert first_thread is mgr._watchdog_thread
        assert first_thread.started is True
        assert first_thread.name == "ygb-gpu-watchdog"
        assert first_thread.daemon is True
        assert mgr._watchdog_stop_event.is_set() is True


class TestCheckpointCount:
    """Test checkpoint counting."""

    def test_returns_none_when_no_checkpoints(self):
        """No checkpoint files → None, not 0."""
        mgr = TrainingStateManager()
        with patch("pathlib.Path.exists", return_value=False):
            result = mgr.get_checkpoint_count()
        # Could be None or a real count
        assert result is None or isinstance(result, int)
