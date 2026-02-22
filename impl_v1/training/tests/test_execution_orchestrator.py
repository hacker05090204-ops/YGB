"""
test_execution_orchestrator.py — Tests for 7-Phase Execution Orchestrator
"""

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
# PHASE 1 — GLOBAL STORAGE CAP
# ===========================================================================

class TestGlobalStorageCap:

    def test_within_cap(self):
        from impl_v1.training.distributed.global_storage_cap import GlobalStorageCap
        cap = GlobalStorageCap(cap_gb=110.0)
        cap.add_shard("s1", "vuln", 50 * 1024**3)
        report = cap.check_cap()
        assert report.within_cap is True

    def test_exceeds_cap(self):
        from impl_v1.training.distributed.global_storage_cap import (
            GlobalStorageCap, PoolShard,
        )
        cap = GlobalStorageCap(cap_gb=0.001)  # tiny ~1MB
        # Register directly to bypass add_shard cap check
        cap.register_shard(PoolShard(
            shard_id="s1", field_name="vuln",
            size_bytes=2 * 1024**2, tier="ssd",
            state="active", last_accessed=100,
        ))
        report = cap.check_cap()
        assert report.within_cap is False
        assert report.eviction is not None

    def test_field_breakdown(self):
        from impl_v1.training.distributed.global_storage_cap import GlobalStorageCap
        cap = GlobalStorageCap(cap_gb=110.0)
        cap.add_shard("s1", "vuln", 1024**3)       # 1GB
        cap.add_shard("s2", "pattern", 2 * 1024**3) # 2GB
        report = cap.check_cap()
        assert "vuln" in report.field_breakdown
        assert "pattern" in report.field_breakdown

    def test_evict_shard(self):
        from impl_v1.training.distributed.global_storage_cap import GlobalStorageCap
        cap = GlobalStorageCap(cap_gb=110.0)
        cap.add_shard("s1", "vuln", 1024)
        cap.evict_shard("s1", "nas")
        report = cap.check_cap()
        assert report.within_cap is True

    def test_reject_if_over(self):
        from impl_v1.training.distributed.global_storage_cap import GlobalStorageCap
        cap = GlobalStorageCap(cap_gb=0.001)  # ~1MB
        cap.add_shard("s1", "vuln", 500_000)
        ok = cap.add_shard("s2", "vuln", 2 * 1024**2)  # too big
        assert ok is False


# ===========================================================================
# PHASE 2 — AUTO START
# ===========================================================================

class TestAutoStartTrainer:

    def test_auto_start_with_trainable(self):
        from impl_v1.training.distributed.auto_start_trainer import (
            AutoStartTrainer, FieldDataset,
        )
        ast = AutoStartTrainer(idle_threshold=0.1)
        ast.register_field(FieldDataset("vuln", 50000, "hash1", "trainable"))
        ast._last_interaction = time.time() - 1  # past threshold
        state = ast.check_auto_start()
        assert state.mode == "running"

    def test_no_trainable_waiting(self):
        from impl_v1.training.distributed.auto_start_trainer import (
            AutoStartTrainer, FieldDataset,
        )
        ast = AutoStartTrainer()
        ast.register_field(FieldDataset("vuln", 0, "", "locked"))
        state = ast.check_auto_start()
        assert state.mode == "waiting"

    def test_lock_prevents_start(self):
        from impl_v1.training.distributed.auto_start_trainer import (
            AutoStartTrainer, FieldDataset,
        )
        ast = AutoStartTrainer(idle_threshold=0.1)
        ast.register_field(FieldDataset("vuln", 50000, "h", "trainable"))
        ast.lock()
        ast._last_interaction = time.time() - 1
        state = ast.check_auto_start()
        assert state.mode == "locked"


# ===========================================================================
# PHASE 4 — CONTINUOUS ROTATION
# ===========================================================================

class TestContinuousRotation:

    def test_register_fields(self):
        from impl_v1.training.distributed.continuous_rotation import ContinuousRotation
        rot = ContinuousRotation()
        rot.register_fields(["vuln", "pattern", "anomaly"])
        assert rot.total_fields == 3

    def test_next_field(self):
        from impl_v1.training.distributed.continuous_rotation import ContinuousRotation
        rot = ContinuousRotation()
        rot.register_fields(["a", "b", "c"])
        f1 = rot.next_field()
        f2 = rot.next_field()
        assert f1.field_name != f2.field_name

    def test_run_cycle(self):
        from impl_v1.training.distributed.continuous_rotation import ContinuousRotation
        rot = ContinuousRotation()
        rot.register_fields(["a", "b"])
        report = rot.run_cycle(
            train_fn=lambda n: {'accuracy': 0.8, 'loss': 0.3},
        )
        assert report.fields_trained == 2

    def test_cycle_counting(self):
        from impl_v1.training.distributed.continuous_rotation import ContinuousRotation
        rot = ContinuousRotation()
        rot.register_fields(["a", "b"])
        rot.run_cycle(train_fn=lambda n: {'accuracy': 0.8})
        assert rot.cycle_count >= 1


