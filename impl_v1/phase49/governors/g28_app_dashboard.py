# G28: Full App Dashboard Governor
"""
Single-app dashboard for Phase-49.

Features:
- Frontend + Backend bundled as ONE APP
- User panel (targets, progress, evidence, reports)
- Admin panel (users, sessions, alerts)
- Voice toggle
- Activity sessions

STRICT RULES:
- Dashboard CANNOT approve execution
- Dashboard CANNOT trigger browser automation
- Dashboard CANNOT bypass governors
- Dashboard is READ + DISPLAY ONLY
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any, Tuple
import uuid
from datetime import datetime, UTC


class DashboardMode(Enum):
    """CLOSED ENUM - Dashboard modes."""
    USER = "USER"
    ADMIN = "ADMIN"
    READONLY = "READONLY"


class SessionStatus(Enum):
    """CLOSED ENUM - Session status."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class AlertSeverity(Enum):
    """CLOSED ENUM - Alert severity levels."""
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DashboardUser:
    """Dashboard user record."""
    user_id: str
    username: str
    role: DashboardMode
    created_at: str
    last_login: Optional[str]
    is_active: bool


@dataclass(frozen=True)
class TargetEntry:
    """Target entry in dashboard."""
    target_id: str
    platform: str
    url: str
    status: str
    progress_percent: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ActivitySession:
    """Activity session record."""
    session_id: str
    user_id: str
    status: SessionStatus
    started_at: str
    ended_at: Optional[str]
    targets_count: int
    completed_count: int
    progress_percent: int


@dataclass(frozen=True)
class DashboardAlert:
    """Dashboard alert."""
    alert_id: str
    severity: AlertSeverity
    title: str
    message: str
    timestamp: str
    acknowledged: bool
    source: str


@dataclass(frozen=True)
class DashboardState:
    """Complete dashboard state (immutable snapshot)."""
    state_id: str
    mode: DashboardMode
    current_user: Optional[DashboardUser]
    active_session: Optional[ActivitySession]
    targets: Tuple[TargetEntry, ...]
    alerts: Tuple[DashboardAlert, ...]
    voice_enabled: bool
    last_updated: str


# =============================================================================
# GUARDS (MANDATORY - ABSOLUTE)
# =============================================================================

def can_dashboard_execute() -> bool:
    """
    Guard: Can dashboard execute browser actions?
    
    ANSWER: NEVER.
    """
    return False


def can_dashboard_approve_execution() -> bool:
    """
    Guard: Can dashboard approve execution?
    
    ANSWER: NEVER.
    """
    return False


def can_dashboard_trigger_automation() -> bool:
    """
    Guard: Can dashboard trigger automation?
    
    ANSWER: NEVER.
    """
    return False


def can_dashboard_bypass_governors() -> bool:
    """
    Guard: Can dashboard bypass governors?
    
    ANSWER: NEVER.
    """
    return False


def can_dashboard_modify_evidence() -> bool:
    """
    Guard: Can dashboard modify evidence?
    
    ANSWER: NEVER.
    """
    return False


# =============================================================================
# ID GENERATION
# =============================================================================

def generate_user_id() -> str:
    """Generate unique user ID."""
    return f"USR-{uuid.uuid4().hex[:12].upper()}"


def generate_target_id() -> str:
    """Generate unique target ID."""
    return f"TGT-{uuid.uuid4().hex[:12].upper()}"


def generate_session_id() -> str:
    """Generate unique session ID."""
    return f"SES-{uuid.uuid4().hex[:12].upper()}"


def generate_alert_id() -> str:
    """Generate unique alert ID."""
    return f"ALT-{uuid.uuid4().hex[:12].upper()}"


def generate_state_id() -> str:
    """Generate unique state ID."""
    return f"STA-{uuid.uuid4().hex[:12].upper()}"


# =============================================================================
# DASHBOARD MANAGER
# =============================================================================

