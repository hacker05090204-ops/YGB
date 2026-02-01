"""
Phase-32 Apply Decision Tests.

Tests for apply_decision function.
"""
import pytest

from HUMANOID_HUNTER.decision import (
    HumanDecision,
    DecisionOutcome,
    DecisionRecord,
    DecisionRequest,
    create_request,
    accept_decision,
    apply_decision
)


class TestApplyDecision:
    """Test apply_decision function."""
    
    @pytest.fixture
    def sample_request(self) -> DecisionRequest:
        """Create a sample decision request."""
        return create_request(
            session_id="OBS-test",
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            evidence_timestamp="2026-01-25T19:00:00-05:00",
            chain_length=3,
            execution_state="DISPATCHED",
            confidence_score=0.85,
            chain_hash="abc123",
            timeout_seconds=300,
            current_timestamp="2026-01-25T19:01:00-05:00"
        )
    
    def test_abort_always_applied(self, sample_request: DecisionRequest) -> None:
        """ABORT decision is always applicable."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.ABORT,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        # ABORT works even in HALTED state
        result = apply_decision(record, "HALTED")
        assert result == DecisionOutcome.APPLIED
        
        result = apply_decision(record, "DISPATCHED")
        assert result == DecisionOutcome.APPLIED
    
    def test_continue_rejected_in_halted_state(
        self, sample_request: DecisionRequest
    ) -> None:
        """CONTINUE is rejected in HALTED state."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        result = apply_decision(record, "HALTED")
        assert result == DecisionOutcome.REJECTED
    
    def test_continue_applied_in_non_halted_state(
        self, sample_request: DecisionRequest
    ) -> None:
        """CONTINUE is applied in non-HALTED states."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        for state in ["DISPATCHED", "AWAITING_RESPONSE", "EVALUATED", "INIT"]:
            result = apply_decision(record, state)
            assert result == DecisionOutcome.APPLIED, f"CONTINUE should be APPLIED in {state}"
    
    def test_retry_rejected_when_max_retries_exceeded(
        self, sample_request: DecisionRequest
    ) -> None:
        """RETRY is rejected when max retries exceeded."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.RETRY,
            human_id="human-001",
            reason="Try again",
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        result = apply_decision(record, "DISPATCHED", retry_count=3, max_retries=3)
        assert result == DecisionOutcome.REJECTED
    
    def test_retry_applied_when_under_max(
        self, sample_request: DecisionRequest
    ) -> None:
        """RETRY is applied when under max retries."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.RETRY,
            human_id="human-001",
            reason="Try again",
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        result = apply_decision(record, "DISPATCHED", retry_count=0, max_retries=3)
        assert result == DecisionOutcome.APPLIED
        
        result = apply_decision(record, "DISPATCHED", retry_count=2, max_retries=3)
        assert result == DecisionOutcome.APPLIED
    
    def test_escalate_is_pending_with_target(
        self, sample_request: DecisionRequest
    ) -> None:
        """ESCALATE is PENDING when target is specified."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.ESCALATE,
            human_id="human-001",
            reason="Need higher authority",
            escalation_target="manager-001",
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        result = apply_decision(record, "DISPATCHED")
        assert result == DecisionOutcome.PENDING
    
    def test_escalate_rejected_without_target(self) -> None:
        """ESCALATE is REJECTED when target is None (direct record creation)."""
        # Create a record directly to bypass accept_decision validation
        record = DecisionRecord(
            decision_id="DEC-test",
            request_id="REQ-test",
            human_id="human-001",
            decision=HumanDecision.ESCALATE,
            reason="Need higher authority",
            escalation_target=None,  # No target!
            timestamp="2026-01-25T19:02:00-05:00",
            evidence_chain_hash="abc123"
        )
        
        result = apply_decision(record, "DISPATCHED")
        assert result == DecisionOutcome.REJECTED
