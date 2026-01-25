"""
Tests for Phase-18 State Transitions.

Tests:
- Valid state transitions
- Invalid state transitions → DENIED
"""
import pytest


class TestValidStateTransitions:
    """Test valid state transitions."""

    def test_requested_to_allowed(self):
        """REQUESTED → ALLOWED is valid."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.REQUESTED, ExecutionState.ALLOWED) is True

    def test_requested_to_escalated(self):
        """REQUESTED → ESCALATED is valid."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.REQUESTED, ExecutionState.ESCALATED) is True

    def test_allowed_to_attempted(self):
        """ALLOWED → ATTEMPTED is valid."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.ALLOWED, ExecutionState.ATTEMPTED) is True

    def test_attempted_to_failed(self):
        """ATTEMPTED → FAILED is valid."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.ATTEMPTED, ExecutionState.FAILED) is True

    def test_attempted_to_completed(self):
        """ATTEMPTED → COMPLETED is valid."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.ATTEMPTED, ExecutionState.COMPLETED) is True

    def test_failed_to_attempted(self):
        """FAILED → ATTEMPTED (retry) is valid."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.FAILED, ExecutionState.ATTEMPTED) is True


class TestInvalidStateTransitions:
    """Test invalid state transitions."""

    def test_completed_to_anything_invalid(self):
        """COMPLETED → anything is invalid."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.COMPLETED, ExecutionState.FAILED) is False
        assert is_valid_transition(ExecutionState.COMPLETED, ExecutionState.ATTEMPTED) is False
        assert is_valid_transition(ExecutionState.COMPLETED, ExecutionState.REQUESTED) is False

    def test_to_requested_invalid(self):
        """Any → REQUESTED is invalid."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.ATTEMPTED, ExecutionState.REQUESTED) is False
        assert is_valid_transition(ExecutionState.FAILED, ExecutionState.REQUESTED) is False

    def test_requested_to_completed_invalid(self):
        """REQUESTED → COMPLETED is invalid (skip states)."""
        from python.phase18_ledger.ledger_engine import is_valid_transition
        from python.phase18_ledger.ledger_types import ExecutionState

        assert is_valid_transition(ExecutionState.REQUESTED, ExecutionState.COMPLETED) is False
