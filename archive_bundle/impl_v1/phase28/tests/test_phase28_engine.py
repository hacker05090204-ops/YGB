"""
Phase-28 Engine Tests.

Tests for VALIDATION-ONLY functions:
- validate_executor_identity
- validate_envelope_hash
- validate_handshake_context
- decide_handshake
- is_handshake_valid

Tests enforce:
- Deny-by-default (None, empty, malformed)
- Negative paths > positive paths
- Decision table correctness
"""
import pytest

from impl_v1.phase28.phase28_types import (
    ExecutorIdentityStatus,
    HandshakeDecision,
)
from impl_v1.phase28.phase28_context import (
    HandshakeContext,
    HandshakeResult,
)
from impl_v1.phase28.phase28_engine import (
    validate_executor_identity,
    validate_envelope_hash,
    validate_handshake_context,
    decide_handshake,
    is_handshake_valid,
)


# --- Helpers ---

def _make_valid_context(
    handshake_id: str = "HANDSHAKE-12345678",
    executor_id: str = "EXECUTOR-001",
    identity_status: ExecutorIdentityStatus = ExecutorIdentityStatus.VERIFIED,
    envelope_hash: str = "hash123",
    expected_hash: str = "hash123",
    timestamp: str = "2026-01-26T12:00:00Z"
) -> HandshakeContext:
    return HandshakeContext(
        handshake_id=handshake_id,
        executor_id=executor_id,
        identity_status=identity_status,
        envelope_hash=envelope_hash,
        expected_hash=expected_hash,
        timestamp=timestamp
    )


# ============================================================================
# validate_executor_identity TESTS
# ============================================================================

class TestValidateExecutorIdentityDenyByDefault:
    """Deny-by-default tests for validate_executor_identity."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_executor_identity(None) is False

    def test_non_identity_status_returns_false(self) -> None:
        """Non-ExecutorIdentityStatus → False."""
        assert validate_executor_identity("VERIFIED") is False  # type: ignore

    def test_unknown_returns_false(self) -> None:
        """UNKNOWN → False."""
        assert validate_executor_identity(ExecutorIdentityStatus.UNKNOWN) is False

    def test_revoked_returns_false(self) -> None:
        """REVOKED → False."""
        assert validate_executor_identity(ExecutorIdentityStatus.REVOKED) is False

    def test_unverified_returns_false(self) -> None:
        """UNVERIFIED → False."""
        assert validate_executor_identity(ExecutorIdentityStatus.UNVERIFIED) is False


class TestValidateExecutorIdentityPositive:
    """Positive tests for validate_executor_identity."""

    def test_verified_returns_true(self) -> None:
        """VERIFIED → True."""
        assert validate_executor_identity(ExecutorIdentityStatus.VERIFIED) is True


# ============================================================================
# validate_envelope_hash TESTS
# ============================================================================

class TestValidateEnvelopeHashDenyByDefault:
    """Deny-by-default tests for validate_envelope_hash."""

    def test_none_envelope_returns_false(self) -> None:
        """None envelope_hash → False."""
        assert validate_envelope_hash(None, "expected") is False

    def test_none_expected_returns_false(self) -> None:
        """None expected_hash → False."""
        assert validate_envelope_hash("envelope", None) is False

    def test_empty_envelope_returns_false(self) -> None:
        """Empty envelope_hash → False."""
        assert validate_envelope_hash("", "expected") is False

    def test_empty_expected_returns_false(self) -> None:
        """Empty expected_hash → False."""
        assert validate_envelope_hash("envelope", "") is False

    def test_whitespace_envelope_returns_false(self) -> None:
        """Whitespace envelope_hash → False."""
        assert validate_envelope_hash("   ", "expected") is False

    def test_whitespace_expected_returns_false(self) -> None:
        """Whitespace expected_hash → False."""
        assert validate_envelope_hash("envelope", "   ") is False

    def test_mismatch_returns_false(self) -> None:
        """Mismatch → False."""
        assert validate_envelope_hash("hash1", "hash2") is False

    def test_non_string_envelope_returns_false(self) -> None:
        """Non-string envelope_hash → False."""
        assert validate_envelope_hash(123, "expected") is False  # type: ignore

    def test_non_string_expected_returns_false(self) -> None:
        """Non-string expected_hash → False."""
        assert validate_envelope_hash("envelope", 456) is False  # type: ignore


class TestValidateEnvelopeHashPositive:
    """Positive tests for validate_envelope_hash."""

    def test_matching_hashes_returns_true(self) -> None:
        """Matching hashes → True."""
        assert validate_envelope_hash("hash123", "hash123") is True


# ============================================================================
# validate_handshake_context TESTS
# ============================================================================

class TestValidateHandshakeContextDenyByDefault:
    """Deny-by-default tests for validate_handshake_context."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert validate_handshake_context(None) is False

    def test_empty_handshake_id_returns_false(self) -> None:
        """Empty handshake_id → False."""
        context = _make_valid_context(handshake_id="")
        assert validate_handshake_context(context) is False

    def test_invalid_handshake_id_returns_false(self) -> None:
        """Invalid handshake_id format → False."""
        context = _make_valid_context(handshake_id="INVALID-123")
        assert validate_handshake_context(context) is False

    def test_empty_executor_id_returns_false(self) -> None:
        """Empty executor_id → False."""
        context = _make_valid_context(executor_id="")
        assert validate_handshake_context(context) is False

    def test_invalid_executor_id_returns_false(self) -> None:
        """Invalid executor_id format → False."""
        context = _make_valid_context(executor_id="INVALID")
        assert validate_handshake_context(context) is False

    def test_non_identity_status_returns_false(self) -> None:
        """Non-ExecutorIdentityStatus → False."""
        context = HandshakeContext(
            handshake_id="HANDSHAKE-12345678",
            executor_id="EXECUTOR-001",
            identity_status="VERIFIED",  # type: ignore
            envelope_hash="hash123",
            expected_hash="hash123",
            timestamp="2026-01-26T12:00:00Z"
        )
        assert validate_handshake_context(context) is False

    def test_empty_envelope_hash_returns_false(self) -> None:
        """Empty envelope_hash → False."""
        context = _make_valid_context(envelope_hash="")
        assert validate_handshake_context(context) is False

    def test_whitespace_envelope_hash_returns_false(self) -> None:
        """Whitespace envelope_hash → False."""
        context = _make_valid_context(envelope_hash="   ")
        assert validate_handshake_context(context) is False

    def test_empty_expected_hash_returns_false(self) -> None:
        """Empty expected_hash → False."""
        context = _make_valid_context(expected_hash="")
        assert validate_handshake_context(context) is False

    def test_whitespace_expected_hash_returns_false(self) -> None:
        """Whitespace expected_hash → False."""
        context = _make_valid_context(expected_hash="   ")
        assert validate_handshake_context(context) is False

    def test_empty_timestamp_returns_false(self) -> None:
        """Empty timestamp → False."""
        context = _make_valid_context(timestamp="")
        assert validate_handshake_context(context) is False

    def test_whitespace_timestamp_returns_false(self) -> None:
        """Whitespace timestamp → False."""
        context = _make_valid_context(timestamp="   ")
        assert validate_handshake_context(context) is False


