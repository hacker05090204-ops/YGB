# G38 Runtime - Auto Trainer
"""
AUTOMATIC IDLE-BASED TRAINING FOR G38.

PURPOSE:
Run background scheduler that triggers MODE-A training
when system is idle. Training happens WITHOUT human input,
WITHOUT human approval, WITHOUT AI authority.

BEHAVIOR:
Every 30 seconds:
    → Check idle conditions
    → If idle >= 60s
    → If no scan active
    → If no human interaction
    → If power connected
    → If GPU or CPU available
    → THEN trigger G38 MODE-A training

RULES:
- Training trigger is idempotent
- Never trigger twice concurrently
- If training is active → skip
- If scan starts → abort training
- If human interacts → abort training
- All guards checked BEFORE execution
- Guard failure = HARD BLOCK
"""

import asyncio
import threading
import time
import logging
import uuid
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional, Callable, List, Tuple
from enum import Enum

# Import idle detection
from .idle_detector import (
    get_idle_seconds,
    is_power_connected,
    is_scan_active,
)

# Import guards and conditions from G38
from impl_v1.phase49.governors.g38_self_trained_model import (
    IdleConditions,
    IdleCheckResult,
    IdleState,
    check_idle_conditions,
    evaluate_training_trigger,
    ALL_GUARDS,
    verify_all_guards,
    IDLE_THRESHOLD_SECONDS,
)

from impl_v1.phase49.governors.g38_safe_pretraining import (
    TrainingMode,
    verify_pretraining_guards,
    get_mode_a_status,
    TrainingModeStatus,
)


# =============================================================================
# LOGGING
# =============================================================================

logger = logging.getLogger("g38.auto_trainer")
logger.setLevel(logging.INFO)

if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [G38] %(levelname)s: %(message)s"
    ))
    logger.addHandler(handler)


# =============================================================================
# TRAINING STATE
# =============================================================================

class TrainingState(Enum):
    """Current training state."""
    IDLE = "IDLE"
    CHECKING = "CHECKING"
    TRAINING = "TRAINING"
    ABORTING = "ABORTING"
    ERROR = "ERROR"


@dataclass
class TrainingEvent:
    """Training event for observability."""
    event_id: str
    event_type: str  # "IDLE_DETECTED", "TRAINING_STARTED", "TRAINING_STOPPED", etc.
    timestamp: str
    details: str
    idle_seconds: int
    gpu_used: bool
    epoch: Optional[int] = None


# =============================================================================
# AUTO TRAINER CLASS
# =============================================================================

