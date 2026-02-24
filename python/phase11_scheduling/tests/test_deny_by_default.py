"""
Tests for Phase-11 Deny-By-Default.

Tests:
- Unknown cases denied
- Inactive policy denied
- Inactive worker denied
- No guessing
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_inactive_policy_denied(self):
        """Inactive policy results in denial."""
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
            medium_load_threshold=5, allow_gpu_override=False, active=False  # INACTIVE
        )
        context = WorkAssignmentContext(
            request_id="REQ-001", worker=worker, target=target,
            policy=policy, current_assignments=frozenset(),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.assigned is False
        assert "DN-004" in result.reason_code

    def test_inactive_worker_denied(self):
        """Inactive worker results in denial."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        from python.phase11_scheduling.scheduling_context import (
            WorkerProfile, WorkTarget, SchedulingPolicy, WorkAssignmentContext
        )
        from python.phase11_scheduling.scheduling_engine import assign_work

        worker = WorkerProfile(
            worker_id="W-001", worker_type="standard",
            max_parallel=5, has_gpu=False, gpu_memory_gb=0, active=False  # INACTIVE
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
            policy=policy, current_assignments=frozenset(),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.assigned is False
        assert "DN-005" in result.reason_code


class TestAssignmentResult:
    """Test AssignmentResult dataclass."""

    def test_assignment_result_is_frozen(self):
        """AssignmentResult is frozen."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        from python.phase11_scheduling.scheduling_engine import AssignmentResult

        result = AssignmentResult(
            request_id="REQ-001",
            target_id="T-001",
            status=WorkSlotStatus.ASSIGNED,
            assigned=True,
            reason_code="AS-001",
            reason_description="Assignment granted",
            worker_id="W-001"
        )

        with pytest.raises(Exception):
            result.assigned = False


class TestDeterminism:
    """Test same input produces same output."""

    def test_same_context_same_result(self):
        """Same context produces same result."""
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
            request_id="REQ-001", worker=worker, target=target,
            policy=policy, current_assignments=frozenset(),
            team_assignments=frozenset()
        )

        result1 = assign_work(context)
        result2 = assign_work(context)
        result3 = assign_work(context)

        assert result1.assigned == result2.assigned == result3.assigned
        assert result1.reason_code == result2.reason_code == result3.reason_code


class TestEnumsClosed:
    """Test enums are closed."""

    def test_work_slot_status_has_six_members(self):
        """WorkSlotStatus has exactly 6 members."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        assert len(WorkSlotStatus) == 6

    def test_worker_load_level_has_three_members(self):
        """WorkerLoadLevel has exactly 3 members."""
        from python.phase11_scheduling.scheduling_types import WorkerLoadLevel
        assert len(WorkerLoadLevel) == 3


class TestNoForbiddenImportsInAllFiles:
    """Test no forbidden imports in any file."""

    def test_no_os_import(self):
        """No os import in any module."""
        import python.phase11_scheduling.scheduling_types as types_module
        import python.phase11_scheduling.scheduling_context as context_module
        import python.phase11_scheduling.scheduling_engine as engine_module
        import inspect

        for module in [types_module, context_module, engine_module]:
            source = inspect.getsource(module)
            assert 'import os' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase11_scheduling.scheduling_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_socket_import(self):
        """No socket import."""
        import python.phase11_scheduling.scheduling_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import socket' not in source

    def test_no_exec_eval(self):
        """No exec or eval in any file."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'exec(' not in content, f"Found exec( in {filename}"
                    assert 'eval(' not in content, f"Found eval( in {filename}"

    def test_no_phase12_import(self):
        """No phase12+ imports in implementation files (test files excluded)."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '').replace('\\tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase12' not in content, f"Found phase12 in {filename}"
