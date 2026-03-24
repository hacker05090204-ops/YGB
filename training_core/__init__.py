"""Canonical training core package.

This package is the backend's single source of truth for training execution,
checkpointing, contracts, and entrypoints.
"""

from .contracts import (
    CheckpointBundle,
    DatasetState,
    TrainingControllerConfig,
    TrainingResult,
)
from .execution import run_phase3_training_execution

__all__ = [
    "CheckpointBundle",
    "DatasetState",
    "TrainingControllerConfig",
    "TrainingResult",
    "run_phase3_training_execution",
]
