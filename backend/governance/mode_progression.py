"""
Mode Progression Controller — Chained A → B → C Gate Logic.

MODE-A: Representation only (frozen foundation)
MODE-B: Shadow validation only (no live decisions)
MODE-C: Lab autonomy only (sandboxed, never production)

RULES:
  - Automatic progression ONLY if ALL gate metrics pass
  - Each mode has specific entry requirements
  - Regression is always allowed (C→B, B→A)
  - No mode can bypass governance
  - All transitions are logged

GOVERNANCE: Zero authority unlock at any mode level.
"""
import json
import os
import logging
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger(__name__)


# =========================================================================
# MODE ENUM
# =========================================================================

class OperatingMode(Enum):
    """CLOSED ENUM — 3 modes only. No extension allowed."""
    MODE_A = "MODE_A"  # Representation only
    MODE_B = "MODE_B"  # Shadow validation
    MODE_C = "MODE_C"  # Lab autonomy


# =========================================================================
# GATE METRICS
# =========================================================================

@dataclass
class GateMetrics:
    """Required metrics for mode transition. All must pass."""
    accuracy: float = 0.0           # ≥ 0.95 for B, ≥ 0.97 for C
    ece: float = 1.0                # ≤ 0.02 for B, ≤ 0.015 for C
    drift_stable: bool = False      # No drift detected
    no_containment_24h: bool = False # No containment events
    determinism_proven: bool = False # Replay determinism passed
    long_run_stable: bool = False   # 24h stability passed
    calibration_passed: bool = False # Deep audit passed
    integrity_score: float = 0.0    # ≥ 95 for B, ≥ 98 for C
    precision_above_threshold: float = 0.0  # ≥ 0.95 for B, ≥ 0.97 for C
    scope_engine_accuracy: float = 0.0      # ≥ 0.95 for B, ≥ 0.98 for C


# =========================================================================
# GATE THRESHOLDS
# =========================================================================

# MODE-A → MODE-B: shadow validation entry
GATE_A_TO_B = {
    "min_accuracy": 0.95,
    "max_ece": 0.02,
    "min_integrity": 95.0,
    "require_drift_stable": True,
    "require_no_containment": True,
    "require_determinism": True,
    "require_long_run_stable": True,
    "require_calibration": True,
    "min_precision": 0.95,
    "min_scope_accuracy": 0.95,
}

# MODE-B → MODE-C: lab autonomy entry (stricter)
GATE_B_TO_C = {
    "min_accuracy": 0.97,
    "max_ece": 0.015,
    "min_integrity": 98.0,
    "require_drift_stable": True,
    "require_no_containment": True,
    "require_determinism": True,
    "require_long_run_stable": True,
    "require_calibration": True,
    "min_precision": 0.97,
    "min_scope_accuracy": 0.98,
}

# =========================================================================
# GATE DECISION
# =========================================================================

@dataclass
class GateDecision:
    """Result of a mode gate evaluation."""
    current_mode: str
    target_mode: str
    approved: bool
    reasons: List[str] = field(default_factory=list)
    metrics_snapshot: dict = field(default_factory=dict)
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# =========================================================================
# TRANSITION LOG ENTRY
# =========================================================================

@dataclass
class TransitionEntry:
    from_mode: str
    to_mode: str
    approved: bool
    reasons: List[str]
    timestamp: str


# =========================================================================
# MODE PROGRESSION CONTROLLER
# =========================================================================

