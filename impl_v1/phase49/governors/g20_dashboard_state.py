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
import logging
from typing import Optional, List, Dict, Any
import uuid
from datetime import datetime, UTC


logger = logging.getLogger(__name__)


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
    session_id: str
    active_view: str
    pending_approvals: int
    system_health: str


@dataclass(frozen=True)
class DashboardEvent:
    """Event triggered in dashboard."""
    event_id: str
    event_type: ActivityType
    source_panel: DashboardPanel
    payload: Dict
    timestamp: str


@dataclass(frozen=True)
class StateTransition:
    """Append-only dashboard state transition record."""

    transition_id: str
    session_id: str
    from_view: str
    to_view: str
    timestamp: str
    reason: str
    pending_approvals: int
    system_health: str


class StateTransitionLog:
    """Append-only log for dashboard state transitions."""

    def __init__(self):
        self._entries: List[StateTransition] = []

    def append(self, transition: StateTransition) -> None:
        self._entries.append(transition)

    def snapshot(self) -> tuple[StateTransition, ...]:
        return tuple(self._entries)

    def clear(self) -> None:
        self._entries.clear()


def _get_pending_approval_count() -> int:
    try:
        from .g13_dashboard_router import get_pending_requests

        return len(get_pending_requests())
    except Exception:
        return 0


def _load_peer_statuses() -> Dict[str, str]:
    try:
        from backend.sync.peer_transport import get_peer_statuses, get_peers

        statuses = {
            name: getattr(status, "value", str(status)).upper()
            for name, status in get_peer_statuses().items()
        }
        if statuses:
            return statuses

        peers = get_peers()
        return {
            str(peer.get("name", "unknown")): str(
                peer.get("peer_status") or peer.get("status") or "UNKNOWN"
            ).upper()
            for peer in peers
        }
    except Exception:
        return {}


def _load_circuit_breaker_states() -> List[str]:
    try:
        from backend.cve.cve_pipeline import get_pipeline

        source_status = get_pipeline().get_source_status()
        return [
            str(details.get("circuit_breaker") or "").upper()
            for details in source_status.values()
            if isinstance(details, dict) and details.get("circuit_breaker")
        ]
    except Exception:
        return []


def _derive_system_health(
    circuit_breaker_states: Optional[List[str]] = None,
    peer_statuses: Optional[Dict[str, str]] = None,
) -> str:
    breaker_states = [
        str(state or "").upper()
        for state in (circuit_breaker_states if circuit_breaker_states is not None else _load_circuit_breaker_states())
        if str(state or "").strip()
    ]
    peers = {
        name: str(status or "").upper()
        for name, status in (peer_statuses if peer_statuses is not None else _load_peer_statuses()).items()
    }

    if not breaker_states and not peers:
        return "UNKNOWN"

    any_breaker_degraded = any(state in {"OPEN", "HALF_OPEN"} for state in breaker_states)
    all_breakers_open = bool(breaker_states) and all(state == "OPEN" for state in breaker_states)
    peer_values = list(peers.values())
    any_peer_degraded = any(value in {"DEGRADED", "UNREACHABLE", "OFFLINE", "ERROR"} for value in peer_values)
    all_peers_unreachable = bool(peer_values) and all(
        value in {"UNREACHABLE", "OFFLINE"} for value in peer_values
    )

    if (all_breakers_open and (not peer_values or all_peers_unreachable)) or (
        any_breaker_degraded and all_peers_unreachable
    ):
        return "CRITICAL"
    if any_breaker_degraded or any_peer_degraded:
        return "DEGRADED"
    return "HEALTHY"


