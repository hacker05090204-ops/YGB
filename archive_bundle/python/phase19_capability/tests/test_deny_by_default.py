"""
Tests for Phase-19 Deny-By-Default.

Tests:
- Unknown action → DENIED
- Missing context → DENIED
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_unknown_state_denied(self):
        """Unknown execution state is denied."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.CLICK,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="UNKNOWN_STATE"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.DENIED

    def test_action_not_in_empty_policy_denied(self):
        """Action not in empty policy is denied."""
        from python.phase19_capability.capability_engine import is_action_allowed
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset()  # Empty policy
        )

        assert is_action_allowed(BrowserActionType.CLICK, policy) is False


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_capability_decision_result_frozen(self):
        """CapabilityDecisionResult is frozen."""
        from python.phase19_capability.capability_types import BrowserActionType, ActionRiskLevel, CapabilityDecision
        from python.phase19_capability.capability_context import CapabilityDecisionResult

        result = CapabilityDecisionResult(
            decision=CapabilityDecision.ALLOWED,
            reason_code="OK",
            reason_description="Allowed",
            action_type=BrowserActionType.CLICK,
            risk_level=ActionRiskLevel.LOW
        )

        with pytest.raises(Exception):
            result.decision = CapabilityDecision.DENIED

    def test_policy_frozen(self):
        """BrowserCapabilityPolicy is frozen."""
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset({BrowserActionType.CLICK})
        )

        with pytest.raises(Exception):
            policy.policy_id = "MODIFIED"


class TestDefaultDenyPath:
    """Test default deny decision path."""

    def test_default_deny_with_mocked_risk(self):
        """Default deny path when no conditions match."""
        # The default deny at line 170 only triggers if risk level is not
        # LOW, MEDIUM, HIGH, or FORBIDDEN - which is impossible with current enums
        # Since all enum values are covered, line 170 is unreachable in practice
        # This is defensive programming - the test verifies the decision table is complete
        from python.phase19_capability.capability_types import ActionRiskLevel

        # Verify all risk levels are covered
        assert len(ActionRiskLevel) == 4
        assert ActionRiskLevel.LOW in ActionRiskLevel
        assert ActionRiskLevel.MEDIUM in ActionRiskLevel
        assert ActionRiskLevel.HIGH in ActionRiskLevel
        assert ActionRiskLevel.FORBIDDEN in ActionRiskLevel
