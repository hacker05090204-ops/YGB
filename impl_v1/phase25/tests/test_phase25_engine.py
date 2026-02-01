"""
Phase-25 Engine Tests.

Tests for VALIDATION-ONLY functions.
"""
import pytest

from impl_v1.phase25.phase25_types import (
    EnvelopeIntegrityStatus,
    IntegrityViolation,
)
from impl_v1.phase25.phase25_context import (
    ExecutionEnvelope,
    EnvelopeIntegrityResult,
)
from impl_v1.phase25.phase25_engine import (
    validate_envelope_id,
    validate_envelope_structure,
    validate_envelope_hash,
    evaluate_envelope_integrity,
    is_envelope_valid,
)


def _make_valid_envelope(
    envelope_id: str = "ENVELOPE-12345678",
    instruction_id: str = "INSTRUCTION-12345678",
    intent_id: str = "INTENT-12345678",
    authorization_id: str = "AUTHORIZATION-12345678",
    version: str = "1.0",
    payload_hash: str = "hash123",
    created_at: str = "2026-01-26T12:00:00Z"
) -> ExecutionEnvelope:
    return ExecutionEnvelope(
        envelope_id=envelope_id,
        instruction_id=instruction_id,
        intent_id=intent_id,
        authorization_id=authorization_id,
        version=version,
        payload_hash=payload_hash,
        created_at=created_at
    )


class TestValidateEnvelopeIdDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert validate_envelope_id(None) is False

    def test_non_string_returns_false(self) -> None:
        assert validate_envelope_id(123) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        assert validate_envelope_id("") is False

    def test_whitespace_returns_false(self) -> None:
        assert validate_envelope_id("   ") is False

    def test_invalid_format_returns_false(self) -> None:
        assert validate_envelope_id("INVALID-123") is False


class TestValidateEnvelopeIdPositive:
    def test_valid_format_returns_true(self) -> None:
        assert validate_envelope_id("ENVELOPE-12345678") is True


class TestValidateEnvelopeStructureDenyByDefault:
    def test_none_returns_missing_fields(self) -> None:
        is_valid, violations = validate_envelope_structure(None)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_invalid_envelope_id_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(envelope_id="INVALID")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_invalid_instruction_id_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(instruction_id="INVALID")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_invalid_intent_id_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(intent_id="INVALID")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_invalid_authorization_id_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(authorization_id="INVALID")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_empty_instruction_id_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(instruction_id="")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_empty_intent_id_with_valid_others_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(intent_id="")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_empty_authorization_id_with_valid_others_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(authorization_id="")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_unknown_version_returns_unknown_version(self) -> None:
        envelope = _make_valid_envelope(version="9.9")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.UNKNOWN_VERSION in violations

    def test_empty_version_returns_unknown_version(self) -> None:
        envelope = _make_valid_envelope(version="")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.UNKNOWN_VERSION in violations

    def test_empty_payload_hash_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(payload_hash="")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_whitespace_payload_hash_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(payload_hash="   ")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_empty_created_at_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(created_at="")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations

    def test_whitespace_created_at_returns_missing_fields(self) -> None:
        envelope = _make_valid_envelope(created_at="   ")
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is False
        assert IntegrityViolation.MISSING_FIELDS in violations


class TestValidateEnvelopeStructurePositive:
    def test_valid_envelope_returns_true(self) -> None:
        envelope = _make_valid_envelope()
        is_valid, violations = validate_envelope_structure(envelope)
        assert is_valid is True
        assert violations == ()

    def test_valid_versions(self) -> None:
        for version in ("1.0", "1.1", "2.0"):
            envelope = _make_valid_envelope(version=version)
            is_valid, _ = validate_envelope_structure(envelope)
            assert is_valid is True


class TestValidateEnvelopeHashDenyByDefault:
    def test_none_envelope_returns_false(self) -> None:
        assert validate_envelope_hash(None, "expected") is False

    def test_none_expected_returns_false(self) -> None:
        envelope = _make_valid_envelope()
        assert validate_envelope_hash(envelope, None) is False

    def test_non_string_expected_returns_false(self) -> None:
        envelope = _make_valid_envelope()
        assert validate_envelope_hash(envelope, 123) is False  # type: ignore

    def test_empty_expected_returns_false(self) -> None:
        envelope = _make_valid_envelope()
        assert validate_envelope_hash(envelope, "") is False

    def test_whitespace_expected_returns_false(self) -> None:
        envelope = _make_valid_envelope()
        assert validate_envelope_hash(envelope, "   ") is False

    def test_empty_payload_hash_returns_false(self) -> None:
        envelope = _make_valid_envelope(payload_hash="")
        assert validate_envelope_hash(envelope, "expected") is False

    def test_mismatch_returns_false(self) -> None:
        envelope = _make_valid_envelope(payload_hash="hash1")
        assert validate_envelope_hash(envelope, "hash2") is False


class TestValidateEnvelopeHashPositive:
    def test_matching_hash_returns_true(self) -> None:
        envelope = _make_valid_envelope(payload_hash="hash123")
        assert validate_envelope_hash(envelope, "hash123") is True


class TestEvaluateEnvelopeIntegrityDenyByDefault:
    def test_none_returns_invalid(self) -> None:
        result = evaluate_envelope_integrity(None)
        assert result.status == EnvelopeIntegrityStatus.INVALID

    def test_invalid_structure_returns_invalid(self) -> None:
        envelope = _make_valid_envelope(envelope_id="INVALID")
        result = evaluate_envelope_integrity(envelope)
        assert result.status == EnvelopeIntegrityStatus.INVALID

    def test_hash_mismatch_returns_tampered(self) -> None:
        envelope = _make_valid_envelope(payload_hash="hash1")
        result = evaluate_envelope_integrity(envelope, expected_hash="hash2")
        assert result.status == EnvelopeIntegrityStatus.TAMPERED
        assert IntegrityViolation.HASH_MISMATCH in result.violations


class TestEvaluateEnvelopeIntegrityPositive:
    def test_valid_envelope_returns_valid(self) -> None:
        envelope = _make_valid_envelope()
        result = evaluate_envelope_integrity(envelope, timestamp="2026-01-26T12:00:00Z")
        assert result.status == EnvelopeIntegrityStatus.VALID
        assert result.violations == ()

    def test_valid_with_matching_hash_returns_valid(self) -> None:
        envelope = _make_valid_envelope(payload_hash="hash123")
        result = evaluate_envelope_integrity(envelope, expected_hash="hash123")
        assert result.status == EnvelopeIntegrityStatus.VALID


class TestIsEnvelopeValidDenyByDefault:
    def test_none_returns_false(self) -> None:
        assert is_envelope_valid(None) is False

    def test_invalid_status_type_returns_false(self) -> None:
        result = EnvelopeIntegrityResult(
            status="VALID",  # type: ignore
            violations=(),
            evaluated_at=""
        )
        assert is_envelope_valid(result) is False

    def test_invalid_returns_false(self) -> None:
        result = EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.INVALID,
            violations=(IntegrityViolation.MISSING_FIELDS,),
            evaluated_at=""
        )
        assert is_envelope_valid(result) is False

    def test_tampered_returns_false(self) -> None:
        result = EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.TAMPERED,
            violations=(IntegrityViolation.HASH_MISMATCH,),
            evaluated_at=""
        )
        assert is_envelope_valid(result) is False


class TestIsEnvelopeValidPositive:
    def test_valid_returns_true(self) -> None:
        result = EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.VALID,
            violations=(),
            evaluated_at=""
        )
        assert is_envelope_valid(result) is True
