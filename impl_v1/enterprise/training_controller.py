"""
Training Controller (Python Governance)
========================================

Modes:
- DISABLED
- MANUAL_CONTINUOUS
- SCHEDULED
- SAFE_IDLE

API:
- POST /train/start
- POST /train/stop
- GET  /train/status

C++ = performance execution
Python = governance and control only
"""

from dataclasses import dataclass
from typing import Optional, Tuple
from datetime import datetime
from enum import Enum
from pathlib import Path
import json
import threading


# =============================================================================
# TRAINING MODES
# =============================================================================

class TrainingMode(Enum):
    """Training operation modes."""
    DISABLED = "disabled"
    MANUAL_CONTINUOUS = "manual_continuous"
    SCHEDULED = "scheduled"
    SAFE_IDLE = "safe_idle"


# =============================================================================
# TRAINING STATUS
# =============================================================================

@dataclass
class TrainingStatus:
    """Current training status."""
    mode: TrainingMode
    is_running: bool
    current_epoch: int
    total_epochs: int
    last_checkpoint: Optional[str]
    started_at: Optional[str]
    stopped_at: Optional[str]


# =============================================================================
# TRAINING CONTROLLER
# =============================================================================

class TrainingController:
    """Python governance layer for training control."""
    
    STATE_FILE = Path("reports/training_state.json")
    CHECKPOINT_INTERVAL = 5  # epochs
    
    def __init__(self):
        self.mode = TrainingMode.SAFE_IDLE
        self.is_running = False
        self.current_epoch = 0
        self.total_epochs = 0
        self.last_checkpoint = None
        self.started_at = None
        self.stopped_at = None
        self._lock = threading.Lock()
        self._load_state()
    
    def _load_state(self) -> None:
        """Load state from file."""
        if self.STATE_FILE.exists():
            try:
                with open(self.STATE_FILE, "r") as f:
                    data = json.load(f)
                self.mode = TrainingMode(data.get("mode", "safe_idle"))
                self.last_checkpoint = data.get("last_checkpoint")
            except Exception:
                pass
    
    def _save_state(self) -> None:
        """Save state to file."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.STATE_FILE, "w") as f:
            json.dump({
                "mode": self.mode.value,
                "is_running": self.is_running,
                "current_epoch": self.current_epoch,
                "last_checkpoint": self.last_checkpoint,
                "started_at": self.started_at,
                "stopped_at": self.stopped_at,
                "updated": datetime.now().isoformat(),
            }, f, indent=2)
    
    # =========================================================================
    # GOVERNANCE CHECKS
    # =========================================================================
    
    def _check_governance(self) -> Tuple[bool, str]:
        """Check if training is allowed by governance."""
        try:
            from impl_v1.governance.model_registry import ModelRegistry
            from impl_v1.governance.governance_controller import OperationalGovernanceController
            
            # Check model registered
            registry = ModelRegistry()
            active = registry.get_active_model()
            if not active:
                return False, "No registered model"
            
            # Check governance
            controller = OperationalGovernanceController()
            safe, reason = controller.get_auto_mode_safe()
            if not safe:
                return False, reason
            
            return True, "Governance valid"
        
        except Exception as e:
            return False, f"Governance check failed: {e}"
    
    def _check_thermal(self) -> Tuple[bool, str]:
        """Check thermal limits."""
        try:
            from impl_v1.training.monitoring.gpu_thermal_monitor import GPUThermalMonitor
            
            monitor = GPUThermalMonitor()
            status = monitor.get_gpu_status()
            
            if status.temperature_c > 83:
                return False, f"GPU too hot: {status.temperature_c}°C"
            
            return True, "Thermal OK"
        except Exception:
            return True, "Thermal check skipped"
    
    # =========================================================================
    # API METHODS
    # =========================================================================
    
    def start(self, mode: TrainingMode = TrainingMode.MANUAL_CONTINUOUS) -> Tuple[bool, str]:
        """
        POST /train/start
        
        Start training with specified mode.
        """
        with self._lock:
            if self.is_running:
                return False, "Training already running"
            
            if mode == TrainingMode.DISABLED:
                return False, "Cannot start in DISABLED mode"
            
            # Governance check
            allowed, reason = self._check_governance()
            if not allowed:
                return False, f"Start rejected: {reason}"
            
            # Thermal check
            thermal_ok, thermal_msg = self._check_thermal()
            if not thermal_ok:
                return False, f"Start rejected: {thermal_msg}"
            
            self.mode = mode
            self.is_running = True
            self.current_epoch = 0
            self.started_at = datetime.now().isoformat()
            self.stopped_at = None
            
            self._save_state()
            
            return True, f"Training started in {mode.value} mode"
    
    def stop(self) -> Tuple[bool, str]:
        """
        POST /train/stop
        
        Stop training gracefully.
        """
        with self._lock:
            if not self.is_running:
                return False, "Training not running"
            
            self.is_running = False
            self.stopped_at = datetime.now().isoformat()
            self.mode = TrainingMode.SAFE_IDLE
            
            self._save_state()
            
            return True, "Training stopped"
    
    def get_status(self) -> TrainingStatus:
        """
        GET /train/status
        
        Get current training status.
        """
        with self._lock:
            return TrainingStatus(
                mode=self.mode,
                is_running=self.is_running,
                current_epoch=self.current_epoch,
                total_epochs=self.total_epochs,
                last_checkpoint=self.last_checkpoint,
                started_at=self.started_at,
                stopped_at=self.stopped_at,
            )
    
    # =========================================================================
    # EPOCH CALLBACKS
    # =========================================================================
    
    def on_epoch_complete(self, epoch: int) -> Tuple[bool, str]:
        """Called after each epoch completes."""
        with self._lock:
            self.current_epoch = epoch
            
            # Check if should checkpoint
            if epoch % self.CHECKPOINT_INTERVAL == 0:
                self._create_checkpoint(epoch)
            
            # Re-check thermal
            thermal_ok, msg = self._check_thermal()
            if not thermal_ok:
                self.is_running = False
                self.mode = TrainingMode.SAFE_IDLE
                self._save_state()
                return False, f"Training paused: {msg}"
            
            self._save_state()
            return True, "Continue"
    
    def _create_checkpoint(self, epoch: int) -> str:
        """Create checkpoint."""
        checkpoint_name = f"ckpt_epoch_{epoch:05d}"
        self.last_checkpoint = checkpoint_name
        return checkpoint_name
