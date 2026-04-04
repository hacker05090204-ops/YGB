"""
Phase-34 Context Tests.

Tests for dataclass immutability (FrozenInstanceError).
All dataclasses must be frozen=True.
"""
import pytest
from dataclasses import FrozenInstanceError


class TestExecutionAuthorizationImmutability:
    """Test ExecutionAuthorization is frozen and immutable."""

    def _create_valid_authorization(self):
        """Create a valid ExecutionAuthorization for testing."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        return ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-ghi11111",
            session_id="SESS-jkl22222",
            authorization_status=AuthorizationStatus.AUTHORIZED,
            authorized_by="human-operator-1",
            authorized_at="2026-01-26T12:00:00Z",
            authorization_hash="abc123hash456"
        )

    def test_can_create_instance(self) -> None:
        """Can create an ExecutionAuthorization instance."""
        auth = self._create_valid_authorization()
        assert auth is not None
        assert auth.authorization_id == "AUTH-abc12345"

    def test_cannot_modify_authorization_id(self) -> None:
        """Cannot modify authorization_id after creation."""
        auth = self._create_valid_authorization()
        with pytest.raises(FrozenInstanceError):
            auth.authorization_id = "HACKED"  # type: ignore

    def test_cannot_modify_intent_id(self) -> None:
        """Cannot modify intent_id after creation."""
        auth = self._create_valid_authorization()
        with pytest.raises(FrozenInstanceError):
            auth.intent_id = "HACKED"  # type: ignore

    def test_cannot_modify_decision_id(self) -> None:
        """Cannot modify decision_id after creation."""
        auth = self._create_valid_authorization()
        with pytest.raises(FrozenInstanceError):
            auth.decision_id = "HACKED"  # type: ignore

    def test_cannot_modify_session_id(self) -> None:
        """Cannot modify session_id after creation."""
        auth = self._create_valid_authorization()
        with pytest.raises(FrozenInstanceError):
            auth.session_id = "HACKED"  # type: ignore

    def test_cannot_modify_authorization_status(self) -> None:
        """Cannot modify authorization_status after creation."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        auth = self._create_valid_authorization()
        with pytest.raises(FrozenInstanceError):
            auth.authorization_status = AuthorizationStatus.REVOKED  # type: ignore

    def test_cannot_modify_authorized_by(self) -> None:
        """Cannot modify authorized_by after creation."""
        auth = self._create_valid_authorization()
        with pytest.raises(FrozenInstanceError):
            auth.authorized_by = "HACKED"  # type: ignore

    def test_cannot_modify_authorized_at(self) -> None:
        """Cannot modify authorized_at after creation."""
        auth = self._create_valid_authorization()
        with pytest.raises(FrozenInstanceError):
            auth.authorized_at = "HACKED"  # type: ignore

    def test_cannot_modify_authorization_hash(self) -> None:
        """Cannot modify authorization_hash after creation."""
        auth = self._create_valid_authorization()
        with pytest.raises(FrozenInstanceError):
            auth.authorization_hash = "HACKED"  # type: ignore

    def test_has_all_required_fields(self) -> None:
        """ExecutionAuthorization has all 8 required fields."""
        from impl_v1.phase34.phase34_context import ExecutionAuthorization
        import dataclasses
        fields = {f.name for f in dataclasses.fields(ExecutionAuthorization)}
        expected = {
            "authorization_id", "intent_id", "decision_id", "session_id",
            "authorization_status", "authorized_by", "authorized_at", "authorization_hash"
        }
        assert fields == expected


class TestAuthorizationRevocationImmutability:
    """Test AuthorizationRevocation is frozen and immutable."""

    def _create_valid_revocation(self):
        """Create a valid AuthorizationRevocation for testing."""
        from impl_v1.phase34.phase34_context import AuthorizationRevocation
        return AuthorizationRevocation(
            revocation_id="AUTHREV-abc12345",
            authorization_id="AUTH-def67890",
            revoked_by="human-operator-1",
            revocation_reason="Security concern",
            revoked_at="2026-01-26T13:00:00Z",
            revocation_hash="revhash123"
        )

    def test_can_create_instance(self) -> None:
        """Can create an AuthorizationRevocation instance."""
        rev = self._create_valid_revocation()
        assert rev is not None
        assert rev.revocation_id == "AUTHREV-abc12345"

    def test_cannot_modify_revocation_id(self) -> None:
        """Cannot modify revocation_id after creation."""
        rev = self._create_valid_revocation()
        with pytest.raises(FrozenInstanceError):
            rev.revocation_id = "HACKED"  # type: ignore

    def test_cannot_modify_authorization_id(self) -> None:
        """Cannot modify authorization_id after creation."""
        rev = self._create_valid_revocation()
        with pytest.raises(FrozenInstanceError):
            rev.authorization_id = "HACKED"  # type: ignore

    def test_cannot_modify_revoked_by(self) -> None:
        """Cannot modify revoked_by after creation."""
        rev = self._create_valid_revocation()
        with pytest.raises(FrozenInstanceError):
            rev.revoked_by = "HACKED"  # type: ignore

    def test_cannot_modify_revocation_reason(self) -> None:
        """Cannot modify revocation_reason after creation."""
        rev = self._create_valid_revocation()
        with pytest.raises(FrozenInstanceError):
            rev.revocation_reason = "HACKED"  # type: ignore

    def test_cannot_modify_revoked_at(self) -> None:
        """Cannot modify revoked_at after creation."""
        rev = self._create_valid_revocation()
        with pytest.raises(FrozenInstanceError):
            rev.revoked_at = "HACKED"  # type: ignore

    def test_cannot_modify_revocation_hash(self) -> None:
        """Cannot modify revocation_hash after creation."""
        rev = self._create_valid_revocation()
        with pytest.raises(FrozenInstanceError):
            rev.revocation_hash = "HACKED"  # type: ignore

    def test_has_all_required_fields(self) -> None:
        """AuthorizationRevocation has all 6 required fields."""
        from impl_v1.phase34.phase34_context import AuthorizationRevocation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AuthorizationRevocation)}
        expected = {
            "revocation_id", "authorization_id", "revoked_by",
            "revocation_reason", "revoked_at", "revocation_hash"
        }
        assert fields == expected


