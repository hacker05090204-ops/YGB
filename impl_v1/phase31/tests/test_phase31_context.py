"""
Phase-31 Context Tests.

Tests for FROZEN dataclasses:
- EvidenceRecord: 7 fields
- ObservationContext: 5 fields
- EvidenceChain: 4 fields

Tests enforce:
- Immutability (FrozenInstanceError on mutation)
- Correct field counts
- Valid construction
"""
import pytest
from dataclasses import FrozenInstanceError

from impl_v1.phase31.phase31_types import ObservationPoint, EvidenceType
from impl_v1.phase31.phase31_context import (
    EvidenceRecord,
    ObservationContext,
    EvidenceChain,
)


class TestEvidenceRecordFrozen:
    """Tests for EvidenceRecord frozen dataclass."""

    def test_evidence_record_has_7_fields(self) -> None:
        """EvidenceRecord must have exactly 7 fields."""
        from dataclasses import fields
        assert len(fields(EvidenceRecord)) == 7

    def test_evidence_record_can_be_created(self) -> None:
        """EvidenceRecord can be created with valid data."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test data",
            prior_hash="",
            self_hash="abc123"
        )
        assert record.record_id == "EVIDENCE-12345678"
        assert record.observation_point == ObservationPoint.PRE_DISPATCH

    def test_evidence_record_is_immutable_record_id(self) -> None:
        """EvidenceRecord.record_id cannot be mutated."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test data",
            prior_hash="",
            self_hash="abc123"
        )
        with pytest.raises(FrozenInstanceError):
            record.record_id = "NEW-ID"  # type: ignore

    def test_evidence_record_is_immutable_raw_data(self) -> None:
        """EvidenceRecord.raw_data cannot be mutated."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test data",
            prior_hash="",
            self_hash="abc123"
        )
        with pytest.raises(FrozenInstanceError):
            record.raw_data = b"new data"  # type: ignore

    def test_evidence_record_is_immutable_self_hash(self) -> None:
        """EvidenceRecord.self_hash cannot be mutated."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test data",
            prior_hash="",
            self_hash="abc123"
        )
        with pytest.raises(FrozenInstanceError):
            record.self_hash = "new_hash"  # type: ignore


class TestObservationContextFrozen:
    """Tests for ObservationContext frozen dataclass."""

    def test_observation_context_has_5_fields(self) -> None:
        """ObservationContext must have exactly 5 fields."""
        from dataclasses import fields
        assert len(fields(ObservationContext)) == 5

    def test_observation_context_can_be_created(self) -> None:
        """ObservationContext can be created with valid data."""
        context = ObservationContext(
            session_id="SESSION-12345678",
            loop_id="LOOP-ABCD1234",
            executor_id="EXECUTOR-001",
            envelope_hash="env_hash_123",
            created_at="2026-01-26T12:00:00Z"
        )
        assert context.session_id == "SESSION-12345678"
        assert context.executor_id == "EXECUTOR-001"

    def test_observation_context_is_immutable_session_id(self) -> None:
        """ObservationContext.session_id cannot be mutated."""
        context = ObservationContext(
            session_id="SESSION-12345678",
            loop_id="LOOP-ABCD1234",
            executor_id="EXECUTOR-001",
            envelope_hash="env_hash_123",
            created_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            context.session_id = "NEW-ID"  # type: ignore

    def test_observation_context_is_immutable_executor_id(self) -> None:
        """ObservationContext.executor_id cannot be mutated."""
        context = ObservationContext(
            session_id="SESSION-12345678",
            loop_id="LOOP-ABCD1234",
            executor_id="EXECUTOR-001",
            envelope_hash="env_hash_123",
            created_at="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            context.executor_id = "NEW-EXECUTOR"  # type: ignore


class TestEvidenceChainFrozen:
    """Tests for EvidenceChain frozen dataclass."""

    def test_evidence_chain_has_4_fields(self) -> None:
        """EvidenceChain must have exactly 4 fields."""
        from dataclasses import fields
        assert len(fields(EvidenceChain)) == 4

    def test_evidence_chain_can_be_created_empty(self) -> None:
        """EvidenceChain can be created with no records."""
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(),
            head_hash="",
            length=0
        )
        assert chain.chain_id == "CHAIN-12345678"
        assert len(chain.records) == 0
        assert chain.length == 0

    def test_evidence_chain_can_be_created_with_records(self) -> None:
        """EvidenceChain can be created with records."""
        record = EvidenceRecord(
            record_id="EVIDENCE-12345678",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-26T12:00:00Z",
            raw_data=b"test data",
            prior_hash="",
            self_hash="abc123"
        )
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(record,),
            head_hash="abc123",
            length=1
        )
        assert len(chain.records) == 1
        assert chain.length == 1

    def test_evidence_chain_is_immutable_chain_id(self) -> None:
        """EvidenceChain.chain_id cannot be mutated."""
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(),
            head_hash="",
            length=0
        )
        with pytest.raises(FrozenInstanceError):
            chain.chain_id = "NEW-ID"  # type: ignore

    def test_evidence_chain_is_immutable_records(self) -> None:
        """EvidenceChain.records cannot be mutated."""
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(),
            head_hash="",
            length=0
        )
        with pytest.raises(FrozenInstanceError):
            chain.records = (None,)  # type: ignore

    def test_evidence_chain_is_immutable_length(self) -> None:
        """EvidenceChain.length cannot be mutated."""
        chain = EvidenceChain(
            chain_id="CHAIN-12345678",
            records=(),
            head_hash="",
            length=0
        )
        with pytest.raises(FrozenInstanceError):
            chain.length = 99  # type: ignore
