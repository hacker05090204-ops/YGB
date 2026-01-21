"""
Test Constants - Phase-01 Core
REIMPLEMENTED-2026

Tests to verify that system constants exist and are immutable.
These tests MUST fail initially until implementation is complete.
"""

import pytest


class TestSystemConstants:
    """Tests for system-wide constants."""

    def test_system_name_constant_exists(self):
        """Verify SYSTEM_NAME constant exists."""
        from python.phase01_core.constants import SYSTEM_NAME
        assert SYSTEM_NAME is not None
        assert isinstance(SYSTEM_NAME, str)
        assert len(SYSTEM_NAME) > 0

    def test_system_version_constant_exists(self):
        """Verify SYSTEM_VERSION constant exists."""
        from python.phase01_core.constants import SYSTEM_VERSION
        assert SYSTEM_VERSION is not None
        assert isinstance(SYSTEM_VERSION, str)

    def test_reimplemented_marker_exists(self):
        """Verify REIMPLEMENTED_2026 marker exists."""
        from python.phase01_core.constants import REIMPLEMENTED_2026
        assert REIMPLEMENTED_2026 is True

    def test_human_authority_constant(self):
        """Verify HUMAN_AUTHORITY_ABSOLUTE constant is True."""
        from python.phase01_core.constants import HUMAN_AUTHORITY_ABSOLUTE
        assert HUMAN_AUTHORITY_ABSOLUTE is True

    def test_autonomous_execution_forbidden(self):
        """Verify AUTONOMOUS_EXECUTION_ALLOWED is False."""
        from python.phase01_core.constants import AUTONOMOUS_EXECUTION_ALLOWED
        assert AUTONOMOUS_EXECUTION_ALLOWED is False

    def test_background_execution_forbidden(self):
        """Verify BACKGROUND_EXECUTION_ALLOWED is False."""
        from python.phase01_core.constants import BACKGROUND_EXECUTION_ALLOWED
        assert BACKGROUND_EXECUTION_ALLOWED is False

    def test_mutation_requires_confirmation(self):
        """Verify MUTATION_REQUIRES_HUMAN_CONFIRMATION is True."""
        from python.phase01_core.constants import MUTATION_REQUIRES_HUMAN_CONFIRMATION
        assert MUTATION_REQUIRES_HUMAN_CONFIRMATION is True

    def test_audit_required(self):
        """Verify AUDIT_REQUIRED is True."""
        from python.phase01_core.constants import AUDIT_REQUIRED
        assert AUDIT_REQUIRED is True


class TestConstantsImmutability:
    """Tests to verify constants cannot be modified."""

    def test_constants_module_has_no_setters(self):
        """Verify constants module exposes no setter functions."""
        from python.phase01_core import constants
        
        # No function should start with 'set_'
        public_attrs = [attr for attr in dir(constants) if not attr.startswith('_')]
        setter_functions = [attr for attr in public_attrs if attr.startswith('set_')]
        
        assert len(setter_functions) == 0, f"Found setter functions: {setter_functions}"

    def test_all_constants_are_uppercase(self):
        """Verify all public constants follow UPPER_CASE convention."""
        from python.phase01_core import constants
        
        public_attrs = [attr for attr in dir(constants) if not attr.startswith('_')]
        
        for attr in public_attrs:
            if not callable(getattr(constants, attr)):
                assert attr.isupper(), f"Constant {attr} is not UPPER_CASE"
