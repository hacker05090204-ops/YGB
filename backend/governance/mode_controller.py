"""
mode_controller.py — LAB/HUNT Mode Controller

Enforces strict separation between LAB training and HUNT execution modes.
No weight modification during hunt. No auto-submit. No authority unlock.
"""

import json
import os
from enum import Enum
from typing import Optional

class RuntimeMode(str, Enum):
    IDLE = "IDLE"
    LAB = "LAB"
    HUNT = "HUNT"

class ModeController:
    """Controls LAB/HUNT mode transitions with strict isolation."""
    
    ALLOW_AUTO_SUBMIT = False
    ALLOW_AUTHORITY_UNLOCK = False
    
    def __init__(self, state_path: str = "reports/runtime_mode.json"):
        self._mode = RuntimeMode.IDLE
        self._state_path = state_path
        self._transitions = 0
        self._load_state()
    
    @property
    def mode(self) -> RuntimeMode:
        return self._mode
    
    def enter_lab(self) -> dict:
        """Enter LAB training mode. Blocks if currently in HUNT."""
        if self._mode == RuntimeMode.HUNT:
            return {"allowed": False, "reason": "BLOCKED: Cannot enter LAB while in HUNT mode"}
        if self._mode == RuntimeMode.LAB:
            return {"allowed": False, "reason": "ALREADY_IN_LAB"}
        
        self._mode = RuntimeMode.LAB
        self._transitions += 1
        self._persist()
        return {"allowed": True, "reason": "MODE_TRANSITION: IDLE -> LAB"}
    
    def enter_hunt(self) -> dict:
        """Enter HUNT mode. Blocks if currently in LAB."""
        if self._mode == RuntimeMode.LAB:
            return {"allowed": False, "reason": "BLOCKED: Cannot enter HUNT while in LAB mode"}
        if self._mode == RuntimeMode.HUNT:
            return {"allowed": False, "reason": "ALREADY_IN_HUNT"}
        
        self._mode = RuntimeMode.HUNT
        self._transitions += 1
        self._persist()
        return {"allowed": True, "reason": "MODE_TRANSITION: IDLE -> HUNT"}
    
    def return_to_idle(self) -> dict:
        """Return to IDLE state."""
        prev = self._mode
        self._mode = RuntimeMode.IDLE
        self._transitions += 1
        self._persist()
        return {"allowed": True, "reason": f"MODE_TRANSITION: {prev.value} -> IDLE"}
    
    def is_training_allowed(self) -> bool:
        """Weight modification only allowed in LAB mode."""
        return self._mode == RuntimeMode.LAB
    
    def is_hunting_allowed(self) -> bool:
        """Hunting only allowed in HUNT mode."""
        return self._mode == RuntimeMode.HUNT
    
    def _persist(self):
        """Atomic state persistence."""
        tmp = self._state_path + ".tmp"
        data = {
            "mode": self._mode.value,
            "transitions": self._transitions,
            "auto_submit": self.ALLOW_AUTO_SUBMIT,
            "authority_unlock": self.ALLOW_AUTHORITY_UNLOCK
        }
        os.makedirs(os.path.dirname(self._state_path) or ".", exist_ok=True)
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self._state_path)
    
    def _load_state(self):
        """Load persisted state if exists."""
        if os.path.exists(self._state_path):
            try:
                with open(self._state_path) as f:
                    data = json.load(f)
                self._mode = RuntimeMode(data.get("mode", "IDLE"))
                self._transitions = data.get("transitions", 0)
            except (json.JSONDecodeError, ValueError):
                self._mode = RuntimeMode.IDLE
