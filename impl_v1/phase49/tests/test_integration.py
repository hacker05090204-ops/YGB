# test_integration.py
"""Integration tests for Phase-49 governors."""

import pytest
from impl_v1.phase49.governors.g12_voice_input import (
    validate_voice_input,
    VoiceIntentType,
    VoiceInputStatus,
)
from impl_v1.phase49.governors.g13_dashboard_router import (
    clear_requests,
    route_voice_intent,
    submit_decision,
    is_execution_approved,
    ApprovalStatus,
)
from impl_v1.phase49.governors.g11_execution_seal import (
    seal_execution_intent,
    can_execute,
)


class TestVoiceToDashboardFlow:
    """Test voice → dashboard → blocked execution flow."""
    
    def setup_method(self):
        clear_requests()
    
    def test_voice_creates_approval_request(self):
        intent = validate_voice_input("target is example.com")
        assert intent.status == VoiceInputStatus.PARSED
        
        request = route_voice_intent(intent)
        assert request is not None
        assert request.target == "example.com"
    
    def test_voice_blocked_no_execution(self):
        intent = validate_voice_input("execute attack")
        assert intent.status == VoiceInputStatus.BLOCKED
        
        request = route_voice_intent(intent)
        assert request is None  # Blocked intents don't create requests
    
    def test_status_query_no_request(self):
        intent = validate_voice_input("what is the status")
        assert intent.intent_type == VoiceIntentType.QUERY_STATUS
        
        request = route_voice_intent(intent)
        assert request is None  # Queries don't need approval


class TestApprovalRequiredForExecution:
    """Test that execution requires dashboard approval."""
    
    def setup_method(self):
        clear_requests()
    
    def test_no_approval_no_execution(self):
        intent = validate_voice_input("target is test.com")
        request = route_voice_intent(intent)
        
        approved, reason = is_execution_approved(request.request_id)
        assert not approved
        assert "Awaiting" in reason
    
    def test_approval_enables_execution(self):
        intent = validate_voice_input("target is test.com")
        request = route_voice_intent(intent)
        
        submit_decision(request.request_id, True, "human-1", "Approved")
        
        approved, reason = is_execution_approved(request.request_id)
        assert approved
    
    def test_rejection_blocks_execution(self):
        intent = validate_voice_input("target is risky.com")
        request = route_voice_intent(intent)
        
        submit_decision(request.request_id, False, "human-1", "Too risky")
        
        approved, reason = is_execution_approved(request.request_id)
        assert not approved
        assert "REJECTED" in reason


class TestExecutionSealIntegration:
    """Test that execution seal blocks without all approvals."""
    
    def test_seal_requires_all_pass(self):
        seal = seal_execution_intent(
            execution_state_valid=True,
            browser_types_valid=True,
            browser_safety_passed=True,
            voice_ready=True,
            assistant_approved=True,
            autonomy_mode_valid=True,
            cve_loaded=True,
            license_valid=True,
            device_trusted=True,
            no_critical_alerts=True,
            human_confirmed=True,
        )
        assert can_execute(seal)
    
    def test_seal_fails_without_human(self):
        seal = seal_execution_intent(
            execution_state_valid=True,
            browser_types_valid=True,
            browser_safety_passed=True,
            voice_ready=True,
            assistant_approved=True,
            autonomy_mode_valid=True,
            cve_loaded=True,
            license_valid=True,
            device_trusted=True,
            no_critical_alerts=True,
            human_confirmed=False,  # Not confirmed
        )
        assert not can_execute(seal)
