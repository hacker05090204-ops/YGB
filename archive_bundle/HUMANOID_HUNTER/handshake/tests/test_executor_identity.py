"""
Tests for Phase-28 Executor Identity.

Tests:
- ExecutorIdentity structure
- ExecutorIdentityStatus enum
- Immutability
"""
import pytest


class TestExecutorIdentityStructure:
    """Test ExecutorIdentity structure."""

    def test_identity_creation(self):
        """ExecutorIdentity can be created."""
        from HUMANOID_HUNTER.handshake.handshake_context import ExecutorIdentity
        from HUMANOID_HUNTER.handshake.handshake_types import ExecutorIdentityStatus

        identity = ExecutorIdentity(
            executor_id="EXEC-001",
            public_key_hash="abc123def456",
            trust_status=ExecutorIdentityStatus.REGISTERED
        )

        assert identity.executor_id == "EXEC-001"
        assert identity.trust_status == ExecutorIdentityStatus.REGISTERED

    def test_identity_frozen(self):
        """ExecutorIdentity is frozen."""
        from HUMANOID_HUNTER.handshake.handshake_context import ExecutorIdentity
        from HUMANOID_HUNTER.handshake.handshake_types import ExecutorIdentityStatus

        identity = ExecutorIdentity(
            executor_id="EXEC-001",
            public_key_hash="abc123def456",
            trust_status=ExecutorIdentityStatus.REGISTERED
        )

        with pytest.raises(Exception):
            identity.executor_id = "MODIFIED"


class TestExecutorIdentityStatusEnum:
    """Test ExecutorIdentityStatus enum."""

    def test_status_has_three_members(self):
        """ExecutorIdentityStatus has exactly 3 members."""
        from HUMANOID_HUNTER.handshake.handshake_types import ExecutorIdentityStatus
        assert len(ExecutorIdentityStatus) == 3

    def test_status_values(self):
        """ExecutorIdentityStatus has correct values."""
        from HUMANOID_HUNTER.handshake.handshake_types import ExecutorIdentityStatus
        assert hasattr(ExecutorIdentityStatus, 'UNKNOWN')
        assert hasattr(ExecutorIdentityStatus, 'REGISTERED')
        assert hasattr(ExecutorIdentityStatus, 'REVOKED')


class TestHandshakeDecisionEnum:
    """Test HandshakeDecision enum."""

    def test_decision_has_two_members(self):
        """HandshakeDecision has exactly 2 members."""
        from HUMANOID_HUNTER.handshake.handshake_types import HandshakeDecision
        assert len(HandshakeDecision) == 2

    def test_decision_values(self):
        """HandshakeDecision has correct values."""
        from HUMANOID_HUNTER.handshake.handshake_types import HandshakeDecision
        assert hasattr(HandshakeDecision, 'ACCEPT')
        assert hasattr(HandshakeDecision, 'REJECT')
