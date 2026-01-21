"""
Test Identities - Phase-01 Core
REIMPLEMENTED-2026

Tests to verify that identity model is correctly defined.
HUMAN is the only authoritative actor.
These tests MUST fail initially until implementation is complete.
"""

import pytest


class TestHumanIdentity:
    """Tests for HUMAN identity."""

    def test_human_identity_exists(self):
        """Verify HUMAN identity is defined."""
        from python.phase01_core.identities import HUMAN
        assert HUMAN is not None

    def test_human_is_authoritative(self):
        """Verify HUMAN identity is authoritative."""
        from python.phase01_core.identities import HUMAN
        assert HUMAN.is_authoritative is True

    def test_human_can_initiate(self):
        """Verify HUMAN can initiate actions."""
        from python.phase01_core.identities import HUMAN
        assert HUMAN.can_initiate is True

    def test_human_can_confirm(self):
        """Verify HUMAN can confirm mutations."""
        from python.phase01_core.identities import HUMAN
        assert HUMAN.can_confirm is True

    def test_human_cannot_be_overridden(self):
        """Verify HUMAN cannot be overridden."""
        from python.phase01_core.identities import HUMAN
        assert HUMAN.can_be_overridden is False


class TestSystemIdentity:
    """Tests for SYSTEM identity."""

    def test_system_identity_exists(self):
        """Verify SYSTEM identity is defined."""
        from python.phase01_core.identities import SYSTEM
        assert SYSTEM is not None

    def test_system_is_not_authoritative(self):
        """Verify SYSTEM identity is NOT authoritative."""
        from python.phase01_core.identities import SYSTEM
        assert SYSTEM.is_authoritative is False

    def test_system_cannot_initiate(self):
        """Verify SYSTEM cannot initiate actions alone."""
        from python.phase01_core.identities import SYSTEM
        assert SYSTEM.can_initiate is False

    def test_system_cannot_confirm(self):
        """Verify SYSTEM cannot confirm mutations."""
        from python.phase01_core.identities import SYSTEM
        assert SYSTEM.can_confirm is False

    def test_system_can_be_overridden(self):
        """Verify SYSTEM can be overridden by HUMAN."""
        from python.phase01_core.identities import SYSTEM
        assert SYSTEM.can_be_overridden is True


class TestIdentityRelationship:
    """Tests for relationship between HUMAN and SYSTEM."""

    def test_human_authority_greater_than_system(self):
        """Verify HUMAN authority is always greater than SYSTEM."""
        from python.phase01_core.identities import HUMAN, SYSTEM
        assert HUMAN.authority_level > SYSTEM.authority_level

    def test_only_two_identities_defined(self):
        """Verify only HUMAN and SYSTEM identities are defined."""
        from python.phase01_core.identities import get_all_identities
        identities = get_all_identities()
        assert len(identities) == 2
        assert 'HUMAN' in identities
        assert 'SYSTEM' in identities

    def test_identity_class_exists(self):
        """Verify Identity class is defined."""
        from python.phase01_core.identities import Identity
        assert Identity is not None


class TestIdentityImmutability:
    """Tests for identity immutability."""

    def test_human_identity_is_frozen(self):
        """Verify HUMAN identity attributes cannot be changed."""
        from python.phase01_core.identities import HUMAN
        
        with pytest.raises((AttributeError, TypeError)):
            HUMAN.is_authoritative = False

    def test_system_identity_is_frozen(self):
        """Verify SYSTEM identity attributes cannot be changed."""
        from python.phase01_core.identities import SYSTEM
        
        with pytest.raises((AttributeError, TypeError)):
            SYSTEM.is_authoritative = True
