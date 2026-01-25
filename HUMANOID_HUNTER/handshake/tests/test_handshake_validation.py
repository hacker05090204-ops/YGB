"""
Tests for Phase-28 Handshake Validation.

Tests:
- validate_executor_identity
- decide_handshake
"""
import pytest


class TestValidateExecutorIdentity:
    """Test validate_executor_identity function."""

    def test_registered_identity_valid(self):
        """REGISTERED identity is valid."""
        from HUMANOID_HUNTER.handshake.handshake_engine import validate_executor_identity
        from HUMANOID_HUNTER.handshake.handshake_context import ExecutorIdentity
        from HUMANOID_HUNTER.handshake.handshake_types import ExecutorIdentityStatus

        identity = ExecutorIdentity(
            executor_id="EXEC-001",
            public_key_hash="abc123def456",
            trust_status=ExecutorIdentityStatus.REGISTERED
        )

        result = validate_executor_identity(identity)
        assert result is True

    def test_unknown_identity_invalid(self):
        """UNKNOWN identity is invalid."""
        from HUMANOID_HUNTER.handshake.handshake_engine import validate_executor_identity
        from HUMANOID_HUNTER.handshake.handshake_context import ExecutorIdentity
        from HUMANOID_HUNTER.handshake.handshake_types import ExecutorIdentityStatus

        identity = ExecutorIdentity(
            executor_id="EXEC-001",
            public_key_hash="abc123def456",
            trust_status=ExecutorIdentityStatus.UNKNOWN
        )

        result = validate_executor_identity(identity)
        assert result is False

    def test_revoked_identity_invalid(self):
        """REVOKED identity is invalid."""
        from HUMANOID_HUNTER.handshake.handshake_engine import validate_executor_identity
        from HUMANOID_HUNTER.handshake.handshake_context import ExecutorIdentity
        from HUMANOID_HUNTER.handshake.handshake_types import ExecutorIdentityStatus

        identity = ExecutorIdentity(
            executor_id="EXEC-001",
            public_key_hash="abc123def456",
            trust_status=ExecutorIdentityStatus.REVOKED
        )

        result = validate_executor_identity(identity)
        assert result is False


class TestDecideHandshake:
    """Test decide_handshake function."""

    def test_valid_handshake_accepts(self):
        """Valid handshake is ACCEPT."""
        from HUMANOID_HUNTER.handshake.handshake_engine import decide_handshake
        from HUMANOID_HUNTER.handshake.handshake_context import (
            ExecutorIdentity, HandshakeContext
        )
        from HUMANOID_HUNTER.handshake.handshake_types import (
            ExecutorIdentityStatus, HandshakeDecision
        )

        identity = ExecutorIdentity(
            executor_id="EXEC-001",
            public_key_hash="abc123def456",
            trust_status=ExecutorIdentityStatus.REGISTERED
        )

        context = HandshakeContext(
            instruction_envelope_hash="HASH-001",
            executor_identity=identity,
            timestamp="2026-01-25T18:11:00-05:00"
        )

        result = decide_handshake(context, expected_envelope_hash="HASH-001")
        assert result.decision == HandshakeDecision.ACCEPT

    def test_valid_handshake_has_reason(self):
        """Valid handshake has non-empty reason."""
        from HUMANOID_HUNTER.handshake.handshake_engine import decide_handshake
        from HUMANOID_HUNTER.handshake.handshake_context import (
            ExecutorIdentity, HandshakeContext
        )
        from HUMANOID_HUNTER.handshake.handshake_types import ExecutorIdentityStatus

        identity = ExecutorIdentity(
            executor_id="EXEC-001",
            public_key_hash="abc123def456",
            trust_status=ExecutorIdentityStatus.REGISTERED
        )

        context = HandshakeContext(
            instruction_envelope_hash="HASH-001",
            executor_identity=identity,
            timestamp="2026-01-25T18:11:00-05:00"
        )

        result = decide_handshake(context, expected_envelope_hash="HASH-001")
        assert len(result.reason) > 0
