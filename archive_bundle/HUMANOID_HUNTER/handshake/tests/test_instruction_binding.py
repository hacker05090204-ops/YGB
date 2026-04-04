"""
Tests for Phase-28 Instruction Binding.

Tests:
- validate_instruction_binding
- HandshakeContext structure
"""
import pytest


class TestValidateInstructionBinding:
    """Test validate_instruction_binding function."""

    def test_matching_hash_valid(self):
        """Matching envelope hash is valid."""
        from HUMANOID_HUNTER.handshake.handshake_engine import validate_instruction_binding
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

        result = validate_instruction_binding(context, expected_hash="HASH-001")
        assert result is True

    def test_mismatched_hash_invalid(self):
        """Mismatched envelope hash is invalid."""
        from HUMANOID_HUNTER.handshake.handshake_engine import validate_instruction_binding
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

        result = validate_instruction_binding(context, expected_hash="HASH-002")
        assert result is False


class TestHandshakeContextStructure:
    """Test HandshakeContext structure."""

    def test_context_creation(self):
        """HandshakeContext can be created."""
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

        assert context.instruction_envelope_hash == "HASH-001"
        assert context.executor_identity == identity

    def test_context_frozen(self):
        """HandshakeContext is frozen."""
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

        with pytest.raises(Exception):
            context.instruction_envelope_hash = "MODIFIED"


class TestHandshakeResultStructure:
    """Test HandshakeResult structure."""

    def test_result_creation(self):
        """HandshakeResult can be created."""
        from HUMANOID_HUNTER.handshake.handshake_context import HandshakeResult
        from HUMANOID_HUNTER.handshake.handshake_types import HandshakeDecision

        result = HandshakeResult(
            decision=HandshakeDecision.ACCEPT,
            reason="Handshake validated"
        )

        assert result.decision == HandshakeDecision.ACCEPT

    def test_result_frozen(self):
        """HandshakeResult is frozen."""
        from HUMANOID_HUNTER.handshake.handshake_context import HandshakeResult
        from HUMANOID_HUNTER.handshake.handshake_types import HandshakeDecision

        result = HandshakeResult(
            decision=HandshakeDecision.ACCEPT,
            reason="Handshake validated"
        )

        with pytest.raises(Exception):
            result.decision = HandshakeDecision.REJECT
