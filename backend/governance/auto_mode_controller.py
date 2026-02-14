"""
auto_mode_controller.py — Auto Mode Control with Governance Gates

Auto mode = SHADOW ONLY
Requires:
    - Integrity score > 95
    - No containment in 24h
    - Drift stable
    - Dataset balanced
    - Storage healthy
    - Manual approval before report export
"""

from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime, timezone


# =========================================================================
# TYPES
# =========================================================================

@dataclass
class AutoModeCondition:
    integrity_above_95: bool = False
    no_containment_24h: bool = False
    drift_stable: bool = False
    dataset_balanced: bool = False
    storage_healthy: bool = False

    @property
    def all_conditions_met(self) -> bool:
        return all([
            self.integrity_above_95,
            self.no_containment_24h,
            self.drift_stable,
            self.dataset_balanced,
            self.storage_healthy,
        ])

    @property
    def blocked_reasons(self) -> List[str]:
        reasons = []
        if not self.integrity_above_95:
            reasons.append("Integrity score below 95")
        if not self.no_containment_24h:
            reasons.append("Containment event in last 24h")
        if not self.drift_stable:
            reasons.append("Drift instability detected")
        if not self.dataset_balanced:
            reasons.append("Dataset imbalance detected")
        if not self.storage_healthy:
            reasons.append("Storage health warning")
        return reasons


@dataclass
class AutoModeState:
    enabled: bool = False
    shadow_only: bool = True    # Always true — auto-mode is shadow only
    conditions: Optional[AutoModeCondition] = None
    last_check: str = ""
    export_requires_approval: bool = True  # Always true

    @property
    def can_activate(self) -> bool:
        if self.conditions is None:
            return False
        return self.conditions.all_conditions_met


# =========================================================================
# AUTO MODE CONTROLLER
# =========================================================================

class AutoModeController:
    """Controls auto-mode activation with governance gates.

    IMMUTABLE RULES:
        - Auto mode = shadow only
        - Manual approval required before any report export
        - Cannot bypass integrity checks
        - Cannot disable shadow restriction
    """

    # IMMUTABLE CONSTANTS
    CAN_DISABLE_SHADOW: bool = False
    CAN_AUTO_EXPORT: bool = False
    CAN_BYPASS_INTEGRITY: bool = False
    CAN_AUTO_SUBMIT: bool = False
    REQUIRED_INTEGRITY_SCORE: float = 95.0

    def __init__(self) -> None:
        self._state = AutoModeState()
        self._activation_log: List[dict] = []

    # =======================================================================
    # CONDITION EVALUATION
    # =======================================================================

    def evaluate_conditions(
        self,
        integrity_score: float,
        has_containment_24h: bool,
        drift_stable: bool,
        dataset_balanced: bool,
        storage_healthy: bool,
    ) -> AutoModeCondition:
        """Evaluate all auto-mode preconditions."""
        condition = AutoModeCondition(
            integrity_above_95=(integrity_score >= self.REQUIRED_INTEGRITY_SCORE),
            no_containment_24h=(not has_containment_24h),
            drift_stable=drift_stable,
            dataset_balanced=dataset_balanced,
            storage_healthy=storage_healthy,
        )
        self._state.conditions = condition
        self._state.last_check = datetime.now(timezone.utc).isoformat()
        return condition

    # =======================================================================
    # ACTIVATION CONTROL
    # =======================================================================

    def request_activation(self) -> AutoModeState:
        """Request auto-mode activation. Only activates if all conditions met."""
        if self._state.conditions is None:
            self._log("BLOCKED: Conditions not evaluated")
            return self._state

        if not self._state.conditions.all_conditions_met:
            reasons = "; ".join(self._state.conditions.blocked_reasons)
            self._log(f"BLOCKED: {reasons}")
            self._state.enabled = False
            return self._state

        self._state.enabled = True
        self._state.shadow_only = True  # ALWAYS shadow only
        self._state.export_requires_approval = True  # ALWAYS requires approval
        self._log("ACTIVATED: Auto-mode enabled (shadow only)")
        return self._state

    def deactivate(self) -> AutoModeState:
        """Deactivate auto-mode."""
        self._state.enabled = False
        self._log("DEACTIVATED: Auto-mode disabled")
        return self._state

    def request_export_approval(self, report_id: str,
                                 user_approved: bool) -> bool:
        """Export always requires manual user approval."""
        if not user_approved:
            self._log(f"EXPORT BLOCKED: Report {report_id} — no user approval")
            return False
        self._log(f"EXPORT APPROVED: Report {report_id} — user approved")
        return True

    # =======================================================================
    # STATE ACCESS
    # =======================================================================

    @property
    def state(self) -> AutoModeState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state.enabled

    @property
    def is_shadow_only(self) -> bool:
        return True  # ALWAYS

    @property
    def activation_log(self) -> List[dict]:
        return self._activation_log.copy()

    # =======================================================================
    # INTERNAL
    # =======================================================================

    def _log(self, message: str) -> None:
        self._activation_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message,
        })
