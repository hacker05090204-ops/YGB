"""Torch-only GPU status reporting with fail-closed native bridge semantics."""

from __future__ import annotations


_STATUS_SOURCE = "python_torch"


def _default_status() -> dict:
    return {
        "nvml_available": False,
        "cuda_available": False,
        "native_compiled": False,
        "gpu_count": 0,
        "status_source": _STATUS_SOURCE,
    }


def get_native_gpu_status() -> dict:
    """Return a fail-closed GPU status snapshot using Python/torch probes only."""
    status = _default_status()

    try:
        import torch
    except Exception:
        return status

    try:
        cuda = getattr(torch, "cuda", None)
        is_available = getattr(cuda, "is_available", None)
        if not callable(is_available):
            return status

        status["cuda_available"] = bool(is_available())
        if not status["cuda_available"]:
            return status

        device_count = getattr(cuda, "device_count", None)
        if callable(device_count):
            try:
                count = int(device_count())
            except Exception:
                count = 0
        else:
            count = 0

        status["gpu_count"] = max(count, 0)
    except Exception:
        return _default_status()

    return status
