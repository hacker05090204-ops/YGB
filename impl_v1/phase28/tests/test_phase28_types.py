"""
Phase-28 Types Tests.

Tests for CLOSED enums:
- ExecutorIdentityStatus: 4 members
- HandshakeDecision: 2 members

Tests enforce:
- Exact member counts (closedness)
- No additional members
- Correct member names/values
"""
import pytest

from impl_v1.phase28.phase28_types import (
    ExecutorIdentityStatus,
    HandshakeDecision,
)


class TestExecutorIdentityStatusEnum:
    """Tests for ExecutorIdentityStatus enum closedness."""

    def test_executor_identity_status_has_exactly_4_members(self) -> None:
        """ExecutorIdentityStatus must have exactly 4 members."""
        assert len(ExecutorIdentityStatus) == 4

    def test_executor_identity_status_has_verified(self) -> None:
        """ExecutorIdentityStatus must have VERIFIED."""
        assert ExecutorIdentityStatus.VERIFIED is not None
        assert ExecutorIdentityStatus.VERIFIED.name == "VERIFIED"

    def test_executor_identity_status_has_unverified(self) -> None:
        """ExecutorIdentityStatus must have UNVERIFIED."""
        assert ExecutorIdentityStatus.UNVERIFIED is not None
        assert ExecutorIdentityStatus.UNVERIFIED.name == "UNVERIFIED"

    def test_executor_identity_status_has_revoked(self) -> None:
        """ExecutorIdentityStatus must have REVOKED."""
        assert ExecutorIdentityStatus.REVOKED is not None
        assert ExecutorIdentityStatus.REVOKED.name == "REVOKED"

    def test_executor_identity_status_has_unknown(self) -> None:
        """ExecutorIdentityStatus must have UNKNOWN."""
        assert ExecutorIdentityStatus.UNKNOWN is not None
        assert ExecutorIdentityStatus.UNKNOWN.name == "UNKNOWN"

    def test_executor_identity_status_all_members_listed(self) -> None:
        """All ExecutorIdentityStatus members must be exactly as expected."""
        expected = {"VERIFIED", "UNVERIFIED", "REVOKED", "UNKNOWN"}
        actual = {m.name for m in ExecutorIdentityStatus}
        assert actual == expected

    def test_executor_identity_status_members_are_distinct(self) -> None:
        """All ExecutorIdentityStatus members must have distinct values."""
        values = [m.value for m in ExecutorIdentityStatus]
        assert len(values) == len(set(values))


class TestHandshakeDecisionEnum:
    """Tests for HandshakeDecision enum closedness."""

    def test_handshake_decision_has_exactly_2_members(self) -> None:
        """HandshakeDecision must have exactly 2 members."""
        assert len(HandshakeDecision) == 2

    def test_handshake_decision_has_accept(self) -> None:
        """HandshakeDecision must have ACCEPT."""
        assert HandshakeDecision.ACCEPT is not None
        assert HandshakeDecision.ACCEPT.name == "ACCEPT"

    def test_handshake_decision_has_reject(self) -> None:
        """HandshakeDecision must have REJECT."""
        assert HandshakeDecision.REJECT is not None
        assert HandshakeDecision.REJECT.name == "REJECT"

    def test_handshake_decision_all_members_listed(self) -> None:
        """All HandshakeDecision members must be exactly as expected."""
        expected = {"ACCEPT", "REJECT"}
        actual = {m.name for m in HandshakeDecision}
        assert actual == expected

    def test_handshake_decision_members_are_distinct(self) -> None:
        """All HandshakeDecision members must have distinct values."""
        values = [m.value for m in HandshakeDecision]
        assert len(values) == len(set(values))
