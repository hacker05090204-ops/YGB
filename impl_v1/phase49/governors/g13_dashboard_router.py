# G13: Dashboard Router
"""
Single approval authority for all execution requests.

RESPONSIBILITIES:
- Receive target & scope (from voice or UI)
- Show extracted scope, risk summary, proposed mode
- Collect HUMAN approval

RULE: NO approval = NO execution
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Any, Dict, Mapping
import uuid
from datetime import datetime, UTC


class ApprovalStatus(Enum):
    """CLOSED ENUM - 5 statuses"""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class ProposedMode(Enum):
    """CLOSED ENUM - 3 modes"""
    MANUAL = "MANUAL"
    AUTONOMOUS_FIND = "AUTONOMOUS_FIND"
    READ_ONLY = "READ_ONLY"


class RiskLevel(Enum):
    """CLOSED ENUM - 4 levels"""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class ApprovalRequest:
    """Request for dashboard approval."""
    request_id: str
    target: str
    scope: str
    proposed_mode: ProposedMode
    risk_level: RiskLevel
    risk_summary: str
    status: ApprovalStatus
    created_at: str
    expires_at: str


@dataclass(frozen=True)
class ApprovalDecision:
    """Human's approval decision."""
    decision_id: str
    request_id: str
    approved: bool
    approver_id: str
    reason: str
    timestamp: str


@dataclass(frozen=True)
class RouteDecision:
    """Safe, display-only routing decision for dashboard navigation."""

    destination: str
    reason: str
    confidence: float
    fallback: bool


