"""
Phase-33 Intent Audit Tests.

Tests for intent audit trail functionality.
"""
import pytest
from dataclasses import FrozenInstanceError

from HUMANOID_HUNTER.decision import (
    HumanDecision,
    DecisionRecord
)
from HUMANOID_HUNTER.intent import (
    BindingResult,
    IntentAudit,
    IntentRecord,
    bind_decision,
    create_empty_audit,
    record_intent,
    is_intent_revoked,
    validate_audit_chain,
    clear_bound_decisions
)


@pytest.fixture(autouse=True)
def clear_bindings() -> None:
    """Clear bound decisions before each test."""
    clear_bound_decisions()


def create_decision_record(decision_id: str = "DEC-audit1") -> DecisionRecord:
    """Create a test decision record."""
    return DecisionRecord(
        decision_id=decision_id,
        request_id="REQ-test",
        human_id="human-001",
        decision=HumanDecision.CONTINUE,
        reason=None,
        escalation_target=None,
        timestamp="2026-01-26T01:00:00-05:00",
        evidence_chain_hash="abc123"
    )


class TestAuditCreation:
    """Test audit trail creation."""
    
    def test_empty_audit_is_valid(self) -> None:
        """Empty audit is valid."""
        audit = create_empty_audit("OBS-test")
        assert validate_audit_chain(audit) is True
        assert audit.length == 0
        assert audit.head_hash == ""
    
    def test_audit_has_correct_session(self) -> None:
        """Audit has correct session ID."""
        audit = create_empty_audit("OBS-session123")
        assert audit.session_id == "OBS-session123"
    
    def test_audit_has_generated_id(self) -> None:
        """Audit has generated ID."""
        audit = create_empty_audit("OBS-test")
        assert audit.audit_id.startswith("IAUDIT-")