def _normalize_view(view: str) -> str:
    normalized = str(view or "").strip().upper()
    aliases = {
        "": DashboardPanel.USER.value,
        "OVERVIEW": DashboardPanel.USER.value,
        "USER": DashboardPanel.USER.value,
        "ADMIN": DashboardPanel.ADMIN.value,
        "ACTIVITY": DashboardPanel.ACTIVITY.value,
        "REPORT": DashboardPanel.REPORT.value,
        "REPORTS": DashboardPanel.REPORT.value,
        "APPROVALS": "APPROVALS",
        "STATUS": "STATUS",
        "HEALTH": "HEALTH",
        "/DASHBOARD/OVERVIEW": DashboardPanel.USER.value,
        "/DASHBOARD/USER": DashboardPanel.USER.value,
        "/DASHBOARD/ADMIN": DashboardPanel.ADMIN.value,
        "/DASHBOARD/ACTIVITY": DashboardPanel.ACTIVITY.value,
        "/DASHBOARD/REPORT": DashboardPanel.REPORT.value,
        "/DASHBOARD/REPORTS": DashboardPanel.REPORT.value,
        "/DASHBOARD/APPROVALS": "APPROVALS",
        "/DASHBOARD/STATUS": "STATUS",
        "/DASHBOARD/HEALTH": "HEALTH",
    }
    if any(token in normalized for token in ("EXECUTE", "LAUNCH", "SUBMIT", "CLICK", "AUTOMATE", "APPROVE", "BYPASS")):
        return DashboardPanel.USER.value
    return aliases.get(normalized, DashboardPanel.USER.value)


def _panel_for_view(view: str) -> DashboardPanel:
    normalized = _normalize_view(view)
    if normalized in {DashboardPanel.ADMIN.value, "APPROVALS"}:
        return DashboardPanel.ADMIN
    if normalized == DashboardPanel.ACTIVITY.value:
        return DashboardPanel.ACTIVITY
    if normalized == DashboardPanel.REPORT.value:
        return DashboardPanel.REPORT
    return DashboardPanel.USER


def _build_dashboard_snapshot(
    dashboard_id: str,
    user_panel: Optional[UserPanelState],
    admin_panel: Optional[AdminPanelState],
    activity_session: Optional[ActivitySessionState],
    report_session: Optional[ReportSessionState],
    active_panel: DashboardPanel,
    last_updated: str,
) -> DashboardState:
    pending_approvals = _get_pending_approval_count()
    refreshed_admin_panel = admin_panel
    if admin_panel is not None:
        refreshed_admin_panel = AdminPanelState(
            admin_id=admin_panel.admin_id,
            total_users=admin_panel.total_users,
            active_sessions=admin_panel.active_sessions,
            pending_approvals=pending_approvals,
            recent_alerts=admin_panel.recent_alerts,
            risk_flags=admin_panel.risk_flags,
            last_updated=last_updated,
        )

    return DashboardState(
        dashboard_id=dashboard_id,
        user_panel=user_panel,
        admin_panel=refreshed_admin_panel,
        activity_session=activity_session,
        report_session=report_session,
        active_panel=active_panel,
        last_updated=last_updated,
        session_id=activity_session.session_id if activity_session is not None else dashboard_id,
        active_view=active_panel.value,
        pending_approvals=pending_approvals,
        system_health=_derive_system_health(),
    )


_state_transition_log = StateTransitionLog()


def _append_state_transition(
    session_id: str,
    from_view: str,
    to_view: str,
    reason: str,
    *,
    pending_approvals: int,
    system_health: str,
    transition_log: Optional[StateTransitionLog] = None,
) -> StateTransition:
    transition = StateTransition(
        transition_id=f"TRN-{uuid.uuid4().hex[:16].upper()}",
        session_id=session_id,
        from_view=_normalize_view(from_view),
        to_view=_normalize_view(to_view),
        timestamp=datetime.now(UTC).isoformat(),
        reason=reason,
        pending_approvals=pending_approvals,
        system_health=system_health,
    )
    (transition_log or _state_transition_log).append(transition)
    return transition


def get_state_transition_log() -> tuple[StateTransition, ...]:
    """Return a snapshot of the append-only transition log."""
    return _state_transition_log.snapshot()


