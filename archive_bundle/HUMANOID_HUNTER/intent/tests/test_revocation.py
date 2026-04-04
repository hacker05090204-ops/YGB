"""
Phase-33 Intent Revocation Tests.

Tests for intent revocation functionality.
"""
import pytest

from HUMANOID_HUNTER.decision import (
    HumanDecision,
    DecisionRecord
)
from HUMANOID_HUNTER.intent import (
    BindingResult,
    bind_decision,
    revoke_intent,
    clear_bound_decisions
)


@pytest.fixture(autouse=True)
def clear_bindings() -> None:
    """Clear bound decisions before each test."""
    clear_bound_decisions()


def create_decision_record(decision_id: str = "DEC-revoke1") -> DecisionRecord:
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


class TestRevokeIntent:
    """Test revoke_intent function."""
    
    def test_revocation_creates_record(self) -> None:
        """Revocation creates an immutable record."""
        record = create_decision_record()
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        revocation = revoke_intent(
            intent=intent,
            revoked_by="human-002",
            reason="No longer needed",
            timestamp="2026-01-26T01:10:00-05:00"
        )
        
        assert revocation.intent_id == intent.intent_id
        assert revocation.revoked_by == "human-002"
        assert revocation.revocation_reason == "No longer needed"
        assert revocation.revocation_id.startswith("REVOKE-")
    
    def test_revocation_requires_reason(self) -> None:
        """Revocation requires a reason."""
        record = create_decision_record("DEC-revoke2")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        with pytest.raises(ValueError, match="reason is required"):
            revoke_intent(
                intent=intent,
                revoked_by="human-002",
                reason="",
                timestamp="2026-01-26T01:10:00-05:00"
            )
    
    def test_revocation_requires_revoked_by(self) -> None:
        """Revocation requires revoked_by."""
        record = create_decision_record("DEC-revoke3")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        with pytest.raises(ValueError, match="revoked_by is required"):
            revoke_intent(
                intent=intent,
                revoked_by="",
                reason="Test reason",
                timestamp="2026-01-26T01:10:00-05:00"
            )
    
    def test_revocation_requires_timestamp(self) -> None:
        """Revocation requires timestamp."""
        record = create_decision_record("DEC-revoke4")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        with pytest.raises(ValueError, match="timestamp is required"):
            revoke_intent(
                intent=intent,
                revoked_by="human-002",
                reason="Test reason",
                timestamp=""
            )
    
    def test_revocation_has_hash(self) -> None:
        """Revocation has computed hash."""
        record = create_decision_record("DEC-revoke5")
        result, intent = bind_decision(
            decision_record=record,
            evidence_chain_hash="evidence123",
            session_id="OBS-test",
            execution_state="DISPATCHED",
            timestamp="2026-01-26T01:05:00-05:00"
        )
        
        assert intent is not None
        
        revocation = revoke_intent(
            intent=intent,
            revoked_by="human-002",
            reason="No longer needed",
            timestamp="2026-01-26T01:10:00-05:00"
        )
        
        assert len(revocation.revocation_hash) == 64  # SHA-256
