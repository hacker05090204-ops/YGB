"""
Phase-31 Stop Condition Tests.

Tests all 10 STOP conditions that trigger immediate HALT.
"""
import pytest

from HUMANOID_HUNTER.observation import (
    StopCondition,
    ObservationContext,
    check_stop,
    attach_observer
)


class TestStopConditionsExist:
    """Test that all 10 stop conditions exist."""
    
    def test_missing_authorization_exists(self) -> None:
        """MISSING_AUTHORIZATION stop condition exists."""
        assert StopCondition.MISSING_AUTHORIZATION is not None
    
    def test_executor_not_registered_exists(self) -> None:
        """EXECUTOR_NOT_REGISTERED stop condition exists."""
        assert StopCondition.EXECUTOR_NOT_REGISTERED is not None
    
    def test_envelope_hash_mismatch_exists(self) -> None:
        """ENVELOPE_HASH_MISMATCH stop condition exists."""
        assert StopCondition.ENVELOPE_HASH_MISMATCH is not None
    
    def test_context_uninitialized_exists(self) -> None:
        """CONTEXT_UNINITIALIZED stop condition exists."""
        assert StopCondition.CONTEXT_UNINITIALIZED is not None
    
    def test_evidence_chain_broken_exists(self) -> None:
        """EVIDENCE_CHAIN_BROKEN stop condition exists."""
        assert StopCondition.EVIDENCE_CHAIN_BROKEN is not None
    
    def test_resource_limit_exceeded_exists(self) -> None:
        """RESOURCE_LIMIT_EXCEEDED stop condition exists."""
        assert StopCondition.RESOURCE_LIMIT_EXCEEDED is not None
    
    def test_timestamp_invalid_exists(self) -> None:
        """TIMESTAMP_INVALID stop condition exists."""
        assert StopCondition.TIMESTAMP_INVALID is not None
    
    def test_prior_execution_pending_exists(self) -> None:
        """PRIOR_EXECUTION_PENDING stop condition exists."""
        assert StopCondition.PRIOR_EXECUTION_PENDING is not None
    
    def test_ambiguous_intent_exists(self) -> None:
        """AMBIGUOUS_INTENT stop condition exists."""
        assert StopCondition.AMBIGUOUS_INTENT is not None
    
    def test_human_abort_exists(self) -> None:
        """HUMAN_ABORT stop condition exists."""
        assert StopCondition.HUMAN_ABORT is not None
    
    def test_exactly_ten_stop_conditions(self) -> None:
        """Verify exactly 10 stop conditions (closed enum)."""
        assert len(StopCondition) == 10