class TestRecordIntent:
    """Test record_intent function."""
    
    def test_record_binding_adds_to_audit(self) -> None:
        """Recording binding adds to audit."""
        audit = create_empty_audit("OBS-test")
        
        record = create_decision_record()
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        updated_audit = record_intent(
            audit=audit,
            intent_id=intent.intent_id,
            record_type="BINDING",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert updated_audit.length == 1
        assert len(updated_audit.records) == 1
        assert updated_audit.records[0].record_type == "BINDING"
    
    def test_record_revocation_adds_to_audit(self) -> None:
        """Recording revocation adds to audit."""
        audit = create_empty_audit("OBS-test")
        
        record = create_decision_record("DEC-audit2")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        # Record binding
        audit = record_intent(
            audit=audit,
            intent_id=intent.intent_id,
            record_type="BINDING",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        # Record revocation
        audit = record_intent(
            audit=audit,
            intent_id=intent.intent_id,
            record_type="REVOCATION",
            timestamp="2026-01-26T01:10:00-05:00"
        )
        
        assert audit.length == 2
        assert audit.records[1].record_type == "REVOCATION"
    
    def test_invalid_record_type_rejected(self) -> None:
        """Invalid record type is rejected."""
        audit = create_empty_audit("OBS-test")
        
        with pytest.raises(ValueError, match="Invalid record_type"):
            record_intent(
                audit=audit,
                intent_id="INTENT-test",
                record_type="INVALID",
                timestamp="2026-01-26T01:05:00-05:00"
            )
    
    def test_audit_returns_new_object(self) -> None:
        """record_intent returns new audit object."""
        original = create_empty_audit("OBS-test")
        original_id = id(original)
        
        record = create_decision_record("DEC-audit3")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        updated = record_intent(
            audit=original,
            intent_id=intent.intent_id,
            record_type="BINDING",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        # Different objects
        assert id(updated) != original_id
        # Original unchanged
        assert original.length == 0
        # Updated has record
        assert updated.length == 1


class TestIsIntentRevoked:
    """Test is_intent_revoked function."""
    
    def test_non_revoked_returns_false(self) -> None:
        """Non-revoked intent returns False."""
        audit = create_empty_audit("OBS-test")
        
        record = create_decision_record("DEC-audit4")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        # Record only binding
        audit = record_intent(
            audit=audit,
            intent_id=intent.intent_id,
            record_type="BINDING",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert is_intent_revoked(intent.intent_id, audit) is False
    
    def test_revoked_returns_true(self) -> None:
        """Revoked intent returns True."""
        audit = create_empty_audit("OBS-test")
        
        record = create_decision_record("DEC-audit5")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        # Record binding and revocation
        audit = record_intent(audit, intent.intent_id, "BINDING", "2026-01-26T01:05:00-05:00")
        audit = record_intent(audit, intent.intent_id, "REVOCATION", "2026-01-26T01:10:00-05:00")
        
        assert is_intent_revoked(intent.intent_id, audit) is True
    
    def test_unknown_intent_returns_false(self) -> None:
        """Unknown intent returns False."""
        audit = create_empty_audit("OBS-test")
        assert is_intent_revoked("INTENT-unknown", audit) is False


class TestValidateAuditChain:
    """Test validate_audit_chain function."""
    
    def test_empty_audit_is_valid(self) -> None:
        """Empty audit chain is valid."""
        audit = create_empty_audit("OBS-test")
        assert validate_audit_chain(audit) is True
    
    def test_valid_chain_passes(self) -> None:
        """Valid audit chain passes."""
        audit = create_empty_audit("OBS-test")
        
        record = create_decision_record("DEC-audit6")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        audit = record_intent(audit, intent.intent_id, "BINDING", "2026-01-26T01:05:00-05:00")
        
        assert validate_audit_chain(audit) is True
    
    def test_wrong_length_fails(self) -> None:
        """Wrong length fails validation."""
        audit = IntentAudit(
            audit_id="IAUDIT-test",
            records=(),
            session_id="OBS-test",
            head_hash="",
            length=5  # Wrong!
        )
        assert validate_audit_chain(audit) is False
    
    def test_wrong_head_hash_fails(self) -> None:
        """Wrong head hash fails validation."""
        audit = create_empty_audit("OBS-test")
        
        record = create_decision_record("DEC-audit7")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        valid_audit = record_intent(audit, intent.intent_id, "BINDING", "2026-01-26T01:05:00-05:00")
        
        # Tamper with head hash
        tampered = IntentAudit(
            audit_id=valid_audit.audit_id,
            records=valid_audit.records,
            session_id=valid_audit.session_id,
            head_hash="TAMPERED",
            length=valid_audit.length
        )
        
        assert validate_audit_chain(tampered) is False
    
    def test_wrong_prior_hash_fails(self) -> None:
        """Wrong prior hash fails validation."""
        from HUMANOID_HUNTER.intent.intent_context import IntentRecord
        
        # Create a record with wrong prior_hash
        bad_record = IntentRecord(
            record_id="REC-bad",
            record_type="BINDING",
            intent_id="INTENT-test",
            timestamp="2026-01-26T01:00:00-05:00",
            prior_hash="WRONG_PRIOR",  # Wrong!
            self_hash="abc123"
        )
        
        audit = IntentAudit(
            audit_id="IAUDIT-test",
            records=(bad_record,),
            session_id="OBS-test",
            head_hash="abc123",
            length=1
        )
        
        assert validate_audit_chain(audit) is False
    
    def test_wrong_self_hash_fails(self) -> None:
        """Wrong self hash fails validation."""
        from HUMANOID_HUNTER.intent.intent_context import IntentRecord
        
        # Create a valid-looking record with wrong self_hash
        bad_record = IntentRecord(
            record_id="REC-bad2",
            record_type="BINDING",
            intent_id="INTENT-test",
            timestamp="2026-01-26T01:00:00-05:00",
            prior_hash="",  # Correct for first
            self_hash="WRONG_SELF_HASH"  # Wrong!
        )
        
        audit = IntentAudit(
            audit_id="IAUDIT-test",
            records=(bad_record,),
            session_id="OBS-test",
            head_hash="WRONG_SELF_HASH",
            length=1
        )
        
        assert validate_audit_chain(audit) is False


class TestAuditImmutability:
    """Test audit trail immutability."""
    
    def test_audit_is_frozen(self) -> None:
        """IntentAudit cannot be mutated."""
        audit = create_empty_audit("OBS-test")
        
        with pytest.raises(FrozenInstanceError):
            audit.length = 100  # type: ignore
    
    def test_record_is_frozen(self) -> None:
        """IntentRecord cannot be mutated."""
        record = IntentRecord(
            record_id="REC-test",
            record_type="BINDING",
            intent_id="INTENT-test",
            timestamp="2026-01-26T01:00:00-05:00",
            prior_hash="",
            self_hash="abc123"
        )
        
        with pytest.raises(FrozenInstanceError):
            record.record_type = "REVOCATION"  # type: ignore
    
    def test_audit_records_is_tuple(self) -> None:
        """Audit records is a tuple."""
        audit = create_empty_audit("OBS-test")
        assert isinstance(audit.records, tuple)
