"""
Phase-34 Engine Tests.

Tests for pure validation functions.
Deny-by-default on ALL ambiguous inputs.
Negative paths dominate positive paths.
"""
import pytest
import hashlib


class TestValidateAuthorizationId:
    """Test validate_authorization_id function (deny-by-default)."""

    def test_valid_authorization_id(self) -> None:
        """Valid AUTH-{hex8} format returns True."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("AUTH-abc12345") is True

    def test_valid_authorization_id_uppercase(self) -> None:
        """Valid AUTH-{HEX8} uppercase returns True."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("AUTH-ABC12345") is True

    def test_valid_authorization_id_mixed_case(self) -> None:
        """Valid AUTH-{mixed} returns True."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("AUTH-AbC12345") is True

    # NEGATIVE TESTS (deny-by-default)
    def test_none_returns_false(self) -> None:
        """None input returns False (deny-by-default)."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id(None) is False  # type: ignore

    def test_empty_string_returns_false(self) -> None:
        """Empty string returns False (deny-by-default)."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("") is False

    def test_whitespace_only_returns_false(self) -> None:
        """Whitespace only returns False (deny-by-default)."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("   ") is False

    def test_missing_prefix_returns_false(self) -> None:
        """Missing AUTH- prefix returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("abc12345") is False

    def test_wrong_prefix_returns_false(self) -> None:
        """Wrong prefix returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("INTENT-abc12345") is False

    def test_lowercase_prefix_returns_false(self) -> None:
        """Lowercase auth- prefix returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("auth-abc12345") is False

    def test_short_hex_returns_false(self) -> None:
        """Too short hex part returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("AUTH-abc") is False

    def test_non_hex_characters_returns_false(self) -> None:
        """Non-hex characters returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("AUTH-xyz!@#$%") is False

    def test_only_prefix_returns_false(self) -> None:
        """Only prefix without hex returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id("AUTH-") is False

    def test_integer_input_returns_false(self) -> None:
        """Integer input returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_id
        assert validate_authorization_id(12345) is False  # type: ignore


class TestValidateAuthorizationHash:
    """Test validate_authorization_hash function."""

    def _compute_expected_hash(
        self,
        authorization_id: str,
        intent_id: str,
        decision_id: str,
        session_id: str,
        status_name: str,
        authorized_by: str,
        authorized_at: str
    ) -> str:
        """Compute expected hash using same algorithm as impl."""
        hasher = hashlib.sha256()
        hasher.update(authorization_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(intent_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(decision_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(session_id.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(status_name.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(authorized_by.encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update(authorized_at.encode('utf-8'))
        return hasher.hexdigest()

    def test_valid_hash_returns_true(self) -> None:
        """Valid hash returns True."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        from impl_v1.phase34.phase34_engine import validate_authorization_hash
        
        expected_hash = self._compute_expected_hash(
            "AUTH-abc12345", "INTENT-def67890", "DEC-ghi11111",
            "SESS-jkl22222", "AUTHORIZED", "human-1", "2026-01-26T12:00:00Z"
        )
        auth = ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-ghi11111",
            session_id="SESS-jkl22222",
            authorization_status=AuthorizationStatus.AUTHORIZED,
            authorized_by="human-1",
            authorized_at="2026-01-26T12:00:00Z",
            authorization_hash=expected_hash
        )
        assert validate_authorization_hash(auth) is True

    # NEGATIVE TESTS (deny-by-default)
    def test_none_returns_false(self) -> None:
        """None input returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_hash
        assert validate_authorization_hash(None) is False  # type: ignore

    def test_tampered_hash_returns_false(self) -> None:
        """Tampered hash returns False."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        from impl_v1.phase34.phase34_engine import validate_authorization_hash
        
        auth = ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-ghi11111",
            session_id="SESS-jkl22222",
            authorization_status=AuthorizationStatus.AUTHORIZED,
            authorized_by="human-1",
            authorized_at="2026-01-26T12:00:00Z",
            authorization_hash="tampered_hash_value"
        )
        assert validate_authorization_hash(auth) is False

    def test_empty_hash_returns_false(self) -> None:
        """Empty hash returns False."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        from impl_v1.phase34.phase34_engine import validate_authorization_hash
        
        auth = ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-ghi11111",
            session_id="SESS-jkl22222",
            authorization_status=AuthorizationStatus.AUTHORIZED,
            authorized_by="human-1",
            authorized_at="2026-01-26T12:00:00Z",
            authorization_hash=""
        )
        assert validate_authorization_hash(auth) is False


class TestValidateAuthorizationStatus:
    """Test validate_authorization_status function."""

    def test_authorized_status_is_valid(self) -> None:
        """AUTHORIZED status is valid."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        from impl_v1.phase34.phase34_engine import validate_authorization_status
        assert validate_authorization_status(AuthorizationStatus.AUTHORIZED) is True

    def test_rejected_status_is_valid(self) -> None:
        """REJECTED status is valid."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        from impl_v1.phase34.phase34_engine import validate_authorization_status
        assert validate_authorization_status(AuthorizationStatus.REJECTED) is True

    def test_revoked_status_is_valid(self) -> None:
        """REVOKED status is valid."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        from impl_v1.phase34.phase34_engine import validate_authorization_status
        assert validate_authorization_status(AuthorizationStatus.REVOKED) is True

    def test_expired_status_is_valid(self) -> None:
        """EXPIRED status is valid."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        from impl_v1.phase34.phase34_engine import validate_authorization_status
        assert validate_authorization_status(AuthorizationStatus.EXPIRED) is True

    # NEGATIVE TESTS
    def test_none_returns_false(self) -> None:
        """None input returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_status
        assert validate_authorization_status(None) is False  # type: ignore

    def test_string_returns_false(self) -> None:
        """String input returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_status
        assert validate_authorization_status("AUTHORIZED") is False  # type: ignore

    def test_integer_returns_false(self) -> None:
        """Integer input returns False."""
        from impl_v1.phase34.phase34_engine import validate_authorization_status
        assert validate_authorization_status(1) is False  # type: ignore


class TestIsAuthorizationRevoked:
    """Test is_authorization_revoked function."""

    def _create_empty_audit(self) -> "AuthorizationAudit":
        """Create empty AuthorizationAudit."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit
        return AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(),
            session_id="SESS-def67890",
            head_hash="",
            length=0
        )

    def _create_audit_with_revocation(self, auth_id: str) -> "AuthorizationAudit":
        """Create AuthorizationAudit with a revocation record."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit, AuthorizationRecord
        record = AuthorizationRecord(
            record_id="AUTHREC-abc12345",
            record_type="REVOCATION",
            authorization_id=auth_id,
            timestamp="2026-01-26T13:00:00Z",
            prior_hash="",
            self_hash="rechash123"
        )
        return AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(record,),
            session_id="SESS-def67890",
            head_hash="rechash123",
            length=1
        )

    def _create_audit_with_authorization(self, auth_id: str) -> "AuthorizationAudit":
        """Create AuthorizationAudit with an authorization record (not revocation)."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit, AuthorizationRecord
        record = AuthorizationRecord(
            record_id="AUTHREC-abc12345",
            record_type="AUTHORIZATION",
            authorization_id=auth_id,
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash="rechash123"
        )
        return AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(record,),
            session_id="SESS-def67890",
            head_hash="rechash123",
            length=1
        )

    def test_revoked_authorization_returns_true(self) -> None:
        """Authorization with revocation record returns True."""
        from impl_v1.phase34.phase34_engine import is_authorization_revoked
        audit = self._create_audit_with_revocation("AUTH-abc12345")
        assert is_authorization_revoked("AUTH-abc12345", audit) is True

    def test_not_revoked_returns_false(self) -> None:
        """Authorization without revocation returns False."""
        from impl_v1.phase34.phase34_engine import is_authorization_revoked
        audit = self._create_empty_audit()
        assert is_authorization_revoked("AUTH-abc12345", audit) is False

    def test_different_auth_id_returns_false(self) -> None:
        """Revocation for different auth_id returns False."""
        from impl_v1.phase34.phase34_engine import is_authorization_revoked
        audit = self._create_audit_with_revocation("AUTH-other123")
        assert is_authorization_revoked("AUTH-abc12345", audit) is False

    def test_authorization_record_not_revocation(self) -> None:
        """AUTHORIZATION record type is not REVOCATION."""
        from impl_v1.phase34.phase34_engine import is_authorization_revoked
        audit = self._create_audit_with_authorization("AUTH-abc12345")
        assert is_authorization_revoked("AUTH-abc12345", audit) is False

    # NEGATIVE TESTS
    def test_none_auth_id_returns_false(self) -> None:
        """None auth_id returns False."""
        from impl_v1.phase34.phase34_engine import is_authorization_revoked
        audit = self._create_empty_audit()
        assert is_authorization_revoked(None, audit) is False  # type: ignore

    def test_none_audit_returns_false(self) -> None:
        """None audit returns False."""
        from impl_v1.phase34.phase34_engine import is_authorization_revoked
        assert is_authorization_revoked("AUTH-abc12345", None) is False  # type: ignore

    def test_empty_auth_id_returns_false(self) -> None:
        """Empty auth_id returns False."""
        from impl_v1.phase34.phase34_engine import is_authorization_revoked
        audit = self._create_audit_with_revocation("")
        assert is_authorization_revoked("", audit) is False


