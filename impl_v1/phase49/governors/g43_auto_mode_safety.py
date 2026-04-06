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
from typing import Tuple, List, Optional

from backend.governance.authority_lock import AuthorityLock
from impl_v1.phase49.governors.g06_autonomy_modes import AutonomyController, AutonomyLevel


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


@dataclass(frozen=True)
class SafetyCheckResult:
    """Result of a single auto-mode safety check."""

    check_name: str
    passed: bool
    detail: str
    severity: str


class AutoModeSafetyGuard:
    """Safety boundary that forces MANUAL fallback on critical failures."""

    def __init__(
        self,
        controller: Optional[AutonomyController] = None,
        authority_lock=AuthorityLock,
        critical_alert_provider=None,
        training_state_provider=None,
    ):
        self._controller = controller or AutonomyController()
        self._authority_lock = authority_lock
        self._critical_alert_provider = critical_alert_provider or (lambda: [])
        self._training_state_provider = training_state_provider or (lambda: False)
        self._last_results: List[SafetyCheckResult] = []

    def _normalize_critical_alerts(self) -> List[str]:
        alerts = self._critical_alert_provider()
        if alerts is None:
            return []
        if isinstance(alerts, bool):
            return ["CRITICAL_ALERT_PENDING"] if alerts else []
        if isinstance(alerts, dict):
            pending = alerts.get("alerts") or alerts.get("pending") or []
            if isinstance(pending, bool):
                return ["CRITICAL_ALERT_PENDING"] if pending else []
            if isinstance(pending, (list, tuple, set, frozenset)):
                return [str(item) for item in pending if str(item).strip()]
            return [str(pending)] if str(pending).strip() else []
        if isinstance(alerts, (list, tuple, set, frozenset)):
            return [str(item) for item in alerts if str(item).strip()]
        return [str(alerts)] if str(alerts).strip() else []

    def _is_training_mid_epoch(self) -> bool:
        state = self._training_state_provider()
        if isinstance(state, bool):
            return state
        if isinstance(state, dict):
            if "mid_epoch" in state:
                return bool(state["mid_epoch"])
            return bool(state.get("is_training", False))

        mid_epoch = getattr(state, "mid_epoch", None)
        if mid_epoch is not None:
            return bool(mid_epoch)
        return bool(getattr(state, "is_training", False))

    def _check_mode_not_fully_autonomous(self) -> SafetyCheckResult:
        mode = self._controller.get_current_mode()
        passed = isinstance(mode, AutonomyLevel)
        detail = (
            f"Current mode {mode.value} remains human-governed"
            if passed
            else f"Unsupported autonomous mode detected: {mode}"
        )
        return SafetyCheckResult(
            check_name="mode_not_fully_autonomous",
            passed=passed,
            detail=detail,
            severity="INFO" if passed else "CRITICAL",
        )

    def _check_authority_lock(self) -> SafetyCheckResult:
        result = self._authority_lock.verify_all_locked()
        passed = bool(result.get("all_locked", False))
        detail = str(result.get("status", "UNKNOWN"))
        return SafetyCheckResult(
            check_name="authority_lock_all_locked",
            passed=passed,
            detail=detail,
            severity="INFO" if passed else "CRITICAL",
        )

    def _check_critical_alerts(self) -> SafetyCheckResult:
        alerts = self._normalize_critical_alerts()
        passed = len(alerts) == 0
        detail = (
            "No critical alerts pending"
            if passed
            else f"Critical alerts pending: {', '.join(alerts)}"
        )
        return SafetyCheckResult(
            check_name="no_critical_alerts_pending",
            passed=passed,
            detail=detail,
            severity="INFO" if passed else "CRITICAL",
        )

    def _check_training_not_mid_epoch(self) -> SafetyCheckResult:
        mid_epoch = self._is_training_mid_epoch()
        return SafetyCheckResult(
            check_name="training_not_mid_epoch",
            passed=not mid_epoch,
            detail="Training is idle" if not mid_epoch else "Training is currently mid-epoch",
            severity="INFO" if not mid_epoch else "CRITICAL",
        )

    def run_all_checks(self) -> list[SafetyCheckResult]:
        results: List[SafetyCheckResult] = []
        fallback_triggered = False

        for check in (
            self._check_mode_not_fully_autonomous,
            self._check_authority_lock,
            self._check_critical_alerts,
            self._check_training_not_mid_epoch,
        ):
            result = check()
            results.append(result)

            if not result.passed and result.severity.upper() == "CRITICAL" and not fallback_triggered:
                self._controller.request_transition(AutonomyLevel.MANUAL, "safety_guard")
                fallback_triggered = True

        self._last_results = results
        return list(results)

    def get_safety_status(self) -> dict:
        results = self._last_results or self.run_all_checks()
        failed_checks = [result.check_name for result in results if not result.passed]
        return {
            "all_safe": len(failed_checks) == 0,
            "failed_checks": failed_checks,
        }


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
