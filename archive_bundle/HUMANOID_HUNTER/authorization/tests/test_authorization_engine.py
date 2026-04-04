"""
Phase-34 Authorization Engine Tests.

Tests for pure functions, deny-by-default, revocation permanence,
audit integrity, and no execution.
"""
import pytest
import hashlib

from HUMANOID_HUNTER.decision import HumanDecision, DecisionRecord
from HUMANOID_HUNTER.intent import (
    ExecutionIntent,
    IntentAudit,
    IntentRecord,
    IntentStatus,
    BindingResult,
    create_empty_audit as create_empty_intent_audit,
    record_intent,
    clear_bound_decisions
)
from HUMANOID_HUNTER.authorization.authorization_types import (
    AuthorizationStatus,
    AuthorizationDecision
)
from HUMANOID_HUNTER.authorization.authorization_context import (
    ExecutionAuthorization,
    AuthorizationRevocation,
    AuthorizationRecord,
    AuthorizationAudit
)
from HUMANOID_HUNTER.authorization.authorization_engine import (
    authorize_execution,
    validate_authorization,
    revoke_authorization,
    record_authorization,
    create_empty_audit,
    is_authorization_revoked,
    is_authorization_valid,
    get_authorization_decision,
    validate_audit_chain,
    clear_authorized_intents
)


def _compute_intent_hash(intent):
    """Recompute intent hash for test fixture creation."""
    hasher = hashlib.sha256()
    hasher.update(intent.intent_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.decision_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.decision_type.name.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.evidence_chain_hash.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.session_id.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.execution_state.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.created_at.encode('utf-8'))
    hasher.update(b'\x00')
    hasher.update(intent.created_by.encode('utf-8'))
    return hasher.hexdigest()


@pytest.fixture
def valid_intent():
    """Create a valid ExecutionIntent."""
    intent = ExecutionIntent(
        intent_id="INTENT-abc12345",
        decision_id="DEC-xyz789",
        decision_type=HumanDecision.CONTINUE,
        evidence_chain_hash="evidencehash123",
        session_id="SESSION-001",
        execution_state="DISPATCHED",
        created_at="2026-01-26T02:00:00-05:00",
        created_by="human-operator-1",
        intent_hash=""  # Will be computed
    )
    # Compute correct hash
    correct_hash = _compute_intent_hash(intent)
    return ExecutionIntent(
        intent_id=intent.intent_id,
        decision_id=intent.decision_id,
        decision_type=intent.decision_type,
        evidence_chain_hash=intent.evidence_chain_hash,
        session_id=intent.session_id,
        execution_state=intent.execution_state,
        created_at=intent.created_at,
        created_by=intent.created_by,
        intent_hash=correct_hash
    )


@pytest.fixture
def intent_audit():
    """Create an empty intent audit."""
    return create_empty_intent_audit("SESSION-001", "IAUDIT-001")


@pytest.fixture(autouse=True)
def setup_teardown():
    """Clear state before and after each test."""
    clear_authorized_intents()
    clear_bound_decisions()
    yield
    clear_authorized_intents()
    clear_bound_decisions()