class TestStopConditionDetection:
    """Test stop condition detection triggers HALT."""
    
    @pytest.fixture
    def valid_context(self) -> ObservationContext:
        """Create a valid observation context."""
        return attach_observer(
            loop_id="LOOP-test123",
            executor_id="EXEC-test456",
            envelope_hash="abc123hash",
            timestamp="2026-01-25T19:00:00-05:00"
        )
    
    def test_missing_authorization_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """MISSING_AUTHORIZATION triggers HALT when no authorization."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.MISSING_AUTHORIZATION,
            authorization_present=False
        )
        assert result is True  # HALT
    
    def test_missing_authorization_no_halt_when_present(
        self, valid_context: ObservationContext
    ) -> None:
        """MISSING_AUTHORIZATION no HALT when authorization present."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.MISSING_AUTHORIZATION,
            authorization_present=True
        )
        assert result is False  # No HALT
    
    def test_executor_not_registered_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """EXECUTOR_NOT_REGISTERED triggers HALT when not registered."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.EXECUTOR_NOT_REGISTERED,
            executor_registered=False
        )
        assert result is True  # HALT
    
    def test_executor_not_registered_no_halt_when_registered(
        self, valid_context: ObservationContext
    ) -> None:
        """EXECUTOR_NOT_REGISTERED no HALT when registered."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.EXECUTOR_NOT_REGISTERED,
            executor_registered=True
        )
        assert result is False  # No HALT
    
    def test_envelope_hash_mismatch_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """ENVELOPE_HASH_MISMATCH triggers HALT on mismatch."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.ENVELOPE_HASH_MISMATCH,
            envelope_hash_matches=False
        )
        assert result is True  # HALT
    
    def test_envelope_hash_mismatch_no_halt_when_matches(
        self, valid_context: ObservationContext
    ) -> None:
        """ENVELOPE_HASH_MISMATCH no HALT when matches."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.ENVELOPE_HASH_MISMATCH,
            envelope_hash_matches=True
        )
        assert result is False  # No HALT
    
    def test_context_uninitialized_halts_on_none(self) -> None:
        """CONTEXT_UNINITIALIZED triggers HALT when context is None."""
        result = check_stop(
            context=None,
            condition=StopCondition.CONTEXT_UNINITIALIZED
        )
        assert result is True  # HALT
    
    def test_evidence_chain_broken_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """EVIDENCE_CHAIN_BROKEN triggers HALT when chain invalid."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.EVIDENCE_CHAIN_BROKEN,
            chain_valid=False
        )
        assert result is True  # HALT
    
    def test_evidence_chain_broken_no_halt_when_valid(
        self, valid_context: ObservationContext
    ) -> None:
        """EVIDENCE_CHAIN_BROKEN no HALT when chain valid."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.EVIDENCE_CHAIN_BROKEN,
            chain_valid=True
        )
        assert result is False  # No HALT
    
    def test_resource_limit_exceeded_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """RESOURCE_LIMIT_EXCEEDED triggers HALT when exceeded."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.RESOURCE_LIMIT_EXCEEDED,
            resources_available=False
        )
        assert result is True  # HALT
    
    def test_resource_limit_exceeded_no_halt_when_available(
        self, valid_context: ObservationContext
    ) -> None:
        """RESOURCE_LIMIT_EXCEEDED no HALT when resources available."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.RESOURCE_LIMIT_EXCEEDED,
            resources_available=True
        )
        assert result is False  # No HALT
    
    def test_timestamp_invalid_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """TIMESTAMP_INVALID triggers HALT when timestamp invalid."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.TIMESTAMP_INVALID,
            timestamp_valid=False
        )
        assert result is True  # HALT
    
    def test_timestamp_invalid_no_halt_when_valid(
        self, valid_context: ObservationContext
    ) -> None:
        """TIMESTAMP_INVALID no HALT when timestamp valid."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.TIMESTAMP_INVALID,
            timestamp_valid=True
        )
        assert result is False  # No HALT
    
    def test_prior_execution_pending_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """PRIOR_EXECUTION_PENDING triggers HALT when not complete."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.PRIOR_EXECUTION_PENDING,
            prior_execution_complete=False
        )
        assert result is True  # HALT
    
    def test_prior_execution_pending_no_halt_when_complete(
        self, valid_context: ObservationContext
    ) -> None:
        """PRIOR_EXECUTION_PENDING no HALT when complete."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.PRIOR_EXECUTION_PENDING,
            prior_execution_complete=True
        )
        assert result is False  # No HALT
    
    def test_ambiguous_intent_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """AMBIGUOUS_INTENT triggers HALT when intent unclear."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.AMBIGUOUS_INTENT,
            intent_clear=False
        )
        assert result is True  # HALT
    
    def test_ambiguous_intent_no_halt_when_clear(
        self, valid_context: ObservationContext
    ) -> None:
        """AMBIGUOUS_INTENT no HALT when intent clear."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.AMBIGUOUS_INTENT,
            intent_clear=True
        )
        assert result is False  # No HALT
    
    def test_human_abort_halts(
        self, valid_context: ObservationContext
    ) -> None:
        """HUMAN_ABORT triggers HALT when signaled."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.HUMAN_ABORT,
            human_abort_signaled=True
        )
        assert result is True  # HALT
    
    def test_human_abort_no_halt_when_not_signaled(
        self, valid_context: ObservationContext
    ) -> None:
        """HUMAN_ABORT no HALT when not signaled."""
        result = check_stop(
            context=valid_context,
            condition=StopCondition.HUMAN_ABORT,
            human_abort_signaled=False
        )
        assert result is False  # No HALT


class TestDenyByDefault:
    """Test deny-by-default behavior."""
    
    def test_none_context_always_halts(self) -> None:
        """None context always triggers HALT regardless of condition."""
        for condition in StopCondition:
            result = check_stop(context=None, condition=condition)
            assert result is True, f"None context should HALT for {condition}"
    
    def test_halted_context_always_halts(self) -> None:
        """Already halted context always triggers HALT."""
        halted_context = attach_observer(
            loop_id="",  # Empty triggers halt
            executor_id="EXEC-test",
            envelope_hash="hash",
            timestamp="2026-01-25T19:00:00-05:00"
        )
        assert halted_context.is_halted is True
        
        for condition in StopCondition:
            result = check_stop(context=halted_context, condition=condition)
            assert result is True, f"Halted context should HALT for {condition}"
