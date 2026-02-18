"""
mode_orchestrator.py — Lifecycle Phase Gate Enforcement

Prevents backward phase execution or re-trigger of Phase 1-7 after freeze.
Loads persisted phase state from reports/phase_state.json.

Rules:
  - Phase number can only increase.
  - Attempted backward execution logs LIFECYCLE_VIOLATION.
  - Frozen state blocks training, baseline recalculation, and all phase routines.

NO weight modification. NO authority change. NO governance change.
"""

import os
import json
import logging
from enum import IntEnum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mode_orchestrator")

# =========================================================================
# PHASE STATE ENUM (mirrors C++ phase_state_engine.cpp)
# =========================================================================

class PhaseState(IntEnum):
    PHASE_1_COMPLETE = 1
    PHASE_2_COMPLETE = 2
    PHASE_3_COMPLETE = 3
    PHASE_4_COMPLETE = 4
    PHASE_5_COMPLETE = 5
    PHASE_6_COMPLETE = 6
    PHASE_7_COMPLETE = 7
    PHASE_MODE_A_FROZEN = 10
    PHASE_MODE_B_SHADOW = 11
    PHASE_MODE_C_LAB = 12


# =========================================================================
# LIFECYCLE VIOLATION
# =========================================================================

class LifecycleViolation(Exception):
    """Raised when a backward phase transition is attempted."""
    pass


# =========================================================================
# MODE ORCHESTRATOR
# =========================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
STATE_FILE = PROJECT_ROOT / "reports" / "phase_state.json"


class ModeOrchestrator:
    """
    Lifecycle guard. Loads phase state and enforces one-way transitions.
    No weight modification. No authority change. No governance change.
    """

    # Singleton pattern — only one orchestrator per process
    _instance: Optional["ModeOrchestrator"] = None

    def __init__(self, state_file: Optional[Path] = None):
        self._state_file = state_file or STATE_FILE
        self._current = self._load()

    @classmethod
    def get(cls) -> "ModeOrchestrator":
        """Get or create singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_singleton(cls):
        """Reset singleton (for testing only)."""
        cls._instance = None

    # -----------------------------------------------------------------
    # STATE ACCESS
    # -----------------------------------------------------------------

    @property
    def current(self) -> PhaseState:
        return self._current

    @property
    def current_name(self) -> str:
        return self._current.name

    def is_frozen(self) -> bool:
        """Returns True if system is in MODE_A_FROZEN."""
        return self._current == PhaseState.PHASE_MODE_A_FROZEN

    # -----------------------------------------------------------------
    # PHASE GATE CHECK
    # -----------------------------------------------------------------

    def check_phase_gate(self, requested_phase: int) -> bool:
        """
        Check if a phase routine is allowed to execute.

        Args:
            requested_phase: Phase number (1-7) being requested.

        Returns:
            True if allowed.

        Raises:
            LifecycleViolation if backward execution is attempted.
        """
        if requested_phase < 1 or requested_phase > 7:
            raise LifecycleViolation(
                f"LIFECYCLE_VIOLATION: Invalid phase {requested_phase}"
            )

        # Frozen → no phase 1-7 routines at all
        if self.is_frozen():
            msg = (
                f"LIFECYCLE_VIOLATION: Phase {requested_phase} blocked — "
                f"system is FROZEN (state={self.current_name})"
            )
            logger.warning(msg)
            raise LifecycleViolation(msg)

        # Backward execution blocked
        if requested_phase < self._current.value:
            msg = (
                f"PHASE_REENTRY_BLOCKED: Phase {requested_phase} < "
                f"current {self.current_name}({self._current.value}) — "
                f"backward execution denied"
            )
            logger.warning(msg)
            raise LifecycleViolation(msg)

        return True

    def is_training_allowed(self) -> bool:
        """Returns True if training scheduler re-init is allowed."""
        return not self.is_frozen()

    def is_baseline_recalc_allowed(self) -> bool:
        """Returns True if baseline recalculation is allowed."""
        return not self.is_frozen()

    # -----------------------------------------------------------------
    # PERSISTENCE
    # -----------------------------------------------------------------

    def _load(self) -> PhaseState:
        """Load phase state from JSON file. Missing → baseline."""
        try:
            if self._state_file.exists():
                with open(self._state_file, "r") as f:
                    data = json.load(f)
                val = data.get("phase_state", 1)
                return PhaseState(val)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Could not load phase state: {e}. Using baseline.")
        return PhaseState.PHASE_1_COMPLETE

    def reload(self):
        """Reload from disk (for cross-process sync)."""
        self._current = self._load()
