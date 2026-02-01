"""
Tests for Phase-18 Deny-By-Default.

Tests:
- Unknown values → DENIED
- Missing values → DENIED
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_decide_retry_completed_denied(self):
        """Retry on COMPLETED is denied."""
        from python.phase18_ledger.ledger_context import ExecutionRecord
        from python.phase18_ledger.ledger_engine import decide_retry
        from python.phase18_ledger.ledger_types import ExecutionState, RetryDecision

        record = ExecutionRecord(
            execution_id="EXEC-001",
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            created_at="2026-01-25T08:35:00-05:00",
            current_state=ExecutionState.COMPLETED
        )

        decision = decide_retry(record)
        assert decision == RetryDecision.DENIED

    def test_decide_retry_escalated_human_required(self):
        """Retry on ESCALATED requires human."""
        from python.phase18_ledger.ledger_context import ExecutionRecord
        from python.phase18_ledger.ledger_engine import decide_retry
        from python.phase18_ledger.ledger_types import ExecutionState, RetryDecision

        record = ExecutionRecord(
            execution_id="EXEC-001",
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            created_at="2026-01-25T08:35:00-05:00",
            current_state=ExecutionState.ESCALATED
        )

        decision = decide_retry(record)
        assert decision == RetryDecision.HUMAN_REQUIRED

    def test_decide_retry_max_attempts_denied(self):
        """Retry at max attempts is denied."""
        from python.phase18_ledger.ledger_context import ExecutionRecord
        from python.phase18_ledger.ledger_engine import decide_retry
        from python.phase18_ledger.ledger_types import ExecutionState, RetryDecision

        record = ExecutionRecord(
            execution_id="EXEC-001",
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            created_at="2026-01-25T08:35:00-05:00",
            current_state=ExecutionState.FAILED,
            attempt_count=3,
            max_attempts=3
        )

        decision = decide_retry(record)
        assert decision == RetryDecision.DENIED

    def test_decide_retry_failed_allowed(self):
        """Retry on FAILED with attempts remaining is allowed."""
        from python.phase18_ledger.ledger_context import ExecutionRecord
        from python.phase18_ledger.ledger_engine import decide_retry
        from python.phase18_ledger.ledger_types import ExecutionState, RetryDecision

        record = ExecutionRecord(
            execution_id="EXEC-001",
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            created_at="2026-01-25T08:35:00-05:00",
            current_state=ExecutionState.FAILED,
            attempt_count=1,
            max_attempts=3
        )

        decision = decide_retry(record)
        assert decision == RetryDecision.ALLOWED


class TestValidateEvidenceLinkage:
    """Test evidence linkage validation."""

    def test_missing_evidence_invalid(self):
        """MISSING evidence is invalid."""
        from python.phase18_ledger.ledger_context import EvidenceRecord
        from python.phase18_ledger.ledger_engine import validate_evidence_linkage
        from python.phase18_ledger.ledger_types import EvidenceStatus

        evidence = EvidenceRecord(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_hash="",
            evidence_status=EvidenceStatus.MISSING,
            linked_at="2026-01-25T08:35:00-05:00"
        )

        result = validate_evidence_linkage(evidence)
        assert result.is_valid is False

    def test_linked_evidence_valid(self):
        """LINKED evidence is valid."""
        from python.phase18_ledger.ledger_context import EvidenceRecord
        from python.phase18_ledger.ledger_engine import validate_evidence_linkage
        from python.phase18_ledger.ledger_types import EvidenceStatus

        evidence = EvidenceRecord(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_hash="abc123",
            evidence_status=EvidenceStatus.LINKED,
            linked_at="2026-01-25T08:35:00-05:00"
        )

        result = validate_evidence_linkage(evidence)
        assert result.is_valid is True

    def test_invalid_evidence_invalid(self):
        """INVALID evidence is invalid."""
        from python.phase18_ledger.ledger_context import EvidenceRecord
        from python.phase18_ledger.ledger_engine import validate_evidence_linkage
        from python.phase18_ledger.ledger_types import EvidenceStatus

        evidence = EvidenceRecord(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_hash="abc123",
            evidence_status=EvidenceStatus.INVALID,
            linked_at="2026-01-25T08:35:00-05:00"
        )

        result = validate_evidence_linkage(evidence)
        assert result.is_valid is False
        assert result.reason_code == "EV-004"

    def test_linked_empty_hash_invalid(self):
        """LINKED with empty hash is invalid."""
        from python.phase18_ledger.ledger_context import EvidenceRecord
        from python.phase18_ledger.ledger_engine import validate_evidence_linkage
        from python.phase18_ledger.ledger_types import EvidenceStatus

        evidence = EvidenceRecord(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_hash="",
            evidence_status=EvidenceStatus.LINKED,
            linked_at="2026-01-25T08:35:00-05:00"
        )

        result = validate_evidence_linkage(evidence)
        assert result.is_valid is False
        assert result.reason_code == "EV-005"

    def test_decide_retry_default_denied(self):
        """Default retry decision is DENIED."""
        from python.phase18_ledger.ledger_context import ExecutionRecord
        from python.phase18_ledger.ledger_engine import decide_retry
        from python.phase18_ledger.ledger_types import ExecutionState, RetryDecision

        record = ExecutionRecord(
            execution_id="EXEC-001",
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            created_at="2026-01-25T08:35:00-05:00",
            current_state=ExecutionState.REQUESTED  # Not FAILED, COMPLETED, or ESCALATED
        )

        decision = decide_retry(record)
        assert decision == RetryDecision.DENIED
