# test_g01_execution_kernel.py
"""Tests for G01: Execution Kernel"""

import pytest
from impl_v1.phase49.governors.g01_execution_kernel import (
    ExecutionState,
    ExecutionTransition,
    TransitionResult,
    ExecutionKernel,
    create_execution_kernel,
    VALID_TRANSITIONS,
)


class TestEnumClosure:
    """Verify enums are closed (cannot be extended)."""
    
    def test_execution_state_6_members(self):
        assert len(ExecutionState) == 6
    
    def test_execution_transition_7_members(self):
        assert len(ExecutionTransition) == 7
    
    def test_transition_result_3_members(self):
        assert len(TransitionResult) == 3


class TestExecutionKernel:
    """Test execution kernel state machine."""
    
    def test_initial_state_is_idle(self):
        kernel = create_execution_kernel()
        assert kernel.state == ExecutionState.IDLE
    
    def test_session_id_generated(self):
        kernel = create_execution_kernel()
        assert kernel.session_id.startswith("SESS-")
    
    def test_custom_session_id(self):
        kernel = create_execution_kernel("MY-SESSION-123")
        assert kernel.session_id == "MY-SESSION-123"
    
    def test_idle_to_planned(self):
        kernel = create_execution_kernel()
        result = kernel.transition(ExecutionTransition.PLAN, "user-1")
        assert result.result == TransitionResult.SUCCESS
        assert kernel.state == ExecutionState.PLANNED
    
    def test_planned_to_simulated(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "user-1")
        result = kernel.transition(ExecutionTransition.SIMULATE, "user-1")
        assert result.result == TransitionResult.SUCCESS
        assert kernel.state == ExecutionState.SIMULATED
    
    def test_simulated_to_await_human(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "user-1")
        kernel.transition(ExecutionTransition.SIMULATE, "user-1")
        result = kernel.transition(ExecutionTransition.REQUEST_APPROVAL, "system")
        assert result.result == TransitionResult.SUCCESS
        assert kernel.state == ExecutionState.AWAIT_HUMAN
    
    def test_human_approve_to_executing(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "user-1")
        kernel.transition(ExecutionTransition.SIMULATE, "user-1")
        kernel.transition(ExecutionTransition.REQUEST_APPROVAL, "system")
        result = kernel.transition(ExecutionTransition.HUMAN_APPROVE, "human-1")
        assert result.result == TransitionResult.SUCCESS
        assert kernel.state == ExecutionState.EXECUTING
        assert kernel.human_approved
    
    def test_human_deny_to_stopped(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "user-1")
        kernel.transition(ExecutionTransition.SIMULATE, "user-1")
        kernel.transition(ExecutionTransition.REQUEST_APPROVAL, "system")
        result = kernel.transition(ExecutionTransition.HUMAN_DENY, "human-1", "Not safe")
        assert result.result == TransitionResult.SUCCESS
        assert kernel.state == ExecutionState.STOPPED
        assert kernel.deny_reason == "Not safe"


class TestTerminalState:
    """Test STOPPED is terminal."""
    
    def test_stopped_is_terminal(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.ABORT, "user-1")
        assert kernel.is_terminal
    
    def test_cannot_transition_from_stopped(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.ABORT, "user-1")
        result = kernel.transition(ExecutionTransition.PLAN, "user-1")
        assert result.result == TransitionResult.DENIED
        assert kernel.state == ExecutionState.STOPPED


class TestInvalidTransitions:
    """Test invalid state transitions."""
    
    def test_idle_cannot_simulate(self):
        kernel = create_execution_kernel()
        result = kernel.transition(ExecutionTransition.SIMULATE, "user-1")
        assert result.result == TransitionResult.INVALID
        assert kernel.state == ExecutionState.IDLE
    
    def test_idle_cannot_approve(self):
        kernel = create_execution_kernel()
        result = kernel.transition(ExecutionTransition.HUMAN_APPROVE, "user-1")
        assert result.result == TransitionResult.INVALID


class TestAuditLog:
    """Test audit logging."""
    
    def test_transitions_logged(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "user-1")
        kernel.transition(ExecutionTransition.SIMULATE, "user-1")
        log = kernel.get_audit_log()
        assert len(log) == 2
        assert log[0].transition == ExecutionTransition.PLAN
        assert log[1].transition == ExecutionTransition.SIMULATE
    
    def test_audit_entry_has_timestamp(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "user-1")
        log = kernel.get_audit_log()
        assert log[0].timestamp is not None


class TestCanExecute:
    """Test can_execute guard."""
    
    def test_cannot_execute_without_approval(self):
        kernel = create_execution_kernel()
        assert not kernel.can_execute()
    
    def test_can_execute_after_approval(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "user-1")
        kernel.transition(ExecutionTransition.SIMULATE, "user-1")
        kernel.transition(ExecutionTransition.REQUEST_APPROVAL, "system")
        kernel.transition(ExecutionTransition.HUMAN_APPROVE, "human-1")
        assert kernel.can_execute()


class TestAbort:
    """Test abort from any state."""
    
    def test_abort_from_idle(self):
        kernel = create_execution_kernel()
        result = kernel.transition(ExecutionTransition.ABORT, "user-1")
        assert result.result == TransitionResult.SUCCESS
        assert kernel.state == ExecutionState.STOPPED
    
    def test_abort_from_planned(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "user-1")
        result = kernel.transition(ExecutionTransition.ABORT, "user-1")
        assert result.result == TransitionResult.SUCCESS
        assert kernel.state == ExecutionState.STOPPED
    
    def test_abort_from_executing(self):
        kernel = create_execution_kernel()
        kernel.transition(ExecutionTransition.PLAN, "u")
        kernel.transition(ExecutionTransition.SIMULATE, "u")
        kernel.transition(ExecutionTransition.REQUEST_APPROVAL, "s")
        kernel.transition(ExecutionTransition.HUMAN_APPROVE, "h")
        result = kernel.transition(ExecutionTransition.ABORT, "user-1")
        assert result.result == TransitionResult.SUCCESS
        assert kernel.state == ExecutionState.STOPPED
