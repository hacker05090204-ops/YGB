"""
test_orchestrator.py — Tests for 8-Phase Autonomous Training Orchestrator
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
# PHASE 1 — FIELD SCHEDULER
# ===========================================================================

class TestFieldScheduler:

    def test_add_and_next(self, tmp_path):
        from impl_v1.training.distributed.field_scheduler import FieldScheduler, FieldEntry
        sched = FieldScheduler(str(tmp_path / "q.json"))
        sched.add_field(FieldEntry("vuln", priority=80))
        sched.add_field(FieldEntry("pattern", priority=60))
        f = sched.next_field()
        assert f is not None
        assert f.field_name == "vuln"

    def test_round_robin(self, tmp_path):
        from impl_v1.training.distributed.field_scheduler import FieldScheduler, FieldEntry
        sched = FieldScheduler(str(tmp_path / "q.json"))
        sched.add_field(FieldEntry("a", priority=50))
        sched.add_field(FieldEntry("b", priority=50))
        f1 = sched.next_field()
        sched.complete_field(f1.field_name)
        sched.reset_queue()
        f2 = sched.next_field()
        assert f2 is not None

    def test_skip_no_data(self, tmp_path):
        from impl_v1.training.distributed.field_scheduler import FieldScheduler, FieldEntry
        sched = FieldScheduler(str(tmp_path / "q.json"))
        sched.add_field(FieldEntry("stale", has_new_data=False))
        f = sched.next_field()
        assert f is None

    def test_idle_auto_continue(self, tmp_path):
        from impl_v1.training.distributed.field_scheduler import FieldScheduler, FieldEntry
        sched = FieldScheduler(str(tmp_path / "q.json"))
        sched.add_field(FieldEntry("vuln"))
        sched.complete_field("vuln")
        sched._idle_since = time.time() - 700  # 11+ min idle
        assert sched.should_auto_continue() is True

    def test_persist(self, tmp_path):
        from impl_v1.training.distributed.field_scheduler import FieldScheduler, FieldEntry
        path = str(tmp_path / "q.json")
        s1 = FieldScheduler(path)
        s1.add_field(FieldEntry("vuln", priority=90))
        s2 = FieldScheduler(path)
        assert s2.queue_size == 1


# ===========================================================================
# PHASE 3 — CONTINUOUS TRAINER
# ===========================================================================

class TestContinuousTrainer:

    def test_train_field(self):
        from impl_v1.training.distributed.continuous_trainer import ContinuousTrainer
        trainer = ContinuousTrainer()
        result = trainer.train_field(
            "vuln",
            train_fn=lambda f: {'epochs': 5, 'accuracy': 0.85, 'loss': 0.3, 'weight_hash': 'abc'},
        )
        assert result.best_accuracy == 0.85
        assert result.epochs == 5

    def test_monitoring_mode(self):
        from impl_v1.training.distributed.continuous_trainer import ContinuousTrainer
        trainer = ContinuousTrainer()
        trainer.enter_monitoring()
        assert trainer.mode == "monitoring"

    def test_check_new_data(self):
        from impl_v1.training.distributed.continuous_trainer import ContinuousTrainer
        trainer = ContinuousTrainer()
        trainer.enter_monitoring()
        found = trainer.check_for_new_data(lambda: True)
        assert found is True
        assert trainer.mode == "idle"


# ===========================================================================
# PHASE 4 — CLUSTER DISTRIBUTOR
# ===========================================================================

class TestClusterDistributor:

    def test_role_assignment(self):
        from impl_v1.training.distributed.cluster_distributor import ClusterDistributor, ClusterNode
        dist = ClusterDistributor()
        dist.register_node(ClusterNode("n1", "cuda", "RTX2050", 4096))
        dist.register_node(ClusterNode("n2", "mps", "M1", 8192))
        dist.register_node(ClusterNode("n3", "cpu", "i7", 0))
        d = dist.distribute()
        assert "n1" in d.ddp_nodes
        assert "n2" in d.shard_nodes
        assert "n3" in d.validator_nodes

    def test_efficiency_balanced(self):
        from impl_v1.training.distributed.cluster_distributor import ClusterDistributor, ClusterNode
        dist = ClusterDistributor()
        dist.register_node(ClusterNode("n1", "cuda", "RTX2050", 4096))
        dist.set_baseline_sps("n1", 1000)
        dist.update_sps("n1", 800)
        d = dist.distribute()
        assert d.scaling_efficiency >= 0.75
        assert d.balanced is True

    def test_rebalance(self):
        from impl_v1.training.distributed.cluster_distributor import ClusterDistributor, ClusterNode
        dist = ClusterDistributor()
        dist.register_node(ClusterNode("n1", "cuda", "RTX2050", 4096))
        dist.register_node(ClusterNode("n2", "cuda", "RTX3050", 4096))
        dist.set_baseline_sps("n1", 1000)
        dist.set_baseline_sps("n2", 1000)
        dist.update_sps("n1", 900)
        dist.update_sps("n2", 100)  # Very slow
        d = dist.rebalance()
        assert d is not None  # Rebalanced


# ===========================================================================
# PHASE 6 — EARLY CONVERGENCE
# ===========================================================================

class TestEarlyConvergence:

    def test_no_plateau_continues(self):
        from impl_v1.training.distributed.early_convergence import EarlyConvergenceDetector
        det = EarlyConvergenceDetector(patience=3)
        for i in range(5):
            stop = det.check(i, 0.5 + i * 0.05)
            assert stop is False

    def test_plateau_stops(self):
        from impl_v1.training.distributed.early_convergence import EarlyConvergenceDetector
        det = EarlyConvergenceDetector(patience=3, min_delta=0.01)
        det.check(0, 0.80)
        det.check(1, 0.80)
        det.check(2, 0.80)
        stop = det.check(3, 0.80)
        assert stop is True

    def test_reset(self):
        from impl_v1.training.distributed.early_convergence import EarlyConvergenceDetector
        det = EarlyConvergenceDetector(patience=2)
        det.check(0, 0.8)
        det.check(1, 0.8)
        det.check(2, 0.8)
        det.reset()
        assert det.should_stop is False


# ===========================================================================
# PHASE 7 — LONG-RUN STABILITY
# ===========================================================================

class TestLongRunStability:

    def test_not_due_immediately(self):
        from impl_v1.training.distributed.long_run_stability import LongRunStabilizer
        stab = LongRunStabilizer(interval_sec=3600)
        assert stab.is_due() is False

    def test_due_after_interval(self):
        from impl_v1.training.distributed.long_run_stability import LongRunStabilizer
        stab = LongRunStabilizer(interval_sec=1)
        stab._last_maintenance = time.time() - 2
        assert stab.is_due() is True

    def test_maintenance_runs(self):
        from impl_v1.training.distributed.long_run_stability import LongRunStabilizer
        stab = LongRunStabilizer(interval_sec=1)
        report = stab.run_maintenance(
            checkpoint_fn=lambda: None,
            cache_clear_fn=lambda: None,
            shard_verify_fn=lambda: None,
        )
        assert report.all_ok is True
        assert stab.cycle_count == 1


# ===========================================================================
# PHASE 8 — SAFETY GUARDS
# ===========================================================================

class TestTrainingSafety:

    def test_single_crash_heals(self):
        from impl_v1.training.distributed.training_safety import TrainingSafetyGuard
        guard = TrainingSafetyGuard(max_crashes=3)
        e = guard.report_crash()
        assert e.severity == "healed"
        assert guard.is_safe is True

    def test_repeated_crash_aborts(self):
        from impl_v1.training.distributed.training_safety import TrainingSafetyGuard
        guard = TrainingSafetyGuard(max_crashes=3)
        guard.report_crash()
        guard.report_crash()
        e = guard.report_crash()
        assert e.severity == "abort"
        assert guard.is_safe is False

    def test_dataset_corruption_aborts(self):
        from impl_v1.training.distributed.training_safety import TrainingSafetyGuard
        guard = TrainingSafetyGuard()
        guard.report_dataset_corruption()
        assert guard.is_safe is False

    def test_determinism_aborts(self):
        from impl_v1.training.distributed.training_safety import TrainingSafetyGuard
        guard = TrainingSafetyGuard()
        guard.report_determinism_failure()
        assert guard.is_safe is False

    def test_regression_aborts(self):
        from impl_v1.training.distributed.training_safety import TrainingSafetyGuard
        guard = TrainingSafetyGuard()
        guard.report_regression_failure()
        assert guard.is_safe is False

    def test_shard_repair_heals(self):
        from impl_v1.training.distributed.training_safety import TrainingSafetyGuard
        guard = TrainingSafetyGuard()
        e = guard.report_shard_repair("abc123")
        assert e.severity == "healed"
        assert guard.is_safe is True


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestOrchestratorIntegration:

    def test_full_pipeline(self, tmp_path):
        """Scheduler → Continuous → Convergence → Safety."""
        from impl_v1.training.distributed.field_scheduler import FieldScheduler, FieldEntry
        from impl_v1.training.distributed.continuous_trainer import ContinuousTrainer
        from impl_v1.training.distributed.early_convergence import EarlyConvergenceDetector
        from impl_v1.training.distributed.training_safety import TrainingSafetyGuard

        # Scheduler
        sched = FieldScheduler(str(tmp_path / "q.json"))
        sched.add_field(FieldEntry("vuln", priority=90))
        sched.add_field(FieldEntry("pattern", priority=70))

        # Safety
        guard = TrainingSafetyGuard()
        assert guard.is_safe

        # Convergence
        conv = EarlyConvergenceDetector(patience=3)

        # Continuous
        trainer = ContinuousTrainer()
        f = sched.next_field()
        assert f is not None
        result = trainer.train_field(
            f.field_name,
            train_fn=lambda n: {'epochs': 3, 'accuracy': 0.82, 'loss': 0.3, 'weight_hash': 'x'},
        )
        sched.complete_field(f.field_name, result.best_accuracy, result.epochs)

        state = trainer.get_state()
        assert state.fields_completed == 1
        assert guard.is_safe
