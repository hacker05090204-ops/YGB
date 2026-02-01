# G43: Auto-Mode Safety Boundary Governor
"""
AUTO-MODE SAFETY BOUNDARY GOVERNOR.

PURPOSE:
Allow AUTO MODE without human approval while remaining safe.

AUTO MODE MAY:
- Verify bugs (G36)
- Reject noise
- Generate final reports
- Produce screenshots + PoC videos

AUTO MODE MAY NOT:
- Exploit
- Submit
- Escalate scope
- Bypass policy
- Override SAFE MODE
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, List


class AutoModeState(Enum):
    """CLOSED ENUM - Auto mode states."""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DISABLED = "DISABLED"


class AutoAction(Enum):
    """CLOSED ENUM - Auto mode actions."""
    # ALLOWED
    VERIFY_BUG = "VERIFY_BUG"
    REJECT_NOISE = "REJECT_NOISE"
    GENERATE_REPORT = "GENERATE_REPORT"
    CAPTURE_SCREENSHOT = "CAPTURE_SCREENSHOT"
    GENERATE_POC_VIDEO = "GENERATE_POC_VIDEO"
    CHECK_DUPLICATE = "CHECK_DUPLICATE"
    # FORBIDDEN
    EXECUTE_EXPLOIT = "EXECUTE_EXPLOIT"
    SUBMIT_REPORT = "SUBMIT_REPORT"
    EXPAND_SCOPE = "EXPAND_SCOPE"
    BYPASS_POLICY = "BYPASS_POLICY"
    OVERRIDE_SAFE_MODE = "OVERRIDE_SAFE_MODE"


@dataclass(frozen=True)
class AutoActionRequest:
    """Request for auto-mode action."""
    request_id: str
    action: AutoAction
    target: str
    context: str


@dataclass(frozen=True)
class AutoActionResult:
    """Result of auto-mode action check."""
    result_id: str
    action: AutoAction
    allowed: bool
    reason: str


@dataclass(frozen=True)
class AutoModeStatus:
    """Auto mode status."""
    status_id: str
    state: AutoModeState
    actions_allowed: int
    actions_blocked: int
    is_safe: bool


# =============================================================================
# ALLOWED / FORBIDDEN ACTIONS
# =============================================================================

ALLOWED_ACTIONS = frozenset([
    AutoAction.VERIFY_BUG,
    AutoAction.REJECT_NOISE,
    AutoAction.GENERATE_REPORT,
    AutoAction.CAPTURE_SCREENSHOT,
    AutoAction.GENERATE_POC_VIDEO,
    AutoAction.CHECK_DUPLICATE,
])

FORBIDDEN_ACTIONS = frozenset([
    AutoAction.EXECUTE_EXPLOIT,
    AutoAction.SUBMIT_REPORT,
    AutoAction.EXPAND_SCOPE,
    AutoAction.BYPASS_POLICY,
    AutoAction.OVERRIDE_SAFE_MODE,
])


# =============================================================================
# AUTO MODE LOGIC
# =============================================================================

def _generate_id(prefix: str) -> str:
    """Generate unique ID."""
    import uuid
    return f"{prefix}-{uuid.uuid4().hex[:16].upper()}"


def is_action_allowed(action: AutoAction) -> bool:
    """Check if action is allowed in auto mode."""
    return action in ALLOWED_ACTIONS


def is_action_forbidden(action: AutoAction) -> bool:
    """Check if action is forbidden in auto mode."""
    return action in FORBIDDEN_ACTIONS


def check_auto_action(request: AutoActionRequest) -> AutoActionResult:
    """
    Check if auto action is allowed.
    
    Returns AutoActionResult with decision.
    """
    if is_action_forbidden(request.action):
        return AutoActionResult(
            result_id=_generate_id("AAR"),
            action=request.action,
            allowed=False,
            reason=f"Action {request.action.value} is FORBIDDEN in auto mode",
        )
    
    if is_action_allowed(request.action):
        return AutoActionResult(
            result_id=_generate_id("AAR"),
            action=request.action,
            allowed=True,
            reason=f"Action {request.action.value} is allowed",
        )
    
    # Unknown action - deny by default
    return AutoActionResult(
        result_id=_generate_id("AAR"),
        action=request.action,
        allowed=False,
        reason=f"Action {request.action.value} is unknown - denied by default",
    )


def get_auto_mode_status(
    actions_checked: List[AutoActionResult],
) -> AutoModeStatus:
    """Get auto mode status."""
    allowed = sum(1 for a in actions_checked if a.allowed)
    blocked = sum(1 for a in actions_checked if not a.allowed)
    
    return AutoModeStatus(
        status_id=_generate_id("AMS"),
        state=AutoModeState.ACTIVE if blocked == 0 else AutoModeState.PAUSED,
        actions_allowed=allowed,
        actions_blocked=blocked,
        is_safe=blocked == 0,
    )


def validate_auto_mode_safety(
    pending_actions: Tuple[AutoAction, ...],
) -> Tuple[bool, Tuple[str, ...]]:
    """
    Validate all pending auto actions are safe.
    
    Returns (all_safe, violations).
    """
    violations = []
    
    for action in pending_actions:
        if is_action_forbidden(action):
            violations.append(f"FORBIDDEN: {action.value}")
    
    return len(violations) == 0, tuple(violations)


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_auto_exploit() -> Tuple[bool, str]:
    """
    Check if auto mode can exploit.
    
    ALWAYS returns (False, ...).
    """
    return False, "Auto mode cannot execute exploits"


def can_auto_submit() -> Tuple[bool, str]:
    """
    Check if auto mode can submit.
    
    ALWAYS returns (False, ...).
    """
    return False, "Auto mode cannot submit reports - human required"


def can_auto_expand_scope() -> Tuple[bool, str]:
    """
    Check if auto mode can expand scope.
    
    ALWAYS returns (False, ...).
    """
    return False, "Auto mode cannot expand scope beyond authorization"


def can_auto_override_safety() -> Tuple[bool, str]:
    """
    Check if auto mode can override safety.
    
    ALWAYS returns (False, ...).
    """
    return False, "Auto mode cannot override safety boundaries"
