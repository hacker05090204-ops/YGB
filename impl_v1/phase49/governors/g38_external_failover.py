# G38: External AI Failover Governance
"""
EXTERNAL AI FAILOVER GOVERNANCE.

PURPOSE:
Strict governance for external AI/model usage.
External AI is FAILOVER-ONLY, NOT normal operation.

FAILOVER CONDITIONS (ALL REQUIRED):
1. Local model fails integrity check
2. OR checkpoint corruption detected
3. OR training/inference throws unrecoverable error
4. OR model enters REPAIR MODE

FAILOVER BEHAVIOR:
- Used temporarily
- Used read-only
- Used ONLY to recover/bootstrap
- Automatically disabled once local model recovers

ABSOLUTE RULES:
❌ NEVER primary
❌ NEVER parallel
❌ NEVER preferred
❌ NEVER silent
❌ NEVER cloud training
❌ NEVER telemetry
❌ NEVER continuous usage

Every failover MUST:
- Be logged
- Be visible in dashboard
- Require explicit "REPAIR MODE" state
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional, List
import uuid
from datetime import datetime


# =============================================================================
# FAILOVER STATE
# =============================================================================

class FailoverState(Enum):
    """External AI failover states."""
    DISABLED = "DISABLED"       # Normal operation - no external AI
    REPAIR_MODE = "REPAIR_MODE" # External AI active for recovery
    RECOVERING = "RECOVERING"   # Local model being restored
    ERROR = "ERROR"             # Unrecoverable error


class FailoverReason(Enum):
    """Reasons for failover activation."""
    NONE = "NONE"
    INTEGRITY_CHECK_FAILED = "INTEGRITY_CHECK_FAILED"
    CHECKPOINT_CORRUPTION = "CHECKPOINT_CORRUPTION"
    TRAINING_ERROR = "TRAINING_ERROR"
    INFERENCE_ERROR = "INFERENCE_ERROR"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"


@dataclass(frozen=True)
class FailoverStatus:
    """Current failover status."""
    status_id: str
    state: FailoverState
    reason: FailoverReason
    external_ai_active: bool
    logged: bool
    dashboard_visible: bool
    activated_at: Optional[str]
    will_auto_disable: bool


@dataclass(frozen=True)
class FailoverLogEntry:
    """Failover event log entry."""
    log_id: str
    event_type: str  # "ACTIVATED", "USED", "RECOVERED", "DISABLED"
    reason: FailoverReason
    details: str
    timestamp: str


@dataclass(frozen=True)
class FailoverRegistry:
    """Registry of failover events."""
    registry_id: str
    current_status: FailoverStatus
    log_entries: Tuple[FailoverLogEntry, ...]
    total_activations: int
    last_recovery: Optional[str]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate unique ID."""
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def _now_iso() -> str:
    """Current timestamp."""
    return datetime.utcnow().isoformat() + "Z"


# =============================================================================
# FAILOVER CONDITION CHECKS
# =============================================================================

def check_failover_conditions(
    integrity_ok: bool,
    checkpoint_valid: bool,
    training_error: Optional[str],
    inference_error: Optional[str],
    model_available: bool,
) -> Tuple[bool, FailoverReason]:
    """
    Check if failover conditions are met.
    
    Returns (should_activate, reason).
    
    Failover activates ONLY if:
    - Local model fails integrity check
    - OR checkpoint corruption detected
    - OR training/inference throws unrecoverable error
    - OR model enters REPAIR MODE
    """
    if not integrity_ok:
        return True, FailoverReason.INTEGRITY_CHECK_FAILED
    
    if not checkpoint_valid:
        return True, FailoverReason.CHECKPOINT_CORRUPTION
    
    if training_error:
        return True, FailoverReason.TRAINING_ERROR
    
    if inference_error:
        return True, FailoverReason.INFERENCE_ERROR
    
    if not model_available:
        return True, FailoverReason.MODEL_UNAVAILABLE
    
    return False, FailoverReason.NONE


# =============================================================================
# FAILOVER REGISTRY MANAGEMENT
# =============================================================================

def create_failover_registry() -> FailoverRegistry:
    """Create new failover registry with disabled state."""
    status = FailoverStatus(
        status_id=_generate_id("FST"),
        state=FailoverState.DISABLED,
        reason=FailoverReason.NONE,
        external_ai_active=False,
        logged=True,
        dashboard_visible=True,
        activated_at=None,
        will_auto_disable=True,
    )
    
    return FailoverRegistry(
        registry_id=_generate_id("FRG"),
        current_status=status,
        log_entries=tuple(),
        total_activations=0,
        last_recovery=None,
    )


def activate_failover(
    registry: FailoverRegistry,
    reason: FailoverReason,
    details: str,
) -> FailoverRegistry:
    """
    Activate external AI failover.
    
    REQUIRES:
    - Valid reason (not NONE)
    - Must log activation
    - Must be visible in dashboard
    """
    # Guard check
    if can_failover_activate_silently()[0]:  # pragma: no cover
        raise RuntimeError("SECURITY: Failover cannot activate silently")
    
    if reason == FailoverReason.NONE:
        raise ValueError("Cannot activate failover without reason")
    
    now = _now_iso()
    
    new_status = FailoverStatus(
        status_id=_generate_id("FST"),
        state=FailoverState.REPAIR_MODE,
        reason=reason,
        external_ai_active=True,
        logged=True,
        dashboard_visible=True,
        activated_at=now,
        will_auto_disable=True,
    )
    
    log_entry = FailoverLogEntry(
        log_id=_generate_id("FLG"),
        event_type="ACTIVATED",
        reason=reason,
        details=details,
        timestamp=now,
    )
    
    return FailoverRegistry(
        registry_id=registry.registry_id,
        current_status=new_status,
        log_entries=registry.log_entries + (log_entry,),
        total_activations=registry.total_activations + 1,
        last_recovery=registry.last_recovery,
    )


