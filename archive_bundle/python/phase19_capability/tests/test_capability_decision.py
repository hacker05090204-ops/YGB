"""
Tests for Phase-19 Capability Decision.

Tests:
- decide_capability for various contexts
- State-based decisions
"""
import pytest


class TestDecideCapability:
    """Test capability decision logic."""

    def test_low_risk_attempted_allowed(self):
        """LOW risk with ATTEMPTED state is ALLOWED."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.CLICK,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="ATTEMPTED"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.ALLOWED

    def test_high_risk_requires_human(self):
        """HIGH risk requires human."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.SUBMIT_FORM,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="ATTEMPTED"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.HUMAN_REQUIRED

    def test_forbidden_always_denied(self):
        """FORBIDDEN is always DENIED."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.FILE_UPLOAD,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="ATTEMPTED"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.DENIED

    def test_completed_state_denied(self):
        """COMPLETED state is always DENIED."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.CLICK,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="COMPLETED"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.DENIED

    def test_escalated_state_human_required(self):
        """ESCALATED state requires human."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.CLICK,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="ESCALATED"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.HUMAN_REQUIRED
