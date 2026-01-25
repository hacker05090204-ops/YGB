"""
Tests for Phase-28 Deny-By-Default.

Tests:
- Unknown identity → REJECT
- Revoked identity → REJECT
- Hash mismatch → REJECT
- None input → REJECT
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_unknown_identity_rejects(self):
        """UNKNOWN identity → REJECT."""
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
            trust_status=ExecutorIdentityStatus.UNKNOWN
        )

        context = HandshakeContext(
            instruction_envelope_hash="HASH-001",
            executor_identity=identity,
            timestamp="2026-01-25T18:11:00-05:00"
        )

        result = decide_handshake(context, expected_envelope_hash="HASH-001")
        assert result.decision == HandshakeDecision.REJECT

    def test_revoked_identity_rejects(self):
        """REVOKED identity → REJECT."""
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
            trust_status=ExecutorIdentityStatus.REVOKED
        )

        context = HandshakeContext(
            instruction_envelope_hash="HASH-001",
            executor_identity=identity,
            timestamp="2026-01-25T18:11:00-05:00"
        )

        result = decide_handshake(context, expected_envelope_hash="HASH-001")
        assert result.decision == HandshakeDecision.REJECT

    def test_hash_mismatch_rejects(self):
        """Hash mismatch → REJECT."""
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

        # Expected hash doesn't match
        result = decide_handshake(context, expected_envelope_hash="HASH-999")
        assert result.decision == HandshakeDecision.REJECT

    def test_none_context_rejects(self):
        """None context → REJECT."""
        from HUMANOID_HUNTER.handshake.handshake_engine import decide_handshake
        from HUMANOID_HUNTER.handshake.handshake_types import HandshakeDecision

        result = decide_handshake(None, expected_envelope_hash="HASH-001")
        assert result.decision == HandshakeDecision.REJECT


class TestRejectionReasons:
    """Test rejection reasons are included."""

    def test_reject_has_reason(self):
        """REJECT decisions have non-empty reason."""
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
            trust_status=ExecutorIdentityStatus.UNKNOWN
        )

        context = HandshakeContext(
            instruction_envelope_hash="HASH-001",
            executor_identity=identity,
            timestamp="2026-01-25T18:11:00-05:00"
        )

        result = decide_handshake(context, expected_envelope_hash="HASH-001")
        assert result.decision == HandshakeDecision.REJECT
        assert len(result.reason) > 0
