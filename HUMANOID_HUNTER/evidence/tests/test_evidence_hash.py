"""
Tests for Phase-23 Evidence Hash Verification.

Tests:
- verify_evidence_hash for matching/mismatching hashes
"""
import pytest


class TestVerifyEvidenceHash:
    """Test evidence hash verification."""

    def test_matching_hash_returns_true(self):
        """Matching hash returns True."""
        from HUMANOID_HUNTER.evidence.evidence_engine import verify_evidence_hash
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="expected_hash_123",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert verify_evidence_hash(envelope, "expected_hash_123") is True

    def test_mismatching_hash_returns_false(self):
        """Mismatching hash returns False."""
        from HUMANOID_HUNTER.evidence.evidence_engine import verify_evidence_hash
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="actual_hash",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert verify_evidence_hash(envelope, "different_expected_hash") is False

    def test_empty_expected_hash_returns_false(self):
        """Empty expected hash returns False."""
        from HUMANOID_HUNTER.evidence.evidence_engine import verify_evidence_hash
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="abc123",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert verify_evidence_hash(envelope, "") is False

    def test_empty_envelope_hash_returns_false(self):
        """Empty envelope hash returns False."""
        from HUMANOID_HUNTER.evidence.evidence_engine import verify_evidence_hash
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="",  # Empty!
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert verify_evidence_hash(envelope, "expected") is False
