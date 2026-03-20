"""
training — Sector entry point for training modules.

Re-exports key modules from impl_v1.training.distributed and
the safetensors I/O module for centralized access.
"""

import warnings
import logging

logger = logging.getLogger(__name__)

# Re-export safetensors_io
try:
    from training.safetensors_io import (  # noqa: F401
        save_safetensors,
        load_safetensors,
    )
except ImportError:
    pass

# Lazy re-export for distributed training modules
_DEPRECATION_MSG = (
    "Importing from 'training' sector is supported. "
    "The canonical source is 'impl_v1.training.distributed'."
)


def __getattr__(name):
    """Lazy re-export from impl_v1.training.distributed."""
    import importlib

    for mod_path in [
        "impl_v1.training.distributed.model_versioning",
        "impl_v1.training.distributed.data_enforcement",
        "impl_v1.training.distributed.drift_guard",
        "impl_v1.training.distributed.cluster_authority",
        "impl_v1.training.distributed.checkpoint_consensus",
        "impl_v1.training.distributed.cloud_backup",
        "impl_v1.training.distributed.distributed_training_orchestrator",
        "impl_v1.training.distributed.wipe_protection",
        "training.safetensors_io",
    ]:
        try:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, name):
                return getattr(mod, name)
        except ImportError:
            continue

    raise AttributeError(f"module 'training' has no attribute '{name}'")
