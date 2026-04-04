"""
test_mode_governance.py — Tests for 5-Phase Mode Governance
"""

import json
import os
import sys
import time

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 1 — MODE STATE LOCK
# ===========================================================================

class TestModeStateLock:

    def test_default_mode_a(self, tmp_path):
        from impl_v1.training.distributed.mode_state_lock import ModeStateLock
        lock = ModeStateLock(str(tmp_path / "state.json"))
        assert lock.mode == "A"

    def test_record_pass(self, tmp_path):
        from impl_v1.training.distributed.mode_state_lock import ModeStateLock
        lock = ModeStateLock(str(tmp_path / "state.json"))
        lock.record_pass(0.95)
        assert lock.consecutive_passes == 1

    def test_record_fail_resets(self, tmp_path):
        from impl_v1.training.distributed.mode_state_lock import ModeStateLock
        lock = ModeStateLock(str(tmp_path / "state.json"))
        lock.record_pass(0.95)
        lock.record_pass(0.96)
        lock.record_fail()
        assert lock.consecutive_passes == 0

    def test_promote_to_b(self, tmp_path):
        from impl_v1.training.distributed.mode_state_lock import ModeStateLock
        lock = ModeStateLock(str(tmp_path / "state.json"))
        lock.promote_to_b()
        assert lock.mode == "B"

    def test_rollback_to_a(self, tmp_path):
        from impl_v1.training.distributed.mode_state_lock import ModeStateLock
        lock = ModeStateLock(str(tmp_path / "state.json"))
        lock.promote_to_b()
        lock.rollback_to_a("test")
        assert lock.mode == "A"
        assert lock.consecutive_passes == 0

    def test_persistence(self, tmp_path):
        from impl_v1.training.distributed.mode_state_lock import ModeStateLock
        path = str(tmp_path / "state.json")
        l1 = ModeStateLock(path)
        l1.record_pass(0.95)
        l1.promote_to_b()
        l2 = ModeStateLock(path)
        assert l2.mode == "B"
        assert l2.consecutive_passes == 1


# ===========================================================================
# PHASE 2 — PROMOTION CONTROLLER
# ===========================================================================

class TestPromotionController:

    def test_all_pass_promotes(self):
        from impl_v1.training.distributed.promotion_controller import PromotionController
        ctrl = PromotionController()
        result = ctrl.evaluate(
            accuracy=0.96, consecutive_passes=3,
            regression_passed=True, semantic_passed=True,
            cross_field_fpr=0.05, drift_stable=True,
            determinism_match=True,
        )
        assert result.promoted is True
        assert len(result.gates) == 7

    def test_low_accuracy_blocks(self):
        from impl_v1.training.distributed.promotion_controller import PromotionController
        ctrl = PromotionController()
        result = ctrl.evaluate(accuracy=0.90, consecutive_passes=3)
        assert result.promoted is False
        assert "accuracy" in result.failed_gates

    def test_insufficient_passes(self):
        from impl_v1.training.distributed.promotion_controller import PromotionController
        ctrl = PromotionController()
        result = ctrl.evaluate(accuracy=0.96, consecutive_passes=1)
        assert result.promoted is False

    def test_regression_blocks(self):
        from impl_v1.training.distributed.promotion_controller import PromotionController
        ctrl = PromotionController()
        result = ctrl.evaluate(
            accuracy=0.96, consecutive_passes=3,
            regression_passed=False,
        )
        assert result.promoted is False

    def test_semantic_blocks(self):
        from impl_v1.training.distributed.promotion_controller import PromotionController
        ctrl = PromotionController()
        result = ctrl.evaluate(
            accuracy=0.96, consecutive_passes=3,
            semantic_passed=False,
        )
        assert result.promoted is False

    def test_cross_field_blocks(self):
        from impl_v1.training.distributed.promotion_controller import PromotionController
        ctrl = PromotionController()
        result = ctrl.evaluate(
            accuracy=0.96, consecutive_passes=3,
            cross_field_fpr=0.20,
        )
        assert result.promoted is False


# ===========================================================================
# PHASE 3 — MODE B PROTECTION
# ===========================================================================

