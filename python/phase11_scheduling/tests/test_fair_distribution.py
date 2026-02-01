"""
Tests for Phase-11 Fair Distribution.

Tests:
- Equitable work distribution
- Load-balanced assignment
- No duplicate assignments
- Capability-aware assignment
"""
import pytest


class TestFairDistributionBasics:
    """Test basic fair distribution rules."""

    def test_light_load_worker_gets_assignment(self):
        """Light load worker gets assignment."""
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
            target_id="T-001", difficulty="medium",
            requires_gpu=False, min_gpu_memory_gb=0
        )
        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        context = WorkAssignmentContext(
            request_id="REQ-001", worker=worker, target=target,
            policy=policy, current_assignments=frozenset(),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.assigned is True
        assert result.status == WorkSlotStatus.ASSIGNED

    def test_heavy_load_worker_gets_queued(self):
        """Heavy load worker gets queued, not assigned."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        from python.phase11_scheduling.scheduling_context import (
            WorkerProfile, WorkTarget, SchedulingPolicy, WorkAssignmentContext
        )
        from python.phase11_scheduling.scheduling_engine import assign_work

        worker = WorkerProfile(
            worker_id="W-001", worker_type="standard",
            max_parallel=10, has_gpu=False, gpu_memory_gb=0, active=True
        )
        target = WorkTarget(
            target_id="T-001", difficulty="medium",
            requires_gpu=False, min_gpu_memory_gb=0
        )
        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        # Worker has 6 assignments (heavy load)
        context = WorkAssignmentContext(
            request_id="REQ-002", worker=worker, target=target,
            policy=policy, current_assignments=frozenset({"a", "b", "c", "d", "e", "f"}),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.status == WorkSlotStatus.QUEUED


class TestNoDuplicateAssignments:
    """Test no duplicate assignments across team."""

    def test_target_already_in_team_denied(self):
        """Target already in team assignments is denied."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        from python.phase11_scheduling.scheduling_context import (
            WorkerProfile, WorkTarget, SchedulingPolicy, WorkAssignmentContext
        )
        from python.phase11_scheduling.scheduling_engine import assign_work

        worker = WorkerProfile(
            worker_id="W-002", worker_type="standard",
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
        # Target T-001 already in team assignments
        context = WorkAssignmentContext(
            request_id="REQ-003", worker=worker, target=target,
            policy=policy, current_assignments=frozenset(),
            team_assignments=frozenset({"T-001"})
        )

        result = assign_work(context)
        assert result.assigned is False
        assert result.status == WorkSlotStatus.DENIED
        assert "DN-002" in result.reason_code

    def test_same_user_cannot_have_duplicate(self):
        """Same user cannot have duplicate target assignment."""
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
        # T-001 already in current assignments
        context = WorkAssignmentContext(
            request_id="REQ-004", worker=worker, target=target,
            policy=policy, current_assignments=frozenset({"T-001"}),
            team_assignments=frozenset({"T-001"})
        )

        result = assign_work(context)
        assert result.assigned is False


class TestCapabilityAwareAssignment:
    """Test capability-aware assignment."""

    def test_gpu_worker_for_gpu_target(self):
        """GPU worker can be assigned GPU target."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        from python.phase11_scheduling.scheduling_context import (
            WorkerProfile, WorkTarget, SchedulingPolicy, WorkAssignmentContext
        )
        from python.phase11_scheduling.scheduling_engine import assign_work

        worker = WorkerProfile(
            worker_id="W-003", worker_type="premium",
            max_parallel=5, has_gpu=True, gpu_memory_gb=8, active=True
        )
        target = WorkTarget(
            target_id="T-002", difficulty="high",
            requires_gpu=True, min_gpu_memory_gb=4
        )
        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        context = WorkAssignmentContext(
            request_id="REQ-005", worker=worker, target=target,
            policy=policy, current_assignments=frozenset(),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.assigned is True

    def test_non_gpu_worker_denied_gpu_target(self):
        """Non-GPU worker cannot be assigned GPU target."""
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
            target_id="T-002", difficulty="high",
            requires_gpu=True, min_gpu_memory_gb=4
        )
        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        context = WorkAssignmentContext(
            request_id="REQ-006", worker=worker, target=target,
            policy=policy, current_assignments=frozenset(),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.assigned is False
        assert "DN-001" in result.reason_code


class TestLoadClassification:
    """Test load classification logic."""

    def test_get_worker_load_returns_count(self):
        """get_worker_load returns assignment count."""
        from python.phase11_scheduling.scheduling_engine import get_worker_load

        load = get_worker_load(frozenset({"a", "b", "c"}))
        assert load == 3

    def test_classify_load_light(self):
        """classify_load correctly identifies light load."""
        from python.phase11_scheduling.scheduling_types import WorkerLoadLevel
        from python.phase11_scheduling.scheduling_context import SchedulingPolicy
        from python.phase11_scheduling.scheduling_engine import classify_load

        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        level = classify_load(1, policy)
        assert level == WorkerLoadLevel.LIGHT

    def test_classify_load_heavy(self):
        """classify_load correctly identifies heavy load."""
        from python.phase11_scheduling.scheduling_types import WorkerLoadLevel
        from python.phase11_scheduling.scheduling_context import SchedulingPolicy
        from python.phase11_scheduling.scheduling_engine import classify_load

        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        level = classify_load(7, policy)
        assert level == WorkerLoadLevel.HEAVY

    def test_classify_load_medium(self):
        """classify_load correctly identifies medium load."""
        from python.phase11_scheduling.scheduling_types import WorkerLoadLevel
        from python.phase11_scheduling.scheduling_context import SchedulingPolicy
        from python.phase11_scheduling.scheduling_engine import classify_load

        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        level = classify_load(4, policy)
        assert level == WorkerLoadLevel.MEDIUM


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_phase12_import(self):
        """No phase12+ imports."""
        import python.phase11_scheduling.scheduling_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'phase12' not in source
