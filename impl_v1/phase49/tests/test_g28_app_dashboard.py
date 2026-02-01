# Test G28: Full App Dashboard
"""
Tests for app dashboard governor.

100% coverage required.
"""

import pytest
from impl_v1.phase49.governors.g28_app_dashboard import (
    DashboardMode,
    SessionStatus,
    AlertSeverity,
    DashboardUser,
    TargetEntry,
    ActivitySession,
    DashboardAlert,
    DashboardState,
    can_dashboard_execute,
    can_dashboard_approve_execution,
    can_dashboard_trigger_automation,
    can_dashboard_bypass_governors,
    can_dashboard_modify_evidence,
    generate_user_id,
    generate_target_id,
    generate_session_id,
    generate_alert_id,
    generate_state_id,
    DashboardManager,
    validate_dashboard_action,
    create_dashboard,
)


class TestGuards:
    """Test all security guards."""
    
    def test_can_dashboard_execute_always_false(self):
        """Guard: Dashboard cannot execute."""
        assert can_dashboard_execute() is False
    
    def test_can_dashboard_approve_execution_always_false(self):
        """Guard: Dashboard cannot approve."""
        assert can_dashboard_approve_execution() is False
    
    def test_can_dashboard_trigger_automation_always_false(self):
        """Guard: Dashboard cannot automate."""
        assert can_dashboard_trigger_automation() is False
    
    def test_can_dashboard_bypass_governors_always_false(self):
        """Guard: Dashboard cannot bypass."""
        assert can_dashboard_bypass_governors() is False
    
    def test_can_dashboard_modify_evidence_always_false(self):
        """Guard: Dashboard cannot modify evidence."""
        assert can_dashboard_modify_evidence() is False


class TestIdGeneration:
    """Test ID generation functions."""
    
    def test_generate_user_id(self):
        """Generate user ID."""
        uid = generate_user_id()
        assert uid.startswith("USR-")
    
    def test_generate_target_id(self):
        """Generate target ID."""
        tid = generate_target_id()
        assert tid.startswith("TGT-")
    
    def test_generate_session_id(self):
        """Generate session ID."""
        sid = generate_session_id()
        assert sid.startswith("SES-")
    
    def test_generate_alert_id(self):
        """Generate alert ID."""
        aid = generate_alert_id()
        assert aid.startswith("ALT-")
    
    def test_generate_state_id(self):
        """Generate state ID."""
        sid = generate_state_id()
        assert sid.startswith("STA-")


class TestDashboardManager:
    """Test dashboard manager."""
    
    def test_create_dashboard(self):
        """Create dashboard."""
        dashboard = create_dashboard()
        assert dashboard is not None
    
    def test_create_user(self):
        """Create user."""
        dashboard = DashboardManager()
        user = dashboard.create_user("testuser")
        
        assert user.username == "testuser"
        assert user.role == DashboardMode.USER
        assert user.is_active is True
    
    def test_create_admin_user(self):
        """Create admin user."""
        dashboard = DashboardManager()
        user = dashboard.create_user("admin", DashboardMode.ADMIN)
        
        assert user.role == DashboardMode.ADMIN
    
    def test_login_user(self):
        """Login user."""
        dashboard = DashboardManager()
        user = dashboard.create_user("testuser")
        logged_in = dashboard.login_user(user.user_id)
        
        assert logged_in is not None
        assert logged_in.last_login is not None
    
    def test_login_invalid_user(self):
        """Login invalid user fails."""
        dashboard = DashboardManager()
        result = dashboard.login_user("INVALID")
        assert result is None
    
    def test_logout_user(self):
        """Logout user."""
        dashboard = DashboardManager()
        user = dashboard.create_user("testuser")
        dashboard.login_user(user.user_id)
        dashboard.logout_user()
        
        state = dashboard.get_state()
        assert state.current_user is None
        assert state.mode == DashboardMode.READONLY
    
    def test_get_all_users(self):
        """Get all users."""
        dashboard = DashboardManager()
        dashboard.create_user("user1")
        dashboard.create_user("user2")
        
        users = dashboard.get_all_users()
        assert len(users) == 2