class TestAuthorizeExecution:
    """Test authorize_execution function."""
    
    def test_valid_intent_returns_allow(self, valid_intent, intent_audit):
        """Valid intent returns ALLOW decision."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.ALLOW
        assert auth is not None
    
    def test_valid_intent_creates_authorization(self, valid_intent, intent_audit):
        """Valid intent creates ExecutionAuthorization."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert isinstance(auth, ExecutionAuthorization)
    
    def test_authorization_has_correct_intent_id(self, valid_intent, intent_audit):
        """Authorization references correct intent."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert auth.intent_id == valid_intent.intent_id
    
    def test_authorization_has_correct_decision_id(self, valid_intent, intent_audit):
        """Authorization references correct decision."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert auth.decision_id == valid_intent.decision_id
    
    def test_authorization_has_correct_session_id(self, valid_intent, intent_audit):
        """Authorization has correct session ID."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert auth.session_id == valid_intent.session_id
    
    def test_authorization_status_is_authorized(self, valid_intent, intent_audit):
        """Authorization status is AUTHORIZED."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert auth.authorization_status == AuthorizationStatus.AUTHORIZED
    
    def test_authorized_by_matches_intent_creator(self, valid_intent, intent_audit):
        """Authorization authorized_by matches intent creator."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert auth.authorized_by == valid_intent.created_by
    
    def test_authorization_has_valid_hash(self, valid_intent, intent_audit):
        """Authorization has non-empty hash."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert auth.authorization_hash
        assert len(auth.authorization_hash) == 64  # SHA-256 hex
    
    def test_none_intent_returns_deny(self, intent_audit):
        """None intent returns DENY."""
        decision, auth = authorize_execution(
            None, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_empty_intent_id_returns_deny(self, intent_audit):
        """Empty intent_id returns DENY."""
        intent = ExecutionIntent(
            intent_id="",
            decision_id="DEC-001",
            decision_type=HumanDecision.CONTINUE,
            evidence_chain_hash="hash",
            session_id="SESSION-001",
            execution_state="DISPATCHED",
            created_at="2026-01-26T02:00:00-05:00",
            created_by="human",
            intent_hash="fakehash"
        )
        decision, auth = authorize_execution(
            intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_empty_decision_id_returns_deny(self, intent_audit):
        """Empty decision_id returns DENY."""
        intent = ExecutionIntent(
            intent_id="INTENT-001",
            decision_id="",
            decision_type=HumanDecision.CONTINUE,
            evidence_chain_hash="hash",
            session_id="SESSION-001",
            execution_state="DISPATCHED",
            created_at="2026-01-26T02:00:00-05:00",
            created_by="human",
            intent_hash="fakehash"
        )
        decision, auth = authorize_execution(
            intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_empty_created_by_returns_deny(self, intent_audit):
        """Empty created_by returns DENY."""
        intent = ExecutionIntent(
            intent_id="INTENT-001",
            decision_id="DEC-001",
            decision_type=HumanDecision.CONTINUE,
            evidence_chain_hash="hash",
            session_id="SESSION-001",
            execution_state="DISPATCHED",
            created_at="2026-01-26T02:00:00-05:00",
            created_by="",
            intent_hash="fakehash"
        )
        decision, auth = authorize_execution(
            intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_empty_session_id_returns_deny(self, intent_audit):
        """Empty session_id returns DENY."""
        intent = ExecutionIntent(
            intent_id="INTENT-001",
            decision_id="DEC-001",
            decision_type=HumanDecision.CONTINUE,
            evidence_chain_hash="hash",
            session_id="",
            execution_state="DISPATCHED",
            created_at="2026-01-26T02:00:00-05:00",
            created_by="human",
            intent_hash="fakehash"
        )
        decision, auth = authorize_execution(
            intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_empty_timestamp_returns_deny(self, valid_intent, intent_audit):
        """Empty timestamp returns DENY."""
        decision, auth = authorize_execution(valid_intent, intent_audit, "")
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_whitespace_timestamp_returns_deny(self, valid_intent, intent_audit):
        """Whitespace timestamp returns DENY."""
        decision, auth = authorize_execution(valid_intent, intent_audit, "   ")
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_invalid_intent_hash_returns_deny(self, intent_audit):
        """Invalid intent hash returns DENY."""
        intent = ExecutionIntent(
            intent_id="INTENT-001",
            decision_id="DEC-001",
            decision_type=HumanDecision.CONTINUE,
            evidence_chain_hash="hash",
            session_id="SESSION-001",
            execution_state="DISPATCHED",
            created_at="2026-01-26T02:00:00-05:00",
            created_by="human",
            intent_hash="invalid_hash_value"
        )
        decision, auth = authorize_execution(
            intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_none_intent_audit_returns_deny(self, valid_intent):
        """None intent_audit returns DENY."""
        decision, auth = authorize_execution(
            valid_intent, None, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_revoked_intent_returns_deny(self, valid_intent):
        """Revoked intent returns DENY."""
        # Create audit with revocation record
        audit = create_empty_intent_audit("SESSION-001", "IAUDIT-001")
        audit = record_intent(audit, valid_intent.intent_id, "REVOCATION", "2026-01-26T02:00:30-05:00")
        
        decision, auth = authorize_execution(
            valid_intent, audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision == AuthorizationDecision.DENY
        assert auth is None
    
    def test_duplicate_authorization_returns_deny(self, valid_intent, intent_audit):
        """Duplicate authorization attempt returns DENY."""
        # First authorization succeeds
        decision1, auth1 = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert decision1 == AuthorizationDecision.ALLOW
        
        # Second authorization fails
        decision2, auth2 = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:02:00-05:00"
        )
        assert decision2 == AuthorizationDecision.DENY
        assert auth2 is None


class TestValidateAuthorization:
    """Test validate_authorization function."""
    
    def test_valid_authorization(self, valid_intent, intent_audit):
        """Valid authorization validates correctly."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert validate_authorization(auth, valid_intent) is True
    
    def test_none_authorization(self, valid_intent):
        """None authorization returns False."""
        assert validate_authorization(None, valid_intent) is False
    
    def test_none_intent(self, valid_intent, intent_audit):
        """None intent returns False."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert validate_authorization(auth, None) is False
    
    def test_mismatched_intent_id(self, valid_intent, intent_audit):
        """Mismatched intent_id returns False."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        # Create different intent
        other_intent = ExecutionIntent(
            intent_id="INTENT-different",
            decision_id=valid_intent.decision_id,
            decision_type=valid_intent.decision_type,
            evidence_chain_hash=valid_intent.evidence_chain_hash,
            session_id=valid_intent.session_id,
            execution_state=valid_intent.execution_state,
            created_at=valid_intent.created_at,
            created_by=valid_intent.created_by,
            intent_hash="differenthash"
        )
        assert validate_authorization(auth, other_intent) is False
    
    def test_mismatched_decision_id(self, valid_intent, intent_audit):
        """Mismatched decision_id returns False."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        other_intent = ExecutionIntent(
            intent_id=valid_intent.intent_id,
            decision_id="DEC-different",
            decision_type=valid_intent.decision_type,
            evidence_chain_hash=valid_intent.evidence_chain_hash,
            session_id=valid_intent.session_id,
            execution_state=valid_intent.execution_state,
            created_at=valid_intent.created_at,
            created_by=valid_intent.created_by,
            intent_hash=valid_intent.intent_hash
        )
        assert validate_authorization(auth, other_intent) is False
    
    def test_mismatched_session_id(self, valid_intent, intent_audit):
        """Mismatched session_id returns False."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        other_intent = ExecutionIntent(
            intent_id=valid_intent.intent_id,
            decision_id=valid_intent.decision_id,
            decision_type=valid_intent.decision_type,
            evidence_chain_hash=valid_intent.evidence_chain_hash,
            session_id="SESSION-different",
            execution_state=valid_intent.execution_state,
            created_at=valid_intent.created_at,
            created_by=valid_intent.created_by,
            intent_hash=valid_intent.intent_hash
        )
        assert validate_authorization(auth, other_intent) is False
    
    def test_mismatched_created_by(self, valid_intent, intent_audit):
        """Mismatched created_by returns False."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        other_intent = ExecutionIntent(
            intent_id=valid_intent.intent_id,
            decision_id=valid_intent.decision_id,
            decision_type=valid_intent.decision_type,
            evidence_chain_hash=valid_intent.evidence_chain_hash,
            session_id=valid_intent.session_id,
            execution_state=valid_intent.execution_state,
            created_at=valid_intent.created_at,
            created_by="different-human",
            intent_hash=valid_intent.intent_hash
        )
        assert validate_authorization(auth, other_intent) is False


class TestRevokeAuthorization:
    """Test revoke_authorization function."""
    
    def test_creates_revocation(self, valid_intent, intent_audit):
        """Creates valid revocation record."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        revocation = revoke_authorization(
            auth, "Security concern", "2026-01-26T02:30:00-05:00", "supervisor"
        )
        assert isinstance(revocation, AuthorizationRevocation)
    
    def test_revocation_authorization_id(self, valid_intent, intent_audit):
        """Revocation references correct authorization."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        revocation = revoke_authorization(
            auth, "Security concern", "2026-01-26T02:30:00-05:00", "supervisor"
        )
        assert revocation.authorization_id == auth.authorization_id
    
    def test_revocation_has_reason(self, valid_intent, intent_audit):
        """Revocation has correct reason."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        revocation = revoke_authorization(
            auth, "Security concern", "2026-01-26T02:30:00-05:00", "supervisor"
        )
        assert revocation.revocation_reason == "Security concern"
    
    def test_revocation_has_revoked_by(self, valid_intent, intent_audit):
        """Revocation has correct revoked_by."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        revocation = revoke_authorization(
            auth, "Security concern", "2026-01-26T02:30:00-05:00", "supervisor"
        )
        assert revocation.revoked_by == "supervisor"
    
    def test_revocation_has_timestamp(self, valid_intent, intent_audit):
        """Revocation has correct timestamp."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        revocation = revoke_authorization(
            auth, "Security concern", "2026-01-26T02:30:00-05:00", "supervisor"
        )
        assert revocation.revoked_at == "2026-01-26T02:30:00-05:00"
    
    def test_revocation_has_valid_hash(self, valid_intent, intent_audit):
        """Revocation has non-empty hash."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        revocation = revoke_authorization(
            auth, "Security concern", "2026-01-26T02:30:00-05:00", "supervisor"
        )
        assert revocation.revocation_hash
        assert len(revocation.revocation_hash) == 64
    
    def test_none_authorization_raises(self):
        """None authorization raises ValueError."""
        with pytest.raises(ValueError, match="authorization is required"):
            revoke_authorization(None, "reason", "timestamp", "human")
    
    def test_empty_revoked_by_raises(self, valid_intent, intent_audit):
        """Empty revoked_by raises ValueError."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        with pytest.raises(ValueError, match="revoked_by is required"):
            revoke_authorization(auth, "reason", "timestamp", "")
    
    def test_whitespace_revoked_by_raises(self, valid_intent, intent_audit):
        """Whitespace revoked_by raises ValueError."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        with pytest.raises(ValueError, match="revoked_by is required"):
            revoke_authorization(auth, "reason", "timestamp", "   ")
    
    def test_empty_reason_raises(self, valid_intent, intent_audit):
        """Empty reason raises ValueError."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        with pytest.raises(ValueError, match="revocation reason is required"):
            revoke_authorization(auth, "", "timestamp", "human")
    
    def test_empty_timestamp_raises(self, valid_intent, intent_audit):
        """Empty timestamp raises ValueError."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        with pytest.raises(ValueError, match="timestamp is required"):
            revoke_authorization(auth, "reason", "", "human")


class TestRecordAuthorization:
    """Test record_authorization function."""
    
    def test_records_authorization(self):
        """Records authorization in audit."""
        audit = create_empty_audit("SESSION-001")
        new_audit = record_authorization(
            audit, "AUTH-001", "AUTHORIZATION", "2026-01-26T02:01:00-05:00"
        )
        assert new_audit.length == 1
    
    def test_records_revocation(self):
        """Records revocation in audit."""
        audit = create_empty_audit("SESSION-001")
        new_audit = record_authorization(
            audit, "AUTH-001", "REVOCATION", "2026-01-26T02:01:00-05:00"
        )
        assert new_audit.length == 1
        assert new_audit.records[0].record_type == "REVOCATION"
    
    def test_returns_new_audit(self):
        """Returns new audit instance (immutable)."""
        audit = create_empty_audit("SESSION-001")
        new_audit = record_authorization(
            audit, "AUTH-001", "AUTHORIZATION", "2026-01-26T02:01:00-05:00"
        )
        assert audit is not new_audit
        assert audit.length == 0
        assert new_audit.length == 1
    
    def test_preserves_session_id(self):
        """Preserves session ID."""
        audit = create_empty_audit("SESSION-001")
        new_audit = record_authorization(
            audit, "AUTH-001", "AUTHORIZATION", "2026-01-26T02:01:00-05:00"
        )
        assert new_audit.session_id == "SESSION-001"
    
    def test_updates_head_hash(self):
        """Updates head hash."""
        audit = create_empty_audit("SESSION-001")
        new_audit = record_authorization(
            audit, "AUTH-001", "AUTHORIZATION", "2026-01-26T02:01:00-05:00"
        )
        assert new_audit.head_hash != ""
        assert new_audit.head_hash == new_audit.records[0].self_hash
    
    def test_invalid_record_type_raises(self):
        """Invalid record_type raises ValueError."""
        audit = create_empty_audit("SESSION-001")
        with pytest.raises(ValueError, match="Invalid record_type"):
            record_authorization(audit, "AUTH-001", "INVALID", "timestamp")
    
    def test_chain_integrity(self):
        """Chain integrity is maintained."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        audit = record_authorization(audit, "AUTH-002", "AUTHORIZATION", "t2")
        audit = record_authorization(audit, "AUTH-001", "REVOCATION", "t3")
        
        # Verify chain
        assert audit.length == 3
        assert audit.records[0].prior_hash == ""
        assert audit.records[1].prior_hash == audit.records[0].self_hash
        assert audit.records[2].prior_hash == audit.records[1].self_hash
        assert audit.head_hash == audit.records[2].self_hash


class TestCreateEmptyAudit:
    """Test create_empty_audit function."""
    
    def test_creates_audit(self):
        """Creates empty audit."""
        audit = create_empty_audit("SESSION-001")
        assert isinstance(audit, AuthorizationAudit)
    
    def test_empty_records(self):
        """Has empty records."""
        audit = create_empty_audit("SESSION-001")
        assert audit.records == ()
    
    def test_zero_length(self):
        """Has zero length."""
        audit = create_empty_audit("SESSION-001")
        assert audit.length == 0
    
    def test_empty_head_hash(self):
        """Has empty head hash."""
        audit = create_empty_audit("SESSION-001")
        assert audit.head_hash == ""
    
    def test_correct_session_id(self):
        """Has correct session ID."""
        audit = create_empty_audit("SESSION-001")
        assert audit.session_id == "SESSION-001"
    
    def test_generated_audit_id(self):
        """Generates audit ID if not provided."""
        audit = create_empty_audit("SESSION-001")
        assert audit.audit_id.startswith("AUTHAUDIT-")
    
    def test_custom_audit_id(self):
        """Uses custom audit ID if provided."""
        audit = create_empty_audit("SESSION-001", "MY-AUDIT-ID")
        assert audit.audit_id == "MY-AUDIT-ID"


class TestIsAuthorizationRevoked:
    """Test is_authorization_revoked function."""
    
    def test_not_revoked(self):
        """Returns False when not revoked."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        assert is_authorization_revoked("AUTH-001", audit) is False
    
    def test_revoked(self):
        """Returns True when revoked."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        audit = record_authorization(audit, "AUTH-001", "REVOCATION", "t2")
        assert is_authorization_revoked("AUTH-001", audit) is True
    
    def test_different_authorization_not_revoked(self):
        """Other authorization revocation doesn't affect this one."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        audit = record_authorization(audit, "AUTH-002", "REVOCATION", "t2")
        assert is_authorization_revoked("AUTH-001", audit) is False


class TestIsAuthorizationValid:
    """Test is_authorization_valid function."""
    
    def test_valid_authorization(self, valid_intent, intent_audit):
        """Valid authorization returns True."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        auth_audit = create_empty_audit("SESSION-001")
        auth_audit = record_authorization(
            auth_audit, auth.authorization_id, "AUTHORIZATION", "t1"
        )
        
        assert is_authorization_valid(auth, valid_intent, intent_audit, auth_audit) is True
    
    def test_revoked_intent(self, valid_intent):
        """Revoked intent returns False."""
        intent_audit_with_revocation = create_empty_intent_audit("SESSION-001")
        intent_audit_with_revocation = record_intent(
            intent_audit_with_revocation, valid_intent.intent_id, "REVOCATION", "t0"
        )
        
        # Need to create auth first with non-revoked audit
        intent_audit_clean = create_empty_intent_audit("SESSION-001")
        decision, auth = authorize_execution(
            valid_intent, intent_audit_clean, "2026-01-26T02:01:00-05:00"
        )
        auth_audit = create_empty_audit("SESSION-001")
        
        # Now check with revoked intent audit
        assert is_authorization_valid(
            auth, valid_intent, intent_audit_with_revocation, auth_audit
        ) is False
    
    def test_revoked_authorization(self, valid_intent, intent_audit):
        """Revoked authorization returns False."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        auth_audit = create_empty_audit("SESSION-001")
        auth_audit = record_authorization(
            auth_audit, auth.authorization_id, "AUTHORIZATION", "t1"
        )
        auth_audit = record_authorization(
            auth_audit, auth.authorization_id, "REVOCATION", "t2"
        )
        
        assert is_authorization_valid(auth, valid_intent, intent_audit, auth_audit) is False


class TestGetAuthorizationDecision:
    """Test get_authorization_decision function."""
    
    def test_authorized_returns_allow(self, valid_intent, intent_audit):
        """AUTHORIZED status returns ALLOW."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        assert get_authorization_decision(auth) == AuthorizationDecision.ALLOW
    
    def test_none_returns_deny(self):
        """None returns DENY."""
        assert get_authorization_decision(None) == AuthorizationDecision.DENY
    
    def test_rejected_returns_deny(self):
        """REJECTED status returns DENY."""
        auth = ExecutionAuthorization(
            authorization_id="AUTH-001",
            intent_id="INTENT-001",
            decision_id="DEC-001",
            session_id="SESSION-001",
            authorization_status=AuthorizationStatus.REJECTED,
            authorized_by="human",
            authorized_at="timestamp",
            authorization_hash="hash"
        )
        assert get_authorization_decision(auth) == AuthorizationDecision.DENY
    
    def test_revoked_returns_deny(self):
        """REVOKED status returns DENY."""
        auth = ExecutionAuthorization(
            authorization_id="AUTH-001",
            intent_id="INTENT-001",
            decision_id="DEC-001",
            session_id="SESSION-001",
            authorization_status=AuthorizationStatus.REVOKED,
            authorized_by="human",
            authorized_at="timestamp",
            authorization_hash="hash"
        )
        assert get_authorization_decision(auth) == AuthorizationDecision.DENY
    
    def test_expired_returns_deny(self):
        """EXPIRED status returns DENY."""
        auth = ExecutionAuthorization(
            authorization_id="AUTH-001",
            intent_id="INTENT-001",
            decision_id="DEC-001",
            session_id="SESSION-001",
            authorization_status=AuthorizationStatus.EXPIRED,
            authorized_by="human",
            authorized_at="timestamp",
            authorization_hash="hash"
        )
        assert get_authorization_decision(auth) == AuthorizationDecision.DENY


class TestValidateAuditChain:
    """Test validate_audit_chain function."""
    
    def test_empty_audit_valid(self):
        """Empty audit is valid."""
        audit = create_empty_audit("SESSION-001")
        assert validate_audit_chain(audit) is True
    
    def test_single_record_valid(self):
        """Single record chain is valid."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        assert validate_audit_chain(audit) is True
    
    def test_multi_record_valid(self):
        """Multi-record chain is valid."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        audit = record_authorization(audit, "AUTH-002", "AUTHORIZATION", "t2")
        audit = record_authorization(audit, "AUTH-001", "REVOCATION", "t3")
        assert validate_audit_chain(audit) is True
    
    def test_tampered_head_hash_invalid(self):
        """Tampered head hash is invalid."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        
        # Tamper with head hash
        tampered = AuthorizationAudit(
            audit_id=audit.audit_id,
            records=audit.records,
            session_id=audit.session_id,
            head_hash="tampered_hash",
            length=audit.length
        )
        assert validate_audit_chain(tampered) is False
    
    def test_length_mismatch_invalid(self):
        """Length mismatch is invalid."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        
        # Create mismatch
        tampered = AuthorizationAudit(
            audit_id=audit.audit_id,
            records=audit.records,
            session_id=audit.session_id,
            head_hash=audit.head_hash,
            length=999
        )
        assert validate_audit_chain(tampered) is False
    
    def test_empty_audit_with_wrong_head_hash_invalid(self):
        """Empty audit with non-empty head hash is invalid."""
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-001",
            records=(),
            session_id="SESSION-001",
            head_hash="should_be_empty",
            length=0
        )
        assert validate_audit_chain(audit) is False


class TestForbiddenImports:
    """Test that forbidden modules are not imported."""
    
    def test_no_os_import(self):
        """Module does not import os."""
        import HUMANOID_HUNTER.authorization.authorization_engine as module
        source = open(module.__file__).read()
        assert "import os" not in source
        assert "from os" not in source
    
    def test_no_subprocess_import(self):
        """Module does not import subprocess."""
        import HUMANOID_HUNTER.authorization.authorization_engine as module
        source = open(module.__file__).read()
        assert "import subprocess" not in source
        assert "from subprocess" not in source
    
    def test_no_socket_import(self):
        """Module does not import socket."""
        import HUMANOID_HUNTER.authorization.authorization_engine as module
        source = open(module.__file__).read()
        assert "import socket" not in source
        assert "from socket" not in source
    
    def test_no_asyncio_import(self):
        """Module does not import asyncio."""
        import HUMANOID_HUNTER.authorization.authorization_engine as module
        source = open(module.__file__).read()
        assert "import asyncio" not in source
        assert "from asyncio" not in source
    
    def test_no_exec_or_eval(self):
        """Module does not use exec or eval."""
        import HUMANOID_HUNTER.authorization.authorization_engine as module
        source = open(module.__file__).read()
        # Check for exec( and eval( to avoid matching variable names
        assert "exec(" not in source
        assert "eval(" not in source


class TestNoExecution:
    """Test that no execution occurs."""
    
    def test_authorize_execution_does_not_execute(self, valid_intent, intent_audit):
        """authorize_execution creates data, does not execute."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        # If no exception, no execution occurred
        # This is a sanity check that we only create data
        assert isinstance(auth, ExecutionAuthorization)
        assert auth.authorization_status == AuthorizationStatus.AUTHORIZED
        # Authorization is DATA, not action
    
    def test_authorization_is_permission_not_invocation(self, valid_intent, intent_audit):
        """Authorization represents permission, not invocation."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        # Decision is ALLOW but nothing is invoked
        assert decision == AuthorizationDecision.ALLOW
        # No side effects, no execution
        # This is verified by the test completing without external effects


class TestValidateAuthorizationHashMismatch:
    """Test validate_authorization with hash mismatch (line 326)."""
    
    def test_tampered_authorization_hash_returns_false(self, valid_intent, intent_audit):
        """Authorization with tampered hash returns False."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        # Create a tampered authorization with wrong hash
        tampered_auth = ExecutionAuthorization(
            authorization_id=auth.authorization_id,
            intent_id=auth.intent_id,
            decision_id=auth.decision_id,
            session_id=auth.session_id,
            authorization_status=auth.authorization_status,
            authorized_by=auth.authorized_by,
            authorized_at=auth.authorized_at,
            authorization_hash="tampered_hash_value"
        )
        assert validate_authorization(tampered_auth, valid_intent) is False


class TestIsAuthorizationValidEdgeCases:
    """Test is_authorization_valid edge cases for coverage."""
    
    def test_invalid_authorization_intent_mismatch(self, valid_intent, intent_audit):
        """Returns False when authorization doesn't match intent (line 514)."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        # Create a different intent that won't match
        other_intent = ExecutionIntent(
            intent_id="INTENT-different",
            decision_id=valid_intent.decision_id,
            decision_type=valid_intent.decision_type,
            evidence_chain_hash=valid_intent.evidence_chain_hash,
            session_id=valid_intent.session_id,
            execution_state=valid_intent.execution_state,
            created_at=valid_intent.created_at,
            created_by=valid_intent.created_by,
            intent_hash="differenthash"
        )
        auth_audit = create_empty_audit("SESSION-001")
        
        assert is_authorization_valid(auth, other_intent, intent_audit, auth_audit) is False
    
    def test_non_authorized_status_returns_false(self, valid_intent, intent_audit):
        """Returns False when status is not AUTHORIZED (lines 517-518)."""
        decision, auth = authorize_execution(
            valid_intent, intent_audit, "2026-01-26T02:01:00-05:00"
        )
        # Create authorization with REJECTED status (but matching hash for valid auth)
        rejected_auth = ExecutionAuthorization(
            authorization_id=auth.authorization_id,
            intent_id=auth.intent_id,
            decision_id=auth.decision_id,
            session_id=auth.session_id,
            authorization_status=AuthorizationStatus.REJECTED,
            authorized_by=auth.authorized_by,
            authorized_at=auth.authorized_at,
            authorization_hash="some_hash"  # Different hash since status changed
        )
        auth_audit = create_empty_audit("SESSION-001")
        
        # This should fail at validate_authorization due to hash mismatch
        # Let's create a properly formed rejected auth
        import hashlib
        hasher = hashlib.sha256()
        hasher.update(auth.authorization_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(auth.intent_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(auth.decision_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(auth.session_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(AuthorizationStatus.REJECTED.name.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(auth.authorized_by.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(auth.authorized_at.encode('utf-8'))
        correct_hash = hasher.hexdigest()
        
        rejected_auth = ExecutionAuthorization(
            authorization_id=auth.authorization_id,
            intent_id=auth.intent_id,
            decision_id=auth.decision_id,
            session_id=auth.session_id,
            authorization_status=AuthorizationStatus.REJECTED,
            authorized_by=auth.authorized_by,
            authorized_at=auth.authorized_at,
            authorization_hash=correct_hash
        )
        
        assert is_authorization_valid(rejected_auth, valid_intent, intent_audit, auth_audit) is False


class TestValidateAuditChainTamperedRecords:
    """Test validate_audit_chain with tampered records for coverage."""
    
    def test_tampered_prior_hash_invalid(self):
        """Tampered prior_hash is invalid (lines 576-577)."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        audit = record_authorization(audit, "AUTH-002", "AUTHORIZATION", "t2")
        
        # Get the second record
        original_record = audit.records[1]
        
        # Create tampered record with wrong prior_hash
        tampered_record = AuthorizationRecord(
            record_id=original_record.record_id,
            record_type=original_record.record_type,
            authorization_id=original_record.authorization_id,
            timestamp=original_record.timestamp,
            prior_hash="tampered_prior_hash",
            self_hash=original_record.self_hash
        )
        
        # Create tampered audit with the bad record
        tampered_audit = AuthorizationAudit(
            audit_id=audit.audit_id,
            records=(audit.records[0], tampered_record),
            session_id=audit.session_id,
            head_hash=audit.head_hash,
            length=audit.length
        )
        
        assert validate_audit_chain(tampered_audit) is False
    
    def test_tampered_self_hash_invalid(self):
        """Tampered self_hash is invalid (lines 587-588)."""
        audit = create_empty_audit("SESSION-001")
        audit = record_authorization(audit, "AUTH-001", "AUTHORIZATION", "t1")
        
        # Get the record
        original_record = audit.records[0]
        
        # Create tampered record with wrong self_hash
        tampered_record = AuthorizationRecord(
            record_id=original_record.record_id,
            record_type=original_record.record_type,
            authorization_id=original_record.authorization_id,
            timestamp=original_record.timestamp,
            prior_hash=original_record.prior_hash,
            self_hash="tampered_self_hash"
        )
        
        # Create tampered audit with the bad record
        tampered_audit = AuthorizationAudit(
            audit_id=audit.audit_id,
            records=(tampered_record,),
            session_id=audit.session_id,
            head_hash=audit.head_hash,
            length=audit.length
        )
        
        assert validate_audit_chain(tampered_audit) is False
