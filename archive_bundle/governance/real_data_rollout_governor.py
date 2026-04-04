"""
Real-Data Rollout Governor — Staged rollout of real data into training.

ROLLOUT STAGES:
    Stage 0  →  20% real data
    Stage 1  →  40% real data
    Stage 2  →  70% real data
    Stage 3  → 100% real data

PROMOTION RULES:
    - 3 consecutive stable cycles required per stage
    - Any blocking condition freezes promotion

BLOCKING CONDITIONS (any failure freezes stage):
    - Label quality    < floor (0.90)
    - Class imbalance  > max   (10.0)
    - Distribution shift (JS divergence) > threshold (0.15)
    - Feature mismatch / unknown-token   > threshold (0.05)
    - FPR regression delta               > threshold (0.02)
    - Drift guard failure
    - Regression gate failure
    - Determinism gate failure
    - Backtest gate failure

STATE:
    Persisted as JSON in secure_data/rollout_governor_state.json

OUTPUT:
    Machine-readable dict with stage, metrics, blocking reasons.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any
from pathlib import Path
from datetime import datetime, UTC
import json
import os


# =============================================================================
# CONSTANTS
# =============================================================================

ROLLOUT_STAGES = (0.20, 0.40, 0.70, 1.00)
REQUIRED_STABLE_CYCLES = 3

# Thresholds
LABEL_QUALITY_FLOOR = 0.90
CLASS_IMBALANCE_MAX = 10.0
DISTRIBUTION_SHIFT_THRESHOLD = 0.15
UNKNOWN_TOKEN_THRESHOLD = 0.05
FPR_REGRESSION_DELTA_THRESHOLD = 0.02

STATE_FILE = "secure_data/rollout_governor_state.json"


# =============================================================================
# ENUMS
# =============================================================================

class RolloutStage(Enum):
    """CLOSED ENUM — 4 rollout stages."""
    STAGE_0 = 0   # 20%
    STAGE_1 = 1   # 40%
    STAGE_2 = 2   # 70%
    STAGE_3 = 3   # 100%


class BlockReason(Enum):
    """CLOSED ENUM — blocking conditions."""
    LABEL_QUALITY_LOW = "LABEL_QUALITY_LOW"
    CLASS_IMBALANCE_HIGH = "CLASS_IMBALANCE_HIGH"
    DISTRIBUTION_SHIFT = "DISTRIBUTION_SHIFT"
    FEATURE_MISMATCH = "FEATURE_MISMATCH"
    UNKNOWN_TOKEN_HIGH = "UNKNOWN_TOKEN_HIGH"
    FPR_REGRESSION = "FPR_REGRESSION"
    DRIFT_GUARD_FAIL = "DRIFT_GUARD_FAIL"
    REGRESSION_GATE_FAIL = "REGRESSION_GATE_FAIL"
    DETERMINISM_GATE_FAIL = "DETERMINISM_GATE_FAIL"
    BACKTEST_GATE_FAIL = "BACKTEST_GATE_FAIL"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CycleMetrics:
    """Metrics for a single evaluation cycle."""
    cycle_id: str
    timestamp: str
    label_quality: float
    class_imbalance_ratio: float
    js_divergence: float
    unknown_token_ratio: float
    feature_mismatch_ratio: float
    fpr_current: float
    fpr_baseline: float
    drift_guard_pass: bool
    regression_gate_pass: bool
    determinism_gate_pass: bool
    backtest_gate_pass: bool


@dataclass
class RolloutState:
    """Persisted governance state."""
    current_stage: int = 0
    consecutive_stable_cycles: int = 0
    is_frozen: bool = False
    freeze_reasons: List[str] = field(default_factory=list)
    last_cycle_id: Optional[str] = None
    last_updated: Optional[str] = None
    promotion_history: List[Dict[str, Any]] = field(default_factory=list)
    total_cycles_evaluated: int = 0


# =============================================================================
# BLOCKING CHECK
# =============================================================================

def evaluate_blocking_conditions(metrics: CycleMetrics) -> List[BlockReason]:
    """
    Evaluate all blocking conditions against thresholds.

    Returns list of active blocking reasons (empty = pass).
    """
    reasons: List[BlockReason] = []

    if metrics.label_quality < LABEL_QUALITY_FLOOR:
        reasons.append(BlockReason.LABEL_QUALITY_LOW)

    if metrics.class_imbalance_ratio > CLASS_IMBALANCE_MAX:
        reasons.append(BlockReason.CLASS_IMBALANCE_HIGH)

    if metrics.js_divergence > DISTRIBUTION_SHIFT_THRESHOLD:
        reasons.append(BlockReason.DISTRIBUTION_SHIFT)

    if metrics.feature_mismatch_ratio > UNKNOWN_TOKEN_THRESHOLD:
        reasons.append(BlockReason.FEATURE_MISMATCH)

    if metrics.unknown_token_ratio > UNKNOWN_TOKEN_THRESHOLD:
        reasons.append(BlockReason.UNKNOWN_TOKEN_HIGH)

    fpr_delta = metrics.fpr_current - metrics.fpr_baseline
    if fpr_delta > FPR_REGRESSION_DELTA_THRESHOLD:
        reasons.append(BlockReason.FPR_REGRESSION)

    if not metrics.drift_guard_pass:
        reasons.append(BlockReason.DRIFT_GUARD_FAIL)

    if not metrics.regression_gate_pass:
        reasons.append(BlockReason.REGRESSION_GATE_FAIL)

    if not metrics.determinism_gate_pass:
        reasons.append(BlockReason.DETERMINISM_GATE_FAIL)

    if not metrics.backtest_gate_pass:
        reasons.append(BlockReason.BACKTEST_GATE_FAIL)

    return reasons


# =============================================================================
# STATE PERSISTENCE
# =============================================================================

def _state_path() -> Path:
    """Resolve state file path relative to project root."""
    root = Path(__file__).parent.parent
    return root / STATE_FILE


def load_state() -> RolloutState:
    """Load governance state from secure_data. Returns default if missing."""
    path = _state_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RolloutState(**data)
        except (json.JSONDecodeError, TypeError):
            pass
    return RolloutState()


def save_state(state: RolloutState) -> None:
    """Persist governance state to secure_data."""
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(state), indent=2, default=str),
        encoding="utf-8",
    )


# =============================================================================
# CORE GOVERNANCE
# =============================================================================

def evaluate_cycle(metrics: CycleMetrics, state: Optional[RolloutState] = None) -> Dict[str, Any]:
    """
    Evaluate a single cycle of real-data metrics.

    1. Check all blocking conditions.
    2. If any block → freeze stage, reset stable counter.
    3. If all pass → increment stable counter.
    4. If stable counter reaches threshold → promote stage.
    5. Persist state and return machine-readable result.

    Returns dict with:
        stage, real_data_pct, blocked, blocking_reasons,
        consecutive_stable, promoted, frozen, result_summary
    """
    if state is None:
        state = load_state()

    blocking = evaluate_blocking_conditions(metrics)
    state.total_cycles_evaluated += 1
    state.last_cycle_id = metrics.cycle_id
    state.last_updated = datetime.now(UTC).isoformat()

    promoted = False

    if blocking:
        # Freeze — reset consecutive counter
        state.consecutive_stable_cycles = 0
        state.is_frozen = True
        state.freeze_reasons = [r.value for r in blocking]
    else:
        # Stable cycle
        state.is_frozen = False
        state.freeze_reasons = []
        state.consecutive_stable_cycles += 1

        # Check promotion
        if (
            state.consecutive_stable_cycles >= REQUIRED_STABLE_CYCLES
            and state.current_stage < len(ROLLOUT_STAGES) - 1
        ):
            old_stage = state.current_stage
            state.current_stage += 1
            state.consecutive_stable_cycles = 0
            promoted = True
            state.promotion_history.append({
                "from_stage": old_stage,
                "to_stage": state.current_stage,
                "cycle_id": metrics.cycle_id,
                "timestamp": state.last_updated,
            })

    save_state(state)

    real_pct = ROLLOUT_STAGES[state.current_stage]

    return {
        "stage": state.current_stage,
        "stage_label": f"STAGE_{state.current_stage}",
        "real_data_pct": real_pct,
        "blocked": bool(blocking),
        "blocking_reasons": [r.value for r in blocking],
        "consecutive_stable": state.consecutive_stable_cycles,
        "promoted": promoted,
        "frozen": state.is_frozen,
        "total_cycles": state.total_cycles_evaluated,
        "result_summary": (
            f"Stage {state.current_stage} ({int(real_pct*100)}% real) — "
            + ("PROMOTED" if promoted else "BLOCKED" if blocking else "STABLE")
        ),
    }


def get_current_status() -> Dict[str, Any]:
    """Get current rollout status (read-only, no side effects)."""
    state = load_state()
    real_pct = ROLLOUT_STAGES[state.current_stage]

    return {
        "stage": state.current_stage,
        "stage_label": f"STAGE_{state.current_stage}",
        "real_data_pct": real_pct,
        "consecutive_stable": state.consecutive_stable_cycles,
        "frozen": state.is_frozen,
        "freeze_reasons": state.freeze_reasons,
        "total_cycles": state.total_cycles_evaluated,
        "last_cycle_id": state.last_cycle_id,
        "last_updated": state.last_updated,
        "promotion_history": state.promotion_history,
    }


def reset_state() -> None:
    """Reset governance state (testing only)."""
    path = _state_path()
    if path.exists():
        path.unlink()
