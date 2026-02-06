"""
Auto-Mode Unlock Controller - Safe Training
=============================================

Final gate for auto-mode activation:
- Accuracy ≥ 97%
- ECE ≤ 0.02
- Brier ≤ 0.03
- 10 stable epochs
- No drift events
- 50+ checkpoints
- Deterministic replay verified
"""

from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from datetime import datetime
from pathlib import Path
import json


# =============================================================================
# AUTO-MODE STATE
# =============================================================================

@dataclass
class AutoModeState:
    """Current auto-mode state."""
    unlocked: bool
    reason: str
    unlock_time: Optional[str]
    requirements_met: Dict[str, bool]


# =============================================================================
# AUTO-MODE CONTROLLER
# =============================================================================

class AutoModeController:
    """Controller for auto-mode unlock."""
    
    STATE_FILE = Path("reports/auto_mode_state.json")
    
    # Minimum requirements
    MIN_ACCURACY = 0.97
    MIN_ECE = 0.02
    MAX_BRIER = 0.03
    MIN_STABLE_EPOCHS = 10
    MIN_CHECKPOINTS = 50
    
    def __init__(self):
        self.state = self._load_state()
    
    def _load_state(self) -> AutoModeState:
        """Load state from file."""
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE, "r") as f:
                    data = json.load(f)
                return AutoModeState(**data)
            except Exception:
                pass
        
        return AutoModeState(
            unlocked=False,
            reason="Not yet evaluated",
            unlock_time=None,
            requirements_met={},
        )
    
    def _save_state(self) -> None:
        """Save state to file."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.STATE_FILE, "w") as f:
            json.dump({
                "unlocked": self.state.unlocked,
                "reason": self.state.reason,
                "unlock_time": self.state.unlock_time,
                "requirements_met": self.state.requirements_met,
            }, f, indent=2)
    
    def evaluate_unlock(
        self,
        accuracy: float,
        ece: float,
        brier: float,
        stable_epochs: int,
        drift_events: int,
        checkpoint_count: int,
        replay_verified: bool,
    ) -> AutoModeState:
        """
        Evaluate all requirements for auto-mode unlock.
        
        Returns current state after evaluation.
        """
        requirements = {
            "accuracy_≥97%": accuracy >= self.MIN_ACCURACY,
            "ece_≤0.02": ece <= self.MIN_ECE,
            "brier_≤0.03": brier <= self.MAX_BRIER,
            "stable_epochs_≥10": stable_epochs >= self.MIN_STABLE_EPOCHS,
            "no_drift_events": drift_events == 0,
            "checkpoints_≥50": checkpoint_count >= self.MIN_CHECKPOINTS,
            "replay_verified": replay_verified,
        }
        
        all_met = all(requirements.values())
        
        if all_met:
            self.state = AutoModeState(
                unlocked=True,
                reason="ALL REQUIREMENTS MET - AUTO MODE SAFE = TRUE",
                unlock_time=datetime.now().isoformat(),
                requirements_met=requirements,
            )
        else:
            failed = [k for k, v in requirements.items() if not v]
            self.state = AutoModeState(
                unlocked=False,
                reason=f"Requirements not met: {', '.join(failed)}",
                unlock_time=None,
                requirements_met=requirements,
            )
        
        self._save_state()
        return self.state
    
    def is_unlocked(self) -> bool:
        """Check if auto-mode is unlocked."""
        return self.state.unlocked
    
    def lock(self, reason: str) -> None:
        """Lock auto-mode (e.g., due to drift)."""
        self.state = AutoModeState(
            unlocked=False,
            reason=f"LOCKED: {reason}",
            unlock_time=None,
            requirements_met=self.state.requirements_met,
        )
        self._save_state()
    
    def get_status_report(self) -> dict:
        """Get full status report."""
        return {
            "auto_mode_safe": self.state.unlocked,
            "reason": self.state.reason,
            "unlock_time": self.state.unlock_time,
            "requirements": self.state.requirements_met,
            "threshold_summary": {
                "accuracy": f"≥ {self.MIN_ACCURACY:.0%}",
                "ece": f"≤ {self.MIN_ECE}",
                "brier": f"≤ {self.MAX_BRIER}",
                "stable_epochs": f"≥ {self.MIN_STABLE_EPOCHS}",
                "checkpoints": f"≥ {self.MIN_CHECKPOINTS}",
            },
        }


# =============================================================================
# FINAL DECLARATION
# =============================================================================

def declare_auto_mode_status() -> str:
    """Generate final auto-mode declaration."""
    controller = AutoModeController()
    
    if controller.is_unlocked():
        return "AUTO MODE SAFE = TRUE"
    else:
        return f"AUTO MODE SAFE = FALSE ({controller.state.reason})"
