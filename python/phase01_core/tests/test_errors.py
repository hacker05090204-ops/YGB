"""
Test Errors - Phase-01 Core
REIMPLEMENTED-2026 (HARDENING)

Tests to validate all custom errors instantiate correctly
and do not mutate global state.

These tests are part of Phase-01 HARDENING.
"""

import pytest
import sys


class TestPhase01ErrorInstantiation:
    """Tests for Phase01Error base class instantiation."""

    def test_phase01_error_instantiates(self):
        """Verify Phase01Error can be instantiated."""
        from python.phase01_core.errors import Phase01Error
        
        error = Phase01Error(message="Test error message")
        assert error is not None
        assert error.message == "Test error message"

    def test_phase01_error_str_format(self):
        """Verify Phase01Error string format."""
        from python.phase01_core.errors import Phase01Error
        
        error = Phase01Error(message="Test message")
        assert "[PHASE-01 ERROR]" in str(error)
        assert "Test message" in str(error)

    def test_phase01_error_is_exception(self):
        """Verify Phase01Error is an Exception subclass."""
        from python.phase01_core.errors import Phase01Error
        
        error = Phase01Error(message="Test")
        assert isinstance(error, Exception)

    def test_phase01_error_is_frozen(self):
        """Verify Phase01Error is immutable (frozen)."""
        from python.phase01_core.errors import Phase01Error
        
        error = Phase01Error(message="Test")
        with pytest.raises((AttributeError, TypeError)):
            error.message = "New message"


class TestInvariantViolationError:
    """Tests for InvariantViolationError instantiation."""

    def test_invariant_error_instantiates(self):
        """Verify InvariantViolationError can be instantiated."""
        from python.phase01_core.errors import InvariantViolationError
        
        error = InvariantViolationError(
            message="Invariant was violated",
            invariant_name="TEST_INVARIANT"
        )
        assert error is not None
        assert error.message == "Invariant was violated"
        assert error.invariant_name == "TEST_INVARIANT"

    def test_invariant_error_str_format(self):
        """Verify InvariantViolationError string format."""
        from python.phase01_core.errors import InvariantViolationError
        
        error = InvariantViolationError(
            message="Violation occurred",
            invariant_name="HUMAN_AUTHORITY"
        )
        assert "[INVARIANT VIOLATION]" in str(error)
        assert "HUMAN_AUTHORITY" in str(error)
        assert "Violation occurred" in str(error)

    def test_invariant_error_is_frozen(self):
        """Verify InvariantViolationError is immutable."""
        from python.phase01_core.errors import InvariantViolationError
        
        error = InvariantViolationError(message="Test", invariant_name="TEST")
        with pytest.raises((AttributeError, TypeError)):
            error.invariant_name = "CHANGED"


class TestUnauthorizedActorError:
    """Tests for UnauthorizedActorError instantiation."""

    def test_unauthorized_actor_error_instantiates(self):
        """Verify UnauthorizedActorError can be instantiated."""
        from python.phase01_core.errors import UnauthorizedActorError
        
        error = UnauthorizedActorError(
            message="Not allowed",
            actor="SYSTEM",
            action="initiate_action"
        )
        assert error is not None
        assert error.actor == "SYSTEM"
        assert error.action == "initiate_action"

    def test_unauthorized_actor_error_str_format(self):
        """Verify UnauthorizedActorError string format."""
        from python.phase01_core.errors import UnauthorizedActorError
        
        error = UnauthorizedActorError(
            message="Denied",
            actor="ROGUE",
            action="admin_override"
        )
        assert "[UNAUTHORIZED ACTOR]" in str(error)
        assert "ROGUE" in str(error)
        assert "admin_override" in str(error)

    def test_unauthorized_actor_error_is_frozen(self):
        """Verify UnauthorizedActorError is immutable."""
        from python.phase01_core.errors import UnauthorizedActorError
        
        error = UnauthorizedActorError(message="Test", actor="X", action="Y")
        with pytest.raises((AttributeError, TypeError)):
            error.actor = "HACKER"


class TestConstantMutationError:
    """Tests for ConstantMutationError instantiation."""

    def test_constant_mutation_error_instantiates(self):
        """Verify ConstantMutationError can be instantiated."""
        from python.phase01_core.errors import ConstantMutationError
        
        error = ConstantMutationError(
            message="Cannot change",
            constant_name="SYSTEM_NAME"
        )
        assert error is not None
        assert error.constant_name == "SYSTEM_NAME"

    def test_constant_mutation_error_str_format(self):
        """Verify ConstantMutationError string format."""
        from python.phase01_core.errors import ConstantMutationError
        
        error = ConstantMutationError(
            message="Immutable",
            constant_name="HUMAN_AUTHORITY_ABSOLUTE"
        )
        assert "[CONSTANT MUTATION]" in str(error)
        assert "HUMAN_AUTHORITY_ABSOLUTE" in str(error)

    def test_constant_mutation_error_is_frozen(self):
        """Verify ConstantMutationError is immutable."""
        from python.phase01_core.errors import ConstantMutationError
        
        error = ConstantMutationError(message="Test", constant_name="X")
        with pytest.raises((AttributeError, TypeError)):
            error.constant_name = "Y"


