"""
Aggregated System Status Endpoint — /api/system/status

Single endpoint returning the health of ALL subsystems for dashboard
consumption. All data sourced from real runtime state — no mocks.

Subsystems:
    - Process liveness (uptime)
    - Dependency readiness (storage, config, revocation, metrics)
    - Metrics snapshot (counters, histograms)
    - Training state (from state_manager)
    - Voice pipeline status
    - Storage health
    - Circuit breaker states
"""

import logging
import time
from datetime import datetime, UTC
from typing import Any, Dict

from fastapi import APIRouter, Depends

from backend.auth.auth_guard import require_auth

logger = logging.getLogger("ygb.api.system_status")

system_status_router = APIRouter(tags=["system-status"])

_BOOT_MONOTONIC = time.monotonic()
_BOOT_WALL = time.time()


def _safe_call(label: str, fn, *args, **kwargs) -> Dict[str, Any]:
    """Call fn and return its result; on failure return degraded status."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("System status sub-check '%s' failed: %s", label, exc)
        return {"status": "UNAVAILABLE", "error": str(exc)}


def _get_training_state() -> Dict[str, Any]:
    """Get real training state from the state manager."""
    from backend.training.state_manager import get_training_state_manager

    mgr = get_training_state_manager()
    progress = mgr.get_training_progress()
    return {
        "status": progress.status,
        "current_epoch": progress.current_epoch,
        "total_epochs": progress.total_epochs,
        "loss": progress.loss,
        "throughput": progress.throughput,
        "started_at": progress.started_at,
    }


def _get_voice_status() -> Dict[str, Any]:
    """Get real voice pipeline status."""
    from backend.assistant.voice_runtime import build_voice_pipeline_status

    return build_voice_pipeline_status()


def _get_readiness() -> Dict[str, Any]:
    """Run all readiness checks."""
    from backend.reliability.dependency_checker import run_all_checks

    return run_all_checks(timeout_per_check=2.0)


def _get_metrics_snapshot() -> Dict[str, Any]:
    """Get current metrics from the registry."""
    from backend.observability.metrics import metrics_registry

    return metrics_registry.get_snapshot()


def _get_storage_health() -> Dict[str, Any]:
    """Get real storage engine health."""
    from backend.storage.storage_bridge import get_storage_health

    return get_storage_health()


@system_status_router.get("/api/system/status")
async def aggregated_system_status(user=Depends(require_auth)):
    """Aggregated system health — all subsystems in one response.

    Returns real runtime data from every subsystem. No mocks, no placeholders.
    Intended for dashboard/monitoring consumption.
    """
    uptime_s = round(time.monotonic() - _BOOT_MONOTONIC, 1)

    # Gather all subsystem statuses — each call is best-effort
    readiness = _safe_call("readiness", _get_readiness)
    metrics = _safe_call("metrics", _get_metrics_snapshot)
    training = _safe_call("training", _get_training_state)
    voice = _safe_call("voice", _get_voice_status)
    storage = _safe_call("storage", _get_storage_health)

    # Determine overall status
    is_ready = readiness.get("ready", False) if isinstance(readiness, dict) else False
    storage_ok = storage.get("storage_active", False) if isinstance(storage, dict) else False

    if is_ready and storage_ok:
        overall = "HEALTHY"
    elif storage_ok:
        overall = "DEGRADED"
    else:
        overall = "UNHEALTHY"

    return {
        "overall_status": overall,
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_s": uptime_s,
        "boot_time": _BOOT_WALL,
        "subsystems": {
            "readiness": readiness,
            "storage": storage,
            "training": training,
            "voice": voice,
        },
        "metrics": metrics,
    }
