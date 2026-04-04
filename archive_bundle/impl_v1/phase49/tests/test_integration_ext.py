# test_integration_ext.py
"""Extended integration tests for Phase-49 governor interactions."""

import pytest

from impl_v1.phase49.governors.g12_voice_input import (
    validate_voice_input,
    VoiceIntentType,
    VoiceInputStatus,
)
from impl_v1.phase49.governors.g13_dashboard_router import (
    route_voice_intent,
    create_approval_request,
    submit_decision,
    clear_requests,
    ProposedMode,
)
from impl_v1.phase49.governors.g14_target_discovery import (
    discover_targets,
    can_discovery_trigger_execution,
)
from impl_v1.phase49.governors.g15_cve_api import (
    fetch_cves_passive,
    can_cve_trigger_execution,
    clear_api_cache,
    get_risk_context,
)
from impl_v1.phase49.governors.g16_gmail_alerts import (
    send_new_device_alert,
    can_email_approve_execution,
    clear_verification_store,
)
from impl_v1.phase49.governors.g17_voice_reporting import (
    generate_high_impact_tips,
    can_voice_execute,
    clear_reports,
)
from impl_v1.phase49.governors.g18_screen_inspection import (
    create_inspection_request,
    authorize_inspection,
    perform_inspection,
    can_inspection_interact,
    clear_inspection_store,
)
from impl_v1.phase49.governors.g10_owner_alerts import clear_alerts


class TestVoiceToRouterIntegration:
    """Tests for voice → router integration."""
    
    def setup_method(self):
        clear_requests()
    
    def test_hindi_target_creates_approval(self):
        intent = validate_voice_input("ye mera target hai example.com")
        request = route_voice_intent(intent)
        assert request is not None
        assert "example.com" in request.target
    
    def test_english_target_creates_approval(self):
        intent = validate_voice_input("target is hackerone.com")
        request = route_voice_intent(intent)
        assert request is not None
    
    def test_find_targets_creates_discovery_approval(self):
        intent = validate_voice_input("find targets for me")
        request = route_voice_intent(intent)
        assert request is not None
        assert request.proposed_mode == ProposedMode.READ_ONLY
    
    def test_status_query_no_approval_needed(self):
        intent = validate_voice_input("status batao")
        request = route_voice_intent(intent)
        assert request is None  # Status queries don't need approval


class TestCVEToRiskIntegration:
    """Tests for CVE → risk context integration."""
    
    def setup_method(self):
        clear_api_cache()
    
    def test_cve_result_provides_risk_context(self):
        result = fetch_cves_passive("test")
        context = get_risk_context(result)
        assert "risk_level" in context
        assert "cve_count" in context


class TestVoiceReportIntegration:
    """Tests for voice report generation integration."""
    
    def setup_method(self):
        clear_reports()
    
    def test_report_help_intent_generates_tips(self):
        intent = validate_voice_input("is report me aur kya add kar sakte hain")
        if intent.intent_type == VoiceIntentType.REPORT_HELP:
            report = generate_high_impact_tips("xss")
            assert len(report.suggestions) > 0


class TestScreenInspectionIntegration:
    """Tests for screen inspection flow integration."""
    
    def setup_method(self):
        clear_inspection_store()
    
    def test_screen_takeover_intent_triggers_inspection_request(self):
        intent = validate_voice_input("takeover the screen")
        if intent.intent_type == VoiceIntentType.SCREEN_TAKEOVER:
            request = create_inspection_request(
                device_id="DEV-TEST",
                user_id="USR-TEST",
                device_trusted=True,
                user_verified=True,
            )
            authorize_inspection(request.request_id)
            result = perform_inspection(request.request_id)
            assert result is not None
            assert len(result.voice_explanation_en) > 0


class TestNoExecutionFromAnySource:
    """Critical tests: no source can trigger execution directly."""
    
    def test_voice_cannot_execute(self):
        can_exec, _ = can_voice_execute()
        assert can_exec == False
    
    def test_cve_cannot_trigger_execution(self):
        can_trigger, _ = can_cve_trigger_execution()
        assert can_trigger == False
    
    def test_discovery_cannot_trigger_execution(self):
        can_trigger, _ = can_discovery_trigger_execution()
        assert can_trigger == False
    
    def test_email_cannot_approve_execution(self):
        can_approve, _ = can_email_approve_execution()
        assert can_approve == False
    
    def test_screen_cannot_interact(self):
        can_interact, _ = can_inspection_interact()
        assert can_interact == False


class TestAlertSystemIntegration:
    """Tests for alert system integration."""
    
    def setup_method(self):
        clear_verification_store()
        clear_alerts()
    
    def test_new_device_triggers_alert(self):
        result = send_new_device_alert("DEV-NEW", "192.168.1.100")
        assert result is not None
        assert result.error_message is None


class TestApprovalRequiredFlow:
    """Tests for approval-required flows."""
    
    def setup_method(self):
        clear_requests()
    
    def test_approval_required_for_target(self):
        intent = validate_voice_input("target is vulnerable.com")
        request = route_voice_intent(intent)
        assert request is not None
        
        # Cannot execute without approval
        from impl_v1.phase49.governors.g13_dashboard_router import is_execution_approved
        approved, _ = is_execution_approved(request.request_id)
        assert approved == False
    
    def test_human_approval_enables_execution(self):
        intent = validate_voice_input("target is safe-target.com")
        request = route_voice_intent(intent)
        
        # Human approves
        submit_decision(request.request_id, approved=True, approver_id="HUMAN-001")
        
        from impl_v1.phase49.governors.g13_dashboard_router import is_execution_approved
        approved, _ = is_execution_approved(request.request_id)
        assert approved == True
    
    def test_human_rejection_blocks_execution(self):
        intent = validate_voice_input("target is blocked-target.com")
        request = route_voice_intent(intent)
        
        # Human rejects
        submit_decision(request.request_id, approved=False, approver_id="HUMAN-001", reason="Out of scope")
        
        from impl_v1.phase49.governors.g13_dashboard_router import is_execution_approved
        approved, _ = is_execution_approved(request.request_id)
        assert approved == False
