"""
Phase-34 Authorization Context Tests.

Tests for frozen dataclasses and immutability.
"""
import pytest
from dataclasses import FrozenInstanceError

from HUMANOID_HUNTER.authorization.authorization_types import AuthorizationStatus
from HUMANOID_HUNTER.authorization.authorization_context import (
    ExecutionAuthorization,
    AuthorizationRevocation,
    AuthorizationRecord,
    AuthorizationAudit
)


class TestExecutionAuthorization:
    """Test ExecutionAuthorization dataclass."""
    
    @pytest.fixture
    def valid_authorization(self):
        """Create a valid authorization."""
        return ExecutionAuthorization(
            authorization_id="AUTH-abc12345",
            intent_id="INTENT-def67890",
            decision_id="DEC-123456",
            session_id="SESSION-789",
            authorization_status=AuthorizationStatus.AUTHORIZED,
            authorized_by="human-operator-1",
            authorized_at="2026-01-26T02:00:00-05:00",
            authorization_hash="abc123def456"
        )
    
    def test_creation(self, valid_authorization):
        """Authorization can be created."""
        assert valid_authorization is not None
    
    def test_authorization_id(self, valid_authorization):
        """Authorization ID is set correctly."""
        assert valid_authorization.authorization_id == "AUTH-abc12345"
    
    def test_intent_id(self, valid_authorization):
        """Intent ID is set correctly."""
        assert valid_authorization.intent_id == "INTENT-def67890"
    
    def test_decision_id(self, valid_authorization):
        """Decision ID is set correctly."""
        assert valid_authorization.decision_id == "DEC-123456"
    
    def test_session_id(self, valid_authorization):
        """Session ID is set correctly."""
        assert valid_authorization.session_id == "SESSION-789"
    
    def test_authorization_status(self, valid_authorization):
        """Authorization status is set correctly."""
        assert valid_authorization.authorization_status == AuthorizationStatus.AUTHORIZED
    
    def test_authorized_by(self, valid_authorization):
        """Authorized by is set correctly."""
        assert valid_authorization.authorized_by == "human-operator-1"
    
    def test_authorized_at(self, valid_authorization):
        """Authorized at is set correctly."""
        assert valid_authorization.authorized_at == "2026-01-26T02:00:00-05:00"
    
    def test_authorization_hash(self, valid_authorization):
        """Authorization hash is set correctly."""
        assert valid_authorization.authorization_hash == "abc123def456"
    
    def test_is_frozen(self, valid_authorization):
        """Authorization is frozen (immutable)."""
        with pytest.raises(FrozenInstanceError):
            valid_authorization.authorization_id = "new-id"
    
    def test_cannot_modify_status(self, valid_authorization):
        """Cannot modify authorization status."""
        with pytest.raises(FrozenInstanceError):
            valid_authorization.authorization_status = AuthorizationStatus.REVOKED
    
    def test_cannot_modify_authorized_by(self, valid_authorization):
        """Cannot modify authorized_by."""
        with pytest.raises(FrozenInstanceError):
            valid_authorization.authorized_by = "attacker"


class TestAuthorizationRevocation:
    """Test AuthorizationRevocation dataclass."""
    
    @pytest.fixture
    def valid_revocation(self):
        """Create a valid revocation."""
        return AuthorizationRevocation(
            revocation_id="AUTHREV-abc123",
            authorization_id="AUTH-xyz789",
            revoked_by="human-supervisor",
            revocation_reason="Security concern",
            revoked_at="2026-01-26T02:30:00-05:00",
            revocation_hash="revhash123"
        )
    
    def test_creation(self, valid_revocation):
        """Revocation can be created."""
        assert valid_revocation is not None
    
    def test_revocation_id(self, valid_revocation):
        """Revocation ID is set correctly."""
        assert valid_revocation.revocation_id == "AUTHREV-abc123"
    
    def test_authorization_id(self, valid_revocation):
        """Authorization ID is set correctly."""
        assert valid_revocation.authorization_id == "AUTH-xyz789"
    
    def test_revoked_by(self, valid_revocation):
        """Revoked by is set correctly."""
        assert valid_revocation.revoked_by == "human-supervisor"
    
    def test_revocation_reason(self, valid_revocation):
        """Revocation reason is set correctly."""
        assert valid_revocation.revocation_reason == "Security concern"
    
    def test_revoked_at(self, valid_revocation):
        """Revoked at is set correctly."""
        assert valid_revocation.revoked_at == "2026-01-26T02:30:00-05:00"
    
    def test_revocation_hash(self, valid_revocation):
        """Revocation hash is set correctly."""
        assert valid_revocation.revocation_hash == "revhash123"
    
    def test_is_frozen(self, valid_revocation):
        """Revocation is frozen (immutable)."""
        with pytest.raises(FrozenInstanceError):
            valid_revocation.revocation_id = "new-id"
    
    def test_cannot_modify_reason(self, valid_revocation):
        """Cannot modify revocation reason."""
        with pytest.raises(FrozenInstanceError):
            valid_revocation.revocation_reason = "Changed reason"


