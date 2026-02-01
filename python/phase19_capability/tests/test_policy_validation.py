"""
Tests for Phase-19 Policy Validation.

Tests:
- is_action_allowed
- validate_action_against_policy
"""
import pytest


class TestIsActionAllowed:
    """Test is_action_allowed function."""

    def test_action_in_policy_allowed(self):
        """Action in allowed_actions is allowed."""
        from python.phase19_capability.capability_engine import is_action_allowed
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset({BrowserActionType.CLICK, BrowserActionType.READ})
        )

        assert is_action_allowed(BrowserActionType.CLICK, policy) is True

    def test_action_not_in_policy_denied(self):
        """Action not in allowed_actions is denied."""
        from python.phase19_capability.capability_engine import is_action_allowed
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset({BrowserActionType.CLICK})
        )

        assert is_action_allowed(BrowserActionType.NAVIGATE, policy) is False


class TestValidateActionAgainstPolicy:
    """Test validate_action_against_policy function."""

    def test_valid_action_passes(self):
        """Valid action passes validation."""
        from python.phase19_capability.capability_engine import validate_action_against_policy
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset({BrowserActionType.CLICK, BrowserActionType.READ})
        )

        result = validate_action_against_policy(
            BrowserActionType.CLICK,
            policy,
            "ATTEMPTED"
        )
        assert result is True

    def test_forbidden_action_fails(self):
        """Forbidden action fails validation."""
        from python.phase19_capability.capability_engine import validate_action_against_policy
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset({BrowserActionType.FILE_UPLOAD})  # In policy but FORBIDDEN
        )

        result = validate_action_against_policy(
            BrowserActionType.FILE_UPLOAD,
            policy,
            "ATTEMPTED"
        )
        assert result is False

    def test_completed_state_fails(self):
        """COMPLETED state fails validation."""
        from python.phase19_capability.capability_engine import validate_action_against_policy
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset({BrowserActionType.CLICK})
        )

        result = validate_action_against_policy(
            BrowserActionType.CLICK,
            policy,
            "COMPLETED"
        )
        assert result is False
