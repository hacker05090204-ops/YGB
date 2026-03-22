"""
Tests for Training Progress Endpoint

Verifies:
- Idle state returns status="idle" with null metrics (no fakes)
- Response schema is correct
- No hardcoded fallback values
- No mock data anywhere
"""

import sys
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.training.state_manager import (
    TrainingStateManager,
    TrainingMetrics,
    get_training_state_manager,
)
from backend.observability.metrics import (
    MetricsRegistry,
    get_measurement_completeness,
    get_null_metric_ratio,
    metrics_registry,
)


class TestTrainingMetrics:
    """Test TrainingMetrics dataclass."""

    def test_idle_metrics_have_null_values(self):
        """Idle state must NOT have any fake numeric values."""
        metrics = TrainingMetrics(status="idle")
        assert metrics.status == "idle"
        assert metrics.current_epoch is None
        assert metrics.total_epochs is None
        assert metrics.loss is None
        assert metrics.throughput is None
        assert metrics.gpu_usage_percent is None
        assert metrics.gpu_memory_used_mb is None
        assert metrics.cpu_usage_percent is None
        assert metrics.dataset_size is None

    def test_to_dict_returns_all_fields(self):
        """to_dict must include all fields."""
        metrics = TrainingMetrics(status="idle")
        d = metrics.to_dict()
        assert "status" in d
        assert "current_epoch" in d
        assert "loss" in d
        assert "throughput" in d
        assert "timestamp" in d

    def test_timestamp_auto_populated(self):
        """Timestamp must be auto-populated, not empty."""
        metrics = TrainingMetrics(status="idle")
        assert metrics.timestamp != ""
        assert "T" in metrics.timestamp  # ISO format


class TestTrainingStateManager:
    """Test TrainingStateManager with mocked G38."""

    def test_idle_when_g38_unavailable(self):
        """When G38 not loaded, status must be idle, not fake training."""
        mgr = TrainingStateManager()
        mgr._g38_available = False
        mgr._trainer = None

        result = mgr.get_training_progress()
        assert result.status == "idle"
        assert result.automode_status == "g38_unavailable"
        assert result.current_epoch is None
        assert result.loss is None

    def test_idle_when_trainer_not_training(self):
        """When trainer exists but is idle, all metrics must be null."""
        mgr = TrainingStateManager()
        mock_trainer = MagicMock()
        mock_trainer.get_status.return_value = {
            "is_training": False,
            "state": "IDLE",
            "epoch": 0,
            "total_epochs": 0,
            "total_completed": 0,
            "last_loss": 0,
            "last_accuracy": 0,
            "samples_per_sec": 0,
            "dataset_size": 0,
        }
        mgr._g38_available = True
        mgr._trainer = mock_trainer

        result = mgr.get_training_progress()
        assert result.status == "idle"
        # Zero values from trainer should become None (not fake zeros)
        assert result.loss is None
        assert result.throughput is None

    def test_training_active_returns_real_data(self):
        """When training is active, return real values from trainer."""
        mgr = TrainingStateManager()
        mock_trainer = MagicMock()
        mock_trainer.get_status.return_value = {
            "is_training": True,
            "state": "TRAINING",
            "epoch": 5,
            "total_epochs": 20,
            "total_completed": 4,
            "last_loss": 0.3421,
            "last_accuracy": 0.8765,
            "samples_per_sec": 128.5,
            "dataset_size": 5000,
            "training_mode": "MANUAL",
        }
        mgr._g38_available = True
        mgr._trainer = mock_trainer

        # Mock GPU/CPU to isolate
        with patch.object(mgr, "get_gpu_metrics", return_value={
            "gpu_available": True,
            "gpu_usage_percent": 85.0,
            "gpu_memory_used_mb": 2048.0,
            "gpu_memory_total_mb": 8192.0,
            "temperature": 72.0,
        }):
            with patch.object(mgr, "get_cpu_usage", return_value=45.2):
                result = mgr.get_training_progress()

        assert result.status == "training"
        assert result.current_epoch == 5
        assert result.total_epochs == 20
        assert result.loss == 0.3421
        assert result.last_accuracy == 0.8765
        assert result.throughput == 128.5
        assert result.dataset_size == 5000
        assert result.gpu_usage_percent == 85.0
        assert result.cpu_usage_percent == 45.2
        assert result.training_mode == "MANUAL"

    def test_trainer_error_returns_error_status(self):
        """If trainer throws, return error status, not crash."""
        mgr = TrainingStateManager()
        mock_trainer = MagicMock()
        mock_trainer.get_status.side_effect = RuntimeError("GPU detached")
        mgr._g38_available = True
        mgr._trainer = mock_trainer

        result = mgr.get_training_progress()
        assert result.status == "error"
        assert "GPU detached" in result.automode_status

    def test_checkpoint_count_includes_safetensors(self):
        mgr = TrainingStateManager()
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reports_dir = root / "reports" / "g38_training"
            ckpt_dir = root / "training" / "checkpoints"
            reports_dir.mkdir(parents=True)
            ckpt_dir.mkdir(parents=True)
            (reports_dir / "epoch_1.safetensors").write_text("x", encoding="utf-8")
            (ckpt_dir / "epoch_2.safetensors").write_text("x", encoding="utf-8")

            with patch("backend.training.state_manager.PROJECT_ROOT", root):
                assert mgr.get_checkpoint_count() == 2

    def test_no_mock_keywords_in_source(self):
        """Source code must NOT contain mock fallback patterns."""
        import inspect
        source = inspect.getsource(TrainingStateManager)
        forbidden = ["random.", "randint", "MOCK_", "FAKE_", "DEMO_",
                      "placeholder", "simulated"]
        for keyword in forbidden:
            assert keyword not in source, \
                f"Forbidden keyword '{keyword}' found in TrainingStateManager source"

    def test_emit_training_metrics_records_latency_accuracy_and_gpu_gauges(self):
        metrics_registry.reset()
        mgr = TrainingStateManager()
        metrics = TrainingMetrics(
            status="training",
            elapsed_seconds=2.5,
            last_accuracy=0.91,
            gpu_usage_percent=62.5,
            gpu_memory_used_mb=1536.0,
        )

        mgr.emit_training_metrics(metrics)
        snapshot = metrics_registry.get_snapshot()

        assert snapshot["histograms"]["training_latency_ms"]["count"] == 1
        assert metrics_registry.get_gauge("model_accuracy") == 0.91
        assert metrics_registry.get_gauge("gpu_memory_used_mb") == 1536.0
        assert metrics_registry.get_gauge("gpu_utilization_pct") == 62.5
        assert metrics_registry.get_gauge("gpu_fallback_active") == 0.0

    def test_get_training_progress_normalizes_zero_values_to_none(self):
        mgr = TrainingStateManager()
        mock_trainer = MagicMock()
        mock_trainer.get_status.return_value = {
            "is_training": True,
            "state": "TRAINING",
            "epoch": 1,
            "total_epochs": 2,
            "last_loss": 0.0,
            "last_accuracy": 0.0,
            "samples_per_sec": 0.0,
            "dataset_size": 0,
            "training_mode": "AUTO",
        }
        mgr._g38_available = True
        mgr._trainer = mock_trainer

        with patch.object(mgr, "get_gpu_metrics", return_value={"gpu_usage_percent": None, "gpu_memory_used_mb": None, "gpu_memory_total_mb": None}):
            with patch.object(mgr, "get_cpu_usage", return_value=None):
                result = mgr.get_training_progress()

        assert result.loss is None
        assert result.last_accuracy is None
        assert result.throughput is None
        assert result.dataset_size is None

    def test_emit_training_metrics_marks_fallback_when_gpu_values_missing(self):
        metrics_registry.reset()
        mgr = TrainingStateManager()
        metrics = TrainingMetrics(status="idle")

        mgr.emit_training_metrics(metrics)
        assert metrics_registry.get_gauge("gpu_fallback_active") == 1.0

    def test_emit_training_metrics_swallows_registry_errors(self):
        mgr = TrainingStateManager()
        metrics = TrainingMetrics(status="training", elapsed_seconds=1.0)

        with patch.object(metrics_registry, "record", side_effect=RuntimeError("boom")):
            mgr.emit_training_metrics(metrics)