class DashboardRouter:
    """Route dashboard requests to safe display endpoints only."""

    SAFE_DEFAULT_VIEW = "/dashboard/overview"
    _DISPLAY_ENDPOINTS = {
        "OVERVIEW": "/dashboard/overview",
        "ADMIN": "/dashboard/admin",
        "ACTIVITY": "/dashboard/activity",
        "REPORTS": "/dashboard/reports",
        "APPROVALS": "/dashboard/approvals",
        "STATUS": "/dashboard/status",
        "HEALTH": "/dashboard/health",
    }
    _ACTION_TOKENS = {
        "execute",
        "launch",
        "submit",
        "click",
        "automate",
        "approve",
        "bypass",
        "modify",
        "delete",
        "write",
        "trigger",
        "action",
    }
    _VIEW_ALIASES = {
        "OVERVIEW": "OVERVIEW",
        "USER": "OVERVIEW",
        "ADMIN": "ADMIN",
        "ACTIVITY": "ACTIVITY",
        "REPORT": "REPORTS",
        "REPORTS": "REPORTS",
        "APPROVAL": "APPROVALS",
        "APPROVALS": "APPROVALS",
        "STATUS": "STATUS",
        "SUMMARY": "STATUS",
        "HEALTH": "HEALTH",
        "/DASHBOARD/OVERVIEW": "OVERVIEW",
        "/DASHBOARD/USER": "OVERVIEW",
        "/DASHBOARD/ADMIN": "ADMIN",
        "/DASHBOARD/ACTIVITY": "ACTIVITY",
        "/DASHBOARD/REPORT": "REPORTS",
        "/DASHBOARD/REPORTS": "REPORTS",
        "/DASHBOARD/APPROVALS": "APPROVALS",
        "/DASHBOARD/STATUS": "STATUS",
        "/DASHBOARD/HEALTH": "HEALTH",
    }
    _ROLE_VIEWS = {
        "admin": {"OVERVIEW", "ADMIN", "ACTIVITY", "REPORTS", "APPROVALS", "STATUS", "HEALTH"},
        "analyst": {"OVERVIEW", "ACTIVITY", "REPORTS", "STATUS", "HEALTH"},
        "hunter": {"OVERVIEW", "ACTIVITY", "REPORTS", "STATUS", "HEALTH"},
        "user": {"OVERVIEW", "ACTIVITY", "REPORTS", "STATUS", "HEALTH"},
        "readonly": {"OVERVIEW", "REPORTS", "STATUS", "HEALTH"},
        "viewer": {"OVERVIEW", "REPORTS", "STATUS", "HEALTH"},
    }

    def __init__(self, state_manager: Optional[Any] = None, safe_default_view: str = SAFE_DEFAULT_VIEW):
        self._state_manager = state_manager
        self._safe_default_key = self._normalize_view(safe_default_view) or "OVERVIEW"

    @staticmethod
    def _read_value(source: Any, key: str, default: Any = None) -> Any:
        if isinstance(source, Mapping):
            return source.get(key, default)
        return getattr(source, key, default)

    @classmethod
    def _normalize_role(cls, role: Any) -> str:
        normalized = str(role or "viewer").strip().lower()
        return normalized if normalized in cls._ROLE_VIEWS else "viewer"

    @classmethod
    def _contains_action_hint(cls, value: Any) -> bool:
        normalized = str(value or "").strip().lower()
        return any(token in normalized for token in cls._ACTION_TOKENS)

    @classmethod
    def _normalize_view(cls, value: Any) -> Optional[str]:
        normalized = str(value or "").strip().upper()
        if not normalized:
            return None
        return cls._VIEW_ALIASES.get(normalized)

    @staticmethod
    def _clamp_confidence(value: float) -> float:
        return max(0.0, min(round(value, 2), 1.0))

    def _load_system_state(self, request: Mapping[str, Any]) -> Dict[str, Any]:
        source: Any = request.get("system_state")
        if source is None and self._state_manager is not None:
            try:
                source = self._state_manager.get_current_state()
            except Exception:
                source = None

        active_view = self._normalize_view(
            self._read_value(source, "active_view", request.get("active_view"))
        ) or "OVERVIEW"

        try:
            pending_approvals = int(
                self._read_value(source, "pending_approvals", request.get("pending_approvals", 0)) or 0
            )
        except (TypeError, ValueError):
            pending_approvals = 0

        system_health = str(
            self._read_value(source, "system_health", request.get("system_health", "UNKNOWN")) or "UNKNOWN"
        ).upper()

        return {
            "active_view": active_view,
            "pending_approvals": pending_approvals,
            "system_health": system_health,
        }

    def route(self, request: dict) -> RouteDecision:
        """Route requests using request type, role, and current system state."""
        request_type = str(request.get("type") or request.get("request_type") or "").strip().lower()
        user_role = self._normalize_role(request.get("user_role") or request.get("role"))
        requested_view = self._normalize_view(
            request.get("view") or request.get("destination") or request.get("endpoint")
        )
        current_state = self._load_system_state(request)

        if self._contains_action_hint(request_type) or self._contains_action_hint(request.get("destination")):
            return RouteDecision(
                destination=self._DISPLAY_ENDPOINTS[self._safe_default_key],
                reason="Blocked action-oriented request; routing to safe display-only overview",
                confidence=0.1,
                fallback=True,
            )

        active_view = current_state["active_view"]
        pending_approvals = current_state["pending_approvals"]
        system_health = current_state["system_health"]

        destination_key = requested_view or active_view
        reason = "Reusing current dashboard view"
        confidence = 0.4

        if request_type in {"overview", "dashboard", "home"}:
            destination_key = "OVERVIEW"
            reason = "Overview requested"
            confidence = 0.75
        elif request_type in {"activity", "targets", "target_discovery", "session"}:
            destination_key = "ACTIVITY"
            reason = "Activity dashboard requested"
            confidence = 0.78
        elif request_type in {"report", "reports", "report_status", "report_session"}:
            destination_key = "REPORTS"
            reason = "Reports dashboard requested"
            confidence = 0.78
        elif request_type in {"admin", "alerts", "audit"}:
            destination_key = "ADMIN"
            reason = "Administrative dashboard requested"
            confidence = 0.72
        elif request_type in {"approvals", "approval_queue", "pending_approvals"}:
            destination_key = "APPROVALS" if pending_approvals > 0 else "ADMIN"
            reason = "Approval queue requested"
            confidence = 0.82 if pending_approvals > 0 else 0.66
        elif request_type in {"status", "summary", "health"}:
            destination_key = "HEALTH" if system_health in {"DEGRADED", "CRITICAL"} else "STATUS"
            reason = "System status requested"
            confidence = 0.8
        elif requested_view is not None:
            destination_key = requested_view
            reason = f"Explicit display view requested: {requested_view.lower()}"
            confidence = 0.62

        if user_role != "admin" and destination_key in {"ADMIN", "APPROVALS"}:
            destination_key = "OVERVIEW"
            reason = "User role is not authorized for administrative dashboard views"
            confidence = min(confidence, 0.32)

        allowed_views = self._ROLE_VIEWS.get(user_role, self._ROLE_VIEWS["viewer"])
        if destination_key not in allowed_views:
            destination_key = "OVERVIEW"
            reason = "Requested display view is outside the allowed role scope"
            confidence = min(confidence, 0.3)

        if system_health in {"DEGRADED", "CRITICAL"} and request_type in {"overview", "dashboard", "home", "status", "summary", "health"}:
            destination_key = "HEALTH"
            reason = f"System health is {system_health}; prioritizing health dashboard"
            confidence = max(confidence, 0.88)

        if pending_approvals > 0 and user_role == "admin" and request_type in {"overview", "dashboard", "home", "admin"}:
            destination_key = "APPROVALS"
            reason = "Pending approvals prioritized for admin dashboard"
            confidence = max(confidence, 0.84)

        if destination_key == active_view:
            confidence += 0.06

        confidence = self._clamp_confidence(confidence)
        fallback = confidence < 0.5
        destination = self._DISPLAY_ENDPOINTS[self._safe_default_key] if fallback else self._DISPLAY_ENDPOINTS[destination_key]

        if fallback:
            reason = f"{reason}; confidence below threshold so safe default view was selected"

        return RouteDecision(
            destination=destination,
            reason=reason,
            confidence=confidence,
            fallback=fallback,
        )