class TestValidateHandshakeContextPositive:
    """Positive tests for validate_handshake_context."""

    def test_valid_context_returns_true(self) -> None:
        """Valid context → True."""
        context = _make_valid_context()
        assert validate_handshake_context(context) is True

    def test_all_identity_statuses_valid_in_context(self) -> None:
        """All identity statuses are valid for context structure."""
        for status in ExecutorIdentityStatus:
            context = _make_valid_context(identity_status=status)
            assert validate_handshake_context(context) is True


# ============================================================================
# decide_handshake TESTS
# ============================================================================

class TestDecideHandshakeDenyByDefault:
    """Deny-by-default tests for decide_handshake."""

    def test_none_returns_reject(self) -> None:
        """None → REJECT."""
        result = decide_handshake(None)
        assert result.decision == HandshakeDecision.REJECT

    def test_invalid_context_returns_reject(self) -> None:
        """Invalid context → REJECT."""
        context = _make_valid_context(handshake_id="INVALID")
        result = decide_handshake(context)
        assert result.decision == HandshakeDecision.REJECT

    def test_unknown_identity_returns_reject(self) -> None:
        """UNKNOWN identity → REJECT."""
        context = _make_valid_context(identity_status=ExecutorIdentityStatus.UNKNOWN)
        result = decide_handshake(context)
        assert result.decision == HandshakeDecision.REJECT

    def test_revoked_identity_returns_reject(self) -> None:
        """REVOKED identity → REJECT."""
        context = _make_valid_context(identity_status=ExecutorIdentityStatus.REVOKED)
        result = decide_handshake(context)
        assert result.decision == HandshakeDecision.REJECT

    def test_unverified_identity_returns_reject(self) -> None:
        """UNVERIFIED identity → REJECT."""
        context = _make_valid_context(identity_status=ExecutorIdentityStatus.UNVERIFIED)
        result = decide_handshake(context)
        assert result.decision == HandshakeDecision.REJECT

    def test_hash_mismatch_returns_reject(self) -> None:
        """Hash mismatch → REJECT."""
        context = _make_valid_context(envelope_hash="hash1", expected_hash="hash2")
        result = decide_handshake(context)
        assert result.decision == HandshakeDecision.REJECT
        assert result.hash_matched is False


class TestDecideHandshakePositive:
    """Positive tests for decide_handshake."""

    def test_verified_and_matching_hash_returns_accept(self) -> None:
        """VERIFIED + matching hash → ACCEPT."""
        context = _make_valid_context()
        result = decide_handshake(context)
        assert result.decision == HandshakeDecision.ACCEPT
        assert result.hash_matched is True
        assert result.identity_status == ExecutorIdentityStatus.VERIFIED


# ============================================================================
# is_handshake_valid TESTS
# ============================================================================

class TestIsHandshakeValidDenyByDefault:
    """Deny-by-default tests for is_handshake_valid."""

    def test_none_returns_false(self) -> None:
        """None → False."""
        assert is_handshake_valid(None) is False

    def test_reject_decision_returns_false(self) -> None:
        """REJECT decision → False."""
        result = HandshakeResult(
            handshake_id="HANDSHAKE-12345678",
            decision=HandshakeDecision.REJECT,
            identity_status=ExecutorIdentityStatus.UNKNOWN,
            hash_matched=False,
            reason="Test"
        )
        assert is_handshake_valid(result) is False

    def test_non_decision_type_returns_false(self) -> None:
        """Non-HandshakeDecision → False."""
        result = HandshakeResult(
            handshake_id="HANDSHAKE-12345678",
            decision="ACCEPT",  # type: ignore
            identity_status=ExecutorIdentityStatus.VERIFIED,
            hash_matched=True,
            reason="Test"
        )
        assert is_handshake_valid(result) is False


class TestIsHandshakeValidPositive:
    """Positive tests for is_handshake_valid."""

    def test_accept_decision_returns_true(self) -> None:
        """ACCEPT decision → True."""
        result = HandshakeResult(
            handshake_id="HANDSHAKE-12345678",
            decision=HandshakeDecision.ACCEPT,
            identity_status=ExecutorIdentityStatus.VERIFIED,
            hash_matched=True,
            reason="Accepted"
        )
        assert is_handshake_valid(result) is True
