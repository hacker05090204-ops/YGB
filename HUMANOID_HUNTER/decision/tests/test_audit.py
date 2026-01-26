"""
Phase-32 Audit Trail Tests.

Tests for decision audit append-only behavior and immutability.
"""
import pytest
from dataclasses import FrozenInstanceError

from HUMANOID_HUNTER.decision import (
    HumanDecision,
    DecisionRecord,
    DecisionAudit,
    DecisionRequest,
    create_request,
    accept_decision,
    record_decision,
    create_empty_audit,
    validate_audit_chain
)


class TestAuditAppendOnly:
    """Test audit trail is append-only."""
    
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
    
    def test_empty_audit_is_valid(self) -> None:
        """Empty audit is valid."""
        audit = create_empty_audit("OBS-test")
        assert validate_audit_chain(audit) is True
        assert audit.length == 0
    
    def test_record_decision_returns_new_audit(
        self, sample_request: DecisionRequest
    ) -> None:
        """record_decision returns a new audit, not modifying original."""
        original_audit = create_empty_audit("OBS-test")
        original_id = id(original_audit)
        
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        new_audit = record_decision(original_audit, record)
        
        # New audit is a different object
        assert id(new_audit) != original_id
        
        # Original audit is unchanged
        assert original_audit.length == 0
        assert new_audit.length == 1
    
    def test_record_decision_adds_to_records(
        self, sample_request: DecisionRequest
    ) -> None:
        """record_decision adds to records tuple."""
        audit = create_empty_audit("OBS-test")
        
        record = accept_decision(
            request=sample_request,
            decision=HumanDecision.ABORT,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        updated_audit = record_decision(audit, record)
        
        assert len(updated_audit.records) == 1
        assert updated_audit.records[0] == record
    
    def test_multiple_records_in_sequence(
        self, sample_request: DecisionRequest
    ) -> None:
        """Multiple records can be added in sequence."""
        audit = create_empty_audit("OBS-test")
        
        # First decision
        record1 = accept_decision(
            request=sample_request,
            decision=HumanDecision.RETRY,
            human_id="human-001",
            reason="Try again",
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        audit = record_decision(audit, record1)
        
        # Second decision
        record2 = accept_decision(
            request=sample_request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:03:00-05:00"
        )
        audit = record_decision(audit, record2)
        
        assert audit.length == 2
        assert validate_audit_chain(audit) is True


class TestAuditImmutability:
    """Test audit trail immutability."""
    
    def test_decision_audit_is_frozen(self) -> None:
        """DecisionAudit cannot be mutated."""
        audit = create_empty_audit("OBS-test")
        
        with pytest.raises(FrozenInstanceError):
            audit.length = 100  # type: ignore
    
    def test_decision_record_is_frozen(self) -> None:
        """DecisionRecord cannot be mutated."""
        request = create_request(
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
        
        record = accept_decision(
            request=request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        with pytest.raises(FrozenInstanceError):
            record.decision = HumanDecision.ABORT  # type: ignore
    
    def test_audit_records_is_tuple(self) -> None:
        """Audit records is a tuple (immutable)."""
        audit = create_empty_audit("OBS-test")
        assert isinstance(audit.records, tuple)


class TestAuditChainIntegrity:
    """Test audit chain hash integrity."""
    
    def test_audit_has_non_empty_hash_after_record(self) -> None:
        """Audit has non-empty head_hash after adding record."""
        audit = create_empty_audit("OBS-test")
        assert audit.head_hash == ""
        
        request = create_request(
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
        
        record = accept_decision(
            request=request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        updated_audit = record_decision(audit, record)
        
        assert updated_audit.head_hash != ""
        assert len(updated_audit.head_hash) == 64  # SHA-256
    
    def test_valid_chain_passes_validation(self) -> None:
        """Valid audit chain passes validation."""
        audit = create_empty_audit("OBS-test")
        
        request = create_request(
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
        
        record = accept_decision(
            request=request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        audit = record_decision(audit, record)
        
        assert validate_audit_chain(audit) is True
    
    def test_wrong_length_fails_validation(self) -> None:
        """Audit with wrong length fails validation."""
        audit = DecisionAudit(
            audit_id="AUDIT-test",
            records=(),
            session_id="OBS-test",
            head_hash="",
            length=5  # Wrong! Should be 0
        )
        
        assert validate_audit_chain(audit) is False
    
    def test_wrong_head_hash_fails_validation(self) -> None:
        """Audit with wrong head_hash fails validation."""
        audit = create_empty_audit("OBS-test")
        
        request = create_request(
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
        
        record = accept_decision(
            request=request,
            decision=HumanDecision.CONTINUE,
            human_id="human-001",
            reason=None,
            escalation_target=None,
            timestamp="2026-01-25T19:02:00-05:00"
        )
        
        valid_audit = record_decision(audit, record)
        
        # Create audit with wrong head_hash
        tampered_audit = DecisionAudit(
            audit_id=valid_audit.audit_id,
            records=valid_audit.records,
            session_id=valid_audit.session_id,
            head_hash="TAMPERED_HASH",  # Wrong!
            length=valid_audit.length
        )
        
        assert validate_audit_chain(tampered_audit) is False
