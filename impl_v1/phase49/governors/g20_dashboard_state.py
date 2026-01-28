# G20: Dashboard State & Events
"""
Unified dashboard state management for the integrated app.

PANELS:
1) User Panel - name, bounty, target, scope, progress, mode
2) Admin Panel - users, sessions, logs, alerts, risks
3) Activity Session - targets, platform, scope, quantity selector
4) Report Session - drafts, progress, voice, suggestions

ALL data routed through G13 Dashboard Router.
Dashboard CANNOT approve execution directly.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
import uuid
from datetime import datetime, UTC


class DashboardPanel(Enum):
    """CLOSED ENUM - Dashboard panels"""
    USER = "USER"
    ADMIN = "ADMIN"
    ACTIVITY = "ACTIVITY"
    REPORT = "REPORT"


class UserMode(Enum):
    """CLOSED ENUM - User operation modes"""
    MANUAL = "MANUAL"
    ASSISTED = "ASSISTED"  # Voice + suggestions
    # Note: No AUTONOMOUS mode - human always in control


class ActivityType(Enum):
    """CLOSED ENUM - Activity types"""
    TARGET_DISCOVERED = "TARGET_DISCOVERED"
    PLATFORM_DETECTED = "PLATFORM_DETECTED"
    SCOPE_EXTRACTED = "SCOPE_EXTRACTED"
    REPORT_STARTED = "REPORT_STARTED"
    REPORT_PROGRESS = "REPORT_PROGRESS"
    VOICE_COMMAND = "VOICE_COMMAND"


class AlertLevel(Enum):
    """CLOSED ENUM - Alert levels"""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class UserPanelState:
    """State for User Panel."""
    user_id: str
    user_name: str
    email: Optional[str]
    bounty_count: int
    total_earnings: float
    current_target: Optional[str]
    current_scope: Optional[str]
    progress_percent: int  # 0-100
    mode: UserMode
    is_authenticated: bool
    last_updated: str


@dataclass(frozen=True)
class AdminPanelState:
    """State for Admin Panel."""
    admin_id: str
    total_users: int
    active_sessions: int
    pending_approvals: int
    recent_alerts: tuple  # Tuple[AlertEntry, ...]
    risk_flags: tuple  # Tuple[str, ...]
    last_updated: str


@dataclass(frozen=True)
class AlertEntry:
    """Alert entry for admin panel."""
    alert_id: str
    level: AlertLevel
    message: str
    source: str
    timestamp: str


@dataclass(frozen=True)
class TargetEntry:
    """Target entry for activity session."""
    target_id: str
    domain: str
    platform: str
    report_count: int
    report_density_percent: float
    payout_range: str
    is_selected: bool


@dataclass(frozen=True)
class ActivitySessionState:
    """State for Activity Session."""
    session_id: str
    platform_detected: Optional[str]
    scope_extracted: Optional[str]
    suggested_targets: tuple  # Tuple[TargetEntry, ...]
    quantity_selected: int  # e.g., 5, 8, 10
    human_approved: bool
    last_updated: str


@dataclass(frozen=True)
class ReportDraft:
    """Report draft entry."""
    draft_id: str
    target: str
    bug_type: str
    severity: str
    progress_percent: int
    voice_explanation: Optional[str]
    payout_suggestions: tuple  # Tuple[str, ...]
    created_at: str


@dataclass(frozen=True)
class ReportSessionState:
    """State for Report Session."""
    session_id: str
    drafts: tuple  # Tuple[ReportDraft, ...]
    current_draft_id: Optional[str]
    overall_progress: int
    last_voice_message: Optional[str]
    last_updated: str


@dataclass(frozen=True)
class DashboardState:
    """Complete dashboard state."""
    dashboard_id: str
    user_panel: Optional[UserPanelState]
    admin_panel: Optional[AdminPanelState]
    activity_session: Optional[ActivitySessionState]
    report_session: Optional[ReportSessionState]
    active_panel: DashboardPanel
    last_updated: str


@dataclass(frozen=True)
class DashboardEvent:
    """Event triggered in dashboard."""
    event_id: str
    event_type: ActivityType
    source_panel: DashboardPanel
    payload: Dict
    timestamp: str


# In-memory state store
_dashboard_states: Dict[str, DashboardState] = {}
_events: List[DashboardEvent] = []


def clear_dashboard_state():
    """Clear all state (for testing)."""
    _dashboard_states.clear()
    _events.clear()


def create_dashboard_state(
    user_id: str,
    user_name: str,
    is_admin: bool = False,
) -> DashboardState:
    """Create initial dashboard state."""
    dashboard_id = f"DASH-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(UTC).isoformat()
    
    user_panel = UserPanelState(
        user_id=user_id,
        user_name=user_name,
        email=None,
        bounty_count=0,
        total_earnings=0.0,
        current_target=None,
        current_scope=None,
        progress_percent=0,
        mode=UserMode.MANUAL,
        is_authenticated=True,
        last_updated=now,
    )
    
    admin_panel = None
    if is_admin:
        admin_panel = AdminPanelState(
            admin_id=f"ADM-{uuid.uuid4().hex[:8].upper()}",
            total_users=0,
            active_sessions=0,
            pending_approvals=0,
            recent_alerts=tuple(),
            risk_flags=tuple(),
            last_updated=now,
        )
    
    activity_session = ActivitySessionState(
        session_id=f"ACT-{uuid.uuid4().hex[:8].upper()}",
        platform_detected=None,
        scope_extracted=None,
        suggested_targets=tuple(),
        quantity_selected=5,  # Default
        human_approved=False,
        last_updated=now,
    )
    
    report_session = ReportSessionState(
        session_id=f"RPT-{uuid.uuid4().hex[:8].upper()}",
        drafts=tuple(),
        current_draft_id=None,
        overall_progress=0,
        last_voice_message=None,
        last_updated=now,
    )
    
    dashboard = DashboardState(
        dashboard_id=dashboard_id,
        user_panel=user_panel,
        admin_panel=admin_panel,
        activity_session=activity_session,
        report_session=report_session,
        active_panel=DashboardPanel.USER,
        last_updated=now,
    )
    
    _dashboard_states[dashboard_id] = dashboard
    return dashboard


def get_dashboard(dashboard_id: str) -> Optional[DashboardState]:
    """Get dashboard state by ID."""
    return _dashboard_states.get(dashboard_id)


def update_activity_with_targets(
    dashboard_id: str,
    platform: str,
    scope: str,
    targets: List[Dict],
) -> Optional[DashboardState]:
    """Update activity session with discovered targets."""
    dashboard = get_dashboard(dashboard_id)
    if not dashboard:
        return None
    
    now = datetime.now(UTC).isoformat()
    
    # Convert target dicts to TargetEntry
    target_entries = []
    for t in targets:
        entry = TargetEntry(
            target_id=f"TGT-{uuid.uuid4().hex[:8].upper()}",
            domain=t.get("domain", "unknown"),
            platform=platform,
            report_count=t.get("report_count", 0),
            report_density_percent=t.get("density", 0.0),
            payout_range=t.get("payout", "Unknown"),
            is_selected=False,
        )
        target_entries.append(entry)
    
    new_activity = ActivitySessionState(
        session_id=dashboard.activity_session.session_id,
        platform_detected=platform,
        scope_extracted=scope,
        suggested_targets=tuple(target_entries),
        quantity_selected=dashboard.activity_session.quantity_selected,
        human_approved=False,  # Needs approval
        last_updated=now,
    )
    
    new_dashboard = DashboardState(
        dashboard_id=dashboard.dashboard_id,
        user_panel=dashboard.user_panel,
        admin_panel=dashboard.admin_panel,
        activity_session=new_activity,
        report_session=dashboard.report_session,
        active_panel=DashboardPanel.ACTIVITY,
        last_updated=now,
    )
    
    _dashboard_states[dashboard_id] = new_dashboard
    
    # Log event
    emit_event(ActivityType.TARGET_DISCOVERED, DashboardPanel.ACTIVITY, {
        "platform": platform,
        "target_count": len(targets),
    })
    
    return new_dashboard


def set_quantity_selected(
    dashboard_id: str,
    quantity: int,
) -> Optional[DashboardState]:
    """Set quantity of targets to work on."""
    dashboard = get_dashboard(dashboard_id)
    if not dashboard:
        return None
    
    # Clamp to valid range
    quantity = max(1, min(quantity, 20))
    now = datetime.now(UTC).isoformat()
    
    new_activity = ActivitySessionState(
        session_id=dashboard.activity_session.session_id,
        platform_detected=dashboard.activity_session.platform_detected,
        scope_extracted=dashboard.activity_session.scope_extracted,
        suggested_targets=dashboard.activity_session.suggested_targets,
        quantity_selected=quantity,
        human_approved=dashboard.activity_session.human_approved,
        last_updated=now,
    )
    
    new_dashboard = DashboardState(
        dashboard_id=dashboard.dashboard_id,
        user_panel=dashboard.user_panel,
        admin_panel=dashboard.admin_panel,
        activity_session=new_activity,
        report_session=dashboard.report_session,
        active_panel=dashboard.active_panel,
        last_updated=now,
    )
    
    _dashboard_states[dashboard_id] = new_dashboard
    return new_dashboard


def emit_event(
    event_type: ActivityType,
    source_panel: DashboardPanel,
    payload: Dict,
) -> DashboardEvent:
    """Emit a dashboard event."""
    event = DashboardEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:16].upper()}",
        event_type=event_type,
        source_panel=source_panel,
        payload=payload,
        timestamp=datetime.now(UTC).isoformat(),
    )
    _events.append(event)
    return event


def get_events() -> List[DashboardEvent]:
    """Get all events."""
    return list(_events)


def update_report_progress(
    dashboard_id: str,
    draft_id: str,
    progress: int,
    voice_message: Optional[str] = None,
) -> Optional[DashboardState]:
    """Update report draft progress."""
    dashboard = get_dashboard(dashboard_id)
    if not dashboard:
        return None
    
    now = datetime.now(UTC).isoformat()
    progress = max(0, min(progress, 100))
    
    new_report = ReportSessionState(
        session_id=dashboard.report_session.session_id,
        drafts=dashboard.report_session.drafts,
        current_draft_id=draft_id,
        overall_progress=progress,
        last_voice_message=voice_message,
        last_updated=now,
    )
    
    new_dashboard = DashboardState(
        dashboard_id=dashboard.dashboard_id,
        user_panel=dashboard.user_panel,
        admin_panel=dashboard.admin_panel,
        activity_session=dashboard.activity_session,
        report_session=new_report,
        active_panel=dashboard.active_panel,
        last_updated=now,
    )
    
    _dashboard_states[dashboard_id] = new_dashboard
    
    emit_event(ActivityType.REPORT_PROGRESS, DashboardPanel.REPORT, {
        "draft_id": draft_id,
        "progress": progress,
    })
    
    return new_dashboard


# ============================================================
# CRITICAL SECURITY GUARDS
# ============================================================

def can_dashboard_approve_execution() -> tuple:
    """
    Check if dashboard can directly approve execution.
    
    Returns (can_approve, reason).
    ALWAYS returns (False, ...) - human approval required via G13.
    """
    return False, "Dashboard cannot directly approve - human approval required via G13 Router"


def can_dashboard_trigger_action() -> tuple:
    """
    Check if dashboard can trigger browser/bot actions.
    
    Returns (can_trigger, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Dashboard cannot trigger actions - display and routing only"


def can_dashboard_bypass_router() -> tuple:
    """
    Check if dashboard can bypass G13 Router.
    
    Returns (can_bypass, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Dashboard MUST route all data through G13 Router"