# In-memory request store (for governance testing)
_pending_requests: dict = {}
_decisions: List[ApprovalDecision] = []


def clear_requests():
    """Clear request store (for testing)."""
    _pending_requests.clear()
    _decisions.clear()


def get_pending_requests() -> List[ApprovalRequest]:
    """Get all pending approval requests."""
    return [r for r in _pending_requests.values() if r.status == ApprovalStatus.PENDING]


def create_approval_request(
    target: str,
    scope: str,
    proposed_mode: ProposedMode = ProposedMode.READ_ONLY,
    risk_level: RiskLevel = RiskLevel.MEDIUM,
    risk_summary: str = "",
) -> ApprovalRequest:
    """Create an approval request for the dashboard."""
    now = datetime.now(UTC)
    
    request = ApprovalRequest(
        request_id=f"APR-{uuid.uuid4().hex[:16].upper()}",
        target=target,
        scope=scope,
        proposed_mode=proposed_mode,
        risk_level=risk_level,
        risk_summary=risk_summary or f"Target: {target}, Mode: {proposed_mode.value}",
        status=ApprovalStatus.PENDING,
        created_at=now.isoformat(),
        expires_at=(now.replace(hour=now.hour + 1)).isoformat(),  # 1 hour expiry
    )
    
    _pending_requests[request.request_id] = request
    return request


def submit_decision(
    request_id: str,
    approved: bool,
    approver_id: str,
    reason: str = "",
) -> Optional[ApprovalDecision]:
    """Submit approval decision from human."""
    if request_id not in _pending_requests:
        return None
    
    request = _pending_requests[request_id]
    if request.status != ApprovalStatus.PENDING:
        return None
    
    decision = ApprovalDecision(
        decision_id=f"DEC-{uuid.uuid4().hex[:16].upper()}",
        request_id=request_id,
        approved=approved,
        approver_id=approver_id,
        reason=reason,
        timestamp=datetime.now(UTC).isoformat(),
    )
    
    # Update request status
    new_status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
    updated = ApprovalRequest(
        request_id=request.request_id,
        target=request.target,
        scope=request.scope,
        proposed_mode=request.proposed_mode,
        risk_level=request.risk_level,
        risk_summary=request.risk_summary,
        status=new_status,
        created_at=request.created_at,
        expires_at=request.expires_at,
    )
    _pending_requests[request_id] = updated
    _decisions.append(decision)
    
    return decision


def is_execution_approved(request_id: str) -> tuple:
    """Check if execution is approved for request. Returns (approved, reason)."""
    if request_id not in _pending_requests:
        return False, "Request not found"
    
    request = _pending_requests[request_id]
    
    if request.status == ApprovalStatus.APPROVED:
        return True, "Execution approved by human"
    
    if request.status == ApprovalStatus.PENDING:
        return False, "Awaiting human approval"
    
    return False, f"Request status: {request.status.value}"


def get_decision_audit_log() -> List[ApprovalDecision]:
    """Get audit log of all decisions."""
    return list(_decisions)


def route_voice_intent(intent) -> Optional[ApprovalRequest]:
    """Route voice intent to dashboard. Creates approval request if actionable."""
    from .g12_voice_input import VoiceIntentType, VoiceInputStatus
    
    if intent.status != VoiceInputStatus.PARSED:
        return None
    
    if intent.intent_type == VoiceIntentType.SET_TARGET:
        return create_approval_request(
            target=intent.extracted_value or "unknown",
            scope="*",
            proposed_mode=ProposedMode.READ_ONLY,
        )
    
    if intent.intent_type == VoiceIntentType.FIND_TARGETS:
        return create_approval_request(
            target="discovery",
            scope="public_programs",
            proposed_mode=ProposedMode.READ_ONLY,
            risk_level=RiskLevel.LOW,
            risk_summary="Target discovery - read-only public sources",
        )
    
    # Status/progress queries don't need approval
    return None
