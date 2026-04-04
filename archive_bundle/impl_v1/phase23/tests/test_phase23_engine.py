"""Phase-23 Engine Tests."""
import pytest
from impl_v1.phase23.phase23_types import (
    EvidenceFormat,
    EvidenceIntegrityStatus,
    VerificationDecision,
)
from impl_v1.phase23.phase23_context import (
    EvidenceEnvelope,
    EvidenceVerificationContext,
    EvidenceVerificationResult,
)
from impl_v1.phase23.phase23_engine import (
    validate_evidence_id,
    validate_evidence_format,
    validate_payload_hash,
    detect_replay,
    verify_evidence_integrity,
    get_verification_decision,
)


def _make_valid_envelope(
    evidence_id: str = "EVIDENCE-12345678",
    format: EvidenceFormat = EvidenceFormat.JSON,
    payload_hash: str = "hash123",
    prior_hash: str = "prior123",
    timestamp: str = "2026-01-26T12:00:00Z",
    source: str = "test_source",
    version: str = "1.0"
) -> EvidenceEnvelope:
    return EvidenceEnvelope(
        evidence_id=evidence_id,
        format=format,
        payload_hash=payload_hash,
        prior_hash=prior_hash,
        timestamp=timestamp,
        source=source,
        version=version
    )


def _make_valid_context(
    expected_format: EvidenceFormat = EvidenceFormat.JSON,
    expected_source: str = "test_source",
    allow_replay: bool = False
) -> EvidenceVerificationContext:
    return EvidenceVerificationContext(
        expected_format=expected_format,
        expected_source=expected_source,
        allow_replay=allow_replay
    )


class TestValidateEvidenceIdDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert validate_evidence_id(None) is False

    def test_non_string_returns_false(self) -> None:
        assert validate_evidence_id(123) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        assert validate_evidence_id("") is False

    def test_whitespace_returns_false(self) -> None:
        assert validate_evidence_id("   ") is False

    def test_invalid_format_returns_false(self) -> None:
        assert validate_evidence_id("INVALID-123") is False


class TestValidateEvidenceIdPositive:
    def test_valid_format_returns_true(self) -> None:
        assert validate_evidence_id("EVIDENCE-12345678") is True


class TestValidateEvidenceFormatDenyByDefault:
    def test_none_envelope_returns_false(self) -> None:
        assert validate_evidence_format(None, EvidenceFormat.JSON) is False

    def test_none_expected_returns_false(self) -> None:
        env = _make_valid_envelope()
        assert validate_evidence_format(env, None) is False

    def test_format_mismatch_returns_false(self) -> None:
        env = _make_valid_envelope(format=EvidenceFormat.TEXT)
        assert validate_evidence_format(env, EvidenceFormat.JSON) is False

    def test_invalid_format_type_returns_false(self) -> None:
        env = EvidenceEnvelope(
            evidence_id="EVIDENCE-12345678",
            format="JSON",  # type: ignore - not an enum
            payload_hash="hash",
            prior_hash="prior",
            timestamp="2026-01-26T12:00:00Z",
            source="test",
            version="1.0"
        )
        assert validate_evidence_format(env, EvidenceFormat.JSON) is False


class TestValidateEvidenceFormatPositive:
    def test_format_matches_returns_true(self) -> None:
        env = _make_valid_envelope(format=EvidenceFormat.JSON)
        assert validate_evidence_format(env, EvidenceFormat.JSON) is True


class TestValidatePayloadHashDenyByDefault:
    def test_none_envelope_returns_false(self) -> None:
        assert validate_payload_hash(None, "expected") is False

    def test_none_expected_returns_false(self) -> None:
        env = _make_valid_envelope()
        assert validate_payload_hash(env, None) is False

    def test_non_string_expected_returns_false(self) -> None:
        env = _make_valid_envelope()
        assert validate_payload_hash(env, 123) is False  # type: ignore

    def test_empty_expected_returns_false(self) -> None:
        env = _make_valid_envelope()
        assert validate_payload_hash(env, "") is False

    def test_whitespace_expected_returns_false(self) -> None:
        env = _make_valid_envelope()
        assert validate_payload_hash(env, "   ") is False

    def test_empty_payload_hash_returns_false(self) -> None:
        env = _make_valid_envelope(payload_hash="")
        assert validate_payload_hash(env, "expected") is False

    def test_mismatch_returns_false(self) -> None:
        env = _make_valid_envelope(payload_hash="hash1")
        assert validate_payload_hash(env, "hash2") is False


class TestValidatePayloadHashPositive:
    def test_matching_hash_returns_true(self) -> None:
        env = _make_valid_envelope(payload_hash="hash123")
        assert validate_payload_hash(env, "hash123") is True


class TestDetectReplay:
    def test_none_envelope_returns_true(self) -> None:
        assert detect_replay(None, {"hash1"}) is True

    def test_none_seen_hashes_returns_false(self) -> None:
        env = _make_valid_envelope()
        assert detect_replay(env, None) is False

    def test_non_set_seen_hashes_returns_false(self) -> None:
        env = _make_valid_envelope()
        assert detect_replay(env, ["hash1"]) is False  # type: ignore

    def test_empty_payload_hash_returns_true(self) -> None:
        env = _make_valid_envelope(payload_hash="")
        assert detect_replay(env, set()) is True

    def test_hash_in_seen_returns_true(self) -> None:
        env = _make_valid_envelope(payload_hash="hash123")
        assert detect_replay(env, {"hash123", "other"}) is True

    def test_hash_not_in_seen_returns_false(self) -> None:
        env = _make_valid_envelope(payload_hash="hash123")
        assert detect_replay(env, {"other"}) is False


