"""
Tests for Phase-19 Forbidden Actions.

Tests:
- FORBIDDEN actions always denied
"""
import pytest


class TestForbiddenActions:
    """Test forbidden action handling."""

    def test_file_upload_always_denied(self):
        """FILE_UPLOAD is always DENIED."""
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
        assert result.reason_code == "CAP-001"

    def test_script_execute_always_denied(self):
        """SCRIPT_EXECUTE is always DENIED."""
        from python.phase19_capability.capability_engine import decide_capability
        from python.phase19_capability.capability_types import BrowserActionType, CapabilityDecision
        from python.phase19_capability.capability_context import ActionRequestContext

        context = ActionRequestContext(
            execution_id="EXEC-001",
            action_type=BrowserActionType.SCRIPT_EXECUTE,
            request_timestamp="2026-01-25T15:05:00-05:00",
            execution_state="ATTEMPTED"
        )

        result = decide_capability(context)
        assert result.decision == CapabilityDecision.DENIED

    def test_forbidden_even_if_in_policy(self):
        """FORBIDDEN action denied even if in policy."""
        from python.phase19_capability.capability_engine import validate_action_against_policy
        from python.phase19_capability.capability_types import BrowserActionType
        from python.phase19_capability.capability_context import BrowserCapabilityPolicy

        policy = BrowserCapabilityPolicy(
            policy_id="POL-001",
            allowed_actions=frozenset({BrowserActionType.FILE_UPLOAD, BrowserActionType.SCRIPT_EXECUTE})
        )

        assert validate_action_against_policy(BrowserActionType.FILE_UPLOAD, policy, "ATTEMPTED") is False
        assert validate_action_against_policy(BrowserActionType.SCRIPT_EXECUTE, policy, "ATTEMPTED") is False
