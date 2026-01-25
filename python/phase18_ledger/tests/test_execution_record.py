"""
Tests for Phase-18 Execution Record.

Tests:
- Create execution record
- Unique execution ID
- Immutability
"""
import pytest


class TestCreateExecutionRecord:
    """Test execution record creation."""

    def test_create_execution_record(self):
        """Create valid execution record."""
        from python.phase18_ledger.ledger_engine import create_execution_record
        from python.phase18_ledger.ledger_types import ExecutionState

        record = create_execution_record(
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            timestamp="2026-01-25T08:35:00-05:00"
        )

        assert record.request_id == "REQ-001"
        assert record.current_state == ExecutionState.REQUESTED
        assert record.attempt_count == 0

    def test_execution_id_is_unique(self):
        """Each record has unique execution_id."""
        from python.phase18_ledger.ledger_engine import create_execution_record

        record1 = create_execution_record(
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            timestamp="2026-01-25T08:35:00-05:00"
        )
        record2 = create_execution_record(
            request_id="REQ-002",
            bug_id="BUG-002",
            target_id="TARGET-002",
            timestamp="2026-01-25T08:36:00-05:00"
        )

        assert record1.execution_id != record2.execution_id


class TestRecordAttempt:
    """Test record attempt."""

    def test_record_attempt_increments_count(self):
        """Record attempt increments attempt_count."""
        from python.phase18_ledger.ledger_engine import create_execution_record, record_attempt

        record = create_execution_record(
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            timestamp="2026-01-25T08:35:00-05:00"
        )

        updated = record_attempt(record)
        assert updated.attempt_count == 1

    def test_record_is_frozen(self):
        """ExecutionRecord is frozen."""
        from python.phase18_ledger.ledger_engine import create_execution_record

        record = create_execution_record(
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            timestamp="2026-01-25T08:35:00-05:00"
        )

        with pytest.raises(Exception):
            record.attempt_count = 5
