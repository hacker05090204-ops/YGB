"""
Phase-33 Immutability Tests.

Tests for dataclass immutability.
"""
import pytest
from dataclasses import FrozenInstanceError

from HUMANOID_HUNTER.decision import HumanDecision
from HUMANOID_HUNTER.intent import (
    ExecutionIntent,
    IntentRevocation,
    IntentRecord,
    IntentAudit
)


class TestExecutionIntentImmutability:
    """Test ExecutionIntent immutability."""
    
    def test_intent_is_frozen(self) -> None:
        """ExecutionIntent cannot be mutated."""
        intent = ExecutionIntent(
            intent_id="INTENT-test",
            decision_id="DEC-test",
            decision_type=HumanDecision.CONTINUE,
            evidence_chain_hash="abc123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            created_at="2026-01-26T01:00:00-05:00",
            created_by="human-001",
            intent_hash="hash123"
        )
        
        with pytest.raises(FrozenInstanceError):
            intent.decision_type = HumanDecision.ABORT  # type: ignore
    
    def test_intent_id_immutable(self) -> None:
        """Intent ID cannot be changed."""
        intent = ExecutionIntent(
            intent_id="INTENT-test",
            decision_id="DEC-test",
            decision_type=HumanDecision.CONTINUE,
            evidence_chain_hash="abc123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            created_at="2026-01-26T01:00:00-05:00",
            created_by="human-001",
            intent_hash="hash123"
        )
        
        with pytest.raises(FrozenInstanceError):
            intent.intent_id = "INTENT-new"  # type: ignore
    
    def test_intent_hash_immutable(self) -> None:
        """Intent hash cannot be changed."""
        intent = ExecutionIntent(
            intent_id="INTENT-test",
            decision_id="DEC-test",
            decision_type=HumanDecision.CONTINUE,
            evidence_chain_hash="abc123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            created_at="2026-01-26T01:00:00-05:00",
            created_by="human-001",
            intent_hash="hash123"
        )
        
        with pytest.raises(FrozenInstanceError):
            intent.intent_hash = "TAMPERED"  # type: ignore


class TestIntentRevocationImmutability:
    """Test IntentRevocation immutability."""
    
    def test_revocation_is_frozen(self) -> None:
        """IntentRevocation cannot be mutated."""
        revocation = IntentRevocation(
            revocation_id="REVOKE-test",
            intent_id="INTENT-test",
            revoked_by="human-001",
            revocation_reason="No longer needed",
            revoked_at="2026-01-26T01:10:00-05:00",
            revocation_hash="hash123"
        )
        
        with pytest.raises(FrozenInstanceError):
            revocation.revocation_reason = "Changed reason"  # type: ignore
    
    def test_revocation_cannot_be_undone(self) -> None:
        """Revocation intent_id cannot be cleared."""
        revocation = IntentRevocation(
            revocation_id="REVOKE-test",
            intent_id="INTENT-test",
            revoked_by="human-001",
            revocation_reason="No longer needed",
            revoked_at="2026-01-26T01:10:00-05:00",
            revocation_hash="hash123"
        )
        
        with pytest.raises(FrozenInstanceError):
            revocation.intent_id = ""  # type: ignore


class TestIntentRecordImmutability:
    """Test IntentRecord immutability."""
    
    def test_record_is_frozen(self) -> None:
        """IntentRecord cannot be mutated."""
        record = IntentRecord(
            record_id="REC-test",
            record_type="BINDING",
            intent_id="INTENT-test",
            timestamp="2026-01-26T01:00:00-05:00",
            prior_hash="",
            self_hash="hash123"
        )
        
        with pytest.raises(FrozenInstanceError):
            record.record_type = "REVOCATION"  # type: ignore
    
    def test_record_hash_immutable(self) -> None:
        """Record hash cannot be changed."""
        record = IntentRecord(
            record_id="REC-test",
            record_type="BINDING",
            intent_id="INTENT-test",
            timestamp="2026-01-26T01:00:00-05:00",
            prior_hash="",
            self_hash="hash123"
        )
        
        with pytest.raises(FrozenInstanceError):
            record.self_hash = "TAMPERED"  # type: ignore


class TestIntentAuditImmutability:
    """Test IntentAudit immutability."""
    
    def test_audit_is_frozen(self) -> None:
        """IntentAudit cannot be mutated."""
        audit = IntentAudit(
            audit_id="IAUDIT-test",
            records=(),
            session_id="OBS-test",
            head_hash="",
            length=0
        )
        
        with pytest.raises(FrozenInstanceError):
            audit.length = 100  # type: ignore
    
    def test_audit_records_immutable(self) -> None:
        """Audit records tuple cannot be replaced."""
        audit = IntentAudit(
            audit_id="IAUDIT-test",
            records=(),
            session_id="OBS-test",
            head_hash="",
            length=0
        )
        
        with pytest.raises(FrozenInstanceError):
            audit.records = (None,)  # type: ignore
