"""
test_stabilizer.py — Tests for 6-Phase Production Stabilizer
"""

import hashlib
import json
import os
import sys
import time

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 2 — TELEMETRY STREAM
# ===========================================================================

class TestTelemetryStream:

    def test_record_frame(self):
        from impl_v1.training.distributed.telemetry_stream import TelemetryStream
        stream = TelemetryStream()
        stream.start_training(10000)
        frame = stream.record(
            epoch=0, batch=5, total_batches=20,
            samples_processed=2500, samples_per_sec=5000,
        )
        assert frame.epoch == 0
        assert frame.samples_per_sec == 5000.0
        assert frame.eta_seconds > 0

    def test_eta_calculation(self):
        from impl_v1.training.distributed.telemetry_stream import TelemetryStream
        stream = TelemetryStream()
        stream.start_training(10000)
        frame = stream.record(
            epoch=0, batch=10, total_batches=20,
            samples_processed=5000, samples_per_sec=1000,
        )
        # ETA = 5000 remaining / 1000 sps = 5.0s
        assert frame.eta_seconds == 5.0

    def test_stall_detection(self):
        from impl_v1.training.distributed.telemetry_stream import TelemetryStream
        stream = TelemetryStream()
        stream.start_training(10000)
        stream.record(epoch=0, batch=1, total_batches=10,
                      samples_processed=100, samples_per_sec=100)
        # Manually expire
        stream._last_update = time.time() - 15
        assert stream.is_stalled is True

    def test_to_json(self):
        from impl_v1.training.distributed.telemetry_stream import TelemetryStream
        stream = TelemetryStream()
        stream.start_training(1000)
        stream.record(0, 1, 10, 100, 500)
        j = stream.to_json()
        data = json.loads(j)
        assert 'epoch' in data
        assert 'samples_per_sec' in data

    def test_loss_history(self):
        from impl_v1.training.distributed.telemetry_stream import TelemetryStream
        stream = TelemetryStream()
        stream.start_training(1000)
        for i in range(5):
            stream.record(0, i, 10, i*100, 500, loss=0.5-i*0.05,
                          running_accuracy=0.5+i*0.05)
        h = stream.get_loss_history()
        assert len(h) == 5
        assert 'loss' in h[0]


# ===========================================================================
# PHASE 4 — AUTO-HEAL
# ===========================================================================

class TestAutoHeal:

    def test_crash_with_checkpoint(self, tmp_path):
        from impl_v1.training.distributed.auto_heal import AutoHealPolicy
        ckpt = tmp_path / "latest.pt"
        ckpt.write_bytes(b"model_data")

        heal = AutoHealPolicy(str(tmp_path / "logs"))
        report = heal.handle_crash(str(ckpt), checkpoint_valid=True)
        assert report.healed is True
        assert report.training_can_continue is True

    def test_crash_no_checkpoint(self, tmp_path):
        from impl_v1.training.distributed.auto_heal import AutoHealPolicy
        heal = AutoHealPolicy(str(tmp_path / "logs"))
        report = heal.handle_crash("/nonexistent/ckpt.pt", checkpoint_valid=False)
        assert report.healed is False
        assert report.training_can_continue is False

    def test_shard_corruption_repaired(self, tmp_path):
        from impl_v1.training.distributed.auto_heal import AutoHealPolicy
        heal = AutoHealPolicy(str(tmp_path / "logs"))
        report = heal.handle_shard_corruption(
            "shard123", "aaa", "bbb", peer_available=True,
        )
        assert report.healed is True

    def test_shard_corruption_no_peer(self, tmp_path):
        from impl_v1.training.distributed.auto_heal import AutoHealPolicy
        heal = AutoHealPolicy(str(tmp_path / "logs"))
        report = heal.handle_shard_corruption(
            "shard123", "aaa", "bbb", peer_available=False,
        )
        assert report.healed is False

    def test_dataset_mismatch_aborts(self, tmp_path):
        from impl_v1.training.distributed.auto_heal import AutoHealPolicy
        heal = AutoHealPolicy(str(tmp_path / "logs"))
        report = heal.handle_dataset_mismatch("hash1", "hash2")
        assert report.healed is False
        assert report.training_can_continue is False

    def test_determinism_mismatch_aborts(self, tmp_path):
        from impl_v1.training.distributed.auto_heal import AutoHealPolicy
        heal = AutoHealPolicy(str(tmp_path / "logs"))
        report = heal.handle_determinism_mismatch("run1hash", "run2hash")
        assert report.healed is False
        assert report.training_can_continue is False


# ===========================================================================
# PHASE 5 — REGRESSION VALIDATOR
# ===========================================================================

