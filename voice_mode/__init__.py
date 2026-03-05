"""
voice_mode — Sector shim for voice pipeline modules.

Re-exports from backend.voice and impl_v1.training.voice for
centralised sector access. Old import paths continue to work.
"""

import warnings
import logging

logger = logging.getLogger(__name__)

_DEPRECATION_MSG = (
    "Importing from 'voice_mode' is a compatibility shim. "
    "Prefer importing directly from 'backend.voice' or "
    "'impl_v1.training.voice'."
)


def __getattr__(name):
    """Lazy re-export with deprecation warning."""
    import importlib

    # Try backend.voice first
    for mod_path in [
        "backend.voice.intent_router",
        "backend.voice.language_detector",
        "impl_v1.training.voice.stt_trainer",
        "impl_v1.training.voice.stt_model",
        "api.voice_gateway",
        "api.voice_routes",
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

    raise AttributeError(f"module 'voice_mode' has no attribute '{name}'")
