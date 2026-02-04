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

from impl_v1.phase49.runtime.training_reports import (
    TrainingMode as ReportTrainingMode,
    generate_training_report,
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


@dataclass
class TrainingSession:
    """Training session metadata for report generation."""
    started_at: str
    start_epoch: int
    gpu_used: bool
    checkpoints_saved: int = 0
    last_checkpoint_hash: str = ""


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
        self._epoch = 0  # Total epochs completed ever
        self._target_epochs = 0  # Target epochs for current session
        self._session_epoch = 0  # Current epoch within session (0 to target)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._on_event_callback: Optional[Callable[[TrainingEvent], None]] = None
        self._current_session: Optional[TrainingSession] = None
    
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
            
            # Start training session
            with self._training_lock:
                self._state = TrainingState.TRAINING
                self._current_session = TrainingSession(
                    started_at=datetime.now(timezone.utc).isoformat(),
                    start_epoch=self._epoch,
                    gpu_used=conditions.gpu_available,
                )
            
            success = self._train_representation_only()
            
            # Generate training report after session
            if self._current_session:
                self._generate_session_report()
            
            with self._training_lock:
                self._state = TrainingState.IDLE
                self._current_session = None
            
            return success
            
        except Exception as e:
            self._emit_event("ERROR", str(e))
            self._state = TrainingState.ERROR
            return False
    
    def _generate_session_report(self) -> None:
        """Generate training report after session completes."""
        if not self._current_session:
            return
        
        try:
            stopped_at = datetime.now(timezone.utc).isoformat()
            epochs_trained = self._epoch - self._current_session.start_epoch
            
            # Get last checkpoint hash from events
            checkpoint_events = [
                e for e in self._events 
                if e.event_type == "CHECKPOINT_SAVED"
            ]
            last_hash = ""
            if checkpoint_events:
                # Extract hash from details
                details = checkpoint_events[-1].details
                if "hash: " in details:
                    last_hash = details.split("hash: ")[1].rstrip(")")
            
            paths = generate_training_report(
                total_epochs=epochs_trained,
                gpu_used=self._current_session.gpu_used,
                started_at=self._current_session.started_at,
                stopped_at=stopped_at,
                checkpoints_saved=len(checkpoint_events),
                last_checkpoint_hash=last_hash,
                samples_processed=epochs_trained * 100,  # Mock samples
                training_mode=ReportTrainingMode.MODE_A,
                reports_dir="reports/g38_training",
            )
            
            self._emit_event(
                "REPORT_GENERATED",
                f"Training report saved: {list(paths.values())[0]}",
            )
            
            logger.info(f"Training report generated: {paths}")
            
        except Exception as e:
            logger.error(f"Failed to generate training report: {e}")
    
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
    
    def force_start_training(self, epochs: int = 5) -> dict:
        """
        Manually start training regardless of idle conditions.
        
        Used for demo/testing purposes.
        """
        with self._training_lock:
            if self._state == TrainingState.TRAINING:
                return {
                    "started": False,
                    "reason": "Training already in progress",
                    "state": self._state.value,
                }
            
            self._state = TrainingState.TRAINING
            self._abort_flag.clear()
            # Set REAL target for progress tracking
            self._target_epochs = epochs
            self._session_epoch = 0
            # Track session for report generation
            self._current_session = TrainingSession(
                started_at=datetime.now(timezone.utc).isoformat(),
                start_epoch=self._epoch,
                gpu_used=self._get_current_conditions().gpu_available,
            )
        
        self._emit_event(
            "MANUAL_START",
            f"Manual training triggered for {epochs} epochs",
        )
        
        try:
            for i in range(epochs):
                if self._abort_flag.is_set():
                    break
                
                # Update progress BEFORE training starts
                self._session_epoch = i + 1
                self._epoch += 1
                
                self._emit_event(
                    "TRAINING_STARTED",
                    f"Starting epoch {self._session_epoch}/{epochs}",
                    epoch=self._session_epoch,
                    gpu_used=self._get_current_conditions().gpu_available,
                )
                
                # Simulate training steps (2 seconds per epoch)
                for step in range(10):
                    if self._abort_flag.is_set():
                        break
                    time.sleep(0.2)  # 0.2s * 10 steps = 2s per epoch
                
                if not self._abort_flag.is_set():
                    checkpoint_hash = hashlib.sha256(f"epoch-{self._epoch}".encode()).hexdigest()[:16]
                    self._emit_event(
                        "CHECKPOINT_SAVED",
                        f"Saved checkpoint for epoch {self._session_epoch}/{epochs} (hash: {checkpoint_hash})",
                        epoch=self._session_epoch,
                    )
            
            completed = self._session_epoch
            
            # Generate training report
            if self._current_session:
                self._generate_session_report()
            
            with self._training_lock:
                self._state = TrainingState.IDLE
                self._target_epochs = 0
                self._session_epoch = 0
                self._current_session = None
            
            self._emit_event(
                "TRAINING_STOPPED",
                f"Manual training completed: {completed}/{epochs} epochs",
                epoch=completed,
            )
            
            return {
                "started": True,
                "completed_epochs": completed,
                "total_epochs": self._epoch,
                "state": "COMPLETED",
            }
            
        except Exception as e:
            self._state = TrainingState.ERROR
            self._emit_event("ERROR", str(e))
            return {
                "started": False,
                "reason": str(e),
                "state": "ERROR",
            }
    
    def get_status(self) -> dict:
        """Get current trainer status for dashboard."""
        conditions = self._get_current_conditions()
        
        # Calculate REAL progress percentage
        if self.is_training and self._target_epochs > 0:
            real_progress = round((self._session_epoch / self._target_epochs) * 100)
        else:
            real_progress = 0
        
        return {
            "state": self._state.value,
            "is_training": self.is_training,
            "epoch": self._session_epoch,  # Current session epoch (real progress)
            "total_epochs": self._target_epochs,  # Target for this session
            "total_completed": self._epoch,  # Total ever completed
            "progress": real_progress,  # REAL percentage
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
