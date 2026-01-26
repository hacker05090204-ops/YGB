"""
Phase-28 Context Tests.

Tests for FROZEN dataclasses:
- HandshakeContext: 6 fields
- HandshakeResult: 5 fields

Tests enforce:
- Immutability (FrozenInstanceError on mutation)
- Correct field counts
- Valid construction
"""
import pytest
from dataclasses import FrozenInstanceError

from impl_v1.phase28.phase28_types import ExecutorIdentityStatus, HandshakeDecision
from impl_v1.phase28.phase28_context import (
    HandshakeContext,
    HandshakeResult,
)


class TestHandshakeContextFrozen:
    """Tests for HandshakeContext frozen dataclass."""

    def test_handshake_context_has_6_fields(self) -> None:
        """HandshakeContext must have exactly 6 fields."""
        from dataclasses import fields
        assert len(fields(HandshakeContext)) == 6

    def test_handshake_context_can_be_created(self) -> None:
        """HandshakeContext can be created with valid data."""
        context = HandshakeContext(
            handshake_id="HANDSHAKE-12345678",
            executor_id="EXECUTOR-001",
            identity_status=ExecutorIdentityStatus.VERIFIED,
            envelope_hash="hash123",
            expected_hash="hash123",
            timestamp="2026-01-26T12:00:00Z"
        )
        assert context.handshake_id == "HANDSHAKE-12345678"
        assert context.identity_status == ExecutorIdentityStatus.VERIFIED

    def test_handshake_context_is_immutable_handshake_id(self) -> None:
        """HandshakeContext.handshake_id cannot be mutated."""
        context = HandshakeContext(
            handshake_id="HANDSHAKE-12345678",
            executor_id="EXECUTOR-001",
            identity_status=ExecutorIdentityStatus.VERIFIED,
            envelope_hash="hash123",
            expected_hash="hash123",
            timestamp="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            context.handshake_id = "NEW-ID"  # type: ignore

    def test_handshake_context_is_immutable_identity_status(self) -> None:
        """HandshakeContext.identity_status cannot be mutated."""
        context = HandshakeContext(
            handshake_id="HANDSHAKE-12345678",
            executor_id="EXECUTOR-001",
            identity_status=ExecutorIdentityStatus.VERIFIED,
            envelope_hash="hash123",
            expected_hash="hash123",
            timestamp="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            context.identity_status = ExecutorIdentityStatus.REVOKED  # type: ignore

    def test_handshake_context_is_immutable_envelope_hash(self) -> None:
        """HandshakeContext.envelope_hash cannot be mutated."""
        context = HandshakeContext(
            handshake_id="HANDSHAKE-12345678",
            executor_id="EXECUTOR-001",
            identity_status=ExecutorIdentityStatus.VERIFIED,
            envelope_hash="hash123",
            expected_hash="hash123",
            timestamp="2026-01-26T12:00:00Z"
        )
        with pytest.raises(FrozenInstanceError):
            context.envelope_hash = "TAMPERED"  # type: ignore


class TestHandshakeResultFrozen:
    """Tests for HandshakeResult frozen dataclass."""

    def test_handshake_result_has_5_fields(self) -> None:
        """HandshakeResult must have exactly 5 fields."""
        from dataclasses import fields
        assert len(fields(HandshakeResult)) == 5

    def test_handshake_result_can_be_created(self) -> None:
        """HandshakeResult can be created with valid data."""
        result = HandshakeResult(
            handshake_id="HANDSHAKE-12345678",
            decision=HandshakeDecision.ACCEPT,
            identity_status=ExecutorIdentityStatus.VERIFIED,
            hash_matched=True,
            reason="Valid handshake"
        )
        assert result.decision == HandshakeDecision.ACCEPT
        assert result.hash_matched is True

    def test_handshake_result_is_immutable_decision(self) -> None:
        """HandshakeResult.decision cannot be mutated."""
        result = HandshakeResult(
            handshake_id="HANDSHAKE-12345678",
            decision=HandshakeDecision.ACCEPT,
            identity_status=ExecutorIdentityStatus.VERIFIED,
            hash_matched=True,
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.decision = HandshakeDecision.REJECT  # type: ignore

    def test_handshake_result_is_immutable_hash_matched(self) -> None:
        """HandshakeResult.hash_matched cannot be mutated."""
        result = HandshakeResult(
            handshake_id="HANDSHAKE-12345678",
            decision=HandshakeDecision.ACCEPT,
            identity_status=ExecutorIdentityStatus.VERIFIED,
            hash_matched=True,
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.hash_matched = False  # type: ignore

    def test_handshake_result_is_immutable_reason(self) -> None:
        """HandshakeResult.reason cannot be mutated."""
        result = HandshakeResult(
            handshake_id="HANDSHAKE-12345678",
            decision=HandshakeDecision.ACCEPT,
            identity_status=ExecutorIdentityStatus.VERIFIED,
            hash_matched=True,
            reason="Test"
        )
        with pytest.raises(FrozenInstanceError):
            result.reason = "TAMPERED REASON"  # type: ignore
