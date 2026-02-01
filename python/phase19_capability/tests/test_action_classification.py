"""
Tests for Phase-19 Action Classification.

Tests:
- classify_action_risk for each action type
- Risk level assignments
"""
import pytest


class TestClassifyActionRisk:
    """Test action risk classification."""

    def test_navigate_is_medium(self):
        """NAVIGATE is MEDIUM risk."""
        from python.phase19_capability.capability_engine import classify_action_risk
        from python.phase19_capability.capability_types import BrowserActionType, ActionRiskLevel

        risk = classify_action_risk(BrowserActionType.NAVIGATE)
        assert risk == ActionRiskLevel.MEDIUM

    def test_click_is_low(self):
        """CLICK is LOW risk."""
        from python.phase19_capability.capability_engine import classify_action_risk
        from python.phase19_capability.capability_types import BrowserActionType, ActionRiskLevel

        risk = classify_action_risk(BrowserActionType.CLICK)
        assert risk == ActionRiskLevel.LOW

    def test_read_is_low(self):
        """READ is LOW risk."""
        from python.phase19_capability.capability_engine import classify_action_risk
        from python.phase19_capability.capability_types import BrowserActionType, ActionRiskLevel

        risk = classify_action_risk(BrowserActionType.READ)
        assert risk == ActionRiskLevel.LOW

    def test_submit_form_is_high(self):
        """SUBMIT_FORM is HIGH risk."""
        from python.phase19_capability.capability_engine import classify_action_risk
        from python.phase19_capability.capability_types import BrowserActionType, ActionRiskLevel

        risk = classify_action_risk(BrowserActionType.SUBMIT_FORM)
        assert risk == ActionRiskLevel.HIGH

    def test_file_upload_is_forbidden(self):
        """FILE_UPLOAD is FORBIDDEN."""
        from python.phase19_capability.capability_engine import classify_action_risk
        from python.phase19_capability.capability_types import BrowserActionType, ActionRiskLevel

        risk = classify_action_risk(BrowserActionType.FILE_UPLOAD)
        assert risk == ActionRiskLevel.FORBIDDEN

    def test_script_execute_is_forbidden(self):
        """SCRIPT_EXECUTE is FORBIDDEN."""
        from python.phase19_capability.capability_engine import classify_action_risk
        from python.phase19_capability.capability_types import BrowserActionType, ActionRiskLevel

        risk = classify_action_risk(BrowserActionType.SCRIPT_EXECUTE)
        assert risk == ActionRiskLevel.FORBIDDEN

    def test_fill_input_is_medium(self):
        """FILL_INPUT is MEDIUM risk."""
        from python.phase19_capability.capability_engine import classify_action_risk
        from python.phase19_capability.capability_types import BrowserActionType, ActionRiskLevel

        risk = classify_action_risk(BrowserActionType.FILL_INPUT)
        assert risk == ActionRiskLevel.MEDIUM


class TestMediumRiskDecision:
    """Test MEDIUM risk decisions."""

    def test_medium_risk_navigate_allowed(self):
        """MEDIUM risk NAVIGATE is ALLOWED."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.NAVIGATE,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="ATTEMPTED"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.ALLOWED

    def test_medium_risk_fill_input_allowed(self):
        """MEDIUM risk FILL_INPUT is ALLOWED."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.FILL_INPUT,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="ATTEMPTED"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.ALLOWED


class TestActionNotInPolicy:
    """Test action not in policy."""

    def test_action_not_in_policy_validate_fails(self):
        """Action not in policy fails validation."""
        from python.phase19_capability.capability_engine import validate_action_against_policy
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset({BrowserActionType.CLICK})  # Only CLICK
        )

        result = validate_action_against_policy(
            BrowserActionType.NAVIGATE,  # Not in policy
            policy,
            "ATTEMPTED"
        )
        assert result is False
