# test_g20_dashboard_state.py
"""Tests for G20 Dashboard State & Events."""

import pytest

from impl_v1.phase49.governors.g20_dashboard_state import (
    DashboardPanel,
    UserMode,
    ActivityType,
    AlertLevel,
    UserPanelState,
    AdminPanelState,
    ActivitySessionState,
    ReportSessionState,
    DashboardState,
    DashboardEvent,
    create_dashboard_state,
    get_dashboard,
    update_activity_with_targets,
    set_quantity_selected,
    emit_event,
    get_events,
    update_report_progress,
    can_dashboard_approve_execution,
    can_dashboard_trigger_action,
    can_dashboard_bypass_router,
    clear_dashboard_state,
)


class TestDashboardPanel:
    """Tests for DashboardPanel enum."""
    
    def test_has_user(self):
        assert DashboardPanel.USER.value == "USER"
    
    def test_has_admin(self):
        assert DashboardPanel.ADMIN.value == "ADMIN"
    
    def test_has_activity(self):
        assert DashboardPanel.ACTIVITY.value == "ACTIVITY"
    
    def test_has_report(self):
        assert DashboardPanel.REPORT.value == "REPORT"


class TestUserMode:
    """Tests for UserMode enum."""
    
    def test_has_manual(self):
        assert UserMode.MANUAL.value == "MANUAL"
    
    def test_has_assisted(self):
        assert UserMode.ASSISTED.value == "ASSISTED"
    
    def test_no_autonomous_mode(self):
        # Verify no autonomous mode exists
        modes = [m.value for m in UserMode]
        assert "AUTONOMOUS" not in modes


class TestCreateDashboardState:
    """Tests for create_dashboard_state."""
    
    def setup_method(self):
        clear_dashboard_state()
    
    def test_creates_dashboard(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        assert isinstance(dashboard, DashboardState)
    
    def test_dashboard_has_id(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        assert dashboard.dashboard_id.startswith("DASH-")
    
    def test_has_user_panel(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        assert dashboard.user_panel is not None
        assert dashboard.user_panel.user_name == "Hunter1"
    
    def test_admin_panel_for_admin(self):
        dashboard = create_dashboard_state("user1", "Admin1", is_admin=True)
        assert dashboard.admin_panel is not None
    
    def test_no_admin_panel_for_user(self):
        dashboard = create_dashboard_state("user1", "Hunter1", is_admin=False)
        assert dashboard.admin_panel is None
    
    def test_has_activity_session(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        assert dashboard.activity_session is not None
    
    def test_has_report_session(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        assert dashboard.report_session is not None


class TestUpdateActivity:
    """Tests for update_activity_with_targets."""
    
    def setup_method(self):
        clear_dashboard_state()
    
    def test_updates_platform(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        targets = [{"domain": "example.com", "report_count": 5}]
        updated = update_activity_with_targets(
            dashboard.dashboard_id,
            "HackerOne",
            "*.example.com",
            targets,
        )
        assert updated.activity_session.platform_detected == "HackerOne"
    
    def test_updates_scope(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        targets = [{"domain": "test.com"}]
        updated = update_activity_with_targets(
            dashboard.dashboard_id,
            "Bugcrowd",
            "*.test.com",
            targets,
        )
        assert updated.activity_session.scope_extracted == "*.test.com"
    
    def test_adds_targets(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        targets = [
            {"domain": "a.com"},
            {"domain": "b.com"},
        ]
        updated = update_activity_with_targets(
            dashboard.dashboard_id,
            "HackerOne",
            "*",
            targets,
        )
        assert len(updated.activity_session.suggested_targets) == 2
    
    def test_human_not_approved_by_default(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        updated = update_activity_with_targets(
            dashboard.dashboard_id,
            "HackerOne",
            "*",
            [],
        )
        assert updated.activity_session.human_approved == False


class TestSetQuantity:
    """Tests for set_quantity_selected."""
    
    def setup_method(self):
        clear_dashboard_state()
    
    def test_sets_quantity(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        updated = set_quantity_selected(dashboard.dashboard_id, 10)
        assert updated.activity_session.quantity_selected == 10
    
    def test_clamps_max_to_20(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        updated = set_quantity_selected(dashboard.dashboard_id, 100)
        assert updated.activity_session.quantity_selected == 20
    
    def test_clamps_min_to_1(self):
        dashboard = create_dashboard_state("user1", "Hunter1")
        updated = set_quantity_selected(dashboard.dashboard_id, 0)
        assert updated.activity_session.quantity_selected == 1


class TestEmitEvent:
    """Tests for emit_event."""
    
    def setup_method(self):
        clear_dashboard_state()
    
    def test_emits_event(self):
        event = emit_event(ActivityType.TARGET_DISCOVERED, DashboardPanel.ACTIVITY, {})
        assert isinstance(event, DashboardEvent)
    
    def test_event_has_id(self):
        event = emit_event(ActivityType.VOICE_COMMAND, DashboardPanel.USER, {})
        assert event.event_id.startswith("EVT-")
    
    def test_events_are_stored(self):
        emit_event(ActivityType.REPORT_STARTED, DashboardPanel.REPORT, {})
        events = get_events()
        assert len(events) >= 1


class TestCanDashboardApprove:
    """Tests for can_dashboard_approve_execution guard."""
    
    def test_cannot_approve(self):
        can_approve, reason = can_dashboard_approve_execution()
        assert can_approve == False
        assert "G13" in reason or "human" in reason.lower()


class TestCanDashboardTrigger:
    """Tests for can_dashboard_trigger_action guard."""
    
    def test_cannot_trigger(self):
        can_trigger, reason = can_dashboard_trigger_action()
        assert can_trigger == False


class TestCanDashboardBypass:
    """Tests for can_dashboard_bypass_router guard."""
    
    def test_cannot_bypass(self):
        can_bypass, reason = can_dashboard_bypass_router()
        assert can_bypass == False
        assert "G13" in reason or "router" in reason.lower()
