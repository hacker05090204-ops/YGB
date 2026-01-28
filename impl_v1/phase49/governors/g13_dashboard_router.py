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
from typing import Optional, List
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