class StateManager:
    """Authoritative cluster-level dashboard state manager."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        transition_log: Optional[StateTransitionLog] = None,
    ):
        self._session_id = session_id or f"DST-{uuid.uuid4().hex[:12].upper()}"
        self._active_view = DashboardPanel.USER.value
        self._last_updated = datetime.now(UTC).isoformat()
        self._transition_log = transition_log or _state_transition_log

    @property
    def transition_log(self) -> StateTransitionLog:
        return self._transition_log

    def _load_circuit_breaker_states(self) -> List[str]:
        return _load_circuit_breaker_states()

    def _load_peer_statuses(self) -> Dict[str, str]:
        return _load_peer_statuses()

    def _current_health(self) -> str:
        return _derive_system_health(
            self._load_circuit_breaker_states(),
            self._load_peer_statuses(),
        )

    def get_current_state(self) -> DashboardState:
        """Get current dashboard cluster state."""
        return DashboardState(
            dashboard_id=self._session_id,
            user_panel=None,
            admin_panel=None,
            activity_session=None,
            report_session=None,
            active_panel=_panel_for_view(self._active_view),
            last_updated=self._last_updated,
            session_id=self._session_id,
            active_view=self._active_view,
            pending_approvals=_get_pending_approval_count(),
            system_health=self._current_health(),
        )

    def update_view(self, view: str) -> DashboardState:
        """Update the active view and append a transition log entry."""
        previous_view = self._active_view
        self._active_view = _normalize_view(view)
        self._last_updated = datetime.now(UTC).isoformat()
        state = self.get_current_state()
        _append_state_transition(
            self._session_id,
            previous_view,
            self._active_view,
            "dashboard_view_updated",
            pending_approvals=state.pending_approvals,
            system_health=state.system_health,
            transition_log=self._transition_log,
        )
        return state


_default_state_manager: Optional[StateManager] = None
_state_managers: Dict[str, StateManager] = {}


def get_state_manager(session_id: Optional[str] = None) -> StateManager:
    """Return the shared dashboard cluster state manager."""
    global _default_state_manager

    if session_id is None:
        if _default_state_manager is None:
            _default_state_manager = StateManager()
        return _default_state_manager

    if session_id not in _state_managers:
        _state_managers[session_id] = StateManager(session_id=session_id)
    return _state_managers[session_id]


# In-memory state store
_dashboard_states: Dict[str, DashboardState] = {}
_events: List[DashboardEvent] = []


def clear_dashboard_state():
    """Clear all state (for testing)."""
    global _default_state_manager

    _dashboard_states.clear()
    _events.clear()
    _state_transition_log.clear()
    _state_managers.clear()
    _default_state_manager = None
    try:
        from .g13_dashboard_router import clear_requests

        clear_requests()
    except Exception as exc:
        logger.debug("Dashboard request cache clear skipped: %s", exc)


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
    
    dashboard = _build_dashboard_snapshot(
        dashboard_id=dashboard_id,
        user_panel=user_panel,
        admin_panel=admin_panel,
        activity_session=activity_session,
        report_session=report_session,
        active_panel=DashboardPanel.USER,
        last_updated=now,
    )
    
    _dashboard_states[dashboard_id] = dashboard
    _append_state_transition(
        dashboard.session_id,
        "INITIAL",
        dashboard.active_view,
        "dashboard_created",
        pending_approvals=dashboard.pending_approvals,
        system_health=dashboard.system_health,
    )
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
    
    new_dashboard = _build_dashboard_snapshot(
        dashboard_id=dashboard.dashboard_id,
        user_panel=dashboard.user_panel,
        admin_panel=dashboard.admin_panel,
        activity_session=new_activity,
        report_session=dashboard.report_session,
        active_panel=DashboardPanel.ACTIVITY,
        last_updated=now,
    )
    
    _dashboard_states[dashboard_id] = new_dashboard
    if dashboard.active_view != new_dashboard.active_view:
        _append_state_transition(
            new_dashboard.session_id,
            dashboard.active_view,
            new_dashboard.active_view,
            "activity_targets_updated",
            pending_approvals=new_dashboard.pending_approvals,
            system_health=new_dashboard.system_health,
        )
    
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
    
    new_dashboard = _build_dashboard_snapshot(
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
    
    new_dashboard = _build_dashboard_snapshot(
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
