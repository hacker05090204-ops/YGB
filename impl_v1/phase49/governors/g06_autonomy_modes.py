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


class AutonomyLevel(Enum):
    """Human-governed autonomy levels. Fully autonomous mode is intentionally absent."""

    MANUAL = "MANUAL"
    ASSISTED = "ASSISTED"
    SUPERVISED = "SUPERVISED"


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
AUTONOMY_APPROVAL_FIELD_ID = 6


@dataclass(frozen=True)
class ModeTransitionRecord:
    """Append-only record of an autonomy mode transition request."""

    from_mode: AutonomyLevel
    to_mode: AutonomyLevel
    authorized_by: str
    timestamp: str
    reason: str


class ModeTransitionLog:
    """Append-only transition log for autonomy level changes."""

    def __init__(self):
        self._entries: List[ModeTransitionRecord] = []

    def append(self, record: ModeTransitionRecord) -> None:
        self._entries.append(record)

    def snapshot(self) -> tuple[ModeTransitionRecord, ...]:
        return tuple(self._entries)


class AutonomyController:
    """Govern human-authorized autonomy levels without allowing full autonomy."""

    def __init__(
        self,
        *,
        initial_mode: AutonomyLevel = AutonomyLevel.MANUAL,
        approval_ledger=None,
        approval_field_id: int = AUTONOMY_APPROVAL_FIELD_ID,
        transition_log: Optional[ModeTransitionLog] = None,
    ):
        self._current_mode = initial_mode
        self._approval_ledger = approval_ledger
        self._approval_field_id = approval_field_id
        self._transition_log = transition_log or ModeTransitionLog()

    @property
    def approval_field_id(self) -> int:
        return self._approval_field_id

    @property
    def transition_log(self) -> ModeTransitionLog:
        return self._transition_log

    def get_current_mode(self) -> AutonomyLevel:
        return self._current_mode

    def _get_approval_ledger(self):
        if self._approval_ledger is None:
            from backend.governance.approval_ledger import ApprovalLedger

            self._approval_ledger = ApprovalLedger()
        return self._approval_ledger

    def _log_transition(
        self,
        from_mode: AutonomyLevel,
        to_mode: AutonomyLevel,
        authorized_by: str,
        reason: str,
    ) -> None:
        self._transition_log.append(
            ModeTransitionRecord(
                from_mode=from_mode,
                to_mode=to_mode,
                authorized_by=authorized_by,
                timestamp=datetime.now(UTC).isoformat(),
                reason=reason,
            )
        )

    def _validate_human_authorization(self, authorized_by: str) -> tuple[bool, str]:
        actor = (authorized_by or "").strip()
        if not actor:
            return False, "HUMAN_AUTHORIZATION_TOKEN_REQUIRED"

        try:
            from backend.governance.approval_ledger import ApprovalToken, KeyManager

            ledger = self._get_approval_ledger()
            ledger.load()
        except Exception as exc:
            return False, f"AUTH_LEDGER_UNAVAILABLE: {exc}"

        now_ts = datetime.now(UTC).timestamp()
        default_key_id = getattr(KeyManager, "DEFAULT_KEY_ID", "")

        for entry in reversed(getattr(ledger, "_entries", [])):
            token_data = entry.get("token") if isinstance(entry, dict) else None
            if not isinstance(token_data, dict):
                continue

            try:
                token = ApprovalToken.from_dict(token_data)
            except Exception:
                continue

            if token.field_id != self._approval_field_id:
                continue
            if token.approver_id != actor:
                continue

            key_id = token.key_id or default_key_id
            if key_id and ledger.key_manager.is_revoked(key_id):
                continue
            if not ledger.verify_token(token):
                continue

            age_seconds = now_ts - float(token.timestamp)
            if age_seconds < -60:
                continue
            if age_seconds > float(token.expiration_window):
                continue

            return True, f"HUMAN_AUTHORIZED:{token.reason}"

        return False, "HUMAN_AUTHORIZATION_TOKEN_REQUIRED"

    def is_autonomous_action_authorized(self, authorized_by: str) -> bool:
        """No autonomous action is permitted without a valid human authorization token."""

        if self._current_mode == AutonomyLevel.MANUAL:
            return False
        authorized, _ = self._validate_human_authorization(authorized_by)
        return authorized

    def request_transition(self, to: AutonomyLevel, authorized_by: str) -> bool:
        from_mode = self._current_mode
        actor = (authorized_by or "").strip() or "EMERGENCY_FALLBACK"

        if to == AutonomyLevel.MANUAL:
            self._current_mode = AutonomyLevel.MANUAL
            self._log_transition(from_mode, to, actor, "EMERGENCY_FALLBACK")
            return True

        authorized, reason = self._validate_human_authorization(authorized_by)
        if not authorized:
            self._log_transition(from_mode, to, actor, reason)
            return False

        self._current_mode = to
        self._log_transition(from_mode, to, actor, reason)
        return True


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