class TestTargetManagement:
    """Test target management."""
    
    def test_add_target(self):
        """Add target."""
        dashboard = DashboardManager()
        target = dashboard.add_target("HackerOne", "https://example.com")
        
        assert target.platform == "HackerOne"
        assert target.url == "https://example.com"
        assert target.progress_percent == 0
    
    def test_add_targets_batch(self):
        """Add multiple targets."""
        dashboard = DashboardManager()
        targets = dashboard.add_targets_batch([
            ("HackerOne", "https://a.com"),
            ("Bugcrowd", "https://b.com"),
        ])
        
        assert len(targets) == 2
    
    def test_update_target_progress(self):
        """Update target progress."""
        dashboard = DashboardManager()
        target = dashboard.add_target("HackerOne", "https://example.com")
        
        updated = dashboard.update_target_progress(
            target.target_id, 50, "IN_PROGRESS"
        )
        
        assert updated.progress_percent == 50
        assert updated.status == "IN_PROGRESS"
    
    def test_update_target_progress_invalid(self):
        """Update invalid target fails."""
        dashboard = DashboardManager()
        result = dashboard.update_target_progress("INVALID", 50, "test")
        assert result is None
    
    def test_update_target_progress_bounds(self):
        """Progress is bounded 0-100."""
        dashboard = DashboardManager()
        target = dashboard.add_target("HackerOne", "https://example.com")
        
        updated = dashboard.update_target_progress(target.target_id, 150, "test")
        assert updated.progress_percent == 100
        
        updated2 = dashboard.update_target_progress(target.target_id, -10, "test")
        assert updated2.progress_percent == 0
    
    def test_get_target_count(self):
        """Get target count."""
        dashboard = DashboardManager()
        dashboard.add_target("H1", "https://a.com")
        dashboard.add_target("BC", "https://b.com")
        
        assert dashboard.get_target_count() == 2


class TestSessionManagement:
    """Test session management."""
    
    def test_start_session(self):
        """Start session."""
        dashboard = DashboardManager()
        user = dashboard.create_user("testuser")
        dashboard.login_user(user.user_id)
        
        session = dashboard.start_session()
        
        assert session.status == SessionStatus.ACTIVE
        assert session.user_id == user.user_id
    
    def test_start_session_requires_login(self):
        """Session requires logged in user."""
        dashboard = DashboardManager()
        
        with pytest.raises(ValueError):
            dashboard.start_session()
    
    def test_end_session(self):
        """End session."""
        dashboard = DashboardManager()
        user = dashboard.create_user("testuser")
        dashboard.login_user(user.user_id)
        session = dashboard.start_session()
        
        ended = dashboard.end_session(session.session_id)
        
        assert ended.status == SessionStatus.COMPLETED
        assert ended.ended_at is not None
    
    def test_get_all_sessions(self):
        """Get all sessions."""
        dashboard = DashboardManager()
        user = dashboard.create_user("testuser")
        dashboard.login_user(user.user_id)
        dashboard.start_session()
        
        sessions = dashboard.get_all_sessions()
        assert len(sessions) == 1


