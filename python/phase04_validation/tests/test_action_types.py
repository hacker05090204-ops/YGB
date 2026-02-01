"""
Test Action Types - Phase-04 Validation
REIMPLEMENTED-2026

Tests for ActionType enum and related functionality.
These tests are written BEFORE implementation (Test-First).
"""

import pytest


class TestActionTypeEnum:
    """Tests for ActionType enum."""

    def test_action_type_enum_exists(self):
        """Verify ActionType enum exists."""
        from python.phase04_validation.action_types import ActionType
        assert ActionType is not None

    def test_action_type_has_read(self):
        """Verify ActionType has READ."""
        from python.phase04_validation.action_types import ActionType
        assert ActionType.READ is not None

    def test_action_type_has_write(self):
        """Verify ActionType has WRITE."""
        from python.phase04_validation.action_types import ActionType
        assert ActionType.WRITE is not None

    def test_action_type_has_delete(self):
        """Verify ActionType has DELETE."""
        from python.phase04_validation.action_types import ActionType
        assert ActionType.DELETE is not None

    def test_action_type_has_execute(self):
        """Verify ActionType has EXECUTE."""
        from python.phase04_validation.action_types import ActionType
        assert ActionType.EXECUTE is not None

    def test_action_type_has_configure(self):
        """Verify ActionType has CONFIGURE."""
        from python.phase04_validation.action_types import ActionType
        assert ActionType.CONFIGURE is not None

    def test_action_type_is_closed(self):
        """Verify ActionType has exactly 5 types (closed enum)."""
        from python.phase04_validation.action_types import ActionType
        assert len(ActionType) == 5


class TestActionTypeImmutability:
    """Tests for ActionType immutability."""

    def test_action_types_are_enum(self):
        """Verify ActionType is an enum (inherently immutable)."""
        from enum import Enum
        from python.phase04_validation.action_types import ActionType
        assert issubclass(ActionType, Enum)

    def test_cannot_add_new_action_type(self):
        """Verify cannot add new action types to enum."""
        from python.phase04_validation.action_types import ActionType
        initial_count = len(ActionType)
        try:
            ActionType.NEW_TYPE = "new"
        except (AttributeError, TypeError):
            pass
        assert len(ActionType) == initial_count == 5


class TestActionTypeCriticality:
    """Tests for action type criticality levels."""

    def test_get_criticality_exists(self):
        """Verify get_criticality function exists."""
        from python.phase04_validation.action_types import get_criticality
        assert get_criticality is not None

    def test_read_is_low_criticality(self):
        """Verify READ has LOW criticality."""
        from python.phase04_validation.action_types import ActionType, get_criticality
        assert get_criticality(ActionType.READ) == "LOW"

    def test_write_is_high_criticality(self):
        """Verify WRITE has HIGH criticality."""
        from python.phase04_validation.action_types import ActionType, get_criticality
        assert get_criticality(ActionType.WRITE) == "HIGH"

    def test_delete_is_critical(self):
        """Verify DELETE has CRITICAL criticality."""
        from python.phase04_validation.action_types import ActionType, get_criticality
        assert get_criticality(ActionType.DELETE) == "CRITICAL"

    def test_execute_is_critical(self):
        """Verify EXECUTE has CRITICAL criticality."""
        from python.phase04_validation.action_types import ActionType, get_criticality
        assert get_criticality(ActionType.EXECUTE) == "CRITICAL"

    def test_configure_is_high(self):
        """Verify CONFIGURE has HIGH criticality."""
        from python.phase04_validation.action_types import ActionType, get_criticality
        assert get_criticality(ActionType.CONFIGURE) == "HIGH"
