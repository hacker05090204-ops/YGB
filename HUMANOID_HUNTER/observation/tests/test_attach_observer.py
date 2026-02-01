"""
Phase-31 Attach Observer Tests.

Tests attach_observer function for various invalid inputs.
"""
import pytest

from HUMANOID_HUNTER.observation import (
    ObservationContext,
    EvidenceType,
    ObservationPoint,
    EvidenceChain,
    attach_observer,
    capture_evidence,
    create_empty_chain
)


class TestAttachObserverValidInputs:
    """Test attach_observer with valid inputs."""
    
    def test_valid_inputs_not_halted(self) -> None:
        """Valid inputs create non-halted context."""
        ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert ctx.is_halted is False
    
    def test_session_id_generated(self) -> None:
        """Session ID is generated."""
        ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert ctx.session_id.startswith("OBS-")


class TestAttachObserverEmptyLoopId:
    """Test attach_observer with empty loop_id."""
    
    def test_empty_loop_id_halts(self) -> None:
        """Empty loop_id creates halted context."""
        ctx = attach_observer(
            loop_id="",
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert ctx.is_halted is True
    
    def test_whitespace_loop_id_halts(self) -> None:
        """Whitespace-only loop_id creates halted context."""
        ctx = attach_observer(
            loop_id="   ",
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert ctx.is_halted is True


class TestAttachObserverEmptyExecutorId:
    """Test attach_observer with empty executor_id."""
    
    def test_empty_executor_id_halts(self) -> None:
        """Empty executor_id creates halted context."""
        ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert ctx.is_halted is True
    
    def test_whitespace_executor_id_halts(self) -> None:
        """Whitespace-only executor_id creates halted context."""
        ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="   ",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert ctx.is_halted is True


class TestAttachObserverEmptyEnvelopeHash:
    """Test attach_observer with empty envelope_hash."""
    
    def test_empty_envelope_hash_halts(self) -> None:
        """Empty envelope_hash creates halted context."""
        ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert ctx.is_halted is True
    
    def test_whitespace_envelope_hash_halts(self) -> None:
        """Whitespace-only envelope_hash creates halted context."""
        ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="   ",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert ctx.is_halted is True


class TestAttachObserverEmptyTimestamp:
    """Test attach_observer with empty timestamp."""
    
    def test_empty_timestamp_halts(self) -> None:
        """Empty timestamp creates halted context."""
        ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp=""
        )
        assert ctx.is_halted is True
    
    def test_whitespace_timestamp_halts(self) -> None:
        """Whitespace-only timestamp creates halted context."""
        ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp="   "
        )
        assert ctx.is_halted is True


class TestCaptureEvidenceHaltedContext:
    """Test capture_evidence with halted context."""
    
    def test_halted_context_captures_halt_evidence(self) -> None:
        """Halted context captures HALT_ENTRY evidence."""
        halted_ctx = attach_observer(
            loop_id="",  # Empty triggers halt
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert halted_ctx.is_halted is True
        
        chain = capture_evidence(
            context=halted_ctx,
            observation_point=ObservationPoint.PRE_DISPATCH,  # Ignored due to halt
            evidence_type=EvidenceType.STATE_TRANSITION,  # Ignored due to halt
            raw_data=b"test",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=create_empty_chain()
        )
        
        # Should have captured HALT evidence
        assert chain.length == 1
        assert chain.records[0].observation_point == ObservationPoint.HALT_ENTRY
        assert chain.records[0].evidence_type == EvidenceType.STOP_CONDITION
        assert chain.records[0].raw_data == b"CONTEXT_HALTED"
    
    def test_halted_context_chain_is_valid(self) -> None:
        """Chain from halted context is still valid."""
        from HUMANOID_HUNTER.observation import validate_chain
        
        halted_ctx = attach_observer(
            loop_id="",
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        
        chain = capture_evidence(
            context=halted_ctx,
            observation_point=ObservationPoint.PRE_DISPATCH,
            evidence_type=EvidenceType.STATE_TRANSITION,
            raw_data=b"test",
            timestamp="2026-01-25T19:01:00-05:00",
            prior_chain=create_empty_chain()
        )
        
        assert validate_chain(chain) is True


class TestContextUninitializedCondition:
    """Test CONTEXT_UNINITIALIZED stop condition with valid context."""
    
    def test_context_uninitialized_with_valid_context(self) -> None:
        """CONTEXT_UNINITIALIZED returns False (no halt) when context is valid."""
        from HUMANOID_HUNTER.observation import check_stop, StopCondition
        
        valid_ctx = attach_observer(
            loop_id="LOOP-test",
            executor_id="EXEC-test",
            envelope_hash="abc123",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        
        result = check_stop(
            context=valid_ctx,
            condition=StopCondition.CONTEXT_UNINITIALIZED
        )
        # With valid context, this should return False (no halt)
        # because context is not None
        assert result is False
