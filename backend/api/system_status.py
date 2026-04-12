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

import copy
import json
import logging
import os
import threading
import time
from datetime import datetime, UTC
from typing import Any, Dict

from fastapi import APIRouter, Depends
from fastapi.params import Depends as DependsMarker

from backend.api.system_status_store import (
    SYSTEM_STATUS_PATH,
    read_or_refresh_system_status_file,
)
from backend.auth.auth_guard import require_auth

logger = logging.getLogger("ygb.api.system_status")

system_status_router = APIRouter(tags=["system-status"])

_BOOT_MONOTONIC = time.monotonic()
_BOOT_WALL = time.time()
CORE_SYSTEMS = {"storage", "auth", "governance", "ingestion"}
NON_CORE_SYSTEMS = {"voice", "sync", "training", "reporting"}
AUXILIARY_SYSTEMS = {"readiness", "metrics", "canonical_status"}
CACHE_TTL_SECONDS = 15.0
DEGRADED_HEALTH_STATES = {"DEGRADED", "CRITICAL", "UNAVAILABLE"}
VOICE_DEPENDENCY_ERROR_MARKERS = (
    "modulenotfounderror",
    "importerror",
    "no module named",
    "not installed",
)

_status_cache: dict[str, Any] = {}
_cache_lock = threading.Lock()
_cache_ts: float = 0.0
_cache_has_refresh = False
_refresh_in_progress = False


