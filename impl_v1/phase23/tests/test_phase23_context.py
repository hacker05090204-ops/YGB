"""Phase-23 Context Tests."""
import pytest
from dataclasses import FrozenInstanceError
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


class TestEvidenceEnvelopeFrozen:
    def test_has_7_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(EvidenceEnvelope)) == 7

    def test_can_be_created(self) -> None:
        env = EvidenceEnvelope(
            evidence_id="EVIDENCE-12345678",
            format=EvidenceFormat.JSON,
            payload_hash="hash123",
            prior_hash="prior123",
            timestamp="2026-01-26T12:00:00Z",
            source="test_source",
            version="1.0"
        )
        assert env.evidence_id == "EVIDENCE-12345678"

    def test_is_immutable_evidence_id(self) -> None:
        env = EvidenceEnvelope(
            evidence_id="EVIDENCE-12345678",
            format=EvidenceFormat.JSON,
            payload_hash="hash123",
            prior_hash="prior123",
            timestamp="2026-01-26T12:00:00Z",
            source="test_source",
            version="1.0"
        )
        with pytest.raises(FrozenInstanceError):
            env.evidence_id = "TAMPERED"  # type: ignore

    def test_is_immutable_payload_hash(self) -> None:
        env = EvidenceEnvelope(
            evidence_id="EVIDENCE-12345678",
            format=EvidenceFormat.JSON,
            payload_hash="hash123",
            prior_hash="prior123",
            timestamp="2026-01-26T12:00:00Z",
            source="test_source",
            version="1.0"
        )
        with pytest.raises(FrozenInstanceError):
            env.payload_hash = "TAMPERED"  # type: ignore


class TestEvidenceVerificationContextFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(EvidenceVerificationContext)) == 3

    def test_can_be_created(self) -> None:
        ctx = EvidenceVerificationContext(
            expected_format=EvidenceFormat.JSON,
            expected_source="test_source",
            allow_replay=False
        )
        assert ctx.expected_format == EvidenceFormat.JSON

    def test_is_immutable_allow_replay(self) -> None:
        ctx = EvidenceVerificationContext(
            expected_format=EvidenceFormat.JSON,
            expected_source="test_source",
            allow_replay=False
        )
        with pytest.raises(FrozenInstanceError):
            ctx.allow_replay = True  # type: ignore


class TestEvidenceVerificationResultFrozen:
    def test_has_3_fields(self) -> None:
        from dataclasses import fields
        assert len(fields(EvidenceVerificationResult)) == 3

    def test_can_be_created(self) -> None:
        result = EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.VALID,
            decision=VerificationDecision.ACCEPT,
            reasons=()
        )
        assert result.status == EvidenceIntegrityStatus.VALID

    def test_is_immutable_status(self) -> None:
        result = EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.VALID,
            decision=VerificationDecision.ACCEPT,
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.status = EvidenceIntegrityStatus.INVALID  # type: ignore

    def test_is_immutable_decision(self) -> None:
        result = EvidenceVerificationResult(
            status=EvidenceIntegrityStatus.VALID,
            decision=VerificationDecision.ACCEPT,
            reasons=()
        )
        with pytest.raises(FrozenInstanceError):
            result.decision = VerificationDecision.REJECT  # type: ignore