class TestVerifyEvidenceIntegrityDenyByDefault:
    def test_none_envelope_returns_reject(self) -> None:
        ctx = _make_valid_context()
        result = verify_evidence_integrity(None, ctx)
        assert result.status == EvidenceIntegrityStatus.INVALID
        assert result.decision == VerificationDecision.REJECT

    def test_none_context_returns_reject(self) -> None:
        env = _make_valid_envelope()
        result = verify_evidence_integrity(env, None)
        assert result.status == EvidenceIntegrityStatus.INVALID
        assert result.decision == VerificationDecision.REJECT

    def test_invalid_evidence_id_returns_reject(self) -> None:
        env = _make_valid_envelope(evidence_id="INVALID")
        ctx = _make_valid_context()
        result = verify_evidence_integrity(env, ctx)
        assert result.decision == VerificationDecision.REJECT
        assert "Invalid evidence ID" in result.reasons

    def test_empty_timestamp_returns_reject(self) -> None:
        env = _make_valid_envelope(timestamp="")
        ctx = _make_valid_context()
        result = verify_evidence_integrity(env, ctx)
        assert result.decision == VerificationDecision.REJECT

    def test_whitespace_timestamp_returns_reject(self) -> None:
        env = _make_valid_envelope(timestamp="   ")
        ctx = _make_valid_context()
        result = verify_evidence_integrity(env, ctx)
        assert result.decision == VerificationDecision.REJECT
        assert "Empty timestamp" in result.reasons

    def test_empty_version_returns_reject(self) -> None:
        env = _make_valid_envelope(version="")
        ctx = _make_valid_context()
        result = verify_evidence_integrity(env, ctx)
        assert result.decision == VerificationDecision.REJECT

    def test_whitespace_version_returns_reject(self) -> None:
        env = _make_valid_envelope(version="   ")
        ctx = _make_valid_context()
        result = verify_evidence_integrity(env, ctx)
        assert result.decision == VerificationDecision.REJECT
        assert "Empty version" in result.reasons

    def test_format_mismatch_returns_reject(self) -> None:
        env = _make_valid_envelope(format=EvidenceFormat.TEXT)
        ctx = _make_valid_context(expected_format=EvidenceFormat.JSON)
        result = verify_evidence_integrity(env, ctx)
        assert result.decision == VerificationDecision.REJECT
        assert "Format mismatch" in result.reasons

    def test_source_mismatch_returns_escalate(self) -> None:
        env = _make_valid_envelope(source="wrong_source")
        ctx = _make_valid_context()
        result = verify_evidence_integrity(env, ctx)
        assert result.status == EvidenceIntegrityStatus.INVALID
        assert result.decision == VerificationDecision.ESCALATE

    def test_hash_mismatch_returns_tampered(self) -> None:
        env = _make_valid_envelope(payload_hash="hash1")
        ctx = _make_valid_context()
        result = verify_evidence_integrity(env, ctx, expected_hash="hash2")
        assert result.status == EvidenceIntegrityStatus.TAMPERED
        assert result.decision == VerificationDecision.REJECT

    def test_replay_detected_not_allowed_returns_replayed(self) -> None:
        env = _make_valid_envelope(payload_hash="hash123")
        ctx = _make_valid_context(allow_replay=False)
        result = verify_evidence_integrity(env, ctx, seen_hashes={"hash123"})
        assert result.status == EvidenceIntegrityStatus.REPLAYED
        assert result.decision == VerificationDecision.REJECT


class TestVerifyEvidenceIntegrityPositive:
    def test_valid_evidence_returns_accept(self) -> None:
        env = _make_valid_envelope()
        ctx = _make_valid_context()
        result = verify_evidence_integrity(env, ctx)
        assert result.status == EvidenceIntegrityStatus.VALID
        assert result.decision == VerificationDecision.ACCEPT

    def test_replay_allowed_returns_accept(self) -> None:
        env = _make_valid_envelope(payload_hash="hash123")
        ctx = _make_valid_context(allow_replay=True)
        result = verify_evidence_integrity(env, ctx, seen_hashes={"hash123"})
        assert result.status == EvidenceIntegrityStatus.VALID
        assert result.decision == VerificationDecision.ACCEPT


class TestGetVerificationDecisionDenyByDefault:
    def test_none_returns_reject(self) -> None:
        assert get_verification_decision(None) == VerificationDecision.REJECT

    def test_invalid_decision_type_returns_reject(self) -> None:
        result = EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.VALID,
            decision="ACCEPT",  # type: ignore
            reasons=()
        )
        assert get_verification_decision(result) == VerificationDecision.REJECT


class TestGetVerificationDecisionPositive:
    def test_returns_accept(self) -> None:
        result = EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.VALID,
            decision=VerificationDecision.ACCEPT,
            reasons=()
        )
        assert get_verification_decision(result) == VerificationDecision.ACCEPT

    def test_returns_reject(self) -> None:
        result = EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.INVALID,
            decision=VerificationDecision.REJECT,
            reasons=()
        )
        assert get_verification_decision(result) == VerificationDecision.REJECT

    def test_returns_escalate(self) -> None:
        result = EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.INVALID,
            decision=VerificationDecision.ESCALATE,
            reasons=()
        )
        assert get_verification_decision(result) == VerificationDecision.ESCALATE
