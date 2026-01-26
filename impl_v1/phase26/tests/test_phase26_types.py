"""
Phase-26 Types Tests.

Tests for CLOSED enums:
- ReadinessStatus: 3 members
- ReadinessBlocker: 5 members

Tests enforce:
- Exact member counts (closedness)
- No additional members
- Correct member names/values
"""
import pytest

from impl_v1.phase26.phase26_types import (
    ReadinessStatus,
    ReadinessBlocker,
)


class TestReadinessStatusEnum:
    """Tests for ReadinessStatus enum closedness."""

    def test_readiness_status_has_exactly_3_members(self) -> None:
        """ReadinessStatus must have exactly 3 members."""
        assert len(ReadinessStatus) == 3

    def test_readiness_status_has_ready(self) -> None:
        """ReadinessStatus must have READY."""
        assert ReadinessStatus.READY is not None
        assert ReadinessStatus.READY.name == "READY"

    def test_readiness_status_has_not_ready(self) -> None:
        """ReadinessStatus must have NOT_READY."""
        assert ReadinessStatus.NOT_READY is not None
        assert ReadinessStatus.NOT_READY.name == "NOT_READY"

    def test_readiness_status_has_blocked(self) -> None:
        """ReadinessStatus must have BLOCKED."""
        assert ReadinessStatus.BLOCKED is not None
        assert ReadinessStatus.BLOCKED.name == "BLOCKED"

    def test_readiness_status_all_members_listed(self) -> None:
        """All ReadinessStatus members must be exactly as expected."""
        expected = {"READY", "NOT_READY", "BLOCKED"}
        actual = {m.name for m in ReadinessStatus}
        assert actual == expected

    def test_readiness_status_members_are_distinct(self) -> None:
        """All ReadinessStatus members must have distinct values."""
        values = [m.value for m in ReadinessStatus]
        assert len(values) == len(set(values))


class TestReadinessBlockerEnum:
    """Tests for ReadinessBlocker enum closedness."""

    def test_readiness_blocker_has_exactly_5_members(self) -> None:
        """ReadinessBlocker must have exactly 5 members."""
        assert len(ReadinessBlocker) == 5

    def test_readiness_blocker_has_missing_authorization(self) -> None:
        """ReadinessBlocker must have MISSING_AUTHORIZATION."""
        assert ReadinessBlocker.MISSING_AUTHORIZATION is not None
        assert ReadinessBlocker.MISSING_AUTHORIZATION.name == "MISSING_AUTHORIZATION"

    def test_readiness_blocker_has_missing_intent(self) -> None:
        """ReadinessBlocker must have MISSING_INTENT."""
        assert ReadinessBlocker.MISSING_INTENT is not None
        assert ReadinessBlocker.MISSING_INTENT.name == "MISSING_INTENT"

    def test_readiness_blocker_has_handshake_failed(self) -> None:
        """ReadinessBlocker must have HANDSHAKE_FAILED."""
        assert ReadinessBlocker.HANDSHAKE_FAILED is not None
        assert ReadinessBlocker.HANDSHAKE_FAILED.name == "HANDSHAKE_FAILED"

    def test_readiness_blocker_has_observation_invalid(self) -> None:
        """ReadinessBlocker must have OBSERVATION_INVALID."""
        assert ReadinessBlocker.OBSERVATION_INVALID is not None
        assert ReadinessBlocker.OBSERVATION_INVALID.name == "OBSERVATION_INVALID"

    def test_readiness_blocker_has_human_decision_pending(self) -> None:
        """ReadinessBlocker must have HUMAN_DECISION_PENDING."""
        assert ReadinessBlocker.HUMAN_DECISION_PENDING is not None
        assert ReadinessBlocker.HUMAN_DECISION_PENDING.name == "HUMAN_DECISION_PENDING"

    def test_readiness_blocker_all_members_listed(self) -> None:
        """All ReadinessBlocker members must be exactly as expected."""
        expected = {
            "MISSING_AUTHORIZATION",
            "MISSING_INTENT",
            "HANDSHAKE_FAILED",
            "OBSERVATION_INVALID",
            "HUMAN_DECISION_PENDING"
        }
        actual = {m.name for m in ReadinessBlocker}
        assert actual == expected

    def test_readiness_blocker_members_are_distinct(self) -> None:
        """All ReadinessBlocker members must have distinct values."""
        values = [m.value for m in ReadinessBlocker]
        assert len(values) == len(set(values))