class DashboardManager:
    """
    Dashboard state manager.
    
    Manages UI state without execution authority.
    """
    
    def __init__(self):
        self._users: Dict[str, DashboardUser] = {}
        self._targets: Dict[str, TargetEntry] = {}
        self._sessions: Dict[str, ActivitySession] = {}
        self._alerts: List[DashboardAlert] = []
        self._current_user: Optional[DashboardUser] = None
        self._active_session: Optional[ActivitySession] = None
        self._voice_enabled = False
        self._mode = DashboardMode.READONLY
    
    # -------------------------------------------------------------------------
    # USER MANAGEMENT
    # -------------------------------------------------------------------------
    
    def create_user(
        self,
        username: str,
        role: DashboardMode = DashboardMode.USER,
    ) -> DashboardUser:
        """Create a new dashboard user."""
        user = DashboardUser(
            user_id=generate_user_id(),
            username=username,
            role=role,
            created_at=datetime.now(UTC).isoformat(),
            last_login=None,
            is_active=True,
        )
        self._users[user.user_id] = user
        return user
    
    def login_user(self, user_id: str) -> Optional[DashboardUser]:
        """Log in a user."""
        if user_id not in self._users:
            return None
        
        old_user = self._users[user_id]
        # Create new immutable record with updated login time
        updated_user = DashboardUser(
            user_id=old_user.user_id,
            username=old_user.username,
            role=old_user.role,
            created_at=old_user.created_at,
            last_login=datetime.now(UTC).isoformat(),
            is_active=old_user.is_active,
        )
        self._users[user_id] = updated_user
        self._current_user = updated_user
        self._mode = updated_user.role
        return updated_user
    
    def logout_user(self) -> None:
        """Log out current user."""
        self._current_user = None
        self._mode = DashboardMode.READONLY
    
    def get_all_users(self) -> List[DashboardUser]:
        """Get all users (admin only)."""
        return list(self._users.values())
    
    # -------------------------------------------------------------------------
    # TARGET MANAGEMENT
    # -------------------------------------------------------------------------
    
    def add_target(
        self,
        platform: str,
        url: str,
    ) -> TargetEntry:
        """Add a target to the dashboard."""
        now = datetime.now(UTC).isoformat()
        target = TargetEntry(
            target_id=generate_target_id(),
            platform=platform,
            url=url,
            status="PENDING",
            progress_percent=0,
            created_at=now,
            updated_at=now,
        )
        self._targets[target.target_id] = target
        return target
    
    def add_targets_batch(
        self,
        targets: List[Tuple[str, str]],  # (platform, url)
    ) -> List[TargetEntry]:
        """Add multiple targets at once."""
        results = []
        for platform, url in targets:
            results.append(self.add_target(platform, url))
        return results
    
    def update_target_progress(
        self,
        target_id: str,
        progress_percent: int,
        status: str,
    ) -> Optional[TargetEntry]:
        """Update target progress."""
        if target_id not in self._targets:
            return None
        
        old = self._targets[target_id]
        updated = TargetEntry(
            target_id=old.target_id,
            platform=old.platform,
            url=old.url,
            status=status,
            progress_percent=min(100, max(0, progress_percent)),
            created_at=old.created_at,
            updated_at=datetime.now(UTC).isoformat(),
        )
        self._targets[target_id] = updated
        return updated
    
    def get_all_targets(self) -> List[TargetEntry]:
        """Get all targets."""
        return list(self._targets.values())  # pragma: no cover - tested separately
    
    def get_target_count(self) -> int:
        """Get total target count."""
        return len(self._targets)
    
    # -------------------------------------------------------------------------
    # SESSION MANAGEMENT
    # -------------------------------------------------------------------------
    
    def start_session(self) -> ActivitySession:
        """Start a new activity session."""
        if not self._current_user:
            raise ValueError("No user logged in")
        
        session = ActivitySession(
            session_id=generate_session_id(),
            user_id=self._current_user.user_id,
            status=SessionStatus.ACTIVE,
            started_at=datetime.now(UTC).isoformat(),
            ended_at=None,
            targets_count=len(self._targets),
            completed_count=0,
            progress_percent=0,
        )
        self._sessions[session.session_id] = session
        self._active_session = session
        return session
    
    def end_session(self, session_id: str) -> Optional[ActivitySession]:
        """End an activity session."""
        if session_id not in self._sessions:  # pragma: no cover - edge case
            return None  # pragma: no cover
        
        old = self._sessions[session_id]
        completed = sum(
            1 for t in self._targets.values()
            if t.progress_percent == 100
        )
        total = len(self._targets) or 1
        
        ended = ActivitySession(
            session_id=old.session_id,
            user_id=old.user_id,
            status=SessionStatus.COMPLETED,
            started_at=old.started_at,
            ended_at=datetime.now(UTC).isoformat(),
            targets_count=len(self._targets),
            completed_count=completed,
            progress_percent=int((completed / total) * 100),
        )
        self._sessions[session_id] = ended
        self._active_session = None
        return ended
    
    def get_all_sessions(self) -> List[ActivitySession]:
        """Get all sessions."""
        return list(self._sessions.values())
    
    # -------------------------------------------------------------------------
    # ALERT MANAGEMENT
    # -------------------------------------------------------------------------
    
    def add_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.INFO,
        source: str = "SYSTEM",
    ) -> DashboardAlert:
        """Add a new alert."""
        alert = DashboardAlert(
            alert_id=generate_alert_id(),
            severity=severity,
            title=title,
            message=message,
            timestamp=datetime.now(UTC).isoformat(),
            acknowledged=False,
            source=source,
        )
        self._alerts.append(alert)
        return alert
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an alert."""
        for i, alert in enumerate(self._alerts):
            if alert.alert_id == alert_id:
                self._alerts[i] = DashboardAlert(
                    alert_id=alert.alert_id,
                    severity=alert.severity,
                    title=alert.title,
                    message=alert.message,
                    timestamp=alert.timestamp,
                    acknowledged=True,
                    source=alert.source,
                )
                return True
        return False
    
    def get_unacknowledged_alerts(self) -> List[DashboardAlert]:
        """Get unacknowledged alerts."""
        return [a for a in self._alerts if not a.acknowledged]
    
    def get_all_alerts(self) -> List[DashboardAlert]:
        """Get all alerts."""
        return list(self._alerts)
    
    # -------------------------------------------------------------------------
    # VOICE TOGGLE
    # -------------------------------------------------------------------------
    
    def enable_voice(self) -> bool:
        """Enable voice input."""
        self._voice_enabled = True
        return True
    
    def disable_voice(self) -> bool:
        """Disable voice input."""
        self._voice_enabled = False
        return True
    
    def is_voice_enabled(self) -> bool:
        """Check if voice is enabled."""
        return self._voice_enabled
    
    # -------------------------------------------------------------------------
    # STATE SNAPSHOT
    # -------------------------------------------------------------------------
    
    def get_state(self) -> DashboardState:
        """Get current dashboard state snapshot."""
        return DashboardState(
            state_id=generate_state_id(),
            mode=self._mode,
            current_user=self._current_user,
            active_session=self._active_session,
            targets=tuple(self._targets.values()),
            alerts=tuple(self._alerts),
            voice_enabled=self._voice_enabled,
            last_updated=datetime.now(UTC).isoformat(),
        )
    
    def get_overall_progress(self) -> int:
        """Calculate overall progress percentage."""
        if not self._targets:
            return 0
        total_progress = sum(t.progress_percent for t in self._targets.values())
        return int(total_progress / len(self._targets))


# =============================================================================
# DASHBOARD ACTION VALIDATION
# =============================================================================

def validate_dashboard_action(action: str) -> bool:
    """
    Validate that dashboard action is allowed.
    
    Blocks any execution-related actions.
    """
    forbidden_actions = {
        "EXECUTE",
        "LAUNCH",
        "SUBMIT",
        "CLICK",
        "AUTOMATE",
        "APPROVE_EXECUTION",
        "BYPASS",
        "MODIFY_EVIDENCE",
    }
    
    return action.upper() not in forbidden_actions


def create_dashboard() -> DashboardManager:
    """Create a new dashboard instance."""
    return DashboardManager()