class TestForbiddenPatternError:
    """Tests for ForbiddenPatternError instantiation."""

    def test_forbidden_pattern_error_instantiates(self):
        """Verify ForbiddenPatternError can be instantiated."""
        from python.phase01_core.errors import ForbiddenPatternError
        
        error = ForbiddenPatternError(
            message="Pattern detected",
            pattern="auto_execute",
            location="module.py:42"
        )
        assert error is not None
        assert error.pattern == "auto_execute"
        assert error.location == "module.py:42"

    def test_forbidden_pattern_error_str_format(self):
        """Verify ForbiddenPatternError string format."""
        from python.phase01_core.errors import ForbiddenPatternError
        
        error = ForbiddenPatternError(
            message="Not allowed",
            pattern="daemon",
            location="server.py"
        )
        assert "[FORBIDDEN PATTERN]" in str(error)
        assert "daemon" in str(error)
        assert "server.py" in str(error)

    def test_forbidden_pattern_error_is_frozen(self):
        """Verify ForbiddenPatternError is immutable."""
        from python.phase01_core.errors import ForbiddenPatternError
        
        error = ForbiddenPatternError(message="Test", pattern="X", location="Y")
        with pytest.raises((AttributeError, TypeError)):
            error.pattern = "hacked"


class TestErrorsNoGlobalStateMutation:
    """Tests to verify errors do not mutate global state."""

    def test_error_creation_does_not_modify_sys_modules(self):
        """Verify creating errors does not add unexpected sys.modules."""
        from python.phase01_core import errors
        
        modules_before = set(sys.modules.keys())
        
        # Create all error types
        _ = errors.Phase01Error(message="test")
        _ = errors.InvariantViolationError(message="test", invariant_name="X")
        _ = errors.UnauthorizedActorError(message="test", actor="X", action="Y")
        _ = errors.ConstantMutationError(message="test", constant_name="X")
        _ = errors.ForbiddenPatternError(message="test", pattern="X", location="Y")
        
        modules_after = set(sys.modules.keys())
        
        # No new modules should be loaded just by creating errors
        new_modules = modules_after - modules_before
        assert len(new_modules) == 0, f"Unexpected modules loaded: {new_modules}"

    def test_errors_are_independent_instances(self):
        """Verify each error is an independent instance."""
        from python.phase01_core.errors import Phase01Error
        
        error1 = Phase01Error(message="First")
        error2 = Phase01Error(message="Second")
        
        assert error1 is not error2
        assert error1.message != error2.message

    def test_errors_do_not_share_state(self):
        """Verify error instances do not share mutable state."""
        from python.phase01_core.errors import InvariantViolationError
        
        error1 = InvariantViolationError(message="A", invariant_name="INV1")
        error2 = InvariantViolationError(message="B", invariant_name="INV2")
        
        # Changing one should not affect the other (they're frozen, but check values)
        assert error1.invariant_name == "INV1"
        assert error2.invariant_name == "INV2"
        assert error1.message != error2.message


class TestAllErrorsInheritFromBase:
    """Tests to verify error hierarchy."""

    def test_all_errors_inherit_from_phase01_error(self):
        """Verify all custom errors inherit from Phase01Error."""
        from python.phase01_core.errors import (
            Phase01Error,
            InvariantViolationError,
            UnauthorizedActorError,
            ConstantMutationError,
            ForbiddenPatternError,
        )
        
        assert issubclass(InvariantViolationError, Phase01Error)
        assert issubclass(UnauthorizedActorError, Phase01Error)
        assert issubclass(ConstantMutationError, Phase01Error)
        assert issubclass(ForbiddenPatternError, Phase01Error)

    def test_all_errors_are_exceptions(self):
        """Verify all custom errors are Exception subclasses."""
        from python.phase01_core.errors import (
            Phase01Error,
            InvariantViolationError,
            UnauthorizedActorError,
            ConstantMutationError,
            ForbiddenPatternError,
        )
        
        assert issubclass(Phase01Error, Exception)
        assert issubclass(InvariantViolationError, Exception)
        assert issubclass(UnauthorizedActorError, Exception)
        assert issubclass(ConstantMutationError, Exception)
        assert issubclass(ForbiddenPatternError, Exception)
