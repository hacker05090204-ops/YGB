"""
Tests for Phase-11 Parallel Limits.

Tests:
- Max parallel enforcement
- Worker capacity limits
- GPU eligibility (not execution)
"""
import pytest


class TestParallelLimits:
    """Test parallel work limits."""

    def test_worker_at_max_parallel_denied(self):
        """Worker at max parallel gets denied."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        from python.phase11_scheduling.scheduling_context import (
            WorkerProfile, WorkTarget, SchedulingPolicy, WorkAssignmentContext
        )
        from python.phase11_scheduling.scheduling_engine import assign_work

        worker = WorkerProfile(
            worker_id="W-001", worker_type="standard",
            max_parallel=3, has_gpu=False, gpu_memory_gb=0, active=True
        )
        target = WorkTarget(
            target_id="T-001", difficulty="low",
            requires_gpu=False, min_gpu_memory_gb=0
        )
        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        # Worker already at max (3 assignments)
        context = WorkAssignmentContext(
            request_id="REQ-001", worker=worker, target=target,
            policy=policy, current_assignments=frozenset({"a", "b", "c"}),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.assigned is False
        assert "DN-003" in result.reason_code

    def test_worker_below_max_allowed(self):
        """Worker below max parallel can be assigned."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        from python.phase11_scheduling.scheduling_context import (
            WorkerProfile, WorkTarget, SchedulingPolicy, WorkAssignmentContext
        )
        from python.phase11_scheduling.scheduling_engine import assign_work

        worker = WorkerProfile(
            worker_id="W-001", worker_type="standard",
            max_parallel=5, has_gpu=False, gpu_memory_gb=0, active=True
        )
        target = WorkTarget(
            target_id="T-001", difficulty="low",
            requires_gpu=False, min_gpu_memory_gb=0
        )
        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        context = WorkAssignmentContext(
            request_id="REQ-002", worker=worker, target=target,
            policy=policy, current_assignments=frozenset({"a", "b"}),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.assigned is True


class TestGPUEligibility:
    """Test GPU eligibility (not execution)."""

    def test_is_eligible_for_gpu_target_true(self):
        """Worker with sufficient GPU is eligible."""
        from python.phase11_scheduling.scheduling_context import WorkerProfile, WorkTarget
        from python.phase11_scheduling.scheduling_engine import is_eligible_for_target

        worker = WorkerProfile(
            worker_id="W-001", worker_type="premium",
            max_parallel=5, has_gpu=True, gpu_memory_gb=16, active=True
        )
        target = WorkTarget(
            target_id="T-001", difficulty="high",
            requires_gpu=True, min_gpu_memory_gb=8
        )

        result = is_eligible_for_target(worker, target)
        assert result is True

    def test_is_eligible_insufficient_gpu_memory(self):
        """Worker with insufficient GPU memory is not eligible."""
        from python.phase11_scheduling.scheduling_context import WorkerProfile, WorkTarget
        from python.phase11_scheduling.scheduling_engine import is_eligible_for_target

        worker = WorkerProfile(
            worker_id="W-001", worker_type="premium",
            max_parallel=5, has_gpu=True, gpu_memory_gb=4, active=True
        )
        target = WorkTarget(
            target_id="T-001", difficulty="high",
            requires_gpu=True, min_gpu_memory_gb=8
        )

        result = is_eligible_for_target(worker, target)
        assert result is False

    def test_is_eligible_no_gpu_for_non_gpu_target(self):
        """Worker without GPU is eligible for non-GPU target."""
        from python.phase11_scheduling.scheduling_context import WorkerProfile, WorkTarget
        from python.phase11_scheduling.scheduling_engine import is_eligible_for_target

        worker = WorkerProfile(
            worker_id="W-001", worker_type="standard",
            max_parallel=5, has_gpu=False, gpu_memory_gb=0, active=True
        )
        target = WorkTarget(
            target_id="T-001", difficulty="low",
            requires_gpu=False, min_gpu_memory_gb=0
        )

        result = is_eligible_for_target(worker, target)
        assert result is True


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_worker_profile_is_frozen(self):
        """WorkerProfile is frozen."""
        from python.phase11_scheduling.scheduling_context import WorkerProfile

        worker = WorkerProfile(
            worker_id="W-001", worker_type="standard",
            max_parallel=5, has_gpu=False, gpu_memory_gb=0, active=True
        )

        with pytest.raises(Exception):
            worker.worker_id = "MODIFIED"

    def test_scheduling_policy_is_frozen(self):
        """SchedulingPolicy is frozen."""
        from python.phase11_scheduling.scheduling_context import SchedulingPolicy

        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )

        with pytest.raises(Exception):
            policy.active = False


class TestNoForbiddenImports:
    """Test no forbidden imports in context module."""

    def test_no_asyncio_import(self):
        """No asyncio import."""
        import python.phase11_scheduling.scheduling_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import asyncio' not in source

    def test_no_threading_import(self):
        """No threading import."""
        import python.phase11_scheduling.scheduling_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import threading' not in source
