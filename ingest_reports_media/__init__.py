"""
ingest_reports_media — Sector for report, video, and image intake.

Re-exports from backend.bridge, scripts, and impl_v1 modules.
Original media files are kept as-is. Validated tensor artifacts
for training are generated as .safetensors.
"""

import warnings
import logging

logger = logging.getLogger(__name__)

_DEPRECATION_MSG = (
    "Importing from 'ingest_reports_media' is a compatibility shim. "
    "Prefer importing directly from the source module."
)


def __getattr__(name):
    """Lazy re-export with deprecation warning."""
    import importlib

    for mod_path in [
        "scripts.fast_bridge_ingest",
        "scripts.ingestion_bootstrap",
        "impl_v1.training.distributed.report_sync",
        "impl_v1.training.distributed.report_validation_gate",
        "impl_v1.training.distributed.ingestion_policy",
        "impl_v1.training.distributed.data_source_registry",
    ]:
        try:
            mod = importlib.import_module(mod_path)
            if hasattr(mod, name):
                warnings.warn(
                    f"{_DEPRECATION_MSG} Use '{mod_path}.{name}' instead.",
                    DeprecationWarning,
                    stacklevel=2,
                )
                return getattr(mod, name)
        except ImportError:
            continue

    raise AttributeError(f"module 'ingest_reports_media' has no attribute '{name}'")