class TestMetricsRegistryBehavior:
    def test_histogram_helpers_and_snapshot_cover_edge_cases(self):
        registry = MetricsRegistry()
        assert registry.get_histogram_stats("missing") == {"count": 0}

        for value in range(1001):
            registry.record("latency", float(value))

        stats = registry.get_histogram_stats("latency")
        snapshot = registry.get_snapshot()

        assert stats["count"] == 500
        assert snapshot["histograms"]["latency"]["count"] == 500

    def test_check_critical_metrics_reports_missing_entries(self, caplog):
        registry = MetricsRegistry()
        registry.reset()

        with caplog.at_level("WARNING"):
            missing = registry.check_critical_metrics()

        assert "request_count" in missing
        assert registry.get_counter("metric_missing_counter") == len(missing)
        assert any("Critical metric never recorded" in record.getMessage() for record in caplog.records)

    def test_measurement_completeness_and_null_ratio_helpers(self):
        metrics_registry.reset()

        assert get_measurement_completeness({}, []) == 1.0
        completeness = get_measurement_completeness({"a": 1, "b": None}, ["a", "b"])
        assert completeness == 0.5

        assert get_null_metric_ratio({}, []) == 0.0
        null_ratio = get_null_metric_ratio({"a": None, "b": 2}, ["a", "b"])
        assert null_ratio == 0.5


class TestSingleton:
    """Test singleton pattern."""

    def test_singleton_returns_same_instance(self):
        """get_training_state_manager must return the same instance."""
        # Reset
        import backend.training.state_manager as sm
        sm._state_manager = None

        with patch.object(sm.TrainingStateManager, "start_gpu_watchdog") as start_watchdog:
            mgr1 = get_training_state_manager()
            mgr2 = get_training_state_manager()

        assert mgr1 is mgr2
        start_watchdog.assert_called_once()
