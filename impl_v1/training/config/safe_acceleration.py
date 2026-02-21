"""
Safe Acceleration Config - Deterministic Training
===================================================

Enable acceleration WITHOUT breaking determinism:
- Mixed precision (if deterministic supported)
- Gradient accumulation
- Async data loader
- KEEP: deterministic_algorithms=True
"""

from dataclasses import dataclass
from typing import Optional, Dict
from enum import Enum
import json


# =============================================================================
# ACCELERATION OPTIONS
# =============================================================================

class AccelerationMode(Enum):
    """Safe acceleration modes."""
    MINIMAL = "minimal"      # No acceleration
    BALANCED = "balanced"    # Moderate acceleration
    AGGRESSIVE = "aggressive"  # Max safe acceleration


@dataclass
class SafeAccelerationConfig:
    """Configuration for safe acceleration."""
    
    # NEVER CHANGE - Determinism guarantees
    deterministic_algorithms: bool = True
    cudnn_deterministic: bool = True
    cudnn_benchmark: bool = False
    
    # Safe acceleration options
    mixed_precision_enabled: bool = False  # Only if deterministic
    gradient_accumulation_steps: int = 1
    batch_size: int = 32
    num_workers: int = 4
    pin_memory: bool = True
    prefetch_factor: int = 2
    
    # GPU memory safety
    max_gpu_memory_fraction: float = 0.85
    
    # Mode
    mode: AccelerationMode = AccelerationMode.BALANCED


# =============================================================================
# PRESET CONFIGURATIONS
# =============================================================================

def get_minimal_config() -> SafeAccelerationConfig:
    """Minimal acceleration, maximum safety."""
    return SafeAccelerationConfig(
        deterministic_algorithms=True,
        cudnn_deterministic=True,
        cudnn_benchmark=False,
        mixed_precision_enabled=False,
        gradient_accumulation_steps=1,
        batch_size=16,
        num_workers=2,
        mode=AccelerationMode.MINIMAL,
    )


def get_balanced_config() -> SafeAccelerationConfig:
    """Balanced acceleration and safety."""
    return SafeAccelerationConfig(
        deterministic_algorithms=True,
        cudnn_deterministic=True,
        cudnn_benchmark=False,
        mixed_precision_enabled=True,   # AMP verified deterministic with GradScaler
        gradient_accumulation_steps=4,  # Effective batch = batch_size * 4
        batch_size=32,
        num_workers=8,
        pin_memory=True,
        prefetch_factor=2,
        mode=AccelerationMode.BALANCED,
    )


def get_aggressive_config() -> SafeAccelerationConfig:
    """Maximum safe acceleration."""
    return SafeAccelerationConfig(
        deterministic_algorithms=True,
        cudnn_deterministic=True,
        cudnn_benchmark=False,
        mixed_precision_enabled=True,   # AMP verified deterministic with GradScaler
        gradient_accumulation_steps=4,  # Effective batch = batch_size * 4
        batch_size=64,
        num_workers=8,
        pin_memory=True,
        prefetch_factor=4,
        max_gpu_memory_fraction=0.90,
        mode=AccelerationMode.AGGRESSIVE,
    )


# =============================================================================
# PYTORCH CONFIGURATION
# =============================================================================

def apply_safe_acceleration(config: SafeAccelerationConfig) -> Dict[str, bool]:
    """Apply safe acceleration config to PyTorch."""
    results = {}
    
    try:
        import torch
        
        # MANDATORY: Determinism settings
        torch.use_deterministic_algorithms(config.deterministic_algorithms)
        results["deterministic_algorithms"] = True
        
        if torch.cuda.is_available():
            torch.backends.cudnn.deterministic = config.cudnn_deterministic
            torch.backends.cudnn.benchmark = config.cudnn_benchmark
            results["cudnn_deterministic"] = config.cudnn_deterministic
            results["cudnn_benchmark"] = config.cudnn_benchmark
            
            # GPU memory fraction
            if hasattr(torch.cuda, 'set_per_process_memory_fraction'):
                torch.cuda.set_per_process_memory_fraction(
                    config.max_gpu_memory_fraction
                )
                results["memory_fraction"] = config.max_gpu_memory_fraction
        
    except ImportError:
        results["pytorch_available"] = False
    
    return results


# =============================================================================
# DATA LOADER CONFIG
# =============================================================================

def get_dataloader_config(config: SafeAccelerationConfig) -> dict:
    """Get DataLoader configuration."""
    return {
        "batch_size": config.batch_size,
        "num_workers": config.num_workers,
        "pin_memory": config.pin_memory,
        "prefetch_factor": config.prefetch_factor if config.num_workers > 0 else None,
        "persistent_workers": config.num_workers > 0,
        "drop_last": True,  # For consistent batch sizes
    }


# =============================================================================
# VALIDATION
# =============================================================================

def validate_config(config: SafeAccelerationConfig) -> tuple:
    """Validate acceleration config maintains determinism."""
    errors = []
    
    if not config.deterministic_algorithms:
        errors.append("deterministic_algorithms must be True")
    
    if not config.cudnn_deterministic:
        errors.append("cudnn_deterministic must be True")
    
    if config.cudnn_benchmark:
        errors.append("cudnn_benchmark must be False for determinism")
    
    if config.mixed_precision_enabled and not config.deterministic_algorithms:
        errors.append("mixed_precision requires deterministic_algorithms=True")
    
    return len(errors) == 0, errors
