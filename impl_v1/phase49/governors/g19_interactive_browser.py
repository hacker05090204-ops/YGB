# G19: Interactive Browser Session (OBSERVE-ONLY Mode)
"""
Interactive browser session for manual login and assisted observation.

MODE: INTERACTIVE_ASSISTANT_MODE

ALLOWED (READ-ONLY):
✓ Page title extraction
✓ URL extraction
✓ Visible text extraction
✓ Platform detection
✓ Login detection
✓ Scope extraction

FORBIDDEN:
✗ Clicking by bot
✗ Typing by bot
✗ Submitting by bot
✗ Network scanning
✗ Auto execution

Python DECIDES. C/C++ EXECUTES only after approval.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
import uuid
from datetime import datetime, UTC


class InteractiveMode(Enum):
    """CLOSED ENUM - Only OBSERVE_ONLY allowed"""
    OBSERVE_ONLY = "OBSERVE_ONLY"


class SessionState(Enum):
    """CLOSED ENUM - 4 states"""
    IDLE = "IDLE"
    BROWSER_READY = "BROWSER_READY"
    OBSERVING = "OBSERVING"
    CLOSED = "CLOSED"


class Platform(Enum):
    """CLOSED ENUM - Detected platforms"""
    HACKERONE = "HACKERONE"
    BUGCROWD = "BUGCROWD"
    INTIGRITI = "INTIGRITI"
    SYNACK = "SYNACK"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class InteractiveSessionRequest:
    """Request to create an interactive session."""
    request_id: str
    device_id: str
    user_id: str
    initial_url: Optional[str]  # None = blank tab
    mode: InteractiveMode
    timestamp: str


@dataclass(frozen=True)
class InteractiveSession:
    """Active interactive browser session."""
    session_id: str
    request: InteractiveSessionRequest
    state: SessionState
    browser_pid: Optional[int]  # C++ native process
    created_at: str


@dataclass(frozen=True)
class ObservationResult:
    """Read-only observation data from browser."""
    observation_id: str
    session_id: str
    page_title: Optional[str]
    page_url: Optional[str]
    visible_text: Optional[str]
    platform: Platform
    is_logged_in: bool
    scope_hints: tuple  # Tuple[str, ...]
    timestamp: str


@dataclass(frozen=True)
class PlatformDetection:
    """Detected platform information."""
    platform: Platform
    confidence: float
    program_name: Optional[str]
    program_url: Optional[str]


# In-memory session store
_sessions: Dict[str, InteractiveSession] = {}
_observations: Dict[str, ObservationResult] = {}


def clear_sessions():
    """Clear all sessions (for testing)."""
    _sessions.clear()
    _observations.clear()


def create_interactive_session(
    device_id: str,
    user_id: str,
    initial_url: Optional[str] = None,
) -> InteractiveSession:
    """
    Create an interactive browser session in OBSERVE_ONLY mode.
    
    The browser opens automatically but NO automation is performed.
    User must interact manually.
    """
    request_id = f"REQ-{uuid.uuid4().hex[:16].upper()}"
    session_id = f"SES-{uuid.uuid4().hex[:16].upper()}"
    
    request = InteractiveSessionRequest(
        request_id=request_id,
        device_id=device_id,
        user_id=user_id,
        initial_url=initial_url,
        mode=InteractiveMode.OBSERVE_ONLY,  # ALWAYS observe only
        timestamp=datetime.now(UTC).isoformat(),
    )
    
    session = InteractiveSession(
        session_id=session_id,
        request=request,
        state=SessionState.BROWSER_READY,
        browser_pid=None,  # Set by C++ native
        created_at=datetime.now(UTC).isoformat(),
    )
    
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> Optional[InteractiveSession]:
    """Get session by ID."""
    return _sessions.get(session_id)


def update_session_state(
    session_id: str,
    new_state: SessionState,
) -> Optional[InteractiveSession]:
    """Update session state."""
    if session_id not in _sessions:
        return None
    
    old_session = _sessions[session_id]
    
    # Create new session with updated state
    new_session = InteractiveSession(
        session_id=old_session.session_id,
        request=old_session.request,
        state=new_state,
        browser_pid=old_session.browser_pid,
        created_at=old_session.created_at,
    )
    
    _sessions[session_id] = new_session
    return new_session


def close_session(session_id: str) -> bool:
    """Close an interactive session."""
    if session_id not in _sessions:
        return False
    
    update_session_state(session_id, SessionState.CLOSED)
    return True


# ============================================================
# READ-ONLY OBSERVATION FUNCTIONS
# ============================================================

def get_page_title(
    session_id: str,
    _native_title: Optional[str] = None,
) -> Optional[str]:
    """
    Extract page title (READ-ONLY).

    In production: C++ native reads from browser.
    Pass _native_title when integrating with C++ backend.
    """
    session = get_session(session_id)
    if not session or session.state == SessionState.CLOSED:
        return None

    if _native_title is not None:
        return _native_title

    # C++ native provides this via integration bridge
    return None


def get_current_url(
    session_id: str,
    _native_url: Optional[str] = None,
) -> Optional[str]:
    """
    Extract current URL (READ-ONLY).

    In production: C++ native reads from browser.
    Pass _native_url when integrating with C++ backend.
    """
    session = get_session(session_id)
    if not session or session.state == SessionState.CLOSED:
        return None

    if _native_url is not None:
        return _native_url

    # C++ native provides this via integration bridge
    return None


def get_visible_text(
    session_id: str,
    _native_text: Optional[str] = None,
) -> Optional[str]:
    """
    Extract visible text (READ-ONLY).

    In production: C++ native reads from browser DOM.
    Pass _native_text when integrating with C++ backend.
    """
    session = get_session(session_id)
    if not session or session.state == SessionState.CLOSED:
        return None

    if _native_text is not None:
        return _native_text

    return None


def detect_platform(
    url: str,
    page_title: Optional[str] = None,
) -> PlatformDetection:
    """
    Detect bug bounty platform from URL and title.
    
    This is pure Python logic - no execution.
    """
    url_lower = url.lower()
    title_lower = (page_title or "").lower()
    
    if "hackerone.com" in url_lower:
        return PlatformDetection(
            platform=Platform.HACKERONE,
            confidence=0.95,
            program_name=None,
            program_url=url,
        )
    elif "bugcrowd.com" in url_lower:
        return PlatformDetection(
            platform=Platform.BUGCROWD,
            confidence=0.95,
            program_name=None,
            program_url=url,
        )
    elif "intigriti.com" in url_lower:
        return PlatformDetection(
            platform=Platform.INTIGRITI,
            confidence=0.95,
            program_name=None,
            program_url=url,
        )
    elif "synack" in url_lower or "synack" in title_lower:
        return PlatformDetection(
            platform=Platform.SYNACK,
            confidence=0.85,
            program_name=None,
            program_url=url,
        )
    
    return PlatformDetection(
        platform=Platform.UNKNOWN,
        confidence=0.0,
        program_name=None,
        program_url=url,
    )


def detect_login_state(
    page_title: str,
    visible_text: str,
) -> bool:
    """
    Detect if user is logged in (heuristic).
    
    Pure Python logic - no execution.
    """
    text_lower = visible_text.lower()
    title_lower = page_title.lower()
    
    # Login indicators
    logged_in_keywords = [
        "dashboard",
        "my programs",
        "submissions",
        "profile",
        "logout",
        "sign out",
    ]
    
    # Not logged in indicators
    not_logged_in_keywords = [
        "sign in",
        "log in",
        "create account",
        "register",
    ]
    
    for keyword in logged_in_keywords:
        if keyword in text_lower or keyword in title_lower:
            return True
    
    for keyword in not_logged_in_keywords:
        if keyword in text_lower or keyword in title_lower:
            return False
    
    return False


def extract_scope_hints(
    visible_text: str,
) -> tuple:
    """
    Extract scope hints from visible page text.
    
    Looks for common patterns like *.example.com, api.*, etc.
    Pure Python logic - no execution.
    """
    import re
    
    hints = []
    
    # Wildcard domains
    wildcard_pattern = r'\*\.[a-zA-Z0-9\-\.]+\.[a-zA-Z]{2,}'
    matches = re.findall(wildcard_pattern, visible_text)
    hints.extend(matches)
    
    # In-scope / out-of-scope sections
    if "in scope" in visible_text.lower():
        hints.append("SCOPE_SECTION_DETECTED")
    
    if "out of scope" in visible_text.lower():
        hints.append("OUT_OF_SCOPE_SECTION_DETECTED")
    
    # Asset types
    asset_keywords = ["web", "api", "mobile", "android", "ios"]
    for keyword in asset_keywords:
        if keyword in visible_text.lower():
            hints.append(f"ASSET_TYPE:{keyword.upper()}")
    
    return tuple(set(hints))


def perform_observation(
    session_id: str,
    _native_data: Optional[Dict] = None,
) -> Optional[ObservationResult]:
    """
    Perform a complete read-only observation.

    Combines: title, URL, text, platform, login, scope.
    All data is READ-ONLY.

    Args:
        session_id: Active session ID.
        _native_data: Data from C++ native browser integration.
    """
    session = get_session(session_id)
    if not session or session.state == SessionState.CLOSED:
        return None

    # Update state to OBSERVING
    update_session_state(session_id, SessionState.OBSERVING)

    # Get data from C++ native integration
    if _native_data:
        title = _native_data.get("title", "")
        url = _native_data.get("url", "")
        text = _native_data.get("text", "")
    else:
        title = get_page_title(session_id)
        url = get_current_url(session_id)
        text = get_visible_text(session_id)
    
    # Detect platform
    platform_detection = detect_platform(url or "", title)
    
    # Detect login
    is_logged_in = detect_login_state(title or "", text or "")
    
    # Extract scope hints
    scope_hints = extract_scope_hints(text or "")
    
    observation = ObservationResult(
        observation_id=f"OBS-{uuid.uuid4().hex[:16].upper()}",
        session_id=session_id,
        page_title=title,
        page_url=url,
        visible_text=text[:500] if text else None,  # Truncate
        platform=platform_detection.platform,
        is_logged_in=is_logged_in,
        scope_hints=scope_hints,
        timestamp=datetime.now(UTC).isoformat(),
    )
    
    _observations[observation.observation_id] = observation
    return observation


def get_observation(observation_id: str) -> Optional[ObservationResult]:
    """Get observation by ID."""
    return _observations.get(observation_id)


# ============================================================
# CRITICAL SECURITY GUARDS
# ============================================================

def can_session_execute() -> tuple:
    """
    Check if session can trigger execution.
    
    Returns (can_execute, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Interactive session is OBSERVE ONLY - cannot trigger execution"


def can_session_interact() -> tuple:
    """
    Check if session can interact with browser.
    
    Returns (can_interact, reason).
    ALWAYS returns (False, ...).
    """
    return False, "No clicking, typing, or submission allowed - OBSERVE ONLY mode"


def can_session_submit() -> tuple:
    """
    Check if session can submit forms.
    
    Returns (can_submit, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Form submission is FORBIDDEN in interactive mode"


def can_session_scan() -> tuple:
    """
    Check if session can perform network scanning.
    
    Returns (can_scan, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Network scanning is FORBIDDEN in interactive mode"
