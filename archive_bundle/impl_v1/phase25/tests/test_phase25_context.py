"""
Phase-25 Context Tests.

Tests for FROZEN dataclasses:
- ExecutionEnvelope: 7 fields
- EnvelopeIntegrityResult: 3 fields
"""
import pytest
from dataclasses import FrozenInstanceError

from impl_v1.phase25.phase25_types import EnvelopeIntegrityStatus, IntegrityViolation
from impl_v1.phase25.phase25_context import (
    ExecutionEnvelope,
    EnvelopeIntegrityResult,
)


class TestExecutionEnvelopeFrozen:
    """Tests for ExecutionEnvelope frozen dataclass."""

    def test_has_7_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(ExecutionEnvelope)) == 7

    def test_can_be_created(self) -> None:
        envelope = ExecutionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_id="INTENT-12345678",
            authorization_id="AUTHORIZATION-12345678",
            version="1.0",
            payload_hash="hash123",
            created_at="2026-01-26T12:00:00Z"
        )
        assert envelope.envelope_id == "ENVELOPE-12345678"

    def test_is_immutable_envelope_id(self) -> None:
        envelope = ExecutionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_id="INTENT-12345678",
            authorization_id="AUTHORIZATION-12345678",
            version="1.0",
            payload_hash="hash123",
            created_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            envelope.envelope_id = "NEW"  # type: ignore

    def test_is_immutable_payload_hash(self) -> None:
        envelope = ExecutionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_id="INTENT-12345678",
            authorization_id="AUTHORIZATION-12345678",
            version="1.0",
            payload_hash="hash123",
            created_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            envelope.payload_hash = "TAMPERED"  # type: ignore

    def test_is_immutable_version(self) -> None:
        envelope = ExecutionEnvelope(
            envelope_id="ENVELOPE-12345678",
            instruction_id="INSTRUCTION-12345678",
            intent_id="INTENT-12345678",
            authorization_id="AUTHORIZATION-12345678",
            version="1.0",
            payload_hash="hash123",
            created_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            envelope.version = "9.9"  # type: ignore


class TestEnvelopeIntegrityResultFrozen:
    """Tests for EnvelopeIntegrityResult frozen dataclass."""

    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(EnvelopeIntegrityResult)) == 3

    def test_can_be_created(self) -> None:
        result = EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.VALID,
            violations=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        assert result.status == EnvelopeIntegrityStatus.VALID

    def test_is_immutable_status(self) -> None:
        result = EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.VALID,
            violations=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            result.status = EnvelopeIntegrityStatus.TAMPERED  # type: ignore

    def test_is_immutable_violations(self) -> None:
        result = EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.INVALID,
            violations=(IntegrityViolation.MISSING_FIELDS,),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            result.violations = ()  # type: ignore

    def test_is_immutable_evaluated_at(self) -> None:
        result = EnvelopeIntegrityResult(
            status=EnvelopeIntegrityStatus.VALID,
            violations=(),
            evaluated_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            result.evaluated_at = "TAMPERED"  # type: ignore