class TestModeBProtection:

    def test_stable_mode_b(self):
        from impl_v1.training.distributed.mode_b_protection import ModeBProtection
        prot = ModeBProtection()
        report = prot.check(accuracy=0.95)
        assert report.mode_b_stable is True
        assert report.rollback_needed is False

    def test_low_accuracy_rollback(self):
        from impl_v1.training.distributed.mode_b_protection import ModeBProtection
        prot = ModeBProtection()
        report = prot.check(accuracy=0.89)
        assert report.rollback_needed is True

    def test_regression_rollback(self):
        from impl_v1.training.distributed.mode_b_protection import ModeBProtection
        prot = ModeBProtection()
        report = prot.check(accuracy=0.95, regression_delta=-0.05)
        assert report.rollback_needed is True

    def test_cluster_instability(self):
        from impl_v1.training.distributed.mode_b_protection import ModeBProtection
        prot = ModeBProtection()
        report = prot.check(accuracy=0.95, cluster_stable=False)
        assert report.rollback_needed is True

    def test_incident_logged(self):
        from impl_v1.training.distributed.mode_b_protection import ModeBProtection
        prot = ModeBProtection()
        prot.check(accuracy=0.89)
        assert len(prot.incidents) == 1


# ===========================================================================
# PHASE 4 — CLUSTER LOCK
# ===========================================================================

class TestClusterLock:

    def test_lock_unlocked_join(self):
        from impl_v1.training.distributed.cluster_lock import ClusterLock
        lock = ClusterLock()
        assert lock.request_join("n1", "cuda") is True

    def test_locked_queues_join(self):
        from impl_v1.training.distributed.cluster_lock import ClusterLock
        lock = ClusterLock()
        lock.lock(2)
        assert lock.request_join("n3", "cuda") is False

    def test_unlock_releases_pending(self):
        from impl_v1.training.distributed.cluster_lock import ClusterLock
        lock = ClusterLock()
        lock.lock(2)
        lock.request_join("n3", "cuda")
        pending = lock.unlock()
        assert len(pending) == 1
        assert pending[0].node_id == "n3"

    def test_state(self):
        from impl_v1.training.distributed.cluster_lock import ClusterLock
        lock = ClusterLock()
        lock.lock(2)
        state = lock.get_state()
        assert state.locked is True
        assert state.locked_world_size == 2


# ===========================================================================
# PHASE 5 — STABILITY TRACKER
# ===========================================================================

class TestStabilityTracker:

    def test_not_ready_initially(self):
        from impl_v1.training.distributed.stability_tracker import StabilityTracker
        tracker = StabilityTracker(threshold=5)
        tracker.record_cycle("vuln", 0.95, True)
        assert tracker.is_live_ready("vuln") is False

    def test_live_ready_after_5(self):
        from impl_v1.training.distributed.stability_tracker import StabilityTracker
        tracker = StabilityTracker(threshold=5)
        for i in range(5):
            tracker.record_cycle("vuln", 0.95 + i * 0.001, True)
        assert tracker.is_live_ready("vuln") is True

    def test_unstable_resets(self):
        from impl_v1.training.distributed.stability_tracker import StabilityTracker
        tracker = StabilityTracker(threshold=5)
        for i in range(4):
            tracker.record_cycle("vuln", 0.95, True)
        tracker.record_cycle("vuln", 0.80, False)  # unstable
        assert tracker.is_live_ready("vuln") is False

    def test_live_ready_count(self):
        from impl_v1.training.distributed.stability_tracker import StabilityTracker
        tracker = StabilityTracker(threshold=2)
        for _ in range(2):
            tracker.record_cycle("vuln", 0.95, True)
            tracker.record_cycle("pattern", 0.90, True)
        assert tracker.live_ready_count() == 2


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestModeGovernanceIntegration:

    def test_full_promotion_flow(self, tmp_path):
        """State lock → 3 passes → Promotion → MODE B check."""
        from impl_v1.training.distributed.mode_state_lock import ModeStateLock
        from impl_v1.training.distributed.promotion_controller import PromotionController
        from impl_v1.training.distributed.mode_b_protection import ModeBProtection

        state = ModeStateLock(str(tmp_path / "state.json"))
        ctrl = PromotionController()
        prot = ModeBProtection()

        # 3 passes
        for _ in range(3):
            state.record_pass(0.96)

        # Promote
        result = ctrl.evaluate(
            accuracy=0.96, consecutive_passes=state.consecutive_passes,
        )
        assert result.promoted is True
        state.promote_to_b()
        assert state.mode == "B"

        # MODE B stable
        report = prot.check(accuracy=0.95)
        assert report.mode_b_stable is True
