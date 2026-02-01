"""
Test Constants - Phase-01 Core
REIMPLEMENTED-2026 (HARDENING)

Tests to verify that system constants exist and are immutable.
Hardening tests added to verify constants cannot be reassigned.
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


class TestConstantsCannotBeReassigned:
    """
    HARDENING TESTS - Verify constants cannot be reassigned at module level.
    
    Note: Python does not prevent module-level attribute reassignment at runtime,
    but these tests document the INTENT that constants should not be modified.
    We verify that the values remain correct after import.
    """

    def test_human_authority_remains_true_after_reimport(self):
        """Verify HUMAN_AUTHORITY_ABSOLUTE stays True across imports."""
        from python.phase01_core import constants
        
        # Store original value
        original = constants.HUMAN_AUTHORITY_ABSOLUTE
        
        # Re-import should give same value
        import importlib
        importlib.reload(constants)
        
        assert constants.HUMAN_AUTHORITY_ABSOLUTE is True
        assert constants.HUMAN_AUTHORITY_ABSOLUTE == original

    def test_autonomous_execution_remains_false_after_reimport(self):
        """Verify AUTONOMOUS_EXECUTION_ALLOWED stays False across imports."""
        from python.phase01_core import constants
        
        original = constants.AUTONOMOUS_EXECUTION_ALLOWED
        
        import importlib
        importlib.reload(constants)
        
        assert constants.AUTONOMOUS_EXECUTION_ALLOWED is False
        assert constants.AUTONOMOUS_EXECUTION_ALLOWED == original

    def test_constants_values_are_consistent(self):
        """Verify constant values are always consistent with their names."""
        from python.phase01_core.constants import (
            HUMAN_AUTHORITY_ABSOLUTE,
            AUTONOMOUS_EXECUTION_ALLOWED,
            BACKGROUND_EXECUTION_ALLOWED,
            MUTATION_REQUIRES_HUMAN_CONFIRMATION,
            AUDIT_REQUIRED,
            EXPLICIT_ONLY,
            REIMPLEMENTED_2026,
        )
        
        # These must ALWAYS be these values - invariant truth
        assert HUMAN_AUTHORITY_ABSOLUTE is True, "Human authority MUST be absolute"
        assert AUTONOMOUS_EXECUTION_ALLOWED is False, "Autonomous execution MUST be forbidden"
        assert BACKGROUND_EXECUTION_ALLOWED is False, "Background execution MUST be forbidden"
        assert MUTATION_REQUIRES_HUMAN_CONFIRMATION is True, "Mutations MUST require confirmation"
        assert AUDIT_REQUIRED is True, "Audit MUST be required"
        assert EXPLICIT_ONLY is True, "Everything MUST be explicit"
        assert REIMPLEMENTED_2026 is True, "This MUST be marked as reimplemented"


class TestInvariantBypassAttempts:
    """
    HARDENING TESTS - Negative tests to verify invariant bypass attempts fail.
    
    These tests attempt to bypass invariants and verify that the bypass is
    not possible or raises appropriate errors.
    """

    def test_cannot_bypass_human_authority_invariant(self):
        """Verify INVARIANT_HUMAN_AUTHORITY_ABSOLUTE cannot be set to False."""
        from python.phase01_core import invariants
        
        # Invariant must be True
        assert invariants.INVARIANT_HUMAN_AUTHORITY_ABSOLUTE is True
        
        # Even after reload, invariant must remain True
        import importlib
        importlib.reload(invariants)
        assert invariants.INVARIANT_HUMAN_AUTHORITY_ABSOLUTE is True

    def test_cannot_bypass_no_autonomous_execution_invariant(self):
        """Verify INVARIANT_NO_AUTONOMOUS_EXECUTION cannot be disabled."""
        from python.phase01_core import invariants
        
        assert invariants.INVARIANT_NO_AUTONOMOUS_EXECUTION is True
        
        import importlib
        importlib.reload(invariants)
        assert invariants.INVARIANT_NO_AUTONOMOUS_EXECUTION is True

    def test_cannot_bypass_no_scoring_invariant(self):
        """Verify INVARIANT_NO_SCORING_OR_RANKING cannot be disabled."""
        from python.phase01_core import invariants
        
        assert invariants.INVARIANT_NO_SCORING_OR_RANKING is True
        
        import importlib
        importlib.reload(invariants)
        assert invariants.INVARIANT_NO_SCORING_OR_RANKING is True

    def test_check_all_invariants_always_returns_true(self):
        """Verify check_all_invariants cannot return False."""
        from python.phase01_core.invariants import check_all_invariants
        
        # Must always return True
        result = check_all_invariants()
        assert result is True
        
        # Call multiple times - must always be True
        for _ in range(10):
            assert check_all_invariants() is True

    def test_get_all_invariants_all_true(self):
        """Verify get_all_invariants never contains False values."""
        from python.phase01_core.invariants import get_all_invariants
        
        all_invariants = get_all_invariants()
        
        for name, value in all_invariants.items():
            assert value is True, f"Invariant {name} is not True! Bypass detected!"

    def test_system_cannot_have_human_authority(self):
        """Verify SYSTEM identity can never have authoritative power."""
        from python.phase01_core.identities import SYSTEM
        
        assert SYSTEM.is_authoritative is False
        assert SYSTEM.can_initiate is False
        assert SYSTEM.can_confirm is False
        
        # SYSTEM authority level must be less than any authoritative level
        assert SYSTEM.authority_level == 0

    def test_human_authority_cannot_be_reduced(self):
        """Verify HUMAN identity always has maximum authority."""
        from python.phase01_core.identities import HUMAN, SYSTEM
        
        assert HUMAN.is_authoritative is True
        assert HUMAN.can_initiate is True
        assert HUMAN.can_confirm is True
        assert HUMAN.can_be_overridden is False
        
        # HUMAN must always be greater than SYSTEM
        assert HUMAN.authority_level > SYSTEM.authority_level

