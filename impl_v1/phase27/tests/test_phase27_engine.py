"""
Phase-27 Engine Tests.

Tests for VALIDATION-ONLY functions:
- validate_instruction_id
- validate_instruction_envelope
- synthesize_instruction_metadata
- get_envelope_status
- is_envelope_valid

Tests enforce:
- Deny-by-default (None, empty, malformed)
- Negative paths > positive paths
- Status transitions
"""
import pytest

from impl_v1.phase27.phase27_types import EnvelopeStatus
from impl_v1.phase27.phase27_context import (
    InstructionEnvelope,
    SynthesisResult,
)
from impl_v1.phase27.phase27_engine import (
    validate_instruction_id,
    validate_instruction_envelope,
    synthesize_instruction_metadata,
    get_envelope_status,
    is_envelope_valid,
)


# --- Helpers ---

def _make_valid_envelope(
    envelope_id: str = "ENVELOPE-12345678",
    instruction_id: str = "INSTRUCTION-12345678",
    intent_description: str = "Test intent",
    envelope_hash: str = "hash123",
    created_at: str = "2026-01-26T12:00:00Z",
    status: EnvelopeStatus = EnvelopeStatus.CREATED,
    version: str = "1.0"
) -> InstructionEnvelope:
    return InstructionEnvelope(
        envelope_id=envelope_id,
        instruction_id=instruction_id,
        intent_description=intent_description,
        envelope_hash=envelope_hash,
        created_at=created_at,
        status=status,
        version=version
    )


# ============================================================================
# validate_instruction_id TESTS
# ============================================================================

class TestValidateInstructionIdDenyByDefault:
    """Deny-by-default tests for validate_instruction_id."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_instruction_id(None) is False

    def test_non_string_returns_false(self) -> None:
        """Non-string → False."""
        assert validate_instruction_id(12345) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        """Empty → False."""
        assert validate_instruction_id("") is False

    def test_whitespace_returns_false(self) -> None:
        """Whitespace → False."""
        assert validate_instruction_id("   ") is False

    def test_invalid_format_returns_false(self) -> None:
        """Invalid format → False."""
        assert validate_instruction_id("INVALID-123") is False

    def test_wrong_prefix_returns_false(self) -> None:
        """Wrong prefix → False."""
        assert validate_instruction_id("ENVELOPE-12345678") is False


class TestValidateInstructionIdPositive:
    """Positive tests for validate_instruction_id."""

    def test_valid_format_returns_true(self) -> None:
        """Valid format → True."""
        assert validate_instruction_id("INSTRUCTION-12345678") is True

    def test_valid_format_long_hex_returns_true(self) -> None:
        """Valid format with long hex → True."""
        assert validate_instruction_id("INSTRUCTION-abcdef12345678") is True


# ============================================================================
# validate_instruction_envelope TESTS
# ============================================================================

class TestValidateInstructionEnvelopeDenyByDefault:
    """Deny-by-default tests for validate_instruction_envelope."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_instruction_envelope(None) is False

    def test_empty_envelope_id_returns_false(self) -> None:
        """Empty envelope_id → False."""
        envelope = _make_valid_envelope(envelope_id="")
        assert validate_instruction_envelope(envelope) is False

    def test_invalid_envelope_id_returns_false(self) -> None:
        """Invalid envelope_id format → False."""
        envelope = _make_valid_envelope(envelope_id="INVALID-123")
        assert validate_instruction_envelope(envelope) is False

    def test_invalid_instruction_id_returns_false(self) -> None:
        """Invalid instruction_id format → False."""
        envelope = _make_valid_envelope(instruction_id="INVALID-123")
        assert validate_instruction_envelope(envelope) is False

    def test_empty_intent_description_returns_false(self) -> None:
        """Empty intent_description → False."""
        envelope = _make_valid_envelope(intent_description="")
        assert validate_instruction_envelope(envelope) is False

    def test_whitespace_intent_description_returns_false(self) -> None:
        """Whitespace intent_description → False."""
        envelope = _make_valid_envelope(intent_description="   ")
        assert validate_instruction_envelope(envelope) is False

    def test_empty_envelope_hash_returns_false(self) -> None:
        """Empty envelope_hash → False."""
        envelope = _make_valid_envelope(envelope_hash="")
        assert validate_instruction_envelope(envelope) is False

    def test_whitespace_envelope_hash_returns_false(self) -> None:
        """Whitespace envelope_hash → False."""
        envelope = _make_valid_envelope(envelope_hash="   ")
        assert validate_instruction_envelope(envelope) is False

    def test_empty_created_at_returns_false(self) -> None:
        """Empty created_at → False."""
        envelope = _make_valid_envelope(created_at="")
        assert validate_instruction_envelope(envelope) is False

    def test_whitespace_created_at_returns_false(self) -> None:
        """Whitespace created_at → False."""
        envelope = _make_valid_envelope(created_at="   ")
        assert validate_instruction_envelope(envelope) is False

    def test_non_status_type_returns_false(self) -> None:
        """Non-EnvelopeStatus → False."""
        envelope = InstructionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_description="Test",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            status="CREATED",  # type: ignore
            version="1.0"
        )
        assert validate_instruction_envelope(envelope) is False

    def test_empty_version_returns_false(self) -> None:
        """Empty version → False."""
        envelope = _make_valid_envelope(version="")
        assert validate_instruction_envelope(envelope) is False

    def test_whitespace_version_returns_false(self) -> None:
        """Whitespace version → False."""
        envelope = _make_valid_envelope(version="   ")
        assert validate_instruction_envelope(envelope) is False


