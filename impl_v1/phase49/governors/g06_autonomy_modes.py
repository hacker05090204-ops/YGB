# G06: Autonomy Modes
"""
Autonomy and interaction mode management.

MODES:
1. READ_ONLY (default) - Analysis only
2. AUTONOMOUS_FIND - Timed discovery
3. REAL - Human explicit enable required

AUTONOMOUS_FIND RULES:
- Hours selectable (0 = infinite until STOP)
- Max 12 hours by default
- Allowed: target analysis, CVE correlation, draft reports
- FORBIDDEN: exploits, submissions, state changes
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
import uuid
from datetime import datetime, timedelta, UTC


class AutonomyMode(Enum):
    """CLOSED ENUM - 3 modes (MOCK removed)"""
    READ_ONLY = "READ_ONLY"            # Analysis only (default)
    AUTONOMOUS_FIND = "AUTONOMOUS_FIND"  # Timed discovery
    REAL = "REAL"                      # Full execution (human enabled)


class AutonomyAction(Enum):
    """CLOSED ENUM - 8 actions"""
    TARGET_ANALYSIS = "TARGET_ANALYSIS"
    CVE_CORRELATION = "CVE_CORRELATION"
    PASSIVE_DISCOVERY = "PASSIVE_DISCOVERY"
    DRAFT_REPORT = "DRAFT_REPORT"
    EXPLOIT = "EXPLOIT"              # FORBIDDEN in AUTONOMOUS_FIND
    SUBMISSION = "SUBMISSION"         # FORBIDDEN in AUTONOMOUS_FIND
    STATE_CHANGE = "STATE_CHANGE"     # FORBIDDEN in AUTONOMOUS_FIND
    BROWSER_ACTION = "BROWSER_ACTION"  # FORBIDDEN in AUTONOMOUS_FIND


class SessionStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    EXPIRED = "EXPIRED"
    STOPPED = "STOPPED"


# Forbidden actions in AUTONOMOUS_FIND mode
AUTONOMOUS_FORBIDDEN = {
    AutonomyAction.EXPLOIT,
    AutonomyAction.SUBMISSION,
    AutonomyAction.STATE_CHANGE,
    AutonomyAction.BROWSER_ACTION,
}

# Allowed actions in AUTONOMOUS_FIND mode
AUTONOMOUS_ALLOWED = {
    AutonomyAction.TARGET_ANALYSIS,
    AutonomyAction.CVE_CORRELATION,
    AutonomyAction.PASSIVE_DISCOVERY,
    AutonomyAction.DRAFT_REPORT,
}

MAX_AUTONOMOUS_HOURS = 12


@dataclass(frozen=True)
class AutonomySession:
    """Autonomy session state."""
    session_id: str
    mode: AutonomyMode
    status: SessionStatus
    duration_hours: float  # 0 = infinite
    started_at: str
    expires_at: Optional[str]
    human_enabled: bool
    actions_blocked: tuple  # Tuple of AutonomyAction


def create_session(
    mode: AutonomyMode,
    duration_hours: float = 0.0,
    human_enabled: bool = False,
) -> AutonomySession:
    """Create an autonomy session."""
    now = datetime.now(UTC)
    
    # Calculate expiry
    expires_at = None
    if duration_hours > 0:
        # Cap at max hours
        capped_hours = min(duration_hours, MAX_AUTONOMOUS_HOURS)
        expires = now + timedelta(hours=capped_hours)
        expires_at = expires.isoformat()
    
    # Determine blocked actions
    blocked = tuple()
    if mode == AutonomyMode.AUTONOMOUS_FIND:
        blocked = tuple(AUTONOMOUS_FORBIDDEN)
    elif mode == AutonomyMode.READ_ONLY:
        # Only analysis allowed
        blocked = tuple([
            AutonomyAction.EXPLOIT,
            AutonomyAction.SUBMISSION,
            AutonomyAction.STATE_CHANGE,
            AutonomyAction.BROWSER_ACTION,
        ])
    
    return AutonomySession(
        session_id=f"AUT-{uuid.uuid4().hex[:16].upper()}",
        mode=mode,
        status=SessionStatus.ACTIVE,
        duration_hours=duration_hours,
        started_at=now.isoformat(),
        expires_at=expires_at,
        human_enabled=human_enabled,
        actions_blocked=blocked,
    )


def is_action_allowed(session: AutonomySession, action: AutonomyAction) -> tuple:
    """Check if action is allowed in current session. Returns (allowed, reason)."""
    if session.status != SessionStatus.ACTIVE:
        return False, f"Session is {session.status.value}"
    
    if action in session.actions_blocked:
        return False, f"Action {action.value} is BLOCKED in {session.mode.value} mode"
    
    # REAL mode requires human_enabled
    if session.mode == AutonomyMode.REAL and not session.human_enabled:
        return False, "REAL mode requires human_enabled=True"
    
    return True, "Action allowed"


def check_session_expiry(session: AutonomySession) -> SessionStatus:
    """Check if session has expired."""
    if session.status != SessionStatus.ACTIVE:
        return session.status
    
    if session.expires_at is None:
        return SessionStatus.ACTIVE
    
    expires = datetime.fromisoformat(session.expires_at.replace('Z', '+00:00'))
    if datetime.now(UTC) >= expires:
        return SessionStatus.EXPIRED
    
    return SessionStatus.ACTIVE


def stop_session(session: AutonomySession) -> AutonomySession:
    """Stop an autonomy session."""
    return AutonomySession(
        session_id=session.session_id,
        mode=session.mode,
        status=SessionStatus.STOPPED,
        duration_hours=session.duration_hours,
        started_at=session.started_at,
        expires_at=session.expires_at,
        human_enabled=session.human_enabled,
        actions_blocked=session.actions_blocked,
    )
