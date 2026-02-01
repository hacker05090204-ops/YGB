"""
Tests for Phase-18 Evidence Record.

Tests:
- Attach evidence
- Evidence status
- Evidence hash validation
"""
import pytest


class TestAttachEvidence:
    """Test evidence attachment."""

    def test_attach_evidence_success(self):
        """Attach evidence to execution."""
        from python.phase18_ledger.ledger_engine import attach_evidence
        from python.phase18_ledger.ledger_types import EvidenceStatus

        evidence, result = attach_evidence(
            execution_id="EXEC-001",
            evidence_hash="abc123def456",
            timestamp="2026-01-25T08:35:00-05:00",
            used_hashes=frozenset()
        )

        assert evidence.evidence_status == EvidenceStatus.LINKED
        assert result.is_valid is True

    def test_empty_hash_invalid(self):
        """Empty evidence hash is invalid."""
        from python.phase18_ledger.ledger_engine import attach_evidence

        evidence, result = attach_evidence(
            execution_id="EXEC-001",
            evidence_hash="",
            timestamp="2026-01-25T08:35:00-05:00",
            used_hashes=frozenset()
        )

        assert result.is_valid is False
        assert result.reason_code == "EV-001"


class TestEvidenceRecordFrozen:
    """Test evidence record immutability."""

    def test_evidence_record_is_frozen(self):
        """EvidenceRecord is frozen."""
        from python.phase18_ledger.ledger_engine import attach_evidence

        evidence, _ = attach_evidence(
            execution_id="EXEC-001",
            evidence_hash="abc123",
            timestamp="2026-01-25T08:35:00-05:00",
            used_hashes=frozenset()
        )

        with pytest.raises(Exception):
            evidence.evidence_hash = "modified"
