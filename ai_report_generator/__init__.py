"""
ai_report_generator — Sector for AI-powered report generation.

Re-exports from impl_v1.training.distributed report modules.
"""

import warnings
import logging

logger = logging.getLogger(__name__)

_DEPRECATION_MSG = (
    "Importing from 'ai_report_generator' is a compatibility shim. "
    "Prefer importing directly from the source module."
)


def __getattr__(name):
    """Lazy re-export with deprecation warning."""
    import importlib

    for mod_path in [
        "impl_v1.training.distributed.report_structural_compiler",
        "impl_v1.training.distributed.report_sync",
        "impl_v1.training.distributed.report_validation_gate",
        "backend.governance.report_draft_assistant",
        "backend.governance.report_similarity",
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

    raise AttributeError(f"module 'ai_report_generator' has no attribute '{name}'")
