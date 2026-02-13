# G38 Runtime __init__
"""G38 Runtime Module - Auto-training infrastructure."""

from .idle_detector import (
    get_idle_seconds,
    get_idle_info,
    is_power_connected,
    is_scan_active,
    set_scan_active,
)

from .auto_trainer import (
    AutoTrainer,
    TrainingState,
    TrainingEvent,
    get_auto_trainer,
    start_auto_training,
    stop_auto_training,
    start_continuous_training,
    stop_continuous_training,
)

__all__ = [
    # Idle detection
    "get_idle_seconds",
    "get_idle_info",
    "is_power_connected",
    "is_scan_active",
    "set_scan_active",
    # Auto training
    "AutoTrainer",
    "TrainingState",
    "TrainingEvent",
    "get_auto_trainer",
    "start_auto_training",
    "stop_auto_training",
    "start_continuous_training",
    "stop_continuous_training",
]
