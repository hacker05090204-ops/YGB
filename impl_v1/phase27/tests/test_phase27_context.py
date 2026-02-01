"""
Phase-27 Context Tests.

Tests for FROZEN dataclasses:
- InstructionEnvelope: 7 fields
- SynthesisResult: 5 fields

Tests enforce:
- Immutability (FrozenInstanceError on mutation)
- Correct field counts
- Valid construction
"""
import pytest
from dataclasses import FrozenInstanceError

from impl_v1.phase27.phase27_types import EnvelopeStatus
from impl_v1.phase27.phase27_context import (
    InstructionEnvelope,
    SynthesisResult,
)


class TestInstructionEnvelopeFrozen:
    """Tests for InstructionEnvelope frozen dataclass."""

    def test_instruction_envelope_has_7_fields(self) -> None:
        """InstructionEnvelope must have exactly 7 fields."""
        from dataclasses import fields
        assert len(fields(InstructionEnvelope)) == 7

    def test_instruction_envelope_can_be_created(self) -> None:
        """InstructionEnvelope can be created with valid data."""
        envelope = InstructionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_description="Test intent",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            status=EnvelopeStatus.CREATED,
            version="1.0"
        )
        assert envelope.envelope_id == "ENVELOPE-12345678"
        assert envelope.status == EnvelopeStatus.CREATED

    def test_instruction_envelope_is_immutable_envelope_id(self) -> None:
        """InstructionEnvelope.envelope_id cannot be mutated."""
        envelope = InstructionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_description="Test intent",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            status=EnvelopeStatus.CREATED,
            version="1.0"
        )
        with pytest.raises(FrozenInstanceError):
            envelope.envelope_id = "NEW-ID"  # type: ignore

    def test_instruction_envelope_is_immutable_status(self) -> None:
        """InstructionEnvelope.status cannot be mutated."""
        envelope = InstructionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_description="Test intent",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            status=EnvelopeStatus.CREATED,
            version="1.0"
        )
        with pytest.raises(FrozenInstanceError):
            envelope.status = EnvelopeStatus.INVALID  # type: ignore

    def test_instruction_envelope_is_immutable_envelope_hash(self) -> None:
        """InstructionEnvelope.envelope_hash cannot be mutated."""
        envelope = InstructionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_description="Test intent",
            envelope_hash="hash123",
            created_at="2026-01-26T12:00:00Z",
            status=EnvelopeStatus.CREATED,
            version="1.0"
        )
        with pytest.raises(FrozenInstanceError):
            envelope.envelope_hash = "TAMPERED"  # type: ignore


class TestSynthesisResultFrozen:
    """Tests for SynthesisResult frozen dataclass."""

    def test_synthesis_result_has_5_fields(self) -> None:
        """SynthesisResult must have exactly 5 fields."""
        from dataclasses import fields
        assert len(fields(SynthesisResult)) == 5

    def test_synthesis_result_can_be_created(self) -> None:
        """SynthesisResult can be created with valid data."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.VALIDATED,
            is_valid=True,
            metadata_hash="hash123",
            reason="Valid synthesis"
        )
        assert result.status == EnvelopeStatus.VALIDATED
        assert result.is_valid is True

    def test_synthesis_result_is_immutable_status(self) -> None:
        """SynthesisResult.status cannot be mutated."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.VALIDATED,
            is_valid=True,
            metadata_hash="hash123",
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.status = EnvelopeStatus.INVALID  # type: ignore

    def test_synthesis_result_is_immutable_is_valid(self) -> None:
        """SynthesisResult.is_valid cannot be mutated."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.VALIDATED,
            is_valid=True,
            metadata_hash="hash123",
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.is_valid = False  # type: ignore

    def test_synthesis_result_is_immutable_metadata_hash(self) -> None:
        """SynthesisResult.metadata_hash cannot be mutated."""
        result = SynthesisResult(
            envelope_id="ENVELOPE-12345678",
            status=EnvelopeStatus.VALIDATED,
            is_valid=True,
            metadata_hash="hash123",
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.metadata_hash = "TAMPERED"  # type: ignore
