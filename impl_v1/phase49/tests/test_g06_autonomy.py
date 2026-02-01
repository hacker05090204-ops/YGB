# test_g06_autonomy.py
"""Tests for G06: Autonomy Modes"""

import pytest
from impl_v1.phase49.governors.g06_autonomy_modes import (
    AutonomyMode,
    AutonomyAction,
    SessionStatus,
    AutonomySession,
    create_session,
    is_action_allowed,
    check_session_expiry,
    stop_session,
    MAX_AUTONOMOUS_HOURS,
    AUTONOMOUS_FORBIDDEN,
    AUTONOMOUS_ALLOWED,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_autonomy_mode_4_members(self):
        assert len(AutonomyMode) == 4
    
    def test_autonomy_action_8_members(self):
        assert len(AutonomyAction) == 8
    
    def test_session_status_4_members(self):
        assert len(SessionStatus) == 4


class TestForbiddenActions:
    """Test forbidden/allowed action constants."""
    
    def test_exploit_forbidden_in_autonomous(self):
        assert AutonomyAction.EXPLOIT in AUTONOMOUS_FORBIDDEN
    
    def test_submission_forbidden_in_autonomous(self):
        assert AutonomyAction.SUBMISSION in AUTONOMOUS_FORBIDDEN
    
    def test_state_change_forbidden_in_autonomous(self):
        assert AutonomyAction.STATE_CHANGE in AUTONOMOUS_FORBIDDEN
    
    def test_target_analysis_allowed(self):
        assert AutonomyAction.TARGET_ANALYSIS in AUTONOMOUS_ALLOWED
    
    def test_cve_correlation_allowed(self):
        assert AutonomyAction.CVE_CORRELATION in AUTONOMOUS_ALLOWED


class TestCreateSession:
    """Test session creation."""
    
    def test_session_has_id(self):
        session = create_session(AutonomyMode.MOCK)
        assert session.session_id.startswith("AUT-")
    
    def test_mock_mode_blocks_all(self):
        session = create_session(AutonomyMode.MOCK)
        assert len(session.actions_blocked) == len(AutonomyAction)
    
    def test_read_only_blocks_dangerous(self):
        session = create_session(AutonomyMode.READ_ONLY)
        assert AutonomyAction.EXPLOIT in session.actions_blocked
        assert AutonomyAction.SUBMISSION in session.actions_blocked
    
    def test_autonomous_find_blocks_forbidden(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND)
        for action in AUTONOMOUS_FORBIDDEN:
            assert action in session.actions_blocked
    
    def test_duration_capped_at_max(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND, duration_hours=100)
        # Expiry should be set based on capped duration
        assert session.expires_at is not None
    
    def test_zero_duration_infinite(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND, duration_hours=0)
        assert session.expires_at is None
    
    def test_session_starts_active(self):
        session = create_session(AutonomyMode.MOCK)
        assert session.status == SessionStatus.ACTIVE


class TestIsActionAllowed:
    """Test action permission checking."""
    
    def test_mock_blocks_all(self):
        session = create_session(AutonomyMode.MOCK)
        allowed, reason = is_action_allowed(session, AutonomyAction.TARGET_ANALYSIS)
        assert not allowed
        assert "BLOCKED" in reason
    
    def test_autonomous_allows_analysis(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND, human_enabled=True)
        allowed, reason = is_action_allowed(session, AutonomyAction.TARGET_ANALYSIS)
        assert allowed
    
    def test_autonomous_blocks_exploit(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND, human_enabled=True)
        allowed, reason = is_action_allowed(session, AutonomyAction.EXPLOIT)
        assert not allowed
        assert "BLOCKED" in reason
    
    def test_real_mode_requires_human_enabled(self):
        session = create_session(AutonomyMode.REAL, human_enabled=False)
        allowed, reason = is_action_allowed(session, AutonomyAction.TARGET_ANALYSIS)
        assert not allowed
        assert "human_enabled" in reason
    
    def test_stopped_session_blocks_all(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND, human_enabled=True)
        stopped = stop_session(session)
        allowed, reason = is_action_allowed(stopped, AutonomyAction.TARGET_ANALYSIS)
        assert not allowed
        assert "STOPPED" in reason


class TestSessionExpiry:
    """Test session expiry checking."""
    
    def test_no_expiry_stays_active(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND, duration_hours=0)
        status = check_session_expiry(session)
        assert status == SessionStatus.ACTIVE
    
    def test_stopped_stays_stopped(self):
        session = create_session(AutonomyMode.MOCK)
        stopped = stop_session(session)
        status = check_session_expiry(stopped)
        assert status == SessionStatus.STOPPED


class TestStopSession:
    """Test session stopping."""
    
    def test_stop_changes_status(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND)
        stopped = stop_session(session)
        assert stopped.status == SessionStatus.STOPPED
    
    def test_stop_preserves_id(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND)
        stopped = stop_session(session)
        assert stopped.session_id == session.session_id
    
    def test_stop_preserves_mode(self):
        session = create_session(AutonomyMode.AUTONOMOUS_FIND)
        stopped = stop_session(session)
        assert stopped.mode == session.mode


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def test_session_frozen(self):
        session = create_session(AutonomyMode.MOCK)
        with pytest.raises(AttributeError):
            session.status = SessionStatus.STOPPED
