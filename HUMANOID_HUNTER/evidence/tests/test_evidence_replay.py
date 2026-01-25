"""
Tests for Phase-23 Evidence Replay Detection.

Tests:
- detect_evidence_replay for known/unknown hashes
"""
import pytest


class TestDetectEvidenceReplay:
    """Test evidence replay detection."""

    def test_known_hash_is_replay(self):
        """Known hash is detected as replay."""
        from HUMANOID_HUNTER.evidence.evidence_engine import detect_evidence_replay
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="hash_already_seen",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        known_hashes = frozenset({"hash_already_seen", "another_old_hash"})
        assert detect_evidence_replay(envelope, known_hashes) is True

    def test_unknown_hash_is_not_replay(self):
        """Unknown hash is not replay."""
        from HUMANOID_HUNTER.evidence.evidence_engine import detect_evidence_replay
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="brand_new_hash",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        known_hashes = frozenset({"old_hash_1", "old_hash_2"})
        assert detect_evidence_replay(envelope, known_hashes) is False

    def test_empty_known_hashes_is_not_replay(self):
        """Empty known hashes never triggers replay."""
        from HUMANOID_HUNTER.evidence.evidence_engine import detect_evidence_replay
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="any_hash",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        known_hashes = frozenset()
        assert detect_evidence_replay(envelope, known_hashes) is False


class TestDecideEvidenceAcceptance:
    """Test evidence acceptance decision."""

    def test_valid_evidence_accepted(self):
        """Valid evidence is accepted."""
        from HUMANOID_HUNTER.evidence.evidence_engine import decide_evidence_acceptance
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope, EvidenceVerificationContext
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat, VerificationDecision

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="valid_hash",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        context = EvidenceVerificationContext(
            envelope=envelope,
            expected_execution_id="EXEC-001",
            expected_format=EvidenceFormat.JSON,
            expected_hash="valid_hash",
            known_hashes=frozenset(),
            timestamp="2026-01-25T16:38:00-05:00"
        )

        result = decide_evidence_acceptance(context)
        assert result.decision == VerificationDecision.ACCEPT

    def test_replay_evidence_rejected(self):
        """Replay evidence is rejected."""
        from HUMANOID_HUNTER.evidence.evidence_engine import decide_evidence_acceptance
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope, EvidenceVerificationContext
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat, VerificationDecision, EvidenceIntegrityStatus

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="replayed_hash",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        context = EvidenceVerificationContext(
            envelope=envelope,
            expected_execution_id="EXEC-001",
            expected_format=EvidenceFormat.JSON,
            expected_hash="replayed_hash",
            known_hashes=frozenset({"replayed_hash"}),  # Replay!
            timestamp="2026-01-25T16:38:00-05:00"
        )

        result = decide_evidence_acceptance(context)
        assert result.decision == VerificationDecision.REJECT
        assert result.integrity_status == EvidenceIntegrityStatus.REPLAY

    def test_hash_mismatch_rejected(self):
        """Hash mismatch is rejected."""
        from HUMANOID_HUNTER.evidence.evidence_engine import decide_evidence_acceptance
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope, EvidenceVerificationContext
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat, VerificationDecision, EvidenceIntegrityStatus

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="actual_hash",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        context = EvidenceVerificationContext(
            envelope=envelope,
            expected_execution_id="EXEC-001",
            expected_format=EvidenceFormat.JSON,
            expected_hash="different_expected_hash",  # Mismatch!
            known_hashes=frozenset(),
            timestamp="2026-01-25T16:38:00-05:00"
        )

        result = decide_evidence_acceptance(context)
        assert result.decision == VerificationDecision.REJECT
        assert result.integrity_status == EvidenceIntegrityStatus.TAMPERED

    def test_execution_id_mismatch_rejected(self):
        """Execution ID mismatch is rejected."""
        from HUMANOID_HUNTER.evidence.evidence_engine import decide_evidence_acceptance
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope, EvidenceVerificationContext
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat, VerificationDecision

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,
            content_hash="valid_hash",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        context = EvidenceVerificationContext(
            envelope=envelope,
            expected_execution_id="EXEC-999",  # Mismatch!
            expected_format=EvidenceFormat.JSON,
            expected_hash="valid_hash",
            known_hashes=frozenset(),
            timestamp="2026-01-25T16:38:00-05:00"
        )

        result = decide_evidence_acceptance(context)
        assert result.decision == VerificationDecision.REJECT

    def test_format_mismatch_rejected(self):
        """Format mismatch is rejected."""
        from HUMANOID_HUNTER.evidence.evidence_engine import decide_evidence_acceptance
        from HUMANOID_HUNTER.evidence.evidence_context import EvidenceEnvelope, EvidenceVerificationContext
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat, VerificationDecision, EvidenceIntegrityStatus

        envelope = EvidenceEnvelope(
            evidence_id="EVD-001",
            execution_id="EXEC-001",
            evidence_format=EvidenceFormat.JSON,  # Actual format
            content_hash="valid_hash",
            timestamp="2026-01-25T16:38:00-05:00",
            schema_version="1.0",
            required_fields=("evidence_id", "execution_id", "content_hash")
        )

        context = EvidenceVerificationContext(
            envelope=envelope,
            expected_execution_id="EXEC-001",
            expected_format=EvidenceFormat.SCREENSHOT,  # Expected different format!
            expected_hash="valid_hash",
            known_hashes=frozenset(),
            timestamp="2026-01-25T16:38:00-05:00"
        )

        result = decide_evidence_acceptance(context)
        assert result.decision == VerificationDecision.REJECT
        assert result.integrity_status == EvidenceIntegrityStatus.INVALID
