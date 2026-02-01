"""
Phase-33 Intent Binding Tests.

Tests for binding decisions to intents.
"""
import pytest

from HUMANOID_HUNTER.decision import (
    HumanDecision,
    DecisionRecord
)
from HUMANOID_HUNTER.intent import (
    BindingResult,
    ExecutionIntent,
    bind_decision,
    validate_intent,
    clear_bound_decisions
)


@pytest.fixture(autouse=True)
def clear_bindings() -> None:
    """Clear bound decisions before each test."""
    clear_bound_decisions()


def create_decision_record(
    decision: HumanDecision,
    decision_id: str = "DEC-test123"
) -> DecisionRecord:
    """Create a test decision record."""
    return DecisionRecord(
        decision_id=decision_id,
        request_id="REQ-test",
        human_id="human-001",
        decision=decision,
        reason="Test reason" if decision in (HumanDecision.RETRY, HumanDecision.ESCALATE) else None,
        escalation_target="manager-001" if decision == HumanDecision.ESCALATE else None,
        timestamp="2026-01-26T01:00:00-05:00",
        evidence_chain_hash="abc123"
    )


class TestBindDecision:
    """Test bind_decision function."""
    
    def test_bind_continue_decision(self) -> None:
        """CONTINUE decision binds successfully."""
        record = create_decision_record(HumanDecision.CONTINUE)
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.SUCCESS
        assert intent is not None
        assert intent.decision_type == HumanDecision.CONTINUE
        assert intent.decision_id == record.decision_id
    
    def test_bind_retry_decision(self) -> None:
        """RETRY decision binds successfully."""
        record = create_decision_record(HumanDecision.RETRY, "DEC-retry1")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.SUCCESS
        assert intent is not None
        assert intent.decision_type == HumanDecision.RETRY
    
    def test_bind_abort_decision(self) -> None:
        """ABORT decision binds successfully."""
        record = create_decision_record(HumanDecision.ABORT, "DEC-abort1")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.SUCCESS
        assert intent is not None
        assert intent.decision_type == HumanDecision.ABORT
    
    def test_bind_escalate_decision(self) -> None:
        """ESCALATE decision binds successfully."""
        record = create_decision_record(HumanDecision.ESCALATE, "DEC-escalate1")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.SUCCESS
        assert intent is not None
        assert intent.decision_type == HumanDecision.ESCALATE
    
    def test_none_decision_rejected(self) -> None:
        """None decision record is rejected."""
        result, intent = bind_decision(
            decision_record=None,  # type: ignore
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.INVALID_DECISION
        assert intent is None
    
    def test_missing_evidence_hash_rejected(self) -> None:
        """Missing evidence hash is rejected."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-miss1")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.MISSING_FIELD
        assert intent is None
    
    def test_missing_session_id_rejected(self) -> None:
        """Missing session ID is rejected."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-miss2")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.MISSING_FIELD
        assert intent is None
    
    def test_missing_execution_state_rejected(self) -> None:
        """Missing execution state is rejected."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-miss3")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.MISSING_FIELD
        assert intent is None
    
    def test_missing_timestamp_rejected(self) -> None:
        """Missing timestamp is rejected."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-miss4")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp=""
        )
        
        assert result == BindingResult.MISSING_FIELD
        assert intent is None
    
    def test_duplicate_binding_rejected(self) -> None:
        """Duplicate binding is rejected."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-dup1")
        
        # First binding succeeds
        result1, intent1 = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        assert result1 == BindingResult.SUCCESS
        
        # Second binding fails
        result2, intent2 = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:06:00-05:00"
        )
        assert result2 == BindingResult.DUPLICATE
        assert intent2 is None
    
    def test_empty_decision_id_rejected(self) -> None:
        """Empty decision_id rejected."""
        record = DecisionRecord(
            decision_id="",  # Empty!
            request_id="REQ-test",
            human_id="human-001",
            decision=HumanDecision.CONTINUE,
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T01:00:00-05:00",
            evidence_chain_hash="abc123"
        )
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.MISSING_FIELD
        assert intent is None
    
    def test_empty_human_id_rejected(self) -> None:
        """Empty human_id rejected."""
        record = DecisionRecord(
            decision_id="DEC-empty-human",
            request_id="REQ-test",
            human_id="",  # Empty!
            decision=HumanDecision.CONTINUE,
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T01:00:00-05:00",
            evidence_chain_hash="abc123"
        )
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.MISSING_FIELD
        assert intent is None
    
    def test_intent_has_correct_hash(self) -> None:
        """Intent hash is computed correctly."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-hash1")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.SUCCESS
        assert intent is not None
        assert len(intent.intent_hash) == 64  # SHA-256


class TestValidateIntent:
    """Test validate_intent function."""
    
    def test_valid_intent_passes(self) -> None:
        """Valid intent passes validation."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-valid1")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert result == BindingResult.SUCCESS
        assert intent is not None
        assert validate_intent(intent, record) is True
    
    def test_none_intent_fails(self) -> None:
        """None intent fails validation."""
        record = create_decision_record(HumanDecision.CONTINUE)
        assert validate_intent(None, record) is False  # type: ignore
    
    def test_none_decision_fails(self) -> None:
        """None decision fails validation."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-none1")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        assert intent is not None
        assert validate_intent(intent, None) is False  # type: ignore
    
    def test_mismatched_decision_id_fails(self) -> None:
        """Mismatched decision ID fails validation."""
        record1 = create_decision_record(HumanDecision.CONTINUE, "DEC-mismatch1")
        result, intent = bind_decision(
            decision_record=record1,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        # Create a different record
        record2 = create_decision_record(HumanDecision.CONTINUE, "DEC-mismatch2")
        
        assert intent is not None
        assert validate_intent(intent, record2) is False
    
    def test_mismatched_decision_type_fails(self) -> None:
        """Mismatched decision type fails validation."""
        record1 = create_decision_record(HumanDecision.CONTINUE, "DEC-typemis1")
        result, intent = bind_decision(
            decision_record=record1,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        # Create a record with same ID but different decision
        record2 = DecisionRecord(
            decision_id="DEC-typemis1",
            request_id="REQ-test",
            human_id="human-001",
            decision=HumanDecision.ABORT,  # Different!
            reason=None,
            escalation_target=None,
            timestamp="2026-01-26T01:00:00-05:00",
            evidence_chain_hash="abc123"
        )
        
        assert intent is not None
        assert validate_intent(intent, record2) is False
    
    def test_tampered_hash_fails(self) -> None:
        """Tampered intent hash fails validation."""
        record = create_decision_record(HumanDecision.CONTINUE, "DEC-tamper1")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        # Create tampered intent
        tampered_intent = ExecutionIntent(
            intent_id=intent.intent_id,
            decision_id=intent.decision_id,
            decision_type=intent.decision_type,
            evidence_chain_hash=intent.evidence_chain_hash,
            session_id=intent.session_id,
            execution_state=intent.execution_state,
            created_at=intent.created_at,
            created_by=intent.created_by,
            intent_hash="TAMPERED_HASH"
        )
        
        assert validate_intent(tampered_intent, record) is False