class TestAuthorizationRecordImmutability:
    """Test AuthorizationRecord is frozen and immutable."""

    def _create_valid_record(self):
        """Create a valid AuthorizationRecord for testing."""
        from impl_v1.phase34.phase34_context import AuthorizationRecord
        return AuthorizationRecord(
            record_id="AUTHREC-abc12345",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-def67890",
            timestamp="2026-01-26T12:00:00Z",
            prior_hash="",
            self_hash="rechash123"
        )

    def test_can_create_instance(self) -> None:
        """Can create an AuthorizationRecord instance."""
        rec = self._create_valid_record()
        assert rec is not None
        assert rec.record_id == "AUTHREC-abc12345"

    def test_cannot_modify_record_id(self) -> None:
        """Cannot modify record_id after creation."""
        rec = self._create_valid_record()
        with pytest.raises(FrozenInstanceError):
            rec.record_id = "HACKED"  # type: ignore

    def test_cannot_modify_record_type(self) -> None:
        """Cannot modify record_type after creation."""
        rec = self._create_valid_record()
        with pytest.raises(FrozenInstanceError):
            rec.record_type = "HACKED"  # type: ignore

    def test_cannot_modify_authorization_id(self) -> None:
        """Cannot modify authorization_id after creation."""
        rec = self._create_valid_record()
        with pytest.raises(FrozenInstanceError):
            rec.authorization_id = "HACKED"  # type: ignore

    def test_cannot_modify_timestamp(self) -> None:
        """Cannot modify timestamp after creation."""
        rec = self._create_valid_record()
        with pytest.raises(FrozenInstanceError):
            rec.timestamp = "HACKED"  # type: ignore

    def test_cannot_modify_prior_hash(self) -> None:
        """Cannot modify prior_hash after creation."""
        rec = self._create_valid_record()
        with pytest.raises(FrozenInstanceError):
            rec.prior_hash = "HACKED"  # type: ignore

    def test_cannot_modify_self_hash(self) -> None:
        """Cannot modify self_hash after creation."""
        rec = self._create_valid_record()
        with pytest.raises(FrozenInstanceError):
            rec.self_hash = "HACKED"  # type: ignore

    def test_has_all_required_fields(self) -> None:
        """AuthorizationRecord has all 6 required fields."""
        from impl_v1.phase34.phase34_context import AuthorizationRecord
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AuthorizationRecord)}
        expected = {
            "record_id", "record_type", "authorization_id",
            "timestamp", "prior_hash", "self_hash"
        }
        assert fields == expected


class TestAuthorizationAuditImmutability:
    """Test AuthorizationAudit is frozen and immutable."""

    def _create_valid_audit(self):
        """Create a valid empty AuthorizationAudit for testing."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit
        return AuthorizationAudit(
            audit_id="AUTHAUDIT-abc12345",
            records=(),
            session_id="SESS-def67890",
            head_hash="",
            length=0
        )

    def test_can_create_instance(self) -> None:
        """Can create an AuthorizationAudit instance."""
        audit = self._create_valid_audit()
        assert audit is not None
        assert audit.audit_id == "AUTHAUDIT-abc12345"

    def test_cannot_modify_audit_id(self) -> None:
        """Cannot modify audit_id after creation."""
        audit = self._create_valid_audit()
        with pytest.raises(FrozenInstanceError):
            audit.audit_id = "HACKED"  # type: ignore

    def test_cannot_modify_records(self) -> None:
        """Cannot modify records after creation."""
        audit = self._create_valid_audit()
        with pytest.raises(FrozenInstanceError):
            audit.records = ()  # type: ignore

    def test_cannot_modify_session_id(self) -> None:
        """Cannot modify session_id after creation."""
        audit = self._create_valid_audit()
        with pytest.raises(FrozenInstanceError):
            audit.session_id = "HACKED"  # type: ignore

    def test_cannot_modify_head_hash(self) -> None:
        """Cannot modify head_hash after creation."""
        audit = self._create_valid_audit()
        with pytest.raises(FrozenInstanceError):
            audit.head_hash = "HACKED"  # type: ignore

    def test_cannot_modify_length(self) -> None:
        """Cannot modify length after creation."""
        audit = self._create_valid_audit()
        with pytest.raises(FrozenInstanceError):
            audit.length = 999  # type: ignore

    def test_has_all_required_fields(self) -> None:
        """AuthorizationAudit has all 5 required fields."""
        from impl_v1.phase34.phase34_context import AuthorizationAudit
        import dataclasses
        fields = {f.name for f in dataclasses.fields(AuthorizationAudit)}
        expected = {"audit_id", "records", "session_id", "head_hash", "length"}
        assert fields == expected

    def test_records_is_tuple_type(self) -> None:
        """records field must be a tuple for immutability."""
        audit = self._create_valid_audit()
        assert isinstance(audit.records, tuple)
