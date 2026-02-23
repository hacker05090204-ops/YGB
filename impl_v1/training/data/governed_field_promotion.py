"""
governed_field_promotion.py — Governed Field Promotion (Phase 7)

██████████████████████████████████████████████████████████████████████
BOUNTY-READY — 7-GATE FIELD PROMOTION ENGINE
██████████████████████████████████████████████████████████████████████

7-Gate Promotion Criteria:
  1. Lab accuracy ≥ 95%
  2. Exploit-verified FPR < 1%
  3. 3 consecutive gate passes
  4. 5 stable cycles
  5. Curriculum complete (all 6 stages)
  6. Evidence binding ratio = 100%
  7. No regression > 2% from previous cycle

Safety:
  - Rollback if regression > 2%
  - Freeze on hallucination breach
  - Freeze on deterministic failure
  - No autonomous submission
  - Human approval mandatory
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Promotion thresholds
GATE_ACCURACY = 0.95         # ≥95% lab accuracy
GATE_FPR = 0.01              # <1% false positive rate
GATE_CONSECUTIVE = 3         # 3 consecutive passes
GATE_STABLE_CYCLES = 5       # 5 stable cycles → LIVE_READY
GATE_BINDING_RATIO = 1.0     # 100% evidence binding
GATE_REGRESSION_MAX = 0.02   # Max 2% regression
GATE_CURRICULUM_COMPLETE = True


@dataclass
class GateResult:
    """Result of one gate check."""
    gate_name: str
    passed: bool
    value: float
    threshold: float
    message: str = ""


@dataclass
class PromotionState:
    """Full promotion state."""
    consecutive_passes: int = 0
    stable_cycles: int = 0
    live_ready: bool = False
    frozen: bool = False
    freeze_reason: str = ""
    last_accuracy: float = 0.0
    last_fpr: float = 1.0
    last_binding_ratio: float = 0.0
    total_evaluations: int = 0
    promotion_history: List[str] = field(default_factory=list)
    rollback_count: int = 0


class GovernedFieldPromotion:
    """
    7-gate promotion engine for transitioning to LIVE_READY.

    Gates must be passed sequentially. Any failure resets consecutive count.
    5 stable cycles (all 7 gates passing) → LIVE_READY.

    Safety mechanisms:
      - Automatic rollback on regression > 2%
      - Freeze on hallucination breach (binding < 100%)
      - Freeze on deterministic exploit failure
      - No autonomous submission — ever
    """

    def __init__(self):
        self.state = PromotionState()

    def evaluate_gates(
        self,
        accuracy: float,
        fpr: float,
        binding_ratio: float,
        curriculum_complete: bool,
        deterministic_verified: bool,
        previous_accuracy: Optional[float] = None,
    ) -> Tuple[bool, List[GateResult]]:
        """
        Evaluate all 7 promotion gates.

        Returns:
            (all_passed, list_of_gate_results)
        """
        self.state.total_evaluations += 1
        gates: List[GateResult] = []

        # Gate 1: Lab accuracy ≥ 95%
        gates.append(GateResult(
            gate_name="Lab Accuracy",
            passed=accuracy >= GATE_ACCURACY,
            value=accuracy,
            threshold=GATE_ACCURACY,
            message=f"{accuracy:.2%} {'≥' if accuracy >= GATE_ACCURACY else '<'} {GATE_ACCURACY:.0%}",
        ))

        # Gate 2: FPR < 1%
        gates.append(GateResult(
            gate_name="Exploit-Verified FPR",
            passed=fpr < GATE_FPR,
            value=fpr,
            threshold=GATE_FPR,
            message=f"{fpr:.4%} {'<' if fpr < GATE_FPR else '≥'} {GATE_FPR:.0%}",
        ))

        # Gate 3: Consecutive passes
        gates.append(GateResult(
            gate_name="Consecutive Passes",
            passed=self.state.consecutive_passes >= GATE_CONSECUTIVE - 1,
            value=float(self.state.consecutive_passes + 1),
            threshold=float(GATE_CONSECUTIVE),
            message=f"{self.state.consecutive_passes + 1}/{GATE_CONSECUTIVE}",
        ))

        # Gate 4: Stable cycles
        gates.append(GateResult(
            gate_name="Stable Cycles",
            passed=self.state.stable_cycles >= GATE_STABLE_CYCLES - 1,
            value=float(self.state.stable_cycles + 1),
            threshold=float(GATE_STABLE_CYCLES),
            message=f"{self.state.stable_cycles + 1}/{GATE_STABLE_CYCLES}",
        ))

        # Gate 5: Curriculum complete
        gates.append(GateResult(
            gate_name="Curriculum Complete",
            passed=curriculum_complete,
            value=1.0 if curriculum_complete else 0.0,
            threshold=1.0,
            message="Complete" if curriculum_complete else "Incomplete",
        ))

        # Gate 6: Evidence binding = 100%
        gates.append(GateResult(
            gate_name="Evidence Binding",
            passed=binding_ratio >= GATE_BINDING_RATIO,
            value=binding_ratio,
            threshold=GATE_BINDING_RATIO,
            message=f"{binding_ratio:.2%}",
        ))

        # Gate 7: No regression > 2%
        regression = 0.0
        if previous_accuracy is not None and previous_accuracy > 0:
            regression = previous_accuracy - accuracy
        no_regression = regression <= GATE_REGRESSION_MAX
        gates.append(GateResult(
            gate_name="No Regression",
            passed=no_regression,
            value=regression,
            threshold=GATE_REGRESSION_MAX,
            message=f"{'Δ' if regression > 0 else '='} {regression:.4f}",
        ))

        # ── Safety checks ──

        # Hallucination breach → FREEZE
        if binding_ratio < GATE_BINDING_RATIO:
            self._freeze("Hallucination breach: evidence binding < 100%")

        # Deterministic failure → FREEZE
        if not deterministic_verified:
            self._freeze("Deterministic exploit verification failed")

        # Regression → ROLLBACK
        if regression > GATE_REGRESSION_MAX and previous_accuracy is not None:
            self._rollback(f"Regression: {regression:.4f} > {GATE_REGRESSION_MAX}")

        # ── Verdict ──
        all_passed = all(g.passed for g in gates) and not self.state.frozen

        if all_passed:
            self.state.consecutive_passes += 1
            self.state.stable_cycles += 1
            self.state.last_accuracy = accuracy
            self.state.last_fpr = fpr
            self.state.last_binding_ratio = binding_ratio

            if self.state.stable_cycles >= GATE_STABLE_CYCLES:
                self.state.live_ready = True
                logger.info("[PROMOTION] ✓ LIVE_READY achieved — all 7 gates × 5 cycles")
        else:
            self.state.consecutive_passes = 0
            failed = [g.gate_name for g in gates if not g.passed]
            logger.info(f"[PROMOTION] ✗ Gates failed: {', '.join(failed)}")

        self.state.promotion_history.append(
            f"{datetime.now().isoformat()}: {'PASS' if all_passed else 'FAIL'} "
            f"(acc={accuracy:.2%}, fpr={fpr:.4%}, binding={binding_ratio:.0%})"
        )

        return all_passed, gates

    def _freeze(self, reason: str):
        """Freeze promotion — safety critical failure."""
        if not self.state.frozen:
            self.state.frozen = True
            self.state.freeze_reason = reason
            self.state.consecutive_passes = 0
            self.state.stable_cycles = 0
            self.state.live_ready = False
            logger.error(f"[PROMOTION] ⚠ FROZEN: {reason}")

    def _rollback(self, reason: str):
        """Rollback on regression."""
        self.state.consecutive_passes = 0
        self.state.stable_cycles = max(0, self.state.stable_cycles - 1)
        self.state.rollback_count += 1
        self.state.live_ready = False
        logger.warning(f"[PROMOTION] ← ROLLBACK: {reason}")

    def unfreeze(self, reason: str = "Manual unfreeze"):
        """Manually unfreeze (requires intervention)."""
        self.state.frozen = False
        self.state.freeze_reason = ""
        self.state.consecutive_passes = 0
        self.state.stable_cycles = 0
        logger.info(f"[PROMOTION] Unfrozen: {reason}")

    def is_live_ready(self) -> bool:
        return self.state.live_ready and not self.state.frozen

    def get_summary(self) -> dict:
        """Get promotion summary for API/UI."""
        return {
            "live_ready": self.state.live_ready,
            "frozen": self.state.frozen,
            "freeze_reason": self.state.freeze_reason,
            "consecutive_passes": self.state.consecutive_passes,
            "stable_cycles": self.state.stable_cycles,
            "required_passes": GATE_CONSECUTIVE,
            "required_cycles": GATE_STABLE_CYCLES,
            "last_accuracy": self.state.last_accuracy,
            "last_fpr": self.state.last_fpr,
            "total_evaluations": self.state.total_evaluations,
            "rollback_count": self.state.rollback_count,
        }
