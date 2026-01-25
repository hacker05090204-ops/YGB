"""
Tests for Phase-23 Evidence Schema Validation.

Tests:
- validate_evidence_schema for valid/invalid envelopes
- Required fields checking
"""
import pytest


class TestValidateEvidenceSchema:
    """Test evidence schema validation."""

    def test_valid_schema_returns_true(self):
        """Valid schema returns True."""
        from HUMANOID_HUNTER.evidence.evidence_engine import validate_evidence_schema
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

        assert validate_evidence_schema(envelope) is True

    def test_empty_evidence_id_returns_false(self):
        """Empty evidence_id returns False."""
        from HUMANOID_HUNTER.evidence.evidence_engine import validate_evidence_schema
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="",  # Invalid!
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="abc123",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert validate_evidence_schema(envelope) is False

    def test_empty_execution_id_returns_false(self):
        """Empty execution_id returns False."""
        from HUMANOID_HUNTER.evidence.evidence_engine import validate_evidence_schema
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="",  # Invalid!
            evidence_format=EvidenceFormat.JSON,
            content_hash="abc123",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert validate_evidence_schema(envelope) is False

    def test_empty_content_hash_returns_false(self):
        """Empty content_hash returns False."""
        from HUMANOID_HUNTER.evidence.evidence_engine import validate_evidence_schema
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="",  # Invalid!
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert validate_evidence_schema(envelope) is False

    def test_empty_timestamp_returns_false(self):
        """Empty timestamp returns False."""
        from HUMANOID_HUNTER.evidence.evidence_engine import validate_evidence_schema
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="abc123",
            timestamp="",  # Invalid!
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert validate_evidence_schema(envelope) is False

    def test_empty_schema_version_returns_false(self):
        """Empty schema_version returns False."""
        from HUMANOID_HUNTER.evidence.evidence_engine import validate_evidence_schema
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="abc123",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="",  # Invalid!
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        assert validate_evidence_schema(envelope) is False
