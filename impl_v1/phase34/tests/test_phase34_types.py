"""
Phase-34 Types Tests.

Tests for enum closedness and immutability.
Negative paths dominate positive paths.
"""
import pytest
from enum import Enum


class TestAuthorizationStatusEnumClosedness:
    """Test AuthorizationStatus enum is closed with exactly 4 members."""

    def test_exactly_four_members(self) -> None:
        """Enum has EXACTLY 4 members - no more, no less."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        assert len(AuthorizationStatus) == 4, (
            f"AuthorizationStatus must have exactly 4 members, has {len(AuthorizationStatus)}"
        )

    def test_authorized_member_exists(self) -> None:
        """AUTHORIZED member exists."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        assert hasattr(AuthorizationStatus, 'AUTHORIZED')
        assert AuthorizationStatus.AUTHORIZED is not None

    def test_rejected_member_exists(self) -> None:
        """REJECTED member exists."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        assert hasattr(AuthorizationStatus, 'REJECTED')
        assert AuthorizationStatus.REJECTED is not None

    def test_revoked_member_exists(self) -> None:
        """REVOKED member exists."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        assert hasattr(AuthorizationStatus, 'REVOKED')
        assert AuthorizationStatus.REVOKED is not None

    def test_expired_member_exists(self) -> None:
        """EXPIRED member exists."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        assert hasattr(AuthorizationStatus, 'EXPIRED')
        assert AuthorizationStatus.EXPIRED is not None

    def test_is_enum_subclass(self) -> None:
        """AuthorizationStatus is an Enum."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        assert issubclass(AuthorizationStatus, Enum)

    def test_member_names_exact(self) -> None:
        """Member names match exactly."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        expected = {"AUTHORIZED", "REJECTED", "REVOKED", "EXPIRED"}
        actual = {m.name for m in AuthorizationStatus}
        assert actual == expected, f"Expected {expected}, got {actual}"

    def test_members_have_unique_values(self) -> None:
        """All members have unique values."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        values = [m.value for m in AuthorizationStatus]
        assert len(values) == len(set(values)), "Enum members must have unique values"

    def test_cannot_instantiate_invalid_value(self) -> None:
        """Cannot create enum with invalid value."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        with pytest.raises(ValueError):
            AuthorizationStatus(999)

    def test_cannot_instantiate_invalid_value_zero(self) -> None:
        """Cannot create enum with value 0."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        with pytest.raises(ValueError):
            AuthorizationStatus(0)

    def test_cannot_instantiate_negative_value(self) -> None:
        """Cannot create enum with negative value."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        with pytest.raises(ValueError):
            AuthorizationStatus(-1)

    def test_enum_member_immutable(self) -> None:
        """Enum members are immutable."""
        from impl_v1.phase34.phase34_types import AuthorizationStatus
        original = AuthorizationStatus.AUTHORIZED.value
        with pytest.raises(AttributeError):
            AuthorizationStatus.AUTHORIZED = "hacked"
        assert AuthorizationStatus.AUTHORIZED.value == original


class TestAuthorizationDecisionEnumClosedness:
    """Test AuthorizationDecision enum is closed with exactly 2 members."""

    def test_exactly_two_members(self) -> None:
        """Enum has EXACTLY 2 members - no more, no less."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        assert len(AuthorizationDecision) == 2, (
            f"AuthorizationDecision must have exactly 2 members, has {len(AuthorizationDecision)}"
        )

    def test_allow_member_exists(self) -> None:
        """ALLOW member exists."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        assert hasattr(AuthorizationDecision, 'ALLOW')
        assert AuthorizationDecision.ALLOW is not None

    def test_deny_member_exists(self) -> None:
        """DENY member exists."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        assert hasattr(AuthorizationDecision, 'DENY')
        assert AuthorizationDecision.DENY is not None

    def test_is_enum_subclass(self) -> None:
        """AuthorizationDecision is an Enum."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        assert issubclass(AuthorizationDecision, Enum)

    def test_member_names_exact(self) -> None:
        """Member names match exactly."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        expected = {"ALLOW", "DENY"}
        actual = {m.name for m in AuthorizationDecision}
        assert actual == expected

    def test_members_have_unique_values(self) -> None:
        """All members have unique values."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        values = [m.value for m in AuthorizationDecision]
        assert len(values) == len(set(values))

    def test_cannot_instantiate_invalid_value(self) -> None:
        """Cannot create enum with invalid value."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        with pytest.raises(ValueError):
            AuthorizationDecision(999)

    def test_enum_member_immutable(self) -> None:
        """Enum members are immutable."""
        from impl_v1.phase34.phase34_types import AuthorizationDecision
        original = AuthorizationDecision.ALLOW.value
        with pytest.raises(AttributeError):
            AuthorizationDecision.ALLOW = "hacked"
        assert AuthorizationDecision.ALLOW.value == original


