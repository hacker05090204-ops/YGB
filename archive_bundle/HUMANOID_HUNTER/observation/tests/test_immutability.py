"""
Phase-31 Immutability Tests.

Tests that all dataclasses are frozen and enums are closed.
"""
import pytest
from dataclasses import FrozenInstanceError

from HUMANOID_HUNTER.observation import (
    ObservationPoint,
    EvidenceType,
    StopCondition,
    EvidenceRecord,
    ObservationContext,
    EvidenceChain,
    attach_observer,
    create_empty_chain
)


class TestEvidenceRecordImmutability:
    """Test EvidenceRecord is immutable."""
    
    def test_evidence_record_is_frozen(self) -> None:
        """EvidenceRecord cannot be mutated."""
        record = EvidenceRecord(
            record_id="REC-test",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-25T19:01:00-05:00",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc123"
        )
        
        with pytest.raises(FrozenInstanceError):
            record.record_id = "MODIFIED"  # type: ignore
    
    def test_evidence_record_raw_data_immutable(self) -> None:
        """EvidenceRecord raw_data field cannot be mutated."""
        record = EvidenceRecord(
            record_id="REC-test",
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            timestamp="2026-01-25T19:01:00-05:00",
            raw_data=b"test",
            prior_hash="",
            self_hash="abc123"
        )
        
        with pytest.raises(FrozenInstanceError):
            record.raw_data = b"MODIFIED"  # type: ignore


class TestObservationContextImmutability:
    """Test ObservationContext is immutable."""
    
    def test_observation_context_is_frozen(self) -> None:
        """ObservationContext cannot be mutated."""
        context = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="hash",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        
        with pytest.raises(FrozenInstanceError):
            context.loop_id = "MODIFIED"  # type: ignore
    
    def test_observation_context_is_halted_immutable(self) -> None:
        """ObservationContext is_halted cannot be mutated."""
        context = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="hash",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        
        with pytest.raises(FrozenInstanceError):
            context.is_halted = True  # type: ignore


class TestEvidenceChainImmutability:
    """Test EvidenceChain is immutable."""
    
    def test_evidence_chain_is_frozen(self) -> None:
        """EvidenceChain cannot be mutated."""
        chain = create_empty_chain()
        
        with pytest.raises(FrozenInstanceError):
            chain.chain_id = "MODIFIED"  # type: ignore
    
    def test_evidence_chain_length_immutable(self) -> None:
        """EvidenceChain length cannot be mutated."""
        chain = create_empty_chain()
        
        with pytest.raises(FrozenInstanceError):
            chain.length = 100  # type: ignore
    
    def test_evidence_chain_records_is_tuple(self) -> None:
        """EvidenceChain records is a tuple (immutable)."""
        chain = create_empty_chain()
        assert isinstance(chain.records, tuple)


class TestEnumsClosed:
    """Test that all enums are closed (no dynamic members)."""
    
    def test_observation_point_count_is_five(self) -> None:
        """ObservationPoint has exactly 5 members."""
        assert len(ObservationPoint) == 5
    
    def test_evidence_type_count_is_five(self) -> None:
        """EvidenceType has exactly 5 members."""
        assert len(EvidenceType) == 5
    
    def test_stop_condition_count_is_ten(self) -> None:
        """StopCondition has exactly 10 members."""
        assert len(StopCondition) == 10
    
    def test_observation_point_members_are_defined(self) -> None:
        """All ObservationPoint members are defined (closed enum verification)."""
        expected_members = {"PRE_DISPATCH", "POST_DISPATCH", "PRE_EVALUATE", "POST_EVALUATE", "HALT_ENTRY"}
        actual_members = {m.name for m in ObservationPoint}
        assert actual_members == expected_members
    
    def test_evidence_type_members_are_defined(self) -> None:
        """All EvidenceType members are defined (closed enum verification)."""
        expected_members = {"STATE_TRANSITION", "EXECUTOR_OUTPUT", "TIMESTAMP_EVENT", "RESOURCE_SNAPSHOT", "STOP_CONDITION"}
        actual_members = {m.name for m in EvidenceType}
        assert actual_members == expected_members
    
    def test_stop_condition_members_are_defined(self) -> None:
        """All StopCondition members are defined (closed enum verification)."""
        expected_members = {
            "MISSING_AUTHORIZATION", "EXECUTOR_NOT_REGISTERED", "ENVELOPE_HASH_MISMATCH",
            "CONTEXT_UNINITIALIZED", "EVIDENCE_CHAIN_BROKEN", "RESOURCE_LIMIT_EXCEEDED",
            "TIMESTAMP_INVALID", "PRIOR_EXECUTION_PENDING", "AMBIGUOUS_INTENT", "HUMAN_ABORT"
        }
        actual_members = {m.name for m in StopCondition}
        assert actual_members == expected_members


class TestAppendOnlyBehavior:
    """Test that chain append returns new chain."""
    
    def test_capture_returns_new_chain(self) -> None:
        """capture_evidence returns a new chain, not modified original."""
        from HUMANOID_HUNTER.observation import capture_evidence, ObservationPoint, EvidenceType
        
        original_chain = create_empty_chain()
        original_id = id(original_chain)
        
        context = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="hash",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        
        new_chain = capture_evidence(
            context=context,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"test",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=original_chain
        )
        
        # New chain is a different object
        assert id(new_chain) != original_id
        
        # Original chain is unchanged
        assert original_chain.length == 0
        assert new_chain.length == 1