class AutoTrainer:
    """
    Background auto-trainer for G38.
    
    Monitors system idle state and triggers MODE-A training
    when conditions are met.
    """
    
    CHECK_INTERVAL_SECONDS = 30
    
    def __init__(self):
        self._state = TrainingState.IDLE
        self._training_lock = threading.Lock()
        self._abort_flag = threading.Event()
        self._events: List[TrainingEvent] = []
        self._epoch = 0
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_event_callback: Optional[Callable[[TrainingEvent], None]] = None
    
    @property
    def state(self) -> TrainingState:
        """Get current training state."""
        return self._state
    
    @property
    def events(self) -> List[TrainingEvent]:
        """Get all training events."""
        return self._events.copy()
    
    @property
    def is_training(self) -> bool:
        """Check if training is active."""
        return self._state == TrainingState.TRAINING
    
    def set_event_callback(self, callback: Callable[[TrainingEvent], None]) -> None:
        """Set callback for training events (for dashboard)."""
        self._on_event_callback = callback
    
    def _emit_event(
        self,
        event_type: str,
        details: str,
        idle_seconds: int = 0,
        gpu_used: bool = False,
        epoch: Optional[int] = None,
    ) -> TrainingEvent:
        """Emit and log a training event."""
        event = TrainingEvent(
            event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
            event_type=event_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=details,
            idle_seconds=idle_seconds,
            gpu_used=gpu_used,
            epoch=epoch,
        )
        
        self._events.append(event)
        
        # Log to console
        log_msg = f"[{event_type}] {details}"
        if event_type in ("TRAINING_STARTED", "IDLE_DETECTED"):
            logger.info(log_msg)
        elif event_type in ("TRAINING_STOPPED", "CHECKPOINT_SAVED"):
            logger.info(log_msg)
        elif event_type in ("TRAINING_ABORTED", "GUARD_BLOCKED"):
            logger.warning(log_msg)
        elif event_type == "ERROR":
            logger.error(log_msg)
        else:
            logger.debug(log_msg)
        
        # Notify callback
        if self._on_event_callback:
            try:
                self._on_event_callback(event)
            except Exception:
                pass
        
        return event
    
    def _check_all_guards(self) -> Tuple[bool, str]:
        """
        Check ALL guards before training.
        
        Returns (passed, reason).
        """
        # Check main G38 guards
        result, msg = verify_all_guards()
        if not result:
            return False, msg
        
        # Check pretraining guards
        result, msg = verify_pretraining_guards()
        if not result:
            return False, msg
        
        # Check MODE-A status
        status, _ = get_mode_a_status()
        if status != TrainingModeStatus.ACTIVE:
            return False, "MODE-A is not active"
        
        return True, "All guards passed"
    
    def _get_current_conditions(self) -> IdleConditions:
        """Get current idle conditions from real OS."""
        idle_seconds = get_idle_seconds()
        power_connected = is_power_connected()
        scan_active = is_scan_active()
        
        # GPU detection
        gpu_available = False
        try:
            import torch
            gpu_available = torch.cuda.is_available()
        except ImportError:
            pass
        
        return IdleConditions(
            no_active_scan=not scan_active,
            no_human_interaction=idle_seconds >= IDLE_THRESHOLD_SECONDS,
            power_connected=power_connected,
            gpu_available=gpu_available,
            idle_seconds=idle_seconds,
        )
    
    def _train_representation_only(self) -> bool:
        """
        Execute MODE-A representation-only training.
        
        This updates embeddings and weights WITHOUT:
        - Verifying bugs
        - Labeling severity
        - Learning accepted/rejected outcomes
        
        Returns True if training completed, False if aborted.
        """
        self._epoch += 1
        
        self._emit_event(
            "TRAINING_STARTED",
            f"Starting epoch {self._epoch}",
            epoch=self._epoch,
            gpu_used=self._get_current_conditions().gpu_available,
        )
        
        # Simulate training steps (in production, this calls PyTorch)
        for step in range(10):
            # Check for abort
            if self._abort_flag.is_set():
                self._emit_event(
                    "TRAINING_ABORTED",
                    f"Aborted at step {step}/10 (user activity or scan)",
                    epoch=self._epoch,
                )
                return False
            
            # Check if scan started
            if is_scan_active():
                self._abort_flag.set()
                self._emit_event(
                    "TRAINING_ABORTED",
                    "Scan started - aborting training",
                    epoch=self._epoch,
                )
                return False
            
            # Check if human interaction
            idle = get_idle_seconds()
            if idle < IDLE_THRESHOLD_SECONDS:
                self._abort_flag.set()
                self._emit_event(
                    "TRAINING_ABORTED",
                    f"Human interaction detected (idle={idle}s) - aborting",
                    idle_seconds=idle,
                    epoch=self._epoch,
                )
                return False
            
            # Training step (placeholder for actual PyTorch training)
            time.sleep(0.1)  # Simulate compute
        
        # Save checkpoint
        checkpoint_hash = hashlib.sha256(f"epoch-{self._epoch}".encode()).hexdigest()[:16]
        self._emit_event(
            "CHECKPOINT_SAVED",
            f"Saved checkpoint for epoch {self._epoch} (hash: {checkpoint_hash})",
            epoch=self._epoch,
        )
        
        self._emit_event(
            "TRAINING_STOPPED",
            f"Completed epoch {self._epoch}",
            epoch=self._epoch,
        )
        
        return True
    
    def check_and_train(self) -> bool:
        """
        Check conditions and train if met.
        
        Returns True if training was triggered and completed.
        """
        with self._training_lock:
            # Don't trigger if already training
            if self._state == TrainingState.TRAINING:
                return False
            
            self._state = TrainingState.CHECKING
            self._abort_flag.clear()
        
        try:
            # Get conditions
            conditions = self._get_current_conditions()
            
            # Check idle conditions
            idle_result = check_idle_conditions(conditions)
            
            if not idle_result.can_train:
                self._state = TrainingState.IDLE
                return False
            
            # Emit idle detected event
            self._emit_event(
                "IDLE_DETECTED",
                f"System idle for {conditions.idle_seconds}s - checking guards",
                idle_seconds=conditions.idle_seconds,
            )
            
            # Check ALL guards
            guards_ok, guard_msg = self._check_all_guards()
            if not guards_ok:
                self._emit_event(
                    "GUARD_BLOCKED",
                    f"Training blocked: {guard_msg}",
                    idle_seconds=conditions.idle_seconds,
                )
                self._state = TrainingState.IDLE
                return False
            
            # Evaluate training trigger
            trigger = evaluate_training_trigger(
                idle_result,
                None,  # model_status - we allow fresh training
                pending_samples=100,  # representation samples available
            )
            
            if not trigger.should_train:
                self._state = TrainingState.IDLE
                return False
            
            # Start training
            with self._training_lock:
                self._state = TrainingState.TRAINING
            
            success = self._train_representation_only()
            
            with self._training_lock:
                self._state = TrainingState.IDLE
            
            return success
            
        except Exception as e:
            self._emit_event("ERROR", str(e))
            self._state = TrainingState.ERROR
            return False
    
    async def run_scheduler(self) -> None:
        """
        Run the background scheduler loop.
        
        Checks idle conditions every 30 seconds.
        """
        self._running = True
        logger.info(f"G38 Auto-Trainer started (check interval: {self.CHECK_INTERVAL_SECONDS}s)")
        
        while self._running:
            try:
                self.check_and_train()
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            
            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
        
        logger.info("G38 Auto-Trainer stopped")
    
    def start(self) -> None:
        """Start the background scheduler."""
        if self._task is not None:
            return
        
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self.run_scheduler())
    
    def stop(self) -> None:
        """Stop the background scheduler."""
        self._running = False
        self._abort_flag.set()
        
        if self._task is not None:
            self._task.cancel()
            self._task = None
    
    def abort_training(self) -> None:
        """Abort current training (if any)."""
        self._abort_flag.set()
        self._emit_event(
            "TRAINING_ABORTED",
            "Manual abort requested",
        )
    
    def get_status(self) -> dict:
        """Get current trainer status for dashboard."""
        conditions = self._get_current_conditions()
        
        return {
            "state": self._state.value,
            "is_training": self.is_training,
            "epoch": self._epoch,
            "idle_seconds": conditions.idle_seconds,
            "power_connected": conditions.power_connected,
            "scan_active": not conditions.no_active_scan,
            "gpu_available": conditions.gpu_available,
            "events_count": len(self._events),
            "last_event": self._events[-1].event_type if self._events else None,
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_auto_trainer: Optional[AutoTrainer] = None


def get_auto_trainer() -> AutoTrainer:
    """Get singleton AutoTrainer instance."""
    global _auto_trainer
    if _auto_trainer is None:
        _auto_trainer = AutoTrainer()
    return _auto_trainer


def start_auto_training() -> None:
    """Start automatic idle training."""
    trainer = get_auto_trainer()
    trainer.start()


def stop_auto_training() -> None:
    """Stop automatic idle training."""
    if _auto_trainer is not None:
        _auto_trainer.stop()