class TestAuthorizationRecord:
    """Test AuthorizationRecord dataclass."""
    
    @pytest.fixture
    def valid_record(self):
        """Create a valid record."""
        return AuthorizationRecord(
            record_id="AUTHREC-abc123",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-xyz789",
            timestamp="2026-01-26T02:00:00-05:00",
            prior_hash="",
            self_hash="recordhash123"
        )
    
    def test_creation(self, valid_record):
        """Record can be created."""
        assert valid_record is not None
    
    def test_record_id(self, valid_record):
        """Record ID is set correctly."""
        assert valid_record.record_id == "AUTHREC-abc123"
    
    def test_record_type(self, valid_record):
        """Record type is set correctly."""
        assert valid_record.record_type == "AUTHORIZATION"
    
    def test_authorization_id(self, valid_record):
        """Authorization ID is set correctly."""
        assert valid_record.authorization_id == "AUTH-xyz789"
    
    def test_timestamp(self, valid_record):
        """Timestamp is set correctly."""
        assert valid_record.timestamp == "2026-01-26T02:00:00-05:00"
    
    def test_prior_hash(self, valid_record):
        """Prior hash is set correctly."""
        assert valid_record.prior_hash == ""
    
    def test_self_hash(self, valid_record):
        """Self hash is set correctly."""
        assert valid_record.self_hash == "recordhash123"
    
    def test_is_frozen(self, valid_record):
        """Record is frozen (immutable)."""
        with pytest.raises(FrozenInstanceError):
            valid_record.record_id = "new-id"
    
    def test_cannot_modify_self_hash(self, valid_record):
        """Cannot modify self_hash."""
        with pytest.raises(FrozenInstanceError):
            valid_record.self_hash = "tampered"


class TestAuthorizationAudit:
    """Test AuthorizationAudit dataclass."""
    
    @pytest.fixture
    def empty_audit(self):
        """Create an empty audit."""
        return AuthorizationAudit(
            audit_id="AUTHAUDIT-abc123",
            records=(),
            session_id="SESSION-123",
            head_hash="",
            length=0
        )
    
    @pytest.fixture
    def audit_with_record(self):
        """Create an audit with one record."""
        record = AuthorizationRecord(
            record_id="AUTHREC-001",
            record_type="AUTHORIZATION",
            authorization_id="AUTH-001",
            timestamp="2026-01-26T02:00:00-05:00",
            prior_hash="",
            self_hash="hash001"
        )
        return AuthorizationAudit(
            audit_id="AUTHAUDIT-abc123",
            records=(record,),
            session_id="SESSION-123",
            head_hash="hash001",
            length=1
        )
    
    def test_creation_empty(self, empty_audit):
        """Empty audit can be created."""
        assert empty_audit is not None
    
    def test_audit_id(self, empty_audit):
        """Audit ID is set correctly."""
        assert empty_audit.audit_id == "AUTHAUDIT-abc123"
    
    def test_empty_records(self, empty_audit):
        """Empty audit has no records."""
        assert empty_audit.records == ()
    
    def test_session_id(self, empty_audit):
        """Session ID is set correctly."""
        assert empty_audit.session_id == "SESSION-123"
    
    def test_empty_head_hash(self, empty_audit):
        """Empty audit has empty head hash."""
        assert empty_audit.head_hash == ""
    
    def test_empty_length(self, empty_audit):
        """Empty audit has length 0."""
        assert empty_audit.length == 0
    
    def test_with_record_length(self, audit_with_record):
        """Audit with record has correct length."""
        assert audit_with_record.length == 1
    
    def test_with_record_head_hash(self, audit_with_record):
        """Audit with record has correct head hash."""
        assert audit_with_record.head_hash == "hash001"
    
    def test_records_is_tuple(self, audit_with_record):
        """Records is a tuple."""
        assert isinstance(audit_with_record.records, tuple)
    
    def test_is_frozen(self, empty_audit):
        """Audit is frozen (immutable)."""
        with pytest.raises(FrozenInstanceError):
            empty_audit.audit_id = "new-id"
    
    def test_cannot_modify_records(self, empty_audit):
        """Cannot modify records directly."""
        with pytest.raises(FrozenInstanceError):
            empty_audit.records = ()
    
    def test_cannot_modify_head_hash(self, empty_audit):
        """Cannot modify head_hash."""
        with pytest.raises(FrozenInstanceError):
            empty_audit.head_hash = "tampered"


class TestForbiddenImports:
    """Test that forbidden modules are not imported."""
    
    def test_no_os_import(self):
        """Module does not import os."""
        import HUMANOID_HUNTER.authorization.authorization_context as module
        source = open(module.__file__).read()
        assert "import os" not in source
        assert "from os" not in source
    
    def test_no_subprocess_import(self):
        """Module does not import subprocess."""
        import HUMANOID_HUNTER.authorization.authorization_context as module
        source = open(module.__file__).read()
        assert "import subprocess" not in source
        assert "from subprocess" not in source
    
    def test_no_socket_import(self):
        """Module does not import socket."""
        import HUMANOID_HUNTER.authorization.authorization_context as module
        source = open(module.__file__).read()
        assert "import socket" not in source
        assert "from socket" not in source
    
    def test_no_asyncio_import(self):
        """Module does not import asyncio."""
        import HUMANOID_HUNTER.authorization.authorization_context as module
        source = open(module.__file__).read()
        assert "import asyncio" not in source
        assert "from asyncio" not in source
