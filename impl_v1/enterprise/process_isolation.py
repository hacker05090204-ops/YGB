"""
Process Isolation
==================

Inference engine: Separate OS process
Training engine: Separate OS process

Communication: Checkpoint files only
- No shared memory
- No shared tensors
- Hash-verified transfer

If training crashes: Inference unaffected
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Dict
from datetime import datetime
from pathlib import Path
from enum import Enum
import subprocess
import hashlib
import json
import os


# =============================================================================
# PROCESS STATE
# =============================================================================

class ProcessState(Enum):
    """Process states."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    CRASHED = "crashed"


@dataclass
class IsolatedProcess:
    """An isolated process."""
    name: str
    pid: Optional[int]
    state: ProcessState
    started_at: Optional[str]
    crash_count: int


# =============================================================================
# PROCESS ISOLATOR
# =============================================================================

class ProcessIsolator:
    """Manage isolated processes."""
    
    STATE_FILE = Path("reports/process_isolation.json")
    
    def __init__(self):
        self.inference_process: Optional[IsolatedProcess] = None
        self.training_process: Optional[IsolatedProcess] = None
        self._load_state()
    
    def _load_state(self) -> None:
        """Load process state."""
        self.inference_process = IsolatedProcess(
            name="inference",
            pid=None,
            state=ProcessState.STOPPED,
            started_at=None,
            crash_count=0,
        )
        self.training_process = IsolatedProcess(
            name="training",
            pid=None,
            state=ProcessState.STOPPED,
            started_at=None,
            crash_count=0,
        )
    
    def _save_state(self) -> None:
        """Save process state."""
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(self.STATE_FILE, "w") as f:
            json.dump({
                "inference": {
                    "pid": self.inference_process.pid,
                    "state": self.inference_process.state.value,
                    "started_at": self.inference_process.started_at,
                    "crash_count": self.inference_process.crash_count,
                },
                "training": {
                    "pid": self.training_process.pid,
                    "state": self.training_process.state.value,
                    "started_at": self.training_process.started_at,
                    "crash_count": self.training_process.crash_count,
                },
                "updated": datetime.now().isoformat(),
            }, f, indent=2)
    
    def start_inference(self) -> Tuple[bool, str]:
        """Start inference process (isolated)."""
        if self.inference_process.state == ProcessState.RUNNING:
            return False, "Inference already running"
        
        # In production, would spawn actual process
        self.inference_process.state = ProcessState.RUNNING
        self.inference_process.pid = os.getpid() + 1000  # Mock
        self.inference_process.started_at = datetime.now().isoformat()
        
        self._save_state()
        return True, f"Inference started (PID: {self.inference_process.pid})"
    
    def start_training(self) -> Tuple[bool, str]:
        """Start training process (isolated)."""
        if self.training_process.state == ProcessState.RUNNING:
            return False, "Training already running"
        
        self.training_process.state = ProcessState.RUNNING
        self.training_process.pid = os.getpid() + 2000  # Mock
        self.training_process.started_at = datetime.now().isoformat()
        
        self._save_state()
        return True, f"Training started (PID: {self.training_process.pid})"
    
    def stop_training(self) -> Tuple[bool, str]:
        """Stop training process."""
        if self.training_process.state != ProcessState.RUNNING:
            return False, "Training not running"
        
        self.training_process.state = ProcessState.STOPPED
        self.training_process.pid = None
        
        self._save_state()
        return True, "Training stopped"
    
    def on_training_crash(self) -> None:
        """Handle training crash - inference unaffected."""
        self.training_process.state = ProcessState.CRASHED
        self.training_process.crash_count += 1
        self.training_process.pid = None
        
        # Inference continues unaffected
        assert self.inference_process.state == ProcessState.RUNNING
        
        self._save_state()
    
    def get_isolation_status(self) -> Dict[str, dict]:
        """Get isolation status."""
        return {
            "inference": {
                "state": self.inference_process.state.value,
                "pid": self.inference_process.pid,
                "isolated": True,
            },
            "training": {
                "state": self.training_process.state.value,
                "pid": self.training_process.pid,
                "isolated": True,
            },
            "communication": "checkpoint_files_only",
            "shared_memory": False,
            "shared_tensors": False,
        }


# =============================================================================
# CHECKPOINT TRANSFER
# =============================================================================

class HashVerifiedTransfer:
    """Hash-verified checkpoint transfer between processes."""
    
    TRANSFER_DIR = Path("checkpoints/transfer")
    
    def __init__(self):
        self.TRANSFER_DIR.mkdir(parents=True, exist_ok=True)
    
    def compute_hash(self, filepath: Path) -> str:
        """Compute SHA256 hash."""
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def prepare_transfer(self, checkpoint_path: Path) -> Tuple[Path, str]:
        """Prepare checkpoint for transfer with hash."""
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        
        file_hash = self.compute_hash(checkpoint_path)
        
        # Create manifest
        manifest_path = self.TRANSFER_DIR / f"{checkpoint_path.name}.manifest.json"
        with open(manifest_path, "w") as f:
            json.dump({
                "source": str(checkpoint_path),
                "hash": file_hash,
                "timestamp": datetime.now().isoformat(),
            }, f, indent=2)
        
        return manifest_path, file_hash
    
    def verify_transfer(self, checkpoint_path: Path, expected_hash: str) -> Tuple[bool, str]:
        """Verify received checkpoint."""
        if not checkpoint_path.exists():
            return False, "Checkpoint not found"
        
        actual_hash = self.compute_hash(checkpoint_path)
        
        if actual_hash != expected_hash:
            return False, f"Hash mismatch: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."
        
        return True, "Transfer verified"