class TestValidateInstructionEnvelopePositive:
    """Positive tests for validate_instruction_envelope."""

    def test_valid_envelope_returns_true(self) -> None:
        """Valid envelope → True."""
        envelope = _make_valid_envelope()
        assert validate_instruction_envelope(envelope) is True

    def test_all_statuses_valid_in_envelope(self) -> None:
        """All EnvelopeStatus values are valid for envelope structure."""
        for status in EnvelopeStatus:
            envelope = _make_valid_envelope(status=status)
            assert validate_instruction_envelope(envelope) is True


# ============================================================================
# synthesize_instruction_metadata TESTS
# ============================================================================

class TestSynthesizeInstructionMetadataDenyByDefault:
    """Deny-by-default tests for synthesize_instruction_metadata."""

    def test_none_returns_invalid(self) -> None:
        """None → INVALID."""
        result = synthesize_instruction_metadata(None)
        assert result.status == EnvelopeStatus.INVALID
        assert result.is_valid is False

    def test_invalid_envelope_returns_invalid(self) -> None:
        """Invalid envelope → INVALID."""
        envelope = _make_valid_envelope(envelope_id="INVALID")
        result = synthesize_instruction_metadata(envelope)
        assert result.status == EnvelopeStatus.INVALID
        assert result.is_valid is False

    def test_invalid_status_envelope_returns_invalid(self) -> None:
        """INVALID status envelope → INVALID."""
        envelope = _make_valid_envelope(status=EnvelopeStatus.INVALID)
        result = synthesize_instruction_metadata(envelope)
        assert result.status == EnvelopeStatus.INVALID
        assert result.is_valid is False


class TestSynthesizeInstructionMetadataPositive:
    """Positive tests for synthesize_instruction_metadata."""

    def test_created_envelope_returns_validated(self) -> None:
        """CREATED envelope → VALIDATED."""
        envelope = _make_valid_envelope(status=EnvelopeStatus.CREATED)
        result = synthesize_instruction_metadata(envelope)
        assert result.status == EnvelopeStatus.VALIDATED
        assert result.is_valid is True
        assert result.metadata_hash == envelope.envelope_hash

    def test_validated_envelope_returns_validated(self) -> None:
        """VALIDATED envelope → VALIDATED."""
        envelope = _make_valid_envelope(status=EnvelopeStatus.VALIDATED)
        result = synthesize_instruction_metadata(envelope)
        assert result.status == EnvelopeStatus.VALIDATED
        assert result.is_valid is True


# ============================================================================
# get_envelope_status TESTS
# ============================================================================

class TestGetEnvelopeStatusDenyByDefault:
    """Deny-by-default tests for get_envelope_status."""

    def test_none_returns_invalid(self) -> None:
        """None → INVALID."""
        assert get_envelope_status(None) == EnvelopeStatus.INVALID

    def test_invalid_envelope_returns_invalid(self) -> None:
        """Invalid envelope → INVALID."""
        envelope = _make_valid_envelope(envelope_id="INVALID")
        assert get_envelope_status(envelope) == EnvelopeStatus.INVALID


class TestGetEnvelopeStatusPositive:
    """Positive tests for get_envelope_status."""

    def test_returns_envelope_status(self) -> None:
        """Returns envelope's status."""
        for status in EnvelopeStatus:
            envelope = _make_valid_envelope(status=status)
            assert get_envelope_status(envelope) == status


# ============================================================================
# is_envelope_valid TESTS
# ============================================================================

class TestIsEnvelopeValidDenyByDefault:
    """Deny-by-default tests for is_envelope_valid."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert is_envelope_valid(None) is False

    def test_invalid_status_returns_false(self) -> None:
        """INVALID status → False."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.INVALID,
            is_valid=False,
            metadata_hash="",
            reason="Test"
        )
        assert is_envelope_valid(result) is False

    def test_non_status_type_returns_false(self) -> None:
        """Non-EnvelopeStatus → False."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status="VALIDATED",  # type: ignore
            is_valid=True,
            metadata_hash="hash123",
            reason="Test"
        )
        assert is_envelope_valid(result) is False

    def test_is_valid_false_returns_false(self) -> None:
        """is_valid False → False."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.VALIDATED,
            is_valid=False,
            metadata_hash="hash123",
            reason="Test"
        )
        assert is_envelope_valid(result) is False

    def test_non_bool_is_valid_returns_false(self) -> None:
        """Non-bool is_valid → False."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.VALIDATED,
            is_valid="True",  # type: ignore
            metadata_hash="hash123",
            reason="Test"
        )
        assert is_envelope_valid(result) is False


class TestIsEnvelopeValidPositive:
    """Positive tests for is_envelope_valid."""

    def test_validated_and_is_valid_returns_true(self) -> None:
        """VALIDATED + is_valid True → True."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.VALIDATED,
            is_valid=True,
            metadata_hash="hash123",
            reason="Valid"
        )
        assert is_envelope_valid(result) is True

    def test_created_and_is_valid_returns_true(self) -> None:
        """CREATED + is_valid True → True."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.CREATED,
            is_valid=True,
            metadata_hash="hash123",
            reason="Valid"
        )
        assert is_envelope_valid(result) is True
