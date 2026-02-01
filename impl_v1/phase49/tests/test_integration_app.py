# test_integration_app.py
"""Integration tests for Full App Mode flow."""

import pytest

from impl_v1.phase49.governors.g01_execution_kernel import (
    ExecutionState,
    create_execution_kernel,
)
from impl_v1.phase49.governors.g12_voice_input import (
    validate_voice_input,
    VoiceIntentType,
)
from impl_v1.phase49.governors.g13_dashboard_router import (
    route_voice_intent,
)
from impl_v1.phase49.governors.g19_interactive_browser import (
    create_interactive_session,
    perform_observation,
    Platform,
    can_session_execute,
    clear_sessions,
)
from impl_v1.phase49.governors.g20_dashboard_state import (
    create_dashboard_state,
    update_activity_with_targets,
    DashboardPanel,
    can_dashboard_approve_execution,
    clear_dashboard_state,
)
from impl_v1.phase49.governors.g21_auto_update import (
    check_for_updates,
    request_update_approval,
    submit_approval,
    install_update,
    UpdateStatus,
    can_auto_update_execute,
    clear_update_state,
)
from impl_v1.phase49.governors.g22_user_database import (
    create_user,
    create_session,
    UserRole,
    can_database_delete_without_approval,
    clear_database,
)


class TestAppStartupFlow:
    """Tests for app startup flow."""
    
    def setup_method(self):
        clear_sessions()
        clear_dashboard_state()
        clear_database()
        clear_update_state()
    
    def test_app_creates_user_session(self):
        """App startup creates user and session."""
        user = create_user("Hunter1", "hunter@test.com")
        session = create_session(user.user_id, "device1", "192.168.1.1")
        assert user is not None
        assert session is not None
    
    def test_app_creates_browser_session(self):
        """App startup creates browser session in OBSERVE_ONLY."""
        user = create_user("Hunter1")
        browser_session = create_interactive_session("device1", user.user_id)
        assert browser_session.request.mode.value == "OBSERVE_ONLY"
    
    def test_app_creates_dashboard(self):
        """App startup creates dashboard state."""
        user = create_user("Hunter1")
        dashboard = create_dashboard_state(user.user_id, user.name)
        assert dashboard.user_panel is not None
        assert dashboard.activity_session is not None


class TestBrowserObservationFlow:
    """Tests for browser observation flow."""
    
    def setup_method(self):
        clear_sessions()
        clear_dashboard_state()
    
    def test_observation_extracts_platform(self):
        """Observation extracts platform from page."""
        session = create_interactive_session("device1", "user1")
        mock_data = {
            "title": "HackerOne Program",
            "url": "https://hackerone.com/program/test",
            "text": "Scope: *.example.com, API",
        }
        result = perform_observation(session.session_id, _mock_data=mock_data)
        assert result.platform == Platform.HACKERONE
    
    def test_observation_detects_scope(self):
        """Observation extracts scope hints."""
        session = create_interactive_session("device1", "user1")
        mock_data = {
            "title": "Program",
            "url": "https://bugcrowd.com/test",
            "text": "In Scope: *.test.com, web applications",
        }
        result = perform_observation(session.session_id, _mock_data=mock_data)
        assert "SCOPE_SECTION_DETECTED" in result.scope_hints
    
    def test_observation_to_dashboard(self):
        """Observation data routes to dashboard."""
        session = create_interactive_session("device1", "user1")
        dashboard = create_dashboard_state("user1", "Hunter1")
        
        # Perform observation
        mock_data = {
            "title": "Test Program",
            "url": "https://hackerone.com",
            "text": "Targets available",
        }
        observation = perform_observation(session.session_id, _mock_data=mock_data)
        
        # Update dashboard with discovered targets
        targets = [{"domain": "example.com", "report_count": 10}]
        updated = update_activity_with_targets(
            dashboard.dashboard_id,
            observation.platform.value,
            "*.example.com",
            targets,
        )
        
        assert updated.activity_session.platform_detected == "HACKERONE"
        assert len(updated.activity_session.suggested_targets) == 1


