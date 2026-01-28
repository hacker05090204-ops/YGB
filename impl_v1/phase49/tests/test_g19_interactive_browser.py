# test_g19_interactive_browser.py
"""Tests for G19 Interactive Browser Session."""

import pytest

from impl_v1.phase49.governors.g19_interactive_browser import (
    InteractiveMode,
    SessionState,
    Platform,
    InteractiveSessionRequest,
    InteractiveSession,
    ObservationResult,
    PlatformDetection,
    create_interactive_session,
    get_session,
    update_session_state,
    close_session,
    get_page_title,
    get_current_url,
    get_visible_text,
    detect_platform,
    detect_login_state,
    extract_scope_hints,
    perform_observation,
    can_session_execute,
    can_session_interact,
    can_session_submit,
    can_session_scan,
    clear_sessions,
)


class TestInteractiveMode:
    """Tests for InteractiveMode enum."""
    
    def test_only_observe_only(self):
        assert len(InteractiveMode) == 1
        assert InteractiveMode.OBSERVE_ONLY.value == "OBSERVE_ONLY"


class TestSessionState:
    """Tests for SessionState enum."""
    
    def test_has_idle(self):
        assert SessionState.IDLE.value == "IDLE"
    
    def test_has_browser_ready(self):
        assert SessionState.BROWSER_READY.value == "BROWSER_READY"
    
    def test_has_observing(self):
        assert SessionState.OBSERVING.value == "OBSERVING"
    
    def test_has_closed(self):
        assert SessionState.CLOSED.value == "CLOSED"


class TestPlatform:
    """Tests for Platform enum."""
    
    def test_has_hackerone(self):
        assert Platform.HACKERONE.value == "HACKERONE"
    
    def test_has_bugcrowd(self):
        assert Platform.BUGCROWD.value == "BUGCROWD"


class TestCreateInteractiveSession:
    """Tests for create_interactive_session."""
    
    def setup_method(self):
        clear_sessions()
    
    def test_creates_session(self):
        session = create_interactive_session("device1", "user1")
        assert isinstance(session, InteractiveSession)
    
    def test_session_has_id(self):
        session = create_interactive_session("device1", "user1")
        assert session.session_id.startswith("SES-")
    
    def test_mode_is_observe_only(self):
        session = create_interactive_session("device1", "user1")
        assert session.request.mode == InteractiveMode.OBSERVE_ONLY
    
    def test_initial_state_browser_ready(self):
        session = create_interactive_session("device1", "user1")
        assert session.state == SessionState.BROWSER_READY
    
    def test_can_get_session(self):
        session = create_interactive_session("device1", "user1")
        retrieved = get_session(session.session_id)
        assert retrieved.session_id == session.session_id


class TestUpdateSessionState:
    """Tests for update_session_state."""
    
    def setup_method(self):
        clear_sessions()
    
    def test_updates_state(self):
        session = create_interactive_session("device1", "user1")
        updated = update_session_state(session.session_id, SessionState.OBSERVING)
        assert updated.state == SessionState.OBSERVING
    
    def test_invalid_id_returns_none(self):
        result = update_session_state("INVALID", SessionState.CLOSED)
        assert result is None


class TestCloseSession:
    """Tests for close_session."""
    
    def setup_method(self):
        clear_sessions()
    
    def test_closes_session(self):
        session = create_interactive_session("device1", "user1")
        result = close_session(session.session_id)
        assert result == True
        
        closed = get_session(session.session_id)
        assert closed.state == SessionState.CLOSED


class TestDetectPlatform:
    """Tests for detect_platform."""
    
    def test_detects_hackerone(self):
        result = detect_platform("https://hackerone.com/programs")
        assert result.platform == Platform.HACKERONE
        assert result.confidence >= 0.9
    
    def test_detects_bugcrowd(self):
        result = detect_platform("https://bugcrowd.com/programs")
        assert result.platform == Platform.BUGCROWD
    
    def test_detects_intigriti(self):
        result = detect_platform("https://intigriti.com/programs")
        assert result.platform == Platform.INTIGRITI
    
    def test_unknown_platform(self):
        result = detect_platform("https://example.com")
        assert result.platform == Platform.UNKNOWN


class TestDetectLoginState:
    """Tests for detect_login_state."""
    
    def test_logged_in_dashboard(self):
        result = detect_login_state("Dashboard", "Welcome to dashboard, logout")
        assert result == True
    
    def test_not_logged_in(self):
        result = detect_login_state("Login", "Sign in to continue")
        assert result == False


class TestExtractScopeHints:
    """Tests for extract_scope_hints."""
    
    def test_extracts_wildcards(self):
        hints = extract_scope_hints("Scope: *.example.com and api.test.io")
        assert "*.example.com" in hints
    
    def test_detects_in_scope_section(self):
        hints = extract_scope_hints("In Scope: web application")
        assert "SCOPE_SECTION_DETECTED" in hints
    
    def test_detects_asset_types(self):
        hints = extract_scope_hints("Assets: Web, API, Mobile applications")
        assert "ASSET_TYPE:WEB" in hints or "ASSET_TYPE:API" in hints


class TestPerformObservation:
    """Tests for perform_observation."""
    
    def setup_method(self):
        clear_sessions()
    
    def test_performs_observation(self):
        session = create_interactive_session("device1", "user1")
        mock_data = {
            "title": "HackerOne - Dashboard",
            "url": "https://hackerone.com/programs",
            "text": "Welcome to dashboard. Scope: *.example.com",
        }
        result = perform_observation(session.session_id, _mock_data=mock_data)
        assert isinstance(result, ObservationResult)
    
    def test_observation_detects_platform(self):
        session = create_interactive_session("device1", "user1")
        mock_data = {
            "title": "Bugcrowd",
            "url": "https://bugcrowd.com/test",
            "text": "Dashboard",
        }
        result = perform_observation(session.session_id, _mock_data=mock_data)
        assert result.platform == Platform.BUGCROWD
    
    def test_observation_detects_login(self):
        session = create_interactive_session("device1", "user1")
        mock_data = {
            "title": "My Dashboard",
            "url": "https://hackerone.com",
            "text": "Welcome back. Click logout to exit.",
        }
        result = perform_observation(session.session_id, _mock_data=mock_data)
        assert result.is_logged_in == True


class TestCanSessionExecute:
    """Tests for can_session_execute guard."""
    
    def test_returns_tuple(self):
        result = can_session_execute()
        assert isinstance(result, tuple)
    
    def test_cannot_execute(self):
        can_exec, reason = can_session_execute()
        assert can_exec == False
    
    def test_has_reason(self):
        _, reason = can_session_execute()
        assert "OBSERVE" in reason


class TestCanSessionInteract:
    """Tests for can_session_interact guard."""
    
    def test_cannot_interact(self):
        can_interact, reason = can_session_interact()
        assert can_interact == False
        assert "click" in reason.lower() or "typing" in reason.lower()


class TestCanSessionSubmit:
    """Tests for can_session_submit guard."""
    
    def test_cannot_submit(self):
        can_submit, reason = can_session_submit()
        assert can_submit == False
        assert "submission" in reason.lower() or "forbidden" in reason.lower()


class TestCanSessionScan:
    """Tests for can_session_scan guard."""
    
    def test_cannot_scan(self):
        can_scan, reason = can_session_scan()
        assert can_scan == False
        assert "scanning" in reason.lower() or "forbidden" in reason.lower()