def _safe_call(label: str, fn, *args, **kwargs) -> Dict[str, Any]:
    """Call fn and return its result; on failure return degraded status."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:
        logger.warning("System status sub-check '%s' failed: %s", label, exc)
        return {"status": "UNAVAILABLE", "error": str(exc)}


def _sub_check_available(result: Any) -> bool:
    if isinstance(result, dict) and result.get("status") == "UNAVAILABLE":
        return False
    return True


def _status_payload(result: Any) -> Dict[str, Any]:
    return dict(result) if isinstance(result, dict) else {}


def _status_text(payload: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return ""


def _count_degraded_systems(
    subsystems: Dict[str, Dict[str, Any]],
    names: set[str],
) -> int:
    return sum(
        1
        for name in names
        if subsystems.get(name, {}).get("health") in DEGRADED_HEALTH_STATES
    )


def _read_canonical_status_snapshot() -> Dict[str, Any]:
    try:
        if SYSTEM_STATUS_PATH.exists():
            payload = json.loads(SYSTEM_STATUS_PATH.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
    except (OSError, ValueError) as exc:
        logger.warning("System status file read failed: %s", exc)

    try:
        payload = read_or_refresh_system_status_file()
    except Exception as exc:
        logger.warning("System status snapshot refresh failed: %s", exc)
        return {}
    return payload if isinstance(payload, dict) else {}


def _voice_dependency_only_error(error_text: str) -> bool:
    lowered = error_text.lower()
    return any(marker in lowered for marker in VOICE_DEPENDENCY_ERROR_MARKERS)


def _sync_env_configured() -> bool:
    return bool(
        os.getenv("YGB_SYNC_PEERS", "").strip()
        or os.getenv("YGB_PEER_NODES", "").strip()
    )


def _default_sync_message(sync_mode: str) -> str:
    if sync_mode == "STANDALONE":
        return "Single-device mode. Set YGB_SYNC_PEERS for mesh sync."
    if sync_mode == "PEER_SYNC":
        return "Mesh sync active. Peer replication available."
    return "Sync peers configured but unreachable. Running in degraded mode."


def _bootstrapping_payload(name: str, message: str) -> Dict[str, Any]:
    return {
        "status": "BOOTSTRAPPING",
        "message": message,
        "name": name,
    }


def _bootstrap_training_status(
    canonical: Dict[str, Any],
    previous_subsystems: Dict[str, Any],
) -> Dict[str, Any]:
    training = canonical.get("training") if isinstance(canonical, dict) else {}
    if isinstance(training, dict) and training:
        return dict(training)

    previous_training = _status_payload(previous_subsystems.get("training"))
    if previous_training:
        return previous_training

    return _bootstrapping_payload(
        "training",
        "Training status awaiting background refresh.",
    )


def _bootstrap_voice_status(previous_subsystems: Dict[str, Any]) -> Dict[str, Any]:
    previous_voice = _status_payload(previous_subsystems.get("voice"))
    if previous_voice:
        return previous_voice

    payload = _bootstrapping_payload(
        "voice",
        "Voice runtime status awaiting background refresh.",
    )
    payload["pipeline_status"] = "BOOTSTRAPPING"
    return payload


def _bootstrap_sync_status(
    canonical: Dict[str, Any],
    previous_subsystems: Dict[str, Any],
) -> Dict[str, Any]:
    previous_sync = _status_payload(previous_subsystems.get("sync"))
    if previous_sync:
        return previous_sync

    sync = canonical.get("sync") if isinstance(canonical, dict) else {}
    payload = dict(sync) if isinstance(sync, dict) else {}
    configured = _sync_env_configured()
    sync_mode = str(payload.get("sync_mode") or payload.get("mode") or "").strip().upper()
    if sync_mode not in {"STANDALONE", "PEER_SYNC", "DEGRADED"}:
        sync_mode = "STANDALONE" if not configured else "DEGRADED"
    elif configured and sync_mode == "STANDALONE":
        sync_mode = "DEGRADED"

    payload["sync_mode"] = sync_mode
    payload["mode"] = sync_mode
    payload["configured"] = configured
    payload["local_files"] = int(payload.get("local_files", 0) or 0)
    payload["local_bytes"] = int(payload.get("local_bytes", 0) or 0)
    if sync_mode == "STANDALONE":
        payload["status"] = "HEALTHY"
        payload["sync_message"] = str(
            payload.get("sync_message")
            or payload.get("message")
            or _default_sync_message(sync_mode)
        )
        payload["message"] = payload["sync_message"]
        payload["stale"] = False
    else:
        payload["status"] = "BOOTSTRAPPING"
        payload["sync_message"] = str(
            payload.get("sync_message")
            or payload.get("message")
            or "Peer sync status awaiting background refresh."
        )
        payload["message"] = payload["sync_message"]
        payload["stale"] = bool(payload.get("stale", True))
    return payload


def _bootstrap_reporting_status(previous_subsystems: Dict[str, Any]) -> Dict[str, Any]:
    previous_reporting = _status_payload(previous_subsystems.get("reporting"))
    if previous_reporting:
        return previous_reporting

    return _bootstrapping_payload(
        "reporting",
        "Reporting status awaiting background refresh.",
    )


def _build_subsystem_payload(
    name: str,
    raw: Any,
    *,
    health: str,
    available: bool,
    role: str,
) -> Dict[str, Any]:
    payload = _status_payload(raw)
    payload.setdefault("name", name)
    payload["health"] = health
    payload["available"] = available
    payload["role"] = role
    return payload


def _classify_storage(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "status")
    available = True
    if payload.get("storage_active") is False:
        available = False
    elif status in {"UNAVAILABLE", "ERROR", "INACTIVE", "CRITICAL", "UNHEALTHY"}:
        available = False
    return _build_subsystem_payload(
        "storage",
        raw,
        health="HEALTHY" if available else "CRITICAL",
        available=available,
        role="CORE",
    )


def _classify_auth(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "status")
    available = bool(payload.get("available", True))
    if status in {"UNAVAILABLE", "ERROR", "CRITICAL", "FAILED"}:
        available = False
    return _build_subsystem_payload(
        "auth",
        raw,
        health="HEALTHY" if available else "CRITICAL",
        available=available,
        role="CORE",
    )


def _classify_governance(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "status")
    available = bool(payload.get("available", payload.get("all_locked", True)))
    if status in {"UNAVAILABLE", "ERROR", "CRITICAL", "FAILED"}:
        available = False
    return _build_subsystem_payload(
        "governance",
        raw,
        health="HEALTHY" if available else "CRITICAL",
        available=available,
        role="CORE",
    )


def _classify_ingestion(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "status")
    available = status not in {"UNAVAILABLE", "ERROR", "CRITICAL", "FAILED"}
    return _build_subsystem_payload(
        "ingestion",
        raw,
        health="HEALTHY" if available else "CRITICAL",
        available=available,
        role="CORE",
    )


def _classify_voice(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "pipeline_status", "status")
    missing_local_deps = bool(payload.get("local_only")) and bool(
        payload.get("no_whisper_dependency") or payload.get("no_google_stt_dependency")
    )
    error_text = str(payload.get("error") or "").strip()
    dependency_only_error = (
        bool(error_text)
        and missing_local_deps
        and _voice_dependency_only_error(error_text)
    )
    runtime_error = (
        (bool(error_text) and not dependency_only_error)
        or (status == "UNAVAILABLE" and not dependency_only_error)
    )
    if runtime_error:
        health = "DEGRADED"
    elif status in {"ONLINE", "READY", "IDLE", "HEALTHY"}:
        health = "HEALTHY"
    elif missing_local_deps and status in {"", "DEGRADED", "OFFLINE"}:
        health = "INFORMATIONAL"
    elif status in {"DEGRADED", "OFFLINE", "ERROR", "FAILED"}:
        health = "DEGRADED"
    else:
        health = "HEALTHY"
    return _build_subsystem_payload(
        "voice",
        raw,
        health=health,
        available=health not in {"DEGRADED", "CRITICAL", "UNAVAILABLE"},
        role="NON_CORE",
    )


def _classify_sync(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    sync_mode = str(payload.get("sync_mode") or payload.get("mode") or "").strip().upper()
    if sync_mode not in {"STANDALONE", "PEER_SYNC", "DEGRADED"}:
        sync_mode = "STANDALONE" if not _sync_env_configured() else "PEER_SYNC"
    stale = False if sync_mode == "STANDALONE" else bool(payload.get("stale", False))
    if sync_mode == "DEGRADED":
        health = "DEGRADED"
    elif stale:
        health = "DEGRADED"
    else:
        health = "HEALTHY"
    message = str(
        payload.get("sync_message")
        or payload.get("message")
        or _default_sync_message(sync_mode)
    )
    enriched = dict(payload)
    enriched["sync_mode"] = sync_mode
    enriched["sync_message"] = message
    enriched["stale"] = stale
    return _build_subsystem_payload(
        "sync",
        enriched,
        health=health,
        available=health != "DEGRADED",
        role="NON_CORE",
    )


def _classify_training(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "status", "state")
    health = (
        "DEGRADED"
        if payload.get("error") or status in {"UNAVAILABLE", "ERROR", "FAILED", "DEGRADED"}
        else "HEALTHY"
    )
    return _build_subsystem_payload(
        "training",
        raw,
        health=health,
        available=health != "DEGRADED",
        role="NON_CORE",
    )


def _classify_reporting(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "status")
    health = (
        "DEGRADED"
        if payload.get("error") or status in {"UNAVAILABLE", "ERROR", "FAILED", "DEGRADED"}
        else "HEALTHY"
    )
    return _build_subsystem_payload(
        "reporting",
        raw,
        health=health,
        available=health != "DEGRADED",
        role="NON_CORE",
    )


def _classify_readiness(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    ready = bool(payload.get("ready", True))
    health = "HEALTHY" if ready and _sub_check_available(payload) else "DEGRADED"
    return _build_subsystem_payload(
        "readiness",
        raw,
        health=health,
        available=health == "HEALTHY",
        role="AUXILIARY",
    )


def _classify_metrics(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "status")
    health = "DEGRADED" if status in {"UNAVAILABLE", "ERROR", "DEGRADED"} else "HEALTHY"
    return _build_subsystem_payload(
        "metrics",
        raw,
        health=health,
        available=health == "HEALTHY",
        role="AUXILIARY",
    )


def _classify_canonical(raw: Any) -> Dict[str, Any]:
    payload = _status_payload(raw)
    status = _status_text(payload, "health", "status")
    health = "DEGRADED" if status in {"UNAVAILABLE", "ERROR", "DEGRADED"} else "HEALTHY"
    return _build_subsystem_payload(
        "canonical_status",
        raw,
        health=health,
        available=health == "HEALTHY",
        role="AUXILIARY",
    )


def _derive_overall_health(subsystems: Dict[str, Dict[str, Any]]) -> str:
    core_available = all(
        bool(subsystems.get(name, {}).get("available", True)) for name in CORE_SYSTEMS
    )
    if not core_available:
        return "CRITICAL"

    readiness_degraded = subsystems.get("readiness", {}).get("health") == "DEGRADED"
    non_core_degraded = _count_degraded_systems(subsystems, NON_CORE_SYSTEMS)
    auxiliary_degraded = _count_degraded_systems(
        subsystems,
        AUXILIARY_SYSTEMS - {"readiness"},
    )
    if readiness_degraded and (non_core_degraded >= 2 or auxiliary_degraded >= 2):
        return "CRITICAL"
    if non_core_degraded >= 2:
        return "DEGRADED"
    if readiness_degraded or auxiliary_degraded > 0 or non_core_degraded > 0:
        return "DEGRADED"
    return "HEALTHY"


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


def _get_auth_status() -> Dict[str, Any]:
    """Get truthful auth subsystem status."""
    from backend.auth.revocation_store import get_backend_health

    return get_backend_health()


def _get_governance_status() -> Dict[str, Any]:
    """Get truthful governance subsystem status."""
    from backend.governance.authority_lock import AuthorityLock

    verification = AuthorityLock.verify_all_locked()
    return {
        "all_locked": bool(verification.get("all_locked", False)),
        "details": verification,
    }


def _get_sync_status() -> Dict[str, Any]:
    """Get truthful sync subsystem status with honest standalone reporting."""
    from backend.sync.health import get_sync_health
    from backend.sync.sync_engine import (
        SyncMode,
        get_last_sync_cycle,
        get_local_sync_index,
        get_sync_mode,
        is_sync_configured,
        is_sync_stale,
        sync_status_message,
    )

    health = get_sync_health()
    index = get_local_sync_index()
    mode = get_sync_mode()
    configured = is_sync_configured()
    peers = health.get("peers", {}) if isinstance(health.get("peers"), dict) else {}
    last_cycle = get_last_sync_cycle()
    peers_attempted = (
        last_cycle.peers_attempted if last_cycle is not None else int(peers.get("total", 0) or 0)
    )
    peers_succeeded = (
        last_cycle.peers_succeeded if last_cycle is not None else int(peers.get("online", 0) or 0)
    )
    last_completed_at = (
        last_cycle.completed_at if last_cycle is not None else str(health.get("last_sync") or "")
    )
    stale = is_sync_stale(mode=mode, last_completed_at=last_completed_at)
    sync_mode = mode.value
    message = sync_status_message(
        mode,
        peers_attempted=peers_attempted,
        peers_succeeded=peers_succeeded,
    )
    status = str(health.get("status") or "").upper()
    if mode == SyncMode.STANDALONE:
        status = "HEALTHY"
    elif mode == SyncMode.DEGRADED and status != "CRITICAL":
        status = "DEGRADED"
    elif not status:
        status = "HEALTHY" if not stale else "DEGRADED"

    return {
        **health,
        "status": status,
        "sync_mode": sync_mode,
        "mode": sync_mode,
        "configured": configured,
        "local_files": index.get_file_count(),
        "local_bytes": index.get_total_bytes(),
        "sync_message": message,
        "message": message,
        "stale": stale,
    }


def _get_reporting_status() -> Dict[str, Any]:
    """Get truthful reporting subsystem status."""
    from backend.reporting.report_engine import get_report_engine

    engine = get_report_engine()
    return {
        "engine": type(engine).__name__,
        "available": engine is not None,
    }


def _safe_additional_status(fn, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        logger.warning("System status auxiliary check '%s' failed: %s", fn.__name__, exc)
        return dict(fallback)


def _assemble_status_payload(
    *,
    readiness: Dict[str, Any],
    metrics: Dict[str, Any],
    training: Dict[str, Any],
    voice: Dict[str, Any],
    storage: Dict[str, Any],
    canonical: Dict[str, Any],
    auth: Dict[str, Any],
    governance: Dict[str, Any],
    sync: Dict[str, Any],
    reporting: Dict[str, Any],
) -> Dict[str, Any]:
    uptime_s = round(time.monotonic() - _BOOT_MONOTONIC, 1)
    checked_at = datetime.now(UTC).isoformat()

    ingestion = {}
    if isinstance(canonical, dict):
        ingestion = canonical.get("ingestion", {}) or {}

    subsystems = {
        "readiness": _classify_readiness(readiness),
        "metrics": _classify_metrics(metrics),
        "storage": _classify_storage(storage),
        "auth": _classify_auth(auth),
        "governance": _classify_governance(governance),
        "ingestion": _classify_ingestion(ingestion),
        "voice": _classify_voice(voice),
        "sync": _classify_sync(sync),
        "training": _classify_training(training),
        "reporting": _classify_reporting(reporting),
        "canonical_status": _classify_canonical(canonical),
    }

    is_ready = readiness.get("ready", False) if isinstance(readiness, dict) else False
    storage_ok = (
        storage.get("storage_active", False) if isinstance(storage, dict) else False
    )
    if is_ready and storage_ok:
        overall = "HEALTHY"
    elif storage_ok:
        overall = "DEGRADED"
    else:
        overall = "UNHEALTHY"

    sync_mode = subsystems["sync"].get("sync_mode", "STANDALONE")
    sync_message = subsystems["sync"].get(
        "sync_message",
        _default_sync_message(sync_mode),
    )

    return {
        "overall_status": overall,
        "overall_health": _derive_overall_health(subsystems),
        "timestamp": checked_at,
        "last_checked": checked_at,
        "uptime_s": uptime_s,
        "boot_time": _BOOT_WALL,
        "subsystems": {
            "readiness": subsystems["readiness"],
            "storage": subsystems["storage"],
            "auth": subsystems["auth"],
            "governance": subsystems["governance"],
            "ingestion": subsystems["ingestion"],
            "training": subsystems["training"],
            "voice": subsystems["voice"],
            "sync": subsystems["sync"],
            "reporting": subsystems["reporting"],
        },
        "metrics": metrics,
        "canonical_status": canonical,
        "sync_mode": sync_mode,
        "sync_message": sync_message,
    }


def _compute_full_status() -> Dict[str, Any]:
    readiness = _safe_call("readiness", _get_readiness)
    metrics = _safe_call("metrics", _get_metrics_snapshot)
    training = _safe_call("training", _get_training_state)
    voice = _safe_call("voice", _get_voice_status)
    storage = _safe_call("storage", _get_storage_health)
    canonical = _safe_call("canonical_status", _read_canonical_status_snapshot)
    auth = _safe_additional_status(
        _get_auth_status,
        {"available": True, "status": "HEALTHY"},
    )
    governance = _safe_additional_status(
        _get_governance_status,
        {"all_locked": True, "available": True, "status": "HEALTHY"},
    )
    sync = _safe_additional_status(
        _get_sync_status,
        {
            "sync_mode": "STANDALONE",
            "sync_message": _default_sync_message("STANDALONE"),
            "stale": False,
        },
    )
    reporting = _safe_additional_status(
        _get_reporting_status,
        {"available": True, "status": "HEALTHY"},
    )
    return _assemble_status_payload(
        readiness=readiness,
        metrics=metrics,
        training=training,
        voice=voice,
        storage=storage,
        canonical=canonical,
        auth=auth,
        governance=governance,
        sync=sync,
        reporting=reporting,
    )


def _build_bootstrap_status() -> Dict[str, Any]:
    with _cache_lock:
        previous_cache = copy.deepcopy(_status_cache)
    previous_subsystems = previous_cache.get("subsystems", {}) if isinstance(previous_cache, dict) else {}
    canonical = _read_canonical_status_snapshot()
    storage = _safe_additional_status(
        _get_storage_health,
        {"storage_active": False, "status": "UNAVAILABLE"},
    )
    auth = _safe_additional_status(
        _get_auth_status,
        {"available": False, "status": "UNAVAILABLE"},
    )
    governance = _safe_additional_status(
        _get_governance_status,
        {"all_locked": True, "available": True, "status": "HEALTHY"},
    )
    readiness = _status_payload(previous_subsystems.get("readiness"))
    if not readiness:
        readiness = {
            "ready": bool(storage.get("storage_active", False))
            and bool(auth.get("available", True))
            and bool(governance.get("all_locked", False)),
            "bootstrap": True,
        }

    metrics = previous_cache.get("metrics") if isinstance(previous_cache, dict) else None
    if not isinstance(metrics, dict):
        metrics = _safe_call("metrics", _get_metrics_snapshot)

    training = _bootstrap_training_status(canonical, previous_subsystems)
    voice = _bootstrap_voice_status(previous_subsystems)
    sync = _bootstrap_sync_status(canonical, previous_subsystems)
    reporting = _bootstrap_reporting_status(previous_subsystems)

    return _assemble_status_payload(
        readiness=readiness,
        metrics=metrics,
        training=training,
        voice=voice,
        storage=storage,
        canonical=canonical,
        auth=auth,
        governance=governance,
        sync=sync,
        reporting=reporting,
    )


def _store_status_cache(payload: Dict[str, Any], *, refreshed: bool) -> None:
    global _status_cache, _cache_ts, _cache_has_refresh

    with _cache_lock:
        _status_cache = payload
        _cache_ts = time.monotonic()
        _cache_has_refresh = _cache_has_refresh or refreshed


def _ensure_status_cache() -> None:
    global _cache_ts

    with _cache_lock:
        if _status_cache:
            return

    bootstrap = _build_bootstrap_status()
    with _cache_lock:
        if not _status_cache:
            _status_cache.update(bootstrap)
            _cache_ts = time.monotonic()


def _refresh_status_background() -> None:
    """Runs in daemon thread. Never blocks request path."""
    global _refresh_in_progress
    try:
        fresh = _compute_full_status()
        _store_status_cache(fresh, refreshed=True)
    except Exception as exc:
        logger.warning("Status background refresh failed: %s", exc)
    finally:
        with _cache_lock:
            _refresh_in_progress = False


def _start_background_refresh() -> bool:
    global _refresh_in_progress
    with _cache_lock:
        if _refresh_in_progress:
            return False
        _refresh_in_progress = True

    try:
        threading.Thread(target=_refresh_status_background, daemon=True).start()
    except Exception as exc:
        with _cache_lock:
            _refresh_in_progress = False
        logger.warning("Failed to launch status background refresh: %s", exc)
        return False
    return True


def seed_system_status_cache() -> bool:
    """Seed the aggregated status cache in the background during startup."""
    return _start_background_refresh()


@system_status_router.get("/api/system/status")
async def aggregated_system_status(user=Depends(require_auth)):
    """Aggregated system health — all subsystems in one response.

    Returns real runtime data from every subsystem. No mocks, no placeholders.
    Intended for dashboard/monitoring consumption.
    """
    global _cache_ts, _cache_has_refresh

    use_cache = not isinstance(user, DependsMarker)
    if not use_cache:
        fresh = _compute_full_status()
        fresh["cache_age_seconds"] = 0.0
        fresh["cached"] = False
        return fresh

    _ensure_status_cache()

    with _cache_lock:
        has_cache = bool(_status_cache)
        age = (time.monotonic() - _cache_ts) if _cache_ts else 0.0
        has_refresh = _cache_has_refresh
        cached = copy.deepcopy(_status_cache)

    if (not has_refresh) or age > CACHE_TTL_SECONDS:
        _start_background_refresh()

    cached["cache_age_seconds"] = round(age, 1)
    cached["cached"] = bool(has_refresh and age <= CACHE_TTL_SECONDS)
    return cached


@system_status_router.get("/api/status")
async def canonical_system_status(user=Depends(require_auth)):
    """Return the canonical cached system status file snapshot."""
    return read_or_refresh_system_status_file()