class TestAlertManagement:
    """Test alert management."""
    
    def test_add_alert(self):
        """Add alert."""
        dashboard = DashboardManager()
        alert = dashboard.add_alert("Test", "Message")
        
        assert alert.title == "Test"
        assert alert.severity == AlertSeverity.INFO
        assert alert.acknowledged is False
    
    def test_add_alert_with_severity(self):
        """Add alert with custom severity."""
        dashboard = DashboardManager()
        alert = dashboard.add_alert(
            "Error", "Something failed", AlertSeverity.ERROR
        )
        
        assert alert.severity == AlertSeverity.ERROR
    
    def test_acknowledge_alert(self):
        """Acknowledge alert."""
        dashboard = DashboardManager()
        alert = dashboard.add_alert("Test", "Message")
        
        result = dashboard.acknowledge_alert(alert.alert_id)
        assert result is True
        
        alerts = dashboard.get_all_alerts()
        assert alerts[0].acknowledged is True
    
    def test_acknowledge_invalid_alert(self):
        """Acknowledge invalid alert fails."""
        dashboard = DashboardManager()
        result = dashboard.acknowledge_alert("INVALID")
        assert result is False
    
    def test_get_unacknowledged_alerts(self):
        """Get unacknowledged alerts."""
        dashboard = DashboardManager()
        a1 = dashboard.add_alert("A1", "M1")
        dashboard.add_alert("A2", "M2")
        dashboard.acknowledge_alert(a1.alert_id)
        
        unacked = dashboard.get_unacknowledged_alerts()
        assert len(unacked) == 1


class TestVoiceToggle:
    """Test voice toggle."""
    
    def test_enable_voice(self):
        """Enable voice."""
        dashboard = DashboardManager()
        result = dashboard.enable_voice()
        assert result is True
        assert dashboard.is_voice_enabled() is True
    
    def test_disable_voice(self):
        """Disable voice."""
        dashboard = DashboardManager()
        dashboard.enable_voice()
        result = dashboard.disable_voice()
        assert result is True
        assert dashboard.is_voice_enabled() is False


class TestStateSnapshot:
    """Test state snapshot."""
    
    def test_get_state(self):
        """Get state snapshot."""
        dashboard = DashboardManager()
        state = dashboard.get_state()
        
        assert state.state_id.startswith("STA-")
        assert state.mode == DashboardMode.READONLY
        assert state.voice_enabled is False
    
    def test_get_overall_progress(self):
        """Get overall progress."""
        dashboard = DashboardManager()
        t1 = dashboard.add_target("H1", "https://a.com")
        t2 = dashboard.add_target("H1", "https://b.com")
        
        dashboard.update_target_progress(t1.target_id, 50, "test")
        dashboard.update_target_progress(t2.target_id, 100, "test")
        
        progress = dashboard.get_overall_progress()
        assert progress == 75  # (50 + 100) / 2
    
    def test_get_overall_progress_empty(self):
        """Overall progress with no targets."""
        dashboard = DashboardManager()
        assert dashboard.get_overall_progress() == 0


class TestActionValidation:
    """Test action validation."""
    
    def test_validate_allowed_actions(self):
        """Validate allowed actions."""
        assert validate_dashboard_action("VIEW") is True
        assert validate_dashboard_action("READ") is True
        assert validate_dashboard_action("DISPLAY") is True
    
    def test_validate_forbidden_actions(self):
        """Validate forbidden actions."""
        assert validate_dashboard_action("EXECUTE") is False
        assert validate_dashboard_action("LAUNCH") is False
        assert validate_dashboard_action("SUBMIT") is False
        assert validate_dashboard_action("CLICK") is False
        assert validate_dashboard_action("AUTOMATE") is False
        assert validate_dashboard_action("APPROVE_EXECUTION") is False
        assert validate_dashboard_action("BYPASS") is False
        assert validate_dashboard_action("MODIFY_EVIDENCE") is False


class TestDataclasses:
    """Test dataclass immutability."""
    
    def test_dashboard_user_frozen(self):
        """DashboardUser is immutable."""
        user = DashboardUser(
            "USR-1", "test", DashboardMode.USER,
            "2026-01-28T00:00:00Z", None, True
        )
        with pytest.raises(Exception):
            user.username = "changed"
    
    def test_target_entry_frozen(self):
        """TargetEntry is immutable."""
        target = TargetEntry(
            "TGT-1", "H1", "https://a.com",
            "PENDING", 0, "2026-01-28T00:00:00Z", "2026-01-28T00:00:00Z"
        )
        with pytest.raises(Exception):
            target.progress_percent = 50