class TestVoiceToDashboardFlow:
    """Tests for voice command to dashboard flow."""
    
    def setup_method(self):
        clear_sessions()
        clear_dashboard_state()
    
    def test_find_targets_voice_command(self):
        """Voice command to find targets creates approval request."""
        intent = validate_voice_input("find targets for me")
        assert intent.intent_type == VoiceIntentType.FIND_TARGETS
    
    def test_voice_cannot_bypass_dashboard(self):
        """Voice commands cannot bypass dashboard approval."""
        # All guards return False
        can_exec, _ = can_session_execute()
        can_approve, _ = can_dashboard_approve_execution()
        
        assert can_exec == False
        assert can_approve == False


class TestUpdateFlowWithApproval:
    """Tests for update flow requiring approval."""
    
    def setup_method(self):
        clear_update_state()
    
    def test_update_requires_approval(self):
        """Update requires explicit user approval."""
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        
        # Try to install without approval
        result = install_update(update.update_id)
        assert result.status == UpdateStatus.FAILED
    
    def test_update_installs_with_approval(self):
        """Update installs after user approval."""
        mock = {"version": "1.0.1"}
        update = check_for_updates(_mock_update=mock)
        
        approval = request_update_approval(update.update_id, "user1")
        submit_approval(approval.approval_id, True)
        
        result = install_update(update.update_id)
        assert result.status == UpdateStatus.INSTALLED
    
    def test_auto_update_impossible(self):
        """Auto-update without approval is impossible."""
        can_exec, _ = can_auto_update_execute()
        assert can_exec == False


class TestNoSilentExecution:
    """Tests verifying no silent execution is possible."""
    
    def test_all_session_guards_block(self):
        """All session guards block execution."""
        from impl_v1.phase49.governors.g19_interactive_browser import (
            can_session_execute,
            can_session_interact,
            can_session_submit,
            can_session_scan,
        )
        
        guards = [
            can_session_execute,
            can_session_interact,
            can_session_submit,
            can_session_scan,
        ]
        
        for guard in guards:
            can_do, _ = guard()
            assert can_do == False
    
    def test_all_dashboard_guards_block(self):
        """All dashboard guards block direct actions."""
        from impl_v1.phase49.governors.g20_dashboard_state import (
            can_dashboard_approve_execution,
            can_dashboard_trigger_action,
            can_dashboard_bypass_router,
        )
        
        guards = [
            can_dashboard_approve_execution,
            can_dashboard_trigger_action,
            can_dashboard_bypass_router,
        ]
        
        for guard in guards:
            can_do, _ = guard()
            assert can_do == False
    
    def test_all_database_guards_block(self):
        """All database guards block unaudited operations."""
        from impl_v1.phase49.governors.g22_user_database import (
            can_database_delete_without_approval,
            can_database_bulk_delete,
            can_database_skip_audit,
        )
        
        guards = [
            can_database_delete_without_approval,
            can_database_bulk_delete,
            can_database_skip_audit,
        ]
        
        for guard in guards:
            can_do, _ = guard()
            assert can_do == False


class TestExecutionStateRemains:
    """Tests that execution state remains controlled."""
    
    def setup_method(self):
        clear_sessions()
        clear_dashboard_state()
    
    def test_browser_does_not_change_execution_state(self):
        """Opening browser doesn't change execution state."""
        kernel = create_execution_kernel("session1")
        assert kernel.state == ExecutionState.IDLE
        
        # Create browser session
        browser = create_interactive_session("device1", "user1")
        
        # Kernel state should STILL be IDLE
        assert kernel.state == ExecutionState.IDLE
    
    def test_dashboard_requires_human_for_executing(self):
        """Dashboard activity requires human approval for EXECUTING."""
        dashboard = create_dashboard_state("user1", "Hunter1")
        
        # Update with targets
        targets = [{"domain": "test.com"}]
        updated = update_activity_with_targets(
            dashboard.dashboard_id,
            "HackerOne",
            "*",
            targets,
        )
        
        # human_approved should be False
        assert updated.activity_session.human_approved == False
