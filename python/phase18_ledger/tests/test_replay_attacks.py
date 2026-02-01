"""
Tests for Phase-18 Replay Attacks.

Tests:
- Replayed evidence hash → DENIED
- Duplicate execution → DENIED
"""
import pytest


class TestReplayAttacks:
    """Test replay attack prevention."""

    def test_replayed_evidence_hash_denied(self):
        """Replayed evidence hash is denied."""
        from python.phase18_ledger.ledger_engine import attach_evidence

        used_hashes = frozenset({"abc123", "def456"})

        evidence, result = attach_evidence(
            execution_id="EXEC-001",
            evidence_hash="abc123",  # Already used
            timestamp="2026-01-25T08:35:00-05:00",
            used_hashes=used_hashes
        )

        assert result.is_valid is False
        assert result.reason_code == "EV-002"

    def test_new_evidence_hash_allowed(self):
        """New evidence hash is allowed."""
        from python.phase18_ledger.ledger_engine import attach_evidence
        from python.phase18_ledger.ledger_types import EvidenceStatus

        used_hashes = frozenset({"abc123", "def456"})

        evidence, result = attach_evidence(
            execution_id="EXEC-001",
            evidence_hash="xyz789",  # New hash
            timestamp="2026-01-25T08:35:00-05:00",
            used_hashes=used_hashes
        )

        assert result.is_valid is True
        assert evidence.evidence_status == EvidenceStatus.LINKED


class TestDuplicatePrevention:
    """Test duplicate prevention."""

    def test_multiple_success_denied(self):
        """Multiple SUCCESS for same execution denied."""
        from python.phase18_ledger.ledger_context import ExecutionRecord
        from python.phase18_ledger.ledger_engine import transition_state
        from python.phase18_ledger.ledger_types import ExecutionState

        record = ExecutionRecord(
            execution_id="EXEC-001",
            request_id="REQ-001",
            bug_id="BUG-001",
            target_id="TARGET-001",
            created_at="2026-01-25T08:35:00-05:00",
            current_state=ExecutionState.COMPLETED,  # Already completed
            finalized=True
        )

        # Should not allow transition from COMPLETED
        entry = transition_state(record, ExecutionState.COMPLETED, "2026-01-25T08:36:00-05:00")
        assert "DENIED" in entry.reason
