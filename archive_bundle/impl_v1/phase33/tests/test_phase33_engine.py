"""
Phase-33 Engine Tests.

Tests for pure validation functions.
Deny-by-default on ALL ambiguous inputs.
"""
import pytest
import hashlib


class TestValidateIntentId:
    """Test validate_intent_id function."""

    def test_valid_intent_id(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_intent_id
        assert validate_intent_id("INTENT-abc12345") is True

    def test_none_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_intent_id
        assert validate_intent_id(None) is False  # type: ignore

    def test_empty_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_intent_id
        assert validate_intent_id("") is False

    def test_whitespace_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_intent_id
        assert validate_intent_id("   ") is False

    def test_wrong_prefix_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_intent_id
        assert validate_intent_id("AUTH-abc12345") is False

    def test_short_hex_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_intent_id
        assert validate_intent_id("INTENT-abc") is False

    def test_integer_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_intent_id
        assert validate_intent_id(12345) is False  # type: ignore


class TestValidateIntentHash:
    """Test validate_intent_hash function."""

    def _compute_hash(self, intent_id, decision_id, decision_type, evidence_hash, session_id, state, created_at, created_by):
        hasher = hashlib.sha256()
        hasher.update(intent_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(decision_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(decision_type.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(evidence_hash.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(session_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(state.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(created_at.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(created_by.encode('utf-8'))
        return hasher.hexdigest()

    def test_valid_hash_returns_true(self) -> None:
        from impl_v1.phase33.phase33_context import ExecutionIntent
        from impl_v1.phase33.phase33_engine import validate_intent_hash
        
        h = self._compute_hash("INTENT-abc12345", "DEC-def67890", "CONTINUE", "ev", "SESS-1", "STATE", "2026-01-26T12:00:00Z", "human")
        intent = ExecutionIntent(
            intent_id="INTENT-abc12345",
            decision_id="DEC-def67890",
            decision_type="CONTINUE",
            evidence_chain_hash="ev",
            session_id="SESS-1",
            execution_state="STATE",
            created_at="2026-01-26T12:00:00Z",
            created_by="human",
            intent_hash=h
        )
        assert validate_intent_hash(intent) is True

    def test_none_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_intent_hash
        assert validate_intent_hash(None) is False  # type: ignore

    def test_tampered_hash_returns_false(self) -> None:
        from impl_v1.phase33.phase33_context import ExecutionIntent
        from impl_v1.phase33.phase33_engine import validate_intent_hash
        intent = ExecutionIntent(
            intent_id="INTENT-abc12345",
            decision_id="DEC-def67890",
            decision_type="CONTINUE",
            evidence_chain_hash="ev",
            session_id="SESS-1",
            execution_state="STATE",
            created_at="2026-01-26T12:00:00Z",
            created_by="human",
            intent_hash="tampered"
        )
        assert validate_intent_hash(intent) is False

    def test_empty_hash_returns_false(self) -> None:
        from impl_v1.phase33.phase33_context import ExecutionIntent
        from impl_v1.phase33.phase33_engine import validate_intent_hash
        intent = ExecutionIntent(
            intent_id="INTENT-abc12345",
            decision_id="DEC-def67890",
            decision_type="CONTINUE",
            evidence_chain_hash="ev",
            session_id="SESS-1",
            execution_state="STATE",
            created_at="2026-01-26T12:00:00Z",
            created_by="human",
            intent_hash=""
        )
        assert validate_intent_hash(intent) is False


class TestValidateDecisionBinding:
    """Test validate_decision_binding function."""

    def _create_intent(self, **overrides):
        from impl_v1.phase33.phase33_context import ExecutionIntent
        defaults = {
            "intent_id": "INTENT-abc12345",
            "decision_id": "DEC-def67890",
            "decision_type": "CONTINUE",
            "evidence_chain_hash": "ev",
            "session_id": "SESS-1",
            "execution_state": "STATE",
            "created_at": "2026-01-26T12:00:00Z",
            "created_by": "human",
            "intent_hash": "hash"
        }
        defaults.update(overrides)
        return ExecutionIntent(**defaults)

    def test_valid_returns_success(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent()
        assert validate_decision_binding(intent) == BindingResult.SUCCESS

    def test_none_returns_rejected(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        assert validate_decision_binding(None) == BindingResult.REJECTED  # type: ignore

    def test_empty_intent_id_returns_missing(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent(intent_id="")
        assert validate_decision_binding(intent) == BindingResult.MISSING_FIELD

    def test_empty_decision_id_returns_missing(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent(decision_id="")
        assert validate_decision_binding(intent) == BindingResult.MISSING_FIELD

    def test_invalid_decision_type_returns_invalid(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent(decision_type="INVALID")
        assert validate_decision_binding(intent) == BindingResult.INVALID_DECISION

    def test_empty_session_id_returns_missing(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent(session_id="")
        assert validate_decision_binding(intent) == BindingResult.MISSING_FIELD

    def test_empty_created_by_returns_missing(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent(created_by="")
        assert validate_decision_binding(intent) == BindingResult.MISSING_FIELD

    def test_empty_created_at_returns_missing(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent(created_at="")
        assert validate_decision_binding(intent) == BindingResult.MISSING_FIELD

    def test_empty_decision_type_returns_missing(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent(decision_type="")
        assert validate_decision_binding(intent) == BindingResult.MISSING_FIELD

    def test_bad_intent_id_format_returns_rejected(self) -> None:
        from impl_v1.phase33.phase33_types import BindingResult
        from impl_v1.phase33.phase33_engine import validate_decision_binding
        intent = self._create_intent(intent_id="bad-format")
        assert validate_decision_binding(intent) == BindingResult.REJECTED


class TestIsIntentRevoked:
    """Test is_intent_revoked function."""

    def _create_audit_with_revocation(self, intent_id):
        from impl_v1.phase33.phase33_context import IntentAudit, IntentRecord
        rec = IntentRecord("REC-1", "REVOCATION", intent_id, "2026-01-26T12:00:00Z", "", "h")
        return IntentAudit("AUD-1", (rec,), "SESS-1", "h", 1)

    def _create_empty_audit(self):
        from impl_v1.phase33.phase33_context import IntentAudit
        return IntentAudit("AUD-1", (), "SESS-1", "", 0)

    def test_revoked_returns_true(self) -> None:
        from impl_v1.phase33.phase33_engine import is_intent_revoked
        audit = self._create_audit_with_revocation("INTENT-abc12345")
        assert is_intent_revoked("INTENT-abc12345", audit) is True

    def test_not_revoked_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import is_intent_revoked
        audit = self._create_empty_audit()
        assert is_intent_revoked("INTENT-abc12345", audit) is False

    def test_none_intent_id_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import is_intent_revoked
        audit = self._create_empty_audit()
        assert is_intent_revoked(None, audit) is False  # type: ignore

    def test_none_audit_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import is_intent_revoked
        assert is_intent_revoked("INTENT-abc12345", None) is False  # type: ignore

    def test_empty_intent_id_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import is_intent_revoked
        audit = self._create_empty_audit()
        assert is_intent_revoked("", audit) is False


class TestValidateAuditChain:
    """Test validate_audit_chain function."""

    def test_empty_audit_valid(self) -> None:
        from impl_v1.phase33.phase33_context import IntentAudit
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        audit = IntentAudit("AUD-1", (), "SESS-1", "", 0)
        assert validate_audit_chain(audit) is True

    def test_none_returns_false(self) -> None:
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        assert validate_audit_chain(None) is False  # type: ignore

    def test_wrong_head_hash_returns_false(self) -> None:
        from impl_v1.phase33.phase33_context import IntentAudit
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        audit = IntentAudit("AUD-1", (), "SESS-1", "should_be_empty", 0)
        assert validate_audit_chain(audit) is False

    def test_wrong_length_returns_false(self) -> None:
        from impl_v1.phase33.phase33_context import IntentAudit
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        audit = IntentAudit("AUD-1", (), "SESS-1", "", 1)
        assert validate_audit_chain(audit) is False

    def test_valid_single_record(self) -> None:
        import hashlib
        from impl_v1.phase33.phase33_context import IntentAudit, IntentRecord
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        
        hasher = hashlib.sha256()
        hasher.update("REC-1".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("BINDING".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("INTENT-1".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("2026-01-26T12:00:00Z".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("".encode('utf-8'))
        h = hasher.hexdigest()
        
        rec = IntentRecord("REC-1", "BINDING", "INTENT-1", "2026-01-26T12:00:00Z", "", h)
        audit = IntentAudit("AUD-1", (rec,), "SESS-1", h, 1)
        assert validate_audit_chain(audit) is True

    def test_length_mismatch_returns_false(self) -> None:
        from impl_v1.phase33.phase33_context import IntentAudit, IntentRecord
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        rec = IntentRecord("REC-1", "BINDING", "INTENT-1", "2026-01-26T12:00:00Z", "", "h")
        audit = IntentAudit("AUD-1", (rec,), "SESS-1", "h", 2)
        assert validate_audit_chain(audit) is False

    def test_prior_hash_mismatch_returns_false(self) -> None:
        import hashlib
        from impl_v1.phase33.phase33_context import IntentAudit, IntentRecord
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        
        hasher = hashlib.sha256()
        hasher.update("REC-1".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("BINDING".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("INTENT-1".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("2026-01-26T12:00:00Z".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("".encode('utf-8'))
        h1 = hasher.hexdigest()
        
        rec1 = IntentRecord("REC-1", "BINDING", "INTENT-1", "2026-01-26T12:00:00Z", "", h1)
        rec2 = IntentRecord("REC-2", "REVOCATION", "INTENT-1", "2026-01-26T13:00:00Z", "wrong", "h2")
        audit = IntentAudit("AUD-1", (rec1, rec2), "SESS-1", "h2", 2)
        assert validate_audit_chain(audit) is False

    def test_self_hash_mismatch_returns_false(self) -> None:
        from impl_v1.phase33.phase33_context import IntentAudit, IntentRecord
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        rec = IntentRecord("REC-1", "BINDING", "INTENT-1", "2026-01-26T12:00:00Z", "", "wrong")
        audit = IntentAudit("AUD-1", (rec,), "SESS-1", "wrong", 1)
        assert validate_audit_chain(audit) is False

    def test_head_hash_mismatch_returns_false(self) -> None:
        import hashlib
        from impl_v1.phase33.phase33_context import IntentAudit, IntentRecord
        from impl_v1.phase33.phase33_engine import validate_audit_chain
        
        hasher = hashlib.sha256()
        hasher.update("REC-1".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("BINDING".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("INTENT-1".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("2026-01-26T12:00:00Z".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("".encode('utf-8'))
        h = hasher.hexdigest()
        
        rec = IntentRecord("REC-1", "BINDING", "INTENT-1", "2026-01-26T12:00:00Z", "", h)
        audit = IntentAudit("AUD-1", (rec,), "SESS-1", "wrong_head", 1)
        assert validate_audit_chain(audit) is False


class TestGetIntentState:
    """Test get_intent_state function."""

    def _create_intent(self):
        from impl_v1.phase33.phase33_context import ExecutionIntent
        return ExecutionIntent(
            intent_id="INTENT-abc12345",
            decision_id="DEC-def67890",
            decision_type="CONTINUE",
            evidence_chain_hash="ev",
            session_id="SESS-1",
            execution_state="STATE",
            created_at="2026-01-26T12:00:00Z",
            created_by="human",
            intent_hash="hash"
        )

    def _create_empty_audit(self):
        from impl_v1.phase33.phase33_context import IntentAudit
        return IntentAudit("AUD-1", (), "SESS-1", "", 0)

    def test_none_intent_returns_revoked(self) -> None:
        from impl_v1.phase33.phase33_types import IntentStatus
        from impl_v1.phase33.phase33_engine import get_intent_state
        assert get_intent_state(None, None) == IntentStatus.REVOKED  # type: ignore

    def test_valid_intent_returns_pending(self) -> None:
        from impl_v1.phase33.phase33_types import IntentStatus
        from impl_v1.phase33.phase33_engine import get_intent_state
        intent = self._create_intent()
        audit = self._create_empty_audit()
        assert get_intent_state(intent, audit) == IntentStatus.PENDING

    def test_revoked_intent_returns_revoked(self) -> None:
        from impl_v1.phase33.phase33_types import IntentStatus
        from impl_v1.phase33.phase33_context import IntentAudit, IntentRecord
        from impl_v1.phase33.phase33_engine import get_intent_state
        
        intent = self._create_intent()
        rec = IntentRecord("REC-1", "REVOCATION", "INTENT-abc12345", "2026-01-26T13:00:00Z", "", "h")
        audit = IntentAudit("AUD-1", (rec,), "SESS-1", "h", 1)
        assert get_intent_state(intent, audit) == IntentStatus.REVOKED

    def test_none_audit_returns_pending(self) -> None:
        from impl_v1.phase33.phase33_types import IntentStatus
        from impl_v1.phase33.phase33_engine import get_intent_state
        intent = self._create_intent()
        assert get_intent_state(intent, None) == IntentStatus.PENDING  # type: ignore
