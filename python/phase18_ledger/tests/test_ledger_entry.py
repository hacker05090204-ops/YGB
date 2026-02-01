"""
Tests for Phase-18 Ledger Entry.

Tests:
- Transition state
- Ledger entry creation
"""
import pytest


class TestTransitionState:
    """Test state transitions."""

    def test_transition_requested_to_allowed(self):
        """Transition from REQUESTED to ALLOWED."""
        from python.phase18_ledger.ledger_engine import create_execution_record, transition_state
        from python.phase18_ledger.ledger_types import ExecutionState

        record = create_execution_record(
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            timestamp="2026-01-25T08:35:00-05:00"
        )

        entry = transition_state(record, ExecutionState.ALLOWED, "2026-01-25T08:36:00-05:00")

        assert entry.from_state == ExecutionState.REQUESTED
        assert entry.to_state == ExecutionState.ALLOWED

    def test_transition_allowed_to_attempted(self):
        """Transition from ALLOWED to ATTEMPTED."""
        from python.phase18_ledger.ledger_context import ExecutionRecord
        from python.phase18_ledger.ledger_engine import transition_state
        from python.phase18_ledger.ledger_types import ExecutionState

        record = ExecutionRecord(
            execution_id="EXEC-001",
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            created_at="2026-01-25T08:35:00-05:00",
            current_state=ExecutionState.ALLOWED
        )

        entry = transition_state(record, ExecutionState.ATTEMPTED, "2026-01-25T08:36:00-05:00")

        assert entry.to_state == ExecutionState.ATTEMPTED


class TestLedgerEntryFrozen:
    """Test ledger entry immutability."""

    def test_ledger_entry_is_frozen(self):
        """ExecutionLedgerEntry is frozen."""
        from python.phase18_ledger.ledger_engine import create_execution_record, transition_state
        from python.phase18_ledger.ledger_types import ExecutionState

        record = create_execution_record(
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            timestamp="2026-01-25T08:35:00-05:00"
        )

        entry = transition_state(record, ExecutionState.ALLOWED, "2026-01-25T08:36:00-05:00")

        with pytest.raises(Exception):
            entry.reason = "modified"