class TestRegressionValidator:

    def test_compute_metrics(self):
        from impl_v1.training.distributed.regression_validator import compute_metrics
        y_true = np.array([0, 0, 1, 1, 1])
        y_pred = np.array([0, 0, 1, 1, 0])
        m = compute_metrics(y_true, y_pred)
        assert m.accuracy == 0.8
        assert m.f1 > 0

    def test_no_previous_auto_pass(self, tmp_path):
        from impl_v1.training.distributed.regression_validator import RegressionValidator
        v = RegressionValidator(registry_path=str(tmp_path / "reg.json"))
        y_true = np.array([0, 1, 1, 0])
        y_pred = np.array([0, 1, 1, 0])
        result = v.validate("v001", y_true, y_pred)
        assert result.passed is True

    def test_improvement_passes(self, tmp_path):
        from impl_v1.training.distributed.regression_validator import (
            RegressionValidator, ModelMetrics,
        )
        v = RegressionValidator(registry_path=str(tmp_path / "reg.json"))

        prev = ModelMetrics(accuracy=0.70, precision=0.70, recall=0.70, f1=0.70, support=100)
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 0, 1, 1])  # Perfect
        result = v.validate("v002", y_true, y_pred, previous_metrics=prev)
        assert result.passed is True
        assert result.deltas['accuracy'] > 0

    def test_regression_rejected(self, tmp_path):
        from impl_v1.training.distributed.regression_validator import (
            RegressionValidator, ModelMetrics,
        )
        v = RegressionValidator(
            threshold=0.01,
            registry_path=str(tmp_path / "reg.json"),
        )
        prev = ModelMetrics(accuracy=0.95, precision=0.95, recall=0.95, f1=0.95, support=100)
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 1, 0, 1])  # 50% acc
        result = v.validate("v003", y_true, y_pred, previous_metrics=prev)
        assert result.passed is False

    def test_registry_persisted(self, tmp_path):
        from impl_v1.training.distributed.regression_validator import RegressionValidator
        reg_path = str(tmp_path / "reg.json")
        v = RegressionValidator(registry_path=reg_path)
        y = np.array([0, 1])
        v.validate("v001", y, y)
        assert os.path.exists(reg_path)
        with open(reg_path) as f:
            data = json.load(f)
        assert len(data) == 1


# ===========================================================================
# PHASE 6 — FREEZE VALIDATOR
# ===========================================================================

class TestFreezeValidator:

    def test_all_pass_freezes(self):
        from impl_v1.training.distributed.freeze_validator import FreezeValidator
        v = FreezeValidator()
        result = v.validate_freeze(
            "v001",
            determinism_passed=True,
            drift_passed=True,
            regression_passed=True,
        )
        assert result.freeze_allowed is True
        assert len(result.checks) == 3

    def test_determinism_fail_rejects(self):
        from impl_v1.training.distributed.freeze_validator import FreezeValidator
        v = FreezeValidator()
        result = v.validate_freeze(
            "v002",
            determinism_passed=False,
            drift_passed=True,
            regression_passed=True,
        )
        assert result.freeze_allowed is False

    def test_drift_fail_rejects(self):
        from impl_v1.training.distributed.freeze_validator import FreezeValidator
        v = FreezeValidator()
        result = v.validate_freeze(
            "v003",
            determinism_passed=True,
            drift_passed=False,
            regression_passed=True,
        )
        assert result.freeze_allowed is False

    def test_regression_fail_rejects(self):
        from impl_v1.training.distributed.freeze_validator import FreezeValidator
        v = FreezeValidator()
        result = v.validate_freeze(
            "v004",
            determinism_passed=True,
            drift_passed=True,
            regression_passed=False,
        )
        assert result.freeze_allowed is False

    def test_multiple_failures(self):
        from impl_v1.training.distributed.freeze_validator import FreezeValidator
        v = FreezeValidator()
        result = v.validate_freeze(
            "v005",
            determinism_passed=False,
            drift_passed=False,
            regression_passed=False,
        )
        assert result.freeze_allowed is False
        failed = [c.check_name for c in result.checks if not c.passed]
        assert len(failed) == 3


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestStabilizerIntegration:

    def test_heal_then_validate_then_freeze(self, tmp_path):
        """Auto-heal → regression → freeze gate."""
        from impl_v1.training.distributed.auto_heal import AutoHealPolicy
        from impl_v1.training.distributed.regression_validator import RegressionValidator
        from impl_v1.training.distributed.freeze_validator import FreezeValidator

        # Heal: crash with checkpoint
        ckpt = tmp_path / "model.pt"
        ckpt.write_bytes(b"data")
        heal = AutoHealPolicy(str(tmp_path / "heal"))
        h = heal.handle_crash(str(ckpt))
        assert h.training_can_continue is True

        # Regression: no previous, auto pass
        reg = RegressionValidator(registry_path=str(tmp_path / "reg.json"))
        y = np.array([0, 1, 1, 0])
        r = reg.validate("v001", y, y)
        assert r.passed is True

        # Freeze: all pass
        fv = FreezeValidator()
        f = fv.validate_freeze(
            "v001",
            determinism_passed=True,
            drift_passed=True,
            regression_passed=r.passed,
        )
        assert f.freeze_allowed is True