class ModeProgressionController:
    """Controls mode transitions with governance gates.

    IMMUTABLE RULES:
        - No mode has decision authority
        - All transitions require ALL gate metrics to pass
        - Regression is always allowed
        - MODE-C is lab-only, never production
        - Transitions are always logged
    """

    # IMMUTABLE — these can NEVER be changed
    CAN_UNLOCK_AUTHORITY: bool = False
    CAN_SKIP_GATES: bool = False
    CAN_ENTER_PRODUCTION: bool = False

    def __init__(self):
        self._current_mode = OperatingMode.MODE_A
        self._transition_log: List[TransitionEntry] = []
        self._last_metrics: Optional[GateMetrics] = None

    # =======================================================================
    # CURRENT STATE
    # =======================================================================

    @property
    def current_mode(self) -> OperatingMode:
        return self._current_mode

    @property
    def mode_name(self) -> str:
        return self._current_mode.value

    @property
    def transition_log(self) -> List[dict]:
        return [asdict(e) for e in self._transition_log]

    # =======================================================================
    # GATE EVALUATION
    # =======================================================================

    def evaluate_gate(self, metrics: GateMetrics,
                      target: OperatingMode) -> GateDecision:
        """Evaluate whether transition to target mode is allowed."""
        self._last_metrics = metrics

        decision = GateDecision(
            current_mode=self._current_mode.value,
            target_mode=target.value,
            approved=False,
            metrics_snapshot=asdict(metrics),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Regression is always allowed
        if self._mode_order(target) < self._mode_order(self._current_mode):
            decision.approved = True
            decision.reasons.append("Regression allowed")
            return decision

        # Same mode — no-op
        if target == self._current_mode:
            decision.approved = True
            decision.reasons.append("Already in target mode")
            return decision

        # Forward transition — select thresholds
        if self._current_mode == OperatingMode.MODE_A and \
                target == OperatingMode.MODE_B:
            thresholds = GATE_A_TO_B
        elif self._current_mode == OperatingMode.MODE_B and \
                target == OperatingMode.MODE_C:
            thresholds = GATE_B_TO_C
        elif self._current_mode == OperatingMode.MODE_A and \
                target == OperatingMode.MODE_C:
            # Cannot skip B — must go A→B→C
            decision.reasons.append("Cannot skip MODE-B (must advance sequentially)")
            return decision
        else:
            decision.reasons.append("Invalid transition")
            return decision

        # Check all gate metrics
        failures = []

        if metrics.accuracy < thresholds["min_accuracy"]:
            failures.append(
                f"Accuracy {metrics.accuracy:.4f} < {thresholds['min_accuracy']}"
            )

        if metrics.ece > thresholds["max_ece"]:
            failures.append(
                f"ECE {metrics.ece:.4f} > {thresholds['max_ece']}"
            )

        if metrics.integrity_score < thresholds["min_integrity"]:
            failures.append(
                f"Integrity {metrics.integrity_score:.1f} < {thresholds['min_integrity']}"
            )

        if thresholds["require_drift_stable"] and not metrics.drift_stable:
            failures.append("Drift not stable")

        if thresholds["require_no_containment"] and \
                not metrics.no_containment_24h:
            failures.append("Containment event in 24h")

        if thresholds["require_determinism"] and \
                not metrics.determinism_proven:
            failures.append("Determinism not proven")

        if thresholds["require_long_run_stable"] and \
                not metrics.long_run_stable:
            failures.append("Long-run stability not proven")

        if thresholds["require_calibration"] and \
                not metrics.calibration_passed:
            failures.append("Calibration audit not passed")

        if metrics.precision_above_threshold < thresholds.get("min_precision", 0.0):
            failures.append(
                f"Precision {metrics.precision_above_threshold:.4f} < "
                f"{thresholds['min_precision']}"
            )

        if metrics.scope_engine_accuracy < thresholds.get("min_scope_accuracy", 0.0):
            failures.append(
                f"Scope engine accuracy {metrics.scope_engine_accuracy:.4f} < "
                f"{thresholds['min_scope_accuracy']}"
            )

        if failures:
            decision.reasons = failures
            decision.approved = False
        else:
            decision.approved = True
            decision.reasons.append("All gate metrics passed")

        return decision

    # =======================================================================
    # TRANSITION
    # =======================================================================

    def request_transition(self, metrics: GateMetrics,
                           target: OperatingMode) -> GateDecision:
        """Request mode transition. Only succeeds if gate passes."""
        decision = self.evaluate_gate(metrics, target)

        entry = TransitionEntry(
            from_mode=self._current_mode.value,
            to_mode=target.value,
            approved=decision.approved,
            reasons=decision.reasons,
            timestamp=decision.timestamp,
        )
        self._transition_log.append(entry)

        if decision.approved:
            self._current_mode = target
            logger.info(f"MODE TRANSITION: {entry.from_mode} → {target.value}")
        else:
            logger.warning(
                f"MODE TRANSITION BLOCKED: {entry.from_mode} → {target.value}"
                f" — {'; '.join(decision.reasons)}"
            )

        return decision

    def regress_to(self, target: OperatingMode) -> GateDecision:
        """Regress to a lower mode (always allowed)."""
        return self.request_transition(
            self._last_metrics or GateMetrics(),
            target
        )

    # =======================================================================
    # MODE CAPABILITY QUERIES
    # =======================================================================

    def can_expand_representation(self) -> bool:
        """All modes can expand representation."""
        return True

    def can_shadow_validate(self) -> bool:
        """Only MODE-B and MODE-C."""
        return self._current_mode in (
            OperatingMode.MODE_B, OperatingMode.MODE_C
        )

    def can_lab_autonomy(self) -> bool:
        """Only MODE-C."""
        return self._current_mode == OperatingMode.MODE_C

    def can_production_autonomy(self) -> bool:
        """NEVER. Production autonomy is permanently disabled."""
        return False  # IMMUTABLE

    def can_unlock_authority(self) -> bool:
        """NEVER. Authority unlock is permanently disabled."""
        return False  # IMMUTABLE

    # =======================================================================
    # SAVE/LOAD STATE
    # =======================================================================

    def save_state(self, path: str):
        """Save current mode state to file."""
        state = {
            "current_mode": self._current_mode.value,
            "transition_log": self.transition_log,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)

    def load_state(self, path: str):
        """Load mode state from file."""
        try:
            with open(path) as f:
                state = json.load(f)
            mode_str = state.get("current_mode", "MODE_A")
            self._current_mode = OperatingMode(mode_str)
        except Exception:
            self._current_mode = OperatingMode.MODE_A

    # =======================================================================
    # INTERNAL
    # =======================================================================

    @staticmethod
    def _mode_order(mode: OperatingMode) -> int:
        return {
            OperatingMode.MODE_A: 0,
            OperatingMode.MODE_B: 1,
            OperatingMode.MODE_C: 2,
        }.get(mode, 0)
