"""
Phase-32 Decision Validation Tests.

Tests for decision validation in accept_decision().
"""
import pytest

from HUMANOID_HUNTER.decision import (
    HumanDecision,
    DecisionRequest,
    EvidenceSummary,
    accept_decision,
    create_request
)


class TestDecisionValidation:
    """Test accept_decision validation."""
    
    @pytest.fixture
    def sample_request(self) -> DecisionRequest:
        """Create a sample decision request."""
        return create_request(
            session_id="OBS-test123",
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            evidence_timestamp="2026-01-25T19:00:00-05:00",
            chain_length=3,
            execution_state="DISPATCHED",
            confidence_score=0.85,
            chain_hash="abc123hash",
            timeout_seconds=300,
            current_timestamp="2026-01-25T19:01:00-05:00"
        )
    
    def test_continue_valid(self, sample_request: DecisionRequest) -> None:
        """CONTINUE decision is valid with minimal args."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        assert record.decision == HumanDecision.CONTINUE
        assert record.human_id == "human-001"
    
    def test_abort_valid(self, sample_request: DecisionRequest) -> None:
        """ABORT decision is valid with minimal args."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.ABORT,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        assert record.decision == HumanDecision.ABORT
    
    def test_retry_requires_reason(self, sample_request: DecisionRequest) -> None:
        """RETRY decision requires a reason."""
        with pytest.raises(ValueError, match="requires a reason"):
            accept_decision(
                request=sample_request,
                decision=HumanDecision.RETRY,
                human_id="human-001",
                reason=None,
                escalation_target=None,
                timestamp="2026-01-25T19:02:00-05:00"
            )
    
    def test_retry_rejects_empty_reason(self, sample_request: DecisionRequest) -> None:
        """RETRY decision rejects empty reason."""
        with pytest.raises(ValueError, match="requires a reason"):
            accept_decision(
                request=sample_request,
                decision=HumanDecision.RETRY,
                human_id="human-001",
                reason="   ",  # Whitespace only
                escalation_target=None,
                timestamp="2026-01-25T19:02:00-05:00"
            )
    
    def test_retry_valid_with_reason(self, sample_request: DecisionRequest) -> None:
        """RETRY decision is valid with reason."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.RETRY,
            human_id="human-001",
            reason="Network timeout, need to retry",
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        assert record.decision == HumanDecision.RETRY
        assert record.reason == "Network timeout, need to retry"
    
    def test_escalate_requires_reason(self, sample_request: DecisionRequest) -> None:
        """ESCALATE decision requires a reason."""
        with pytest.raises(ValueError, match="requires a reason"):
            accept_decision(
                request=sample_request,
                decision=HumanDecision.ESCALATE,
                human_id="human-001",
                reason=None,
                escalation_target="manager-001",
                timestamp="2026-01-25T19:02:00-05:00"
            )
    
    def test_escalate_requires_target(self, sample_request: DecisionRequest) -> None:
        """ESCALATE decision requires a target."""
        with pytest.raises(ValueError, match="requires an escalation_target"):
            accept_decision(
                request=sample_request,
                decision=HumanDecision.ESCALATE,
                human_id="human-001",
                reason="Needs higher authority",
                escalation_target=None,
                timestamp="2026-01-25T19:02:00-05:00"
            )
    
    def test_escalate_rejects_empty_target(self, sample_request: DecisionRequest) -> None:
        """ESCALATE decision rejects empty target."""
        with pytest.raises(ValueError, match="requires an escalation_target"):
            accept_decision(
                request=sample_request,
                decision=HumanDecision.ESCALATE,
                human_id="human-001",
                reason="Needs higher authority",
                escalation_target="   ",  # Whitespace only
                timestamp="2026-01-25T19:02:00-05:00"
            )
    
    def test_escalate_valid_with_reason_and_target(
        self, sample_request: DecisionRequest
    ) -> None:
        """ESCALATE decision is valid with reason and target."""
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.ESCALATE,
            human_id="human-001",
            reason="Beyond my authority",
            escalation_target="manager-001",
            timestamp="2026-01-25T19:02:00-05:00"
        )
        assert record.decision == HumanDecision.ESCALATE
        assert record.reason == "Beyond my authority"
        assert record.escalation_target == "manager-001"
    
    def test_empty_human_id_rejected(self, sample_request: DecisionRequest) -> None:
        """Empty human_id is rejected."""
        with pytest.raises(ValueError, match="human_id is required"):
            accept_decision(
                request=sample_request,
                decision=HumanDecision.CONTINUE,
                human_id="",
                reason=None,
                escalation_target=None,
                timestamp="2026-01-25T19:02:00-05:00"
            )
    
    def test_whitespace_human_id_rejected(self, sample_request: DecisionRequest) -> None:
        """Whitespace-only human_id is rejected."""
        with pytest.raises(ValueError, match="human_id is required"):
            accept_decision(
                request=sample_request,
                decision=HumanDecision.CONTINUE,
                human_id="   ",
                reason=None,
                escalation_target=None,
                timestamp="2026-01-25T19:02:00-05:00"
            )


class TestDecisionNotAllowed:
    """Test rejection of decisions not in allowed_decisions."""
    
    def test_disallowed_decision_rejected(self) -> None:
        """Decision not in allowed_decisions is rejected."""
        # Create a request with limited allowed decisions
        summary = EvidenceSummary(
            observation_point="PRE_DISPATCH",
            evidence_type="STATE_TRANSITION",
            timestamp="2026-01-25T19:00:00-05:00",
            chain_length=1,
            execution_state="DISPATCHED",
            confidence_score=0.9,
            chain_hash="abc"
        )
        request = DecisionRequest(
            request_id="REQ-test",
            session_id="OBS-test",
            evidence_summary=summary,
            allowed_decisions=(HumanDecision.ABORT,),  # Only ABORT allowed
            created_at="2026-01-25T19:00:00-05:00",
            timeout_at="2026-01-25T19:05:00-05:00",
            timeout_decision=HumanDecision.ABORT
        )
        
        with pytest.raises(ValueError, match="not in allowed decisions"):
            accept_decision(
                request=request,
                decision=HumanDecision.CONTINUE,  # Not allowed!
                human_id="human-001",
                reason=None,
                escalation_target=None,
                timestamp="2026-01-25T19:02:00-05:00"
            )
