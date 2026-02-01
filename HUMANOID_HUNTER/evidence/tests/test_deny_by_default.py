"""
Tests for Phase-23 Deny-By-Default.

Tests:
- Immutability
- Invalid schema rejection
"""
import pytest


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_evidence_envelope_frozen(self):
        """EvidenceEnvelope is frozen."""
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

        with pytest.raises(Exception):
            envelope.evidence_id = "MODIFIED"

    def test_verification_context_frozen(self):
        """EvidenceVerificationContext is frozen."""
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope, EvidenceVerificationContext
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

        context = EvidenceVerificationContext(
            envelope=envelope,
            expected_execution_id="EXEC-001",
            expected_format=EvidenceFormat.JSON,
            expected_hash="abc123",
            known_hashes=frozenset(),
            timestamp="2026-01-25T16:38:00-05:00"
        )

        with pytest.raises(Exception):
            context.expected_execution_id = "MODIFIED"

    def test_verification_result_frozen(self):
        """EvidenceVerificationResult is frozen."""
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceVerificationResult
        from HUMANOID_HUNTER.evidence.evidence_types import VerificationDecision, EvidenceIntegrityStatus

        result = EvidenceVerificationResult(
            decision=VerificationDecision.ACCEPT,
            integrity_status=EvidenceIntegrityStatus.VALID,
            reason_code="OK",
            reason_description="Valid"
        )

        with pytest.raises(Exception):
            result.decision = VerificationDecision.REJECT


class TestInvalidSchemaRejection:
    """Test invalid schema rejection."""

    def test_invalid_schema_rejected(self):
        """Invalid schema leads to rejection."""
        from HUMANOID_HUNTER.evidence.evidence_engine import decide_evidence_acceptance
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope, EvidenceVerificationContext
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat, VerificationDecision, EvidenceIntegrityStatus

        envelope = EvidenceEnvelope(
            evidence_id="",  # Invalid!
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="abc123",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        context = EvidenceVerificationContext(
            envelope=envelope,
            expected_execution_id="EXEC-001",
            expected_format=EvidenceFormat.JSON,
            expected_hash="abc123",
            known_hashes=frozenset(),
            timestamp="2026-01-25T16:38:00-05:00"
        )

        result = decide_evidence_acceptance(context)
        assert result.decision == VerificationDecision.REJECT
        assert result.integrity_status == EvidenceIntegrityStatus.INVALID
