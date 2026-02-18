"""
runtime_mode_controller.py — Train/Hunt Mode Controller

Python orchestration layer for strict TRAIN/HUNT mode separation.
Mirrors native/mode_runtime/mode_lock.cpp logic.

Rules:
  - TRAIN_MODE blocks all external target input
  - HUNT_MODE blocks all weight updates
  - Cannot overlap — transition requires idle state

NO uncontrolled live learning. NO training on real targets.
"""

import json
import logging
from enum import IntEnum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("runtime_mode_controller")

# =========================================================================
# RUNTIME MODE (mirrors C++ mode_lock.cpp)
# =========================================================================

class RuntimeMode(IntEnum):
    IDLE = 0
    TRAIN_MODE = 1
    HUNT_MODE = 2


# =========================================================================
# EXCEPTIONS
# =========================================================================

class ModeOverlapError(Exception):
    """Raised when attempting to enter a mode while another is active."""
    pass


class ModeViolationError(Exception):
    """Raised when an operation violates current mode restrictions."""
    pass


# =========================================================================
# CONTROLLER
# =========================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODE_FILE = PROJECT_ROOT / "reports" / "mode_state.json"


class RuntimeModeController:
    """
    Controls TRAIN/HUNT mode transitions. Enforces mutual exclusion.
    """

    _instance: Optional["RuntimeModeController"] = None

    def __init__(self, mode_file: Optional[Path] = None):
        self._mode_file = mode_file or MODE_FILE
        self._mode = self._load()
        self._active_tasks = 0

    @classmethod
    def get(cls) -> "RuntimeModeController":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_singleton(cls):
        cls._instance = None

    # --- State ---

    @property
    def mode(self) -> RuntimeMode:
        return self._mode

    @property
    def mode_name(self) -> str:
        return self._mode.name

    @property
    def is_idle(self) -> bool:
        return self._mode == RuntimeMode.IDLE

    @property
    def is_training(self) -> bool:
        return self._mode == RuntimeMode.TRAIN_MODE

    @property
    def is_hunting(self) -> bool:
        return self._mode == RuntimeMode.HUNT_MODE

    # --- Permission checks ---

    def can_access_external_targets(self) -> bool:
        """Only allowed in HUNT_MODE."""
        return self._mode == RuntimeMode.HUNT_MODE

    def can_update_weights(self) -> bool:
        """Only allowed in TRAIN_MODE."""
        return self._mode == RuntimeMode.TRAIN_MODE

    # --- Transitions ---

    def start_training(self) -> dict:
        """Enter TRAIN_MODE. Must be IDLE."""
        if self._mode != RuntimeMode.IDLE:
            raise ModeOverlapError(
                f"MODE_OVERLAP_BLOCKED: Cannot enter TRAIN_MODE while in "
                f"{self.mode_name} — must be IDLE first"
            )
        self._mode = RuntimeMode.TRAIN_MODE
        self._save()
        logger.info("MODE_TRANSITION: IDLE -> TRAIN_MODE")
        return {"mode": "TRAIN_MODE", "allowed": True}

    def stop_training(self) -> dict:
        """Return to IDLE from TRAIN_MODE."""
        if self._mode != RuntimeMode.TRAIN_MODE:
            raise ModeViolationError(
                f"Cannot stop training — not in TRAIN_MODE (current: {self.mode_name})"
            )
        if self._active_tasks > 0:
            raise ModeViolationError(
                f"Cannot stop training — {self._active_tasks} active tasks"
            )
        self._mode = RuntimeMode.IDLE
        self._save()
        logger.info("MODE_TRANSITION: TRAIN_MODE -> IDLE")
        return {"mode": "IDLE", "allowed": True}

    def start_hunting(self) -> dict:
        """Enter HUNT_MODE. Must be IDLE."""
        if self._mode != RuntimeMode.IDLE:
            raise ModeOverlapError(
                f"MODE_OVERLAP_BLOCKED: Cannot enter HUNT_MODE while in "
                f"{self.mode_name} — must be IDLE first"
            )
        self._mode = RuntimeMode.HUNT_MODE
        self._save()
        logger.info("MODE_TRANSITION: IDLE -> HUNT_MODE")
        return {"mode": "HUNT_MODE", "allowed": True}

    def stop_hunting(self) -> dict:
        """Return to IDLE from HUNT_MODE."""
        if self._mode != RuntimeMode.HUNT_MODE:
            raise ModeViolationError(
                f"Cannot stop hunting — not in HUNT_MODE (current: {self.mode_name})"
            )
        if self._active_tasks > 0:
            raise ModeViolationError(
                f"Cannot stop hunting — {self._active_tasks} active tasks"
            )
        self._mode = RuntimeMode.IDLE
        self._save()
        logger.info("MODE_TRANSITION: HUNT_MODE -> IDLE")
        return {"mode": "IDLE", "allowed": True}

    # --- Task tracking ---

    def begin_task(self):
        self._active_tasks += 1

    def end_task(self):
        if self._active_tasks > 0:
            self._active_tasks -= 1

    @property
    def active_tasks(self) -> int:
        return self._active_tasks

    # --- Persistence ---

    def _load(self) -> RuntimeMode:
        try:
            if self._mode_file.exists():
                with open(self._mode_file, "r") as f:
                    data = json.load(f)
                return RuntimeMode(data.get("mode", 0))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Could not load mode state: {e}")
        return RuntimeMode.IDLE

    def _save(self):
        self._mode_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._mode_file.with_suffix(".json.tmp")
        with open(tmp, "w") as f:
            json.dump({
                "version": 1,
                "mode": int(self._mode),
                "mode_name": self._mode.name,
            }, f, indent=2)
            f.flush()
        tmp.replace(self._mode_file)

    def reload(self):
        self._mode = self._load()