class TestStatusConstantSets:
    """Test ALLOW_STATUSES and DENY_STATUSES frozensets."""

    def test_allow_statuses_is_frozenset(self) -> None:
        """ALLOW_STATUSES is a frozenset."""
        from impl_v1.phase34.phase34_types import ALLOW_STATUSES
        assert isinstance(ALLOW_STATUSES, frozenset)

    def test_deny_statuses_is_frozenset(self) -> None:
        """DENY_STATUSES is a frozenset."""
        from impl_v1.phase34.phase34_types import DENY_STATUSES
        assert isinstance(DENY_STATUSES, frozenset)

    def test_allow_statuses_contains_authorized(self) -> None:
        """ALLOW_STATUSES contains AUTHORIZED."""
        from impl_v1.phase34.phase34_types import ALLOW_STATUSES, AuthorizationStatus
        assert AuthorizationStatus.AUTHORIZED in ALLOW_STATUSES

    def test_allow_statuses_has_one_member(self) -> None:
        """ALLOW_STATUSES has exactly 1 member."""
        from impl_v1.phase34.phase34_types import ALLOW_STATUSES
        assert len(ALLOW_STATUSES) == 1

    def test_deny_statuses_contains_rejected(self) -> None:
        """DENY_STATUSES contains REJECTED."""
        from impl_v1.phase34.phase34_types import DENY_STATUSES, AuthorizationStatus
        assert AuthorizationStatus.REJECTED in DENY_STATUSES

    def test_deny_statuses_contains_revoked(self) -> None:
        """DENY_STATUSES contains REVOKED."""
        from impl_v1.phase34.phase34_types import DENY_STATUSES, AuthorizationStatus
        assert AuthorizationStatus.REVOKED in DENY_STATUSES

    def test_deny_statuses_contains_expired(self) -> None:
        """DENY_STATUSES contains EXPIRED."""
        from impl_v1.phase34.phase34_types import DENY_STATUSES, AuthorizationStatus
        assert AuthorizationStatus.EXPIRED in DENY_STATUSES

    def test_deny_statuses_has_three_members(self) -> None:
        """DENY_STATUSES has exactly 3 members."""
        from impl_v1.phase34.phase34_types import DENY_STATUSES
        assert len(DENY_STATUSES) == 3

    def test_allow_and_deny_are_disjoint(self) -> None:
        """ALLOW_STATUSES and DENY_STATUSES are disjoint."""
        from impl_v1.phase34.phase34_types import ALLOW_STATUSES, DENY_STATUSES
        assert ALLOW_STATUSES.isdisjoint(DENY_STATUSES)

    def test_allow_and_deny_cover_all(self) -> None:
        """ALLOW and DENY statuses cover all AuthorizationStatus members."""
        from impl_v1.phase34.phase34_types import (
            ALLOW_STATUSES, DENY_STATUSES, AuthorizationStatus
        )
        all_statuses = set(AuthorizationStatus)
        covered = ALLOW_STATUSES | DENY_STATUSES
        assert all_statuses == covered

    def test_frozenset_immutable(self) -> None:
        """Frozensets cannot be modified."""
        from impl_v1.phase34.phase34_types import ALLOW_STATUSES, AuthorizationStatus
        with pytest.raises(AttributeError):
            ALLOW_STATUSES.add(AuthorizationStatus.REJECTED)  # type: ignore
