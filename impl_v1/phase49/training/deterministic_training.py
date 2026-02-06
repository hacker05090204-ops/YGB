"""
Deterministic AI Training - Phase 49
=====================================

GUARANTEES:
1. torch.use_deterministic_algorithms(True)
2. All seeds synchronized (torch, numpy, random, CUDA)
3. Checkpoint stores complete RNG states
4. Replay produces identical loss curve

USAGE:
    from impl_v1.phase49.training.deterministic_training import (
        set_deterministic_mode,
        save_checkpoint_with_rng,
        load_checkpoint_with_rng,
        verify_replay_determinism,
    )
"""

import os
import random
import hashlib
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

# Optional imports with graceful fallback
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_SEED = 42
DETERMINISM_REQUIRED = True
CUBLAS_WORKSPACE_CONFIG = ":4096:8"


# =============================================================================
# DETERMINISTIC MODE
# =============================================================================

def set_deterministic_mode(seed: int = DEFAULT_SEED) -> Dict[str, Any]:
    """
    Set all random seeds for deterministic training.
    
    Args:
        seed: Random seed to use
    
    Returns:
        Dict with all seed states for checkpointing
    """
    states = {}
    
    # Python random
    random.seed(seed)
    states["python_random"] = random.getstate()
    
    # NumPy
    if NUMPY_AVAILABLE:
        np.random.seed(seed)
        states["numpy_random"] = np.random.get_state()
    
    # PyTorch
    if TORCH_AVAILABLE:
        torch.manual_seed(seed)
        states["torch_cpu"] = torch.get_rng_state()
        
        # CUDA
        if torch.cuda.is_available():
            torch.cuda.manual_seed(seed)
            torch.cuda.manual_seed_all(seed)
            states["torch_cuda"] = torch.cuda.get_rng_state_all()
        
        # Deterministic algorithms
        if DETERMINISM_REQUIRED:
            torch.use_deterministic_algorithms(True)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            
            # CUBLAS workspace config for determinism
            os.environ["CUBLAS_WORKSPACE_CONFIG"] = CUBLAS_WORKSPACE_CONFIG
        
        states["deterministic_mode"] = True
    
    states["seed"] = seed
    return states


def get_rng_states() -> Dict[str, Any]:
    """Get current RNG states for all libraries."""
    states = {
        "python_random": random.getstate(),
        "seed": None,  # Unknown if set manually
    }
    
    if NUMPY_AVAILABLE:
        states["numpy_random"] = np.random.get_state()
    
    if TORCH_AVAILABLE:
        states["torch_cpu"] = torch.get_rng_state()
        if torch.cuda.is_available():
            states["torch_cuda"] = torch.cuda.get_rng_state_all()
    
    return states


def restore_rng_states(states: Dict[str, Any]) -> None:
    """Restore RNG states from saved states."""
    if "python_random" in states:
        random.setstate(states["python_random"])
    
    if NUMPY_AVAILABLE and "numpy_random" in states:
        np.random.set_state(states["numpy_random"])
    
    if TORCH_AVAILABLE:
        if "torch_cpu" in states:
            torch.set_rng_state(states["torch_cpu"])
        if "torch_cuda" in states and torch.cuda.is_available():
            torch.cuda.set_rng_state_all(states["torch_cuda"])


# =============================================================================
# CHECKPOINTING WITH RNG
# =============================================================================

@dataclass
class DeterministicCheckpoint:
    """Checkpoint with complete RNG states."""
    model_state: Dict[str, Any]
    optimizer_state: Dict[str, Any]
    rng_states: Dict[str, Any]
    epoch: int
    loss: float
    hash: str  # Determinism verification hash


def save_checkpoint_with_rng(
    model_state: Dict[str, Any],
    optimizer_state: Dict[str, Any],
    epoch: int,
    loss: float,
    filepath: Path,
) -> str:
    """
    Save checkpoint with complete RNG states.
    
    Returns:
        Checkpoint hash for determinism verification
    """
    rng_states = get_rng_states()
    
    # Compute determinism hash
    hash_data = f"{epoch}:{loss:.8f}:{rng_states.get('seed')}"
    checkpoint_hash = hashlib.sha256(hash_data.encode()).hexdigest()[:16]
    
    checkpoint = {
        "model_state": model_state,
        "optimizer_state": optimizer_state,
        "rng_states": rng_states,
        "epoch": epoch,
        "loss": loss,
        "hash": checkpoint_hash,
    }
    
    if TORCH_AVAILABLE:
        torch.save(checkpoint, filepath)
    else:
        # Fallback for non-torch environments
        import pickle
        with open(filepath, "wb") as f:
            pickle.dump(checkpoint, f)
    
    return checkpoint_hash


def load_checkpoint_with_rng(filepath: Path) -> DeterministicCheckpoint:
    """
    Load checkpoint and restore RNG states.
    
    Returns:
        DeterministicCheckpoint with all states
    """
    if TORCH_AVAILABLE:
        checkpoint = torch.load(filepath, weights_only=False)
    else:
        import pickle
        with open(filepath, "rb") as f:
            checkpoint = pickle.load(f)
    
    # Restore RNG states
    restore_rng_states(checkpoint["rng_states"])
    
    return DeterministicCheckpoint(
        model_state=checkpoint["model_state"],
        optimizer_state=checkpoint["optimizer_state"],
        rng_states=checkpoint["rng_states"],
        epoch=checkpoint["epoch"],
        loss=checkpoint["loss"],
        hash=checkpoint["hash"],
    )


# =============================================================================
# REPLAY VERIFICATION
# =============================================================================

def verify_replay_determinism(
    loss_curve_1: list,
    loss_curve_2: list,
    tolerance: float = 1e-6,
) -> Tuple[bool, Optional[str]]:
    """
    Verify that two training runs produced identical loss curves.
    
    Args:
        loss_curve_1: Loss values from first run
        loss_curve_2: Loss values from replay run
        tolerance: Maximum allowed difference
    
    Returns:
        Tuple of (is_deterministic, error_message)
    """
    if len(loss_curve_1) != len(loss_curve_2):
        return False, f"Length mismatch: {len(loss_curve_1)} vs {len(loss_curve_2)}"
    
    for i, (l1, l2) in enumerate(zip(loss_curve_1, loss_curve_2)):
        if abs(l1 - l2) > tolerance:
            return False, f"Drift at epoch {i}: {l1:.8f} vs {l2:.8f}"
    
    return True, None


def compute_loss_hash(loss_curve: list) -> str:
    """Compute deterministic hash of loss curve."""
    loss_str = ":".join(f"{l:.8f}" for l in loss_curve)
    return hashlib.sha256(loss_str.encode()).hexdigest()[:16]