def record_failover_usage(
    registry: FailoverRegistry,
    usage_details: str,
) -> FailoverRegistry:
    """Record external AI usage during failover."""
    if registry.current_status.state != FailoverState.REPAIR_MODE:
        raise RuntimeError("Cannot use external AI outside REPAIR_MODE")
    
    log_entry = FailoverLogEntry(
        log_id=_generate_id("FLG"),
        event_type="USED",
        reason=registry.current_status.reason,
        details=usage_details,
        timestamp=_now_iso(),
    )
    
    return FailoverRegistry(
        registry_id=registry.registry_id,
        current_status=registry.current_status,
        log_entries=registry.log_entries + (log_entry,),
        total_activations=registry.total_activations,
        last_recovery=registry.last_recovery,
    )


def recover_from_failover(
    registry: FailoverRegistry,
    recovery_details: str,
) -> FailoverRegistry:
    """
    Recover from failover state.
    
    Automatically disables external AI once local model recovers.
    """
    now = _now_iso()
    
    new_status = FailoverStatus(
        status_id=_generate_id("FST"),
        state=FailoverState.DISABLED,
        reason=FailoverReason.NONE,
        external_ai_active=False,
        logged=True,
        dashboard_visible=True,
        activated_at=None,
        will_auto_disable=True,
    )
    
    log_entry = FailoverLogEntry(
        log_id=_generate_id("FLG"),
        event_type="RECOVERED",
        reason=registry.current_status.reason,
        details=recovery_details,
        timestamp=now,
    )
    
    return FailoverRegistry(
        registry_id=registry.registry_id,
        current_status=new_status,
        log_entries=registry.log_entries + (log_entry,),
        total_activations=registry.total_activations,
        last_recovery=now,
    )


# =============================================================================
# EXTERNAL AI USAGE CONTROLS
# =============================================================================

def is_external_ai_allowed(registry: FailoverRegistry) -> Tuple[bool, str]:
    """
    Check if external AI usage is currently allowed.
    
    Returns (allowed, reason).
    """
    if registry.current_status.state == FailoverState.REPAIR_MODE:
        return True, "REPAIR_MODE active - external AI temporarily allowed"
    
    if registry.current_status.state == FailoverState.RECOVERING:
        return True, "RECOVERING - external AI temporarily allowed"
    
    return False, "External AI disabled - local model in use"


def validate_external_ai_request(
    registry: FailoverRegistry,
    request_type: str,
) -> Tuple[bool, str]:
    """
    Validate external AI request.
    
    All requests MUST be:
    - In REPAIR_MODE
    - Read-only
    - Logged
    - Visible
    """
    allowed, reason = is_external_ai_allowed(registry)
    
    if not allowed:
        return False, f"Request denied: {reason}"
    
    if not registry.current_status.logged:
        return False, "Request denied: Usage must be logged"
    
    if not registry.current_status.dashboard_visible:
        return False, "Request denied: Usage must be visible"
    
    return True, f"Request allowed: {request_type} in REPAIR_MODE"


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_failover_activate_silently() -> Tuple[bool, str]:
    """
    Check if failover can activate without logging.
    
    ALWAYS returns (False, ...).
    """
    return False, "Failover cannot activate silently - must be logged"


def can_failover_run_continuously() -> Tuple[bool, str]:
    """
    Check if external AI can run continuously.
    
    ALWAYS returns (False, ...).
    """
    return False, "External AI cannot run continuously - repair only"


def can_failover_be_primary() -> Tuple[bool, str]:
    """
    Check if external AI can be primary.
    
    ALWAYS returns (False, ...).
    """
    return False, "External AI cannot be primary - failover only"


def can_failover_send_telemetry() -> Tuple[bool, str]:
    """
    Check if failover can send telemetry.
    
    ALWAYS returns (False, ...).
    """
    return False, "External AI cannot send telemetry - read-only access"


def can_failover_train_remotely() -> Tuple[bool, str]:
    """
    Check if failover can train on cloud.
    
    ALWAYS returns (False, ...).
    """
    return False, "External AI cannot train remotely - local training only"


def can_failover_hide_usage() -> Tuple[bool, str]:
    """
    Check if external usage can be hidden.
    
    ALWAYS returns (False, ...).
    """
    return False, "External AI usage cannot be hidden - all usage logged and visible"


# =============================================================================
# FAILOVER SUMMARY
# =============================================================================

def get_failover_summary(registry: FailoverRegistry) -> str:
    """Get human-readable failover summary."""
    status = registry.current_status
    
    lines = [
        "=== EXTERNAL AI FAILOVER STATUS ===",
        f"State: {status.state.value}",
        f"External AI Active: {'YES' if status.external_ai_active else 'NO'}",
        f"Reason: {status.reason.value}",
        f"Total Activations: {registry.total_activations}",
        f"Last Recovery: {registry.last_recovery or 'Never'}",
        f"Logged: {'YES' if status.logged else 'NO'}",
        f"Dashboard Visible: {'YES' if status.dashboard_visible else 'NO'}",
        "==================================="
    ]
    
    return "\n".join(lines)
