"""
Phase-29 Types Tests.

Tests for CLOSED enums:
- ExecutionLoopState: 5 members
- LoopTransition: 4 members

Tests enforce:
- Exact member counts (closedness)
- No additional members
- Correct member names/values
"""
import pytest

from impl_v1.phase29.phase29_types import (
    ExecutionLoopState,
    LoopTransition,
)


class TestExecutionLoopStateEnum:
    """Tests for ExecutionLoopState enum closedness."""

    def test_execution_loop_state_has_exactly_5_members(self) -> None:
        """ExecutionLoopState must have exactly 5 members."""
        assert len(ExecutionLoopState) == 5

    def test_execution_loop_state_has_initialized(self) -> None:
        """ExecutionLoopState must have INITIALIZED."""
        assert ExecutionLoopState.INITIALIZED is not None
        assert ExecutionLoopState.INITIALIZED.name == "INITIALIZED"

    def test_execution_loop_state_has_ready(self) -> None:
        """ExecutionLoopState must have READY."""
        assert ExecutionLoopState.READY is not None
        assert ExecutionLoopState.READY.name == "READY"

    def test_execution_loop_state_has_dispatched(self) -> None:
        """ExecutionLoopState must have DISPATCHED."""
        assert ExecutionLoopState.DISPATCHED is not None
        assert ExecutionLoopState.DISPATCHED.name == "DISPATCHED"

    def test_execution_loop_state_has_awaiting_response(self) -> None:
        """ExecutionLoopState must have AWAITING_RESPONSE."""
        assert ExecutionLoopState.AWAITING_RESPONSE is not None
        assert ExecutionLoopState.AWAITING_RESPONSE.name == "AWAITING_RESPONSE"

    def test_execution_loop_state_has_halted(self) -> None:
        """ExecutionLoopState must have HALTED."""
        assert ExecutionLoopState.HALTED is not None
        assert ExecutionLoopState.HALTED.name == "HALTED"

    def test_execution_loop_state_all_members_listed(self) -> None:
        """All ExecutionLoopState members must be exactly as expected."""
        expected = {"INITIALIZED", "READY", "DISPATCHED", "AWAITING_RESPONSE", "HALTED"}
        actual = {m.name for m in ExecutionLoopState}
        assert actual == expected

    def test_execution_loop_state_members_are_distinct(self) -> None:
        """All ExecutionLoopState members must have distinct values."""
        values = [m.value for m in ExecutionLoopState]
        assert len(values) == len(set(values))


class TestLoopTransitionEnum:
    """Tests for LoopTransition enum closedness."""

    def test_loop_transition_has_exactly_4_members(self) -> None:
        """LoopTransition must have exactly 4 members."""
        assert len(LoopTransition) == 4

    def test_loop_transition_has_init(self) -> None:
        """LoopTransition must have INIT."""
        assert LoopTransition.INIT is not None
        assert LoopTransition.INIT.name == "INIT"

    def test_loop_transition_has_dispatch(self) -> None:
        """LoopTransition must have DISPATCH."""
        assert LoopTransition.DISPATCH is not None
        assert LoopTransition.DISPATCH.name == "DISPATCH"

    def test_loop_transition_has_receive(self) -> None:
        """LoopTransition must have RECEIVE."""
        assert LoopTransition.RECEIVE is not None
        assert LoopTransition.RECEIVE.name == "RECEIVE"

    def test_loop_transition_has_halt(self) -> None:
        """LoopTransition must have HALT."""
        assert LoopTransition.HALT is not None
        assert LoopTransition.HALT.name == "HALT"

    def test_loop_transition_all_members_listed(self) -> None:
        """All LoopTransition members must be exactly as expected."""
        expected = {"INIT", "DISPATCH", "RECEIVE", "HALT"}
        actual = {m.name for m in LoopTransition}
        assert actual == expected

    def test_loop_transition_members_are_distinct(self) -> None:
        """All LoopTransition members must have distinct values."""
        values = [m.value for m in LoopTransition]
        assert len(values) == len(set(values))