# ===========================================================================
# PHASE 6 — BACKTEST GATE
# ===========================================================================

class TestBacktestGate:

    def test_first_model_auto_pass(self):
        from impl_v1.training.distributed.backtest_gate import BacktestGate
        gate = BacktestGate()
        r = gate.check("vuln", 0.85)
        assert r.freeze_allowed is True

    def test_improvement_passes(self):
        from impl_v1.training.distributed.backtest_gate import BacktestGate
        gate = BacktestGate()
        gate.check("vuln", 0.80)  # first
        r = gate.check("vuln", 0.85)  # +5%
        assert r.freeze_allowed is True
        assert r.delta >= 0.02

    def test_within_tolerance(self):
        from impl_v1.training.distributed.backtest_gate import BacktestGate
        gate = BacktestGate(tolerance=0.01)
        gate.check("vuln", 0.80)
        r = gate.check("vuln", 0.795)  # -0.5%
        assert r.freeze_allowed is True

    def test_regression_rejected(self):
        from impl_v1.training.distributed.backtest_gate import BacktestGate
        gate = BacktestGate(tolerance=0.005)
        gate.check("vuln", 0.90)
        r = gate.check("vuln", 0.85)  # -5%
        assert r.freeze_allowed is False


# ===========================================================================
# PHASE 7 — DATA SCALE
# ===========================================================================

class TestDataScale:

    def test_23_fields(self):
        from impl_v1.training.distributed.data_scale_config import DataScaleManager
        mgr = DataScaleManager()
        assert mgr.field_count == 23

    def test_bootstrap(self):
        from impl_v1.training.distributed.data_scale_config import DataScaleManager
        mgr = DataScaleManager()
        X, y = mgr.generate_bootstrap("vulnerability_detection")
        assert X.shape[0] == 50_000
        assert y.shape[0] == 50_000

    def test_major_target(self):
        from impl_v1.training.distributed.data_scale_config import DataScaleManager
        mgr = DataScaleManager()
        cfg = mgr.get_field_config("vulnerability_detection")
        assert cfg.target_samples == 100_000
        assert cfg.is_major is True

    def test_minor_target(self):
        from impl_v1.training.distributed.data_scale_config import DataScaleManager
        mgr = DataScaleManager()
        cfg = mgr.get_field_config("web_security")
        assert cfg.target_samples == 50_000
        assert cfg.is_major is False

    def test_add_real_data(self):
        from impl_v1.training.distributed.data_scale_config import DataScaleManager
        mgr = DataScaleManager()
        mgr.generate_bootstrap("anomaly_detection")
        mgr.add_real_data("anomaly_detection", 10_000)
        cfg = mgr.get_field_config("anomaly_detection")
        assert cfg.real_samples == 10_000
        assert cfg.bootstrap_only is False

    def test_report(self):
        from impl_v1.training.distributed.data_scale_config import DataScaleManager
        mgr = DataScaleManager()
        mgr.generate_bootstrap("vulnerability_detection")
        report = mgr.get_report()
        assert report.total_fields == 23
        assert report.fields_at_minimum >= 1


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestExecutionIntegration:

    def test_global_cap_with_rotation(self):
        """Global cap + rotation + backtest."""
        from impl_v1.training.distributed.global_storage_cap import GlobalStorageCap
        from impl_v1.training.distributed.continuous_rotation import ContinuousRotation
        from impl_v1.training.distributed.backtest_gate import BacktestGate

        cap = GlobalStorageCap(cap_gb=110.0)
        cap.add_shard("s1", "vuln", 1024**3)
        assert cap.check_cap().within_cap is True

        rot = ContinuousRotation()
        rot.register_fields(["vuln", "pattern"])
        report = rot.run_cycle(
            train_fn=lambda n: {'accuracy': 0.83},
        )
        assert report.fields_trained == 2

        gate = BacktestGate()
        r = gate.check("vuln", 0.83)
        assert r.freeze_allowed is True