class TestValidateAuditChain:
    """Test validate_audit_chain function."""

    def test_empty_audit_is_valid(self) -> None:
        """Empty audit with empty hash is valid."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(),
            session_id="SESS-def67890",
            head_hash="",
            length=0
        )
        assert validate_audit_chain(audit) is True

    # NEGATIVE TESTS
    def test_none_returns_false(self) -> None:
        """None input returns False."""
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        assert validate_audit_chain(None) is False  # type: ignore

    def test_empty_audit_wrong_hash_returns_false(self) -> None:
        """Empty audit with non-empty hash returns False."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(),
            session_id="SESS-def67890",
            head_hash="should_be_empty",
            length=0
        )
        assert validate_audit_chain(audit) is False

    def test_empty_audit_wrong_length_returns_false(self) -> None:
        """Empty audit with non-zero length returns False."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(),
            session_id="SESS-def67890",
            head_hash="",
            length=1
        )
        assert validate_audit_chain(audit) is False

    def test_length_mismatch_returns_false(self) -> None:
        """Length not matching records count returns False."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit, AuthorizationRecord
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        record = AuthorizationRecord(
            record_id="AUTHREC-abc12345",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-def67890",
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash="somehash"
        )
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(record,),
            session_id="SESS-def67890",
            head_hash="somehash",
            length=2  # Wrong - should be 1
        )
        assert validate_audit_chain(audit) is False

    def test_valid_single_record_chain(self) -> None:
        """Valid audit with single record and correct hash chain."""
        import hashlib
        from impl_v1.phase34.phase34_context import AuthorizationAudit, AuthorizationRecord
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        
        # Compute the expected hash for the record
        hasher = hashlib.sha256()
        hasher.update("AUTHREC-abc12345".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("AUTHORIZATION".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("AUTH-def67890".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("2026-01-26T12:00:00Z".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("".encode('utf-8'))  # prior_hash is empty
        computed_hash = hasher.hexdigest()
        
        record = AuthorizationRecord(
            record_id="AUTHREC-abc12345",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-def67890",
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash=computed_hash
        )
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(record,),
            session_id="SESS-def67890",
            head_hash=computed_hash,
            length=1
        )
        assert validate_audit_chain(audit) is True

    def test_invalid_prior_hash_returns_false(self) -> None:
        """Prior hash mismatch returns False."""
        import hashlib
        from impl_v1.phase34.phase34_context import AuthorizationAudit, AuthorizationRecord
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        
        # Create first record with correct hash
        hasher1 = hashlib.sha256()
        hasher1.update("AUTHREC-1".encode('utf-8'))
        hasher1.update(b'\x00')
        hasher1.update("AUTHORIZATION".encode('utf-8'))
        hasher1.update(b'\x00')
        hasher1.update("AUTH-1".encode('utf-8'))
        hasher1.update(b'\x00')
        hasher1.update("2026-01-26T12:00:00Z".encode('utf-8'))
        hasher1.update(b'\x00')
        hasher1.update("".encode('utf-8'))
        hash1 = hasher1.hexdigest()
        
        record1 = AuthorizationRecord(
            record_id="AUTHREC-1",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-1",
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash=hash1
        )
        
        # Second record with WRONG prior_hash
        record2 = AuthorizationRecord(
            record_id="AUTHREC-2",
            record_type="REVOCATION",
            authorization_id="AUTH-1",
            timestamp="2026-01-26T13:00:00Z",
            prior_hash="wrong_prior_hash",  # Should be hash1
            self_hash="somehash"
        )
        
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(record1, record2),
            session_id="SESS-def67890",
            head_hash="somehash",
            length=2
        )
        assert validate_audit_chain(audit) is False

    def test_invalid_self_hash_returns_false(self) -> None:
        """Self hash mismatch returns False."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit, AuthorizationRecord
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        
        # Record with correct prior_hash but wrong self_hash
        record = AuthorizationRecord(
            record_id="AUTHREC-abc12345",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-def67890",
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash="wrong_self_hash"  # This won't match computed
        )
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(record,),
            session_id="SESS-def67890",
            head_hash="wrong_self_hash",
            length=1
        )
        assert validate_audit_chain(audit) is False

    def test_head_hash_mismatch_returns_false(self) -> None:
        """Head hash not matching last record hash returns False."""
        import hashlib
        from impl_v1.phase34.phase34_context import AuthorizationAudit, AuthorizationRecord
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        
        # Compute correct hash
        hasher = hashlib.sha256()
        hasher.update("AUTHREC-abc12345".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("AUTHORIZATION".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("AUTH-def67890".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("2026-01-26T12:00:00Z".encode('utf-8'))
        hasher.update(b'\x00')
        hasher.update("".encode('utf-8'))
        computed_hash = hasher.hexdigest()
        
        record = AuthorizationRecord(
            record_id="AUTHREC-abc12345",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-def67890",
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash=computed_hash
        )
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(record,),
            session_id="SESS-def67890",
            head_hash="wrong_head_hash",  # Doesn't match computed_hash
            length=1
        )
        assert validate_audit_chain(audit) is False

    def test_valid_multi_record_chain(self) -> None:
        """Valid audit with multiple records and correct hash chain."""
        import hashlib
        from impl_v1.phase34.phase34_context import AuthorizationAudit, AuthorizationRecord
        from impl_v1.phase34.phase34_engine import validate_audit_chain
        
        # First record hash
        hasher1 = hashlib.sha256()
        hasher1.update("AUTHREC-1".encode('utf-8'))
        hasher1.update(b'\x00')
        hasher1.update("AUTHORIZATION".encode('utf-8'))
        hasher1.update(b'\x00')
        hasher1.update("AUTH-abc12345".encode('utf-8'))
        hasher1.update(b'\x00')
        hasher1.update("2026-01-26T12:00:00Z".encode('utf-8'))
        hasher1.update(b'\x00')
        hasher1.update("".encode('utf-8'))  # prior_hash empty
        hash1 = hasher1.hexdigest()
        
        record1 = AuthorizationRecord(
            record_id="AUTHREC-1",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-abc12345",
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash=hash1
        )
        
        # Second record hash (prior_hash = hash1)
        hasher2 = hashlib.sha256()
        hasher2.update("AUTHREC-2".encode('utf-8'))
        hasher2.update(b'\x00')
        hasher2.update("REVOCATION".encode('utf-8'))
        hasher2.update(b'\x00')
        hasher2.update("AUTH-abc12345".encode('utf-8'))
        hasher2.update(b'\x00')
        hasher2.update("2026-01-26T13:00:00Z".encode('utf-8'))
        hasher2.update(b'\x00')
        hasher2.update(hash1.encode('utf-8'))  # prior_hash = hash1
        hash2 = hasher2.hexdigest()
        
        record2 = AuthorizationRecord(
            record_id="AUTHREC-2",
            record_type="REVOCATION",
            authorization_id="AUTH-abc12345",
            timestamp="2026-01-26T13:00:00Z",
            prior_hash=hash1,
            self_hash=hash2
        )
        
        audit = AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(record1, record2),
            session_id="SESS-def67890",
            head_hash=hash2,
            length=2
        )
        assert validate_audit_chain(audit) is True


class TestGetAuthorizationDecision:
    """Test get_authorization_decision function."""

    def test_authorized_returns_allow(self) -> None:
        """AUTHORIZED status returns ALLOW decision."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus, AuthorizationDecision
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        from impl_v1.phase34.phase34_engine import get_authorization_decision
        
        auth = ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-ghi11111",
            session_id="SESS-jkl22222",
            authorization_status=AuthorizationStatus.AUTHORIZED,
            authorized_by="human-1",
            authorized_at="2026-01-26T12:00:00Z",
            authorization_hash="hash123"
        )
        assert get_authorization_decision(auth) == AuthorizationDecision.ALLOW

    def test_rejected_returns_deny(self) -> None:
        """REJECTED status returns DENY decision."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus, AuthorizationDecision
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        from impl_v1.phase34.phase34_engine import get_authorization_decision
        
        auth = ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-ghi11111",
            session_id="SESS-jkl22222",
            authorization_status=AuthorizationStatus.REJECTED,
            authorized_by="human-1",
            authorized_at="2026-01-26T12:00:00Z",
            authorization_hash="hash123"
        )
        assert get_authorization_decision(auth) == AuthorizationDecision.DENY

    def test_revoked_returns_deny(self) -> None:
        """REVOKED status returns DENY decision."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus, AuthorizationDecision
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        from impl_v1.phase34.phase34_engine import get_authorization_decision
        
        auth = ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-ghi11111",
            session_id="SESS-jkl22222",
            authorization_status=AuthorizationStatus.REVOKED,
            authorized_by="human-1",
            authorized_at="2026-01-26T12:00:00Z",
            authorization_hash="hash123"
        )
        assert get_authorization_decision(auth) == AuthorizationDecision.DENY

    def test_expired_returns_deny(self) -> None:
        """EXPIRED status returns DENY decision."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus, AuthorizationDecision
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        from impl_v1.phase34.phase34_engine import get_authorization_decision
        
        auth = ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-ghi11111",
            session_id="SESS-jkl22222",
            authorization_status=AuthorizationStatus.EXPIRED,
            authorized_by="human-1",
            authorized_at="2026-01-26T12:00:00Z",
            authorization_hash="hash123"
        )
        assert get_authorization_decision(auth) == AuthorizationDecision.DENY

    # NEGATIVE TESTS (deny-by-default)
    def test_none_returns_deny(self) -> None:
        """None input returns DENY (deny-by-default)."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        from impl_v1.phase34.phase34_engine import get_authorization_decision
        assert get_authorization_decision(None) == AuthorizationDecision.DENY  # type: ignore
