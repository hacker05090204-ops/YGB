"""
mode_state_lock.py — Mode State Lock (Phase 1)

Persistent mode_state.json:
- current_mode: A or B
- consecutive_passes
- last_accuracy
- stability_window
- promotion_locked
"""

import json
import logging
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Optional

logger = logging.getLogger(__name__)

STATE_PATH = os.path.join('secure_data', 'mode_state.json')


@dataclass
class ModeState:
    """Current mode state."""
    current_mode: str = "A"
    consecutive_passes: int = 0
    last_accuracy: float = 0.0
    stability_window: List[float] = field(default_factory=list)
    promotion_locked: bool = False
    last_updated: str = ""
    rollback_count: int = 0


class ModeStateLock:
    """Persistent mode state management.

    Tracks A/B mode, consecutive passes, stability window.
    """

    def __init__(self, state_path: str = STATE_PATH):
        self._path = state_path
        self._state = ModeState()
        self._load()

    def get_state(self) -> ModeState:
        return self._state

    @property
    def mode(self) -> str:
        return self._state.current_mode

    @property
    def consecutive_passes(self) -> int:
        return self._state.consecutive_passes

    def record_pass(self, accuracy: float):
        """Record a successful validation pass."""
        self._state.consecutive_passes += 1
        self._state.last_accuracy = accuracy
        self._state.stability_window.append(accuracy)
        # Keep last 10
        if len(self._state.stability_window) > 10:
            self._state.stability_window = self._state.stability_window[-10:]
        self._state.last_updated = datetime.now().isoformat()
        self._save()
        logger.info(
            f"[MODE_STATE] Pass #{self._state.consecutive_passes}: "
            f"acc={accuracy:.4f} mode={self._state.current_mode}"
        )

    def record_fail(self):
        """Record a failed validation — resets consecutive passes."""
        self._state.consecutive_passes = 0
        self._state.last_updated = datetime.now().isoformat()
        self._save()
        logger.warning("[MODE_STATE] Fail — consecutive passes reset to 0")

    def promote_to_b(self):
        """Promote to MODE B."""
        self._state.current_mode = "B"
        self._state.last_updated = datetime.now().isoformat()
        self._save()
        logger.info("[MODE_STATE] ✓ Promoted to MODE B")

    def rollback_to_a(self, reason: str = ""):
        """Rollback to MODE A."""
        self._state.current_mode = "A"
        self._state.consecutive_passes = 0
        self._state.rollback_count += 1
        self._state.last_updated = datetime.now().isoformat()
        self._save()
        logger.warning(f"[MODE_STATE] ✗ Rolled back to MODE A: {reason}")

    def lock_promotion(self):
        self._state.promotion_locked = True
        self._save()

    def unlock_promotion(self):
        self._state.promotion_locked = False
        self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self._path) or '.', exist_ok=True)
        with open(self._path, 'w') as f:
            json.dump(asdict(self._state), f, indent=2)

    def _load(self):
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    data = json.load(f)
                self._state = ModeState(**data)
            except (json.JSONDecodeError, IOError, TypeError):
                self._state = ModeState()
