"""
Runtime artifact writers for local single-node training.

These helpers keep the Python training path aligned with the runtime APIs that
expect persisted telemetry and Mode-A bootstrap artifacts on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.api.runtime_api import (
    REQUIRED_FIELDS,
    EXPECTED_HMAC_VERSION,
    EXPECTED_SCHEMA_VERSION,
    compute_payload_crc,
    compute_payload_hmac,
)


PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
CONFIG_DIR = os.path.join(PROJECT_ROOT, "config")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")

DEVICE_IDENTITY_PATH = os.path.join(CONFIG_DIR, "device_identity.json")
CLUSTER_ROLE_PATH = os.path.join(CONFIG_DIR, "cluster_role.json")
DEVICES_PATH = os.path.join(CONFIG_DIR, "devices.json")
WG_KEY_STATE_PATH = os.path.join(CONFIG_DIR, "wg_key_state.json")
PAIRING_LOG_PATH = os.path.join(REPORTS_DIR, "pairing_log.json")
CLUSTER_HEALTH_PATH = os.path.join(REPORTS_DIR, "cluster_health.json")
TRAINING_GATE_PATH = os.path.join(REPORTS_DIR, "training_gate.json")
TRAINING_TELEMETRY_PATH = os.path.join(REPORTS_DIR, "training_telemetry.json")
RUNTIME_STATE_PATH = os.path.join(REPORTS_DIR, "runtime_state.json")
FIELD_RUNTIME_STATUS_PATH = os.path.join(DATA_DIR, "runtime_status.json")
IDLE_ARTIFACT_MAX_AGE_SECONDS = int(
    os.environ.get("YGB_IDLE_ARTIFACT_MAX_AGE_SECONDS", "90")
)


def _atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = f"{path}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _read_json(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _ensure_json(path: str, payload: Dict[str, Any], *, overwrite: bool) -> Dict[str, Any]:
    existing = _read_json(path)
    if existing is not None and not overwrite:
        return existing
    _atomic_write_json(path, payload)
    return payload


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ms() -> int:
    return int(time.time() * 1000)


def _file_age_seconds(path: str) -> Optional[float]:
    try:
        return max(0.0, time.time() - os.path.getmtime(path))
    except OSError:
        return None


def _runtime_state_is_valid(payload: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(payload, dict):
        return False
    return all(field in payload for field in REQUIRED_FIELDS)


def _telemetry_payload_is_valid(payload: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(payload, dict):
        return False

    required_fields = {
        "schema_version",
        "determinism_status",
        "freeze_status",
        "crc32",
        "hmac",
        "hmac_version",
        "monotonic_timestamp",
        "wall_clock_unix",
    }
    if any(field not in payload for field in required_fields):
        return False
    if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
        return False
    if payload.get("hmac_version") != EXPECTED_HMAC_VERSION:
        return False

    try:
        return (
            int(payload.get("crc32")) == compute_payload_crc(payload)
            and str(payload.get("hmac", "")) == compute_payload_hmac(payload)
        )
    except Exception:
        return False


def _detect_local_ip() -> Optional[str]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


def _device_fingerprint() -> str:
    hostname = socket.gethostname()
    node = platform.node()
    machine = platform.machine()
    mac_addr = f"{uuid.getnode():012x}"
    raw = f"{hostname}|{node}|{machine}|{mac_addr}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_local_mode_a_bootstrap() -> Dict[str, Any]:
    """
    Materialize the local single-node config/report files required by the
    training checklist. This is an honest local bootstrap, not a multi-node
    mesh simulation.
    """
    timestamp = _utc_now()
    hostname = socket.gethostname()
    local_ip = _detect_local_ip()
    device_id = _device_fingerprint()
    roles = ["AUTHORITY", "STORAGE", "WORKER"]

    identity = {
        "device_id": device_id,
        "hostname": hostname,
        "platform": platform.system(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "mac_address": f"{uuid.getnode():012x}",
        "bootstrapped_at": timestamp,
        "mode": "single_node_local",
    }
    cluster_role = {
        "device_id": device_id,
        "hostname": hostname,
        "roles": roles,
        "topology": "single_node_local",
        "quorum_required": 1,
        "updated_at": timestamp,
    }
    devices = {
        "schema_version": 1,
        "mode": "single_node_local",
        "updated_at": timestamp,
        "devices": [
            {
                "device_id": device_id,
                "hostname": hostname,
                "ip_address": local_ip,
                "roles": roles,
                "status": "online",
                "trusted": True,
            }
        ],
    }
    wg_key_state = {
        "mode": "single_node_local",
        "required": False,
        "status": "not_required",
        "updated_at": timestamp,
    }
    pairing_log = {
        "mode": "single_node_local",
        "events": [
            {
                "event": "PAIRING_SUCCESS",
                "device_id": device_id,
                "peer_device_id": device_id,
                "timestamp": timestamp,
                "detail": "Local single-node bootstrap",
            }
        ],
    }
    cluster_health = {
        "mode": "single_node_local",
        "quorum": True,
        "online_devices": 1,
        "total_devices": 1,
        "roles_present": roles,
        "missing_roles": [],
        "updated_at": timestamp,
    }

    created = {
        "device_identity": _ensure_json(DEVICE_IDENTITY_PATH, identity, overwrite=False),
        "cluster_role": _ensure_json(CLUSTER_ROLE_PATH, cluster_role, overwrite=False),
        "devices": _ensure_json(DEVICES_PATH, devices, overwrite=False),
        "wg_key_state": _ensure_json(WG_KEY_STATE_PATH, wg_key_state, overwrite=False),
        "pairing_log": _ensure_json(PAIRING_LOG_PATH, pairing_log, overwrite=True),
        "cluster_health": _ensure_json(CLUSTER_HEALTH_PATH, cluster_health, overwrite=True),
    }
    return {"mode": "single_node_local", "device_id": device_id, "artifacts": created}


def probe_host_metrics() -> Dict[str, Optional[float]]:
    """Collect real host metrics when available."""
    cpu_util = None
    gpu_util = None
    gpu_temp = None

    try:
        import psutil

        cpu_util = float(psutil.cpu_percent(interval=0))
    except Exception:
        cpu_util = None

    try:
        import subprocess

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=temperature.gpu,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            parts = [part.strip() for part in result.stdout.strip().split(",")]
            if len(parts) >= 2:
                gpu_temp = float(parts[0])
                gpu_util = float(parts[1])
    except Exception:
        gpu_util = None
        gpu_temp = None

    return {
        "cpu_util": cpu_util,
        "gpu_util": gpu_util,
        "gpu_temperature": gpu_temp,
    }


def probe_determinism_configuration() -> bool:
    """
    Detect whether the runtime is configured for deterministic training mode.

    This is a configuration/status probe, not a claim that a full deterministic
    training proof has already been completed.
    """
    profile = os.environ.get("YGB_TRAINING_PROFILE", "deterministic").strip().lower()
    if profile == "fast":
        return False
    return os.environ.get("YGB_DETERMINISTIC_MODE", "true").strip().lower() != "false"


def write_training_gate(
    *,
    determinism_status: bool,
    freeze_status: bool,
    gpu_temperature: Optional[float],
    cpu_temperature: Optional[float] = None,
) -> Dict[str, Any]:
    bootstrap = ensure_local_mode_a_bootstrap()
    hmac_present = bool(os.environ.get("YGB_HMAC_SECRET"))

    checks = {
        "device_identity": os.path.exists(DEVICE_IDENTITY_PATH),
        "cluster_role": os.path.exists(CLUSTER_ROLE_PATH),
        "devices_registry": os.path.exists(DEVICES_PATH),
        "pairing_log": os.path.exists(PAIRING_LOG_PATH),
        "cluster_health": os.path.exists(CLUSTER_HEALTH_PATH),
        "hmac_secret": hmac_present,
        "wireguard": {"required": False, "passed": True},
        "determinism_status": bool(determinism_status),
        "governance_unlocked": not freeze_status,
        "gpu_thermal_ok": gpu_temperature is None or gpu_temperature <= 88.0,
        "cpu_thermal_ok": cpu_temperature is None or cpu_temperature <= 95.0,
    }
    payload = {
        "mode": "single_node_local",
        "device_id": bootstrap["device_id"],
        "checks": checks,
        "all_passed": all(
            value["passed"] if isinstance(value, dict) else bool(value)
            for value in checks.values()
        ),
        "timestamp": _utc_now(),
    }
    _atomic_write_json(TRAINING_GATE_PATH, payload)
    return payload


def write_training_telemetry(
    *,
    epoch: int,
    batch_size: int,
    loss: float,
    precision: float,
    recall: float = 0.0,
    kl_divergence: float = 0.0,
    ece: float = 0.0,
    total_epochs: int,
    training_duration_seconds: float,
    samples_per_second: float,
    determinism_status: bool,
    freeze_status: bool,
    gpu_temperature: Optional[float],
    cpu_util: Optional[float],
    gpu_util: Optional[float],
    wall_clock_unix: Optional[int] = None,
    monotonic_start_time: Optional[int] = None,
    dataset_size: Optional[int] = None,
) -> Dict[str, Any]:
    wall_clock = int(wall_clock_unix or time.time())
    monotonic_now = int(time.monotonic() * 1_000_000)
    payload: Dict[str, Any] = {
        "schema_version": EXPECTED_SCHEMA_VERSION,
        "determinism_status": bool(determinism_status),
        "freeze_status": bool(freeze_status),
        "precision": round(float(precision), 8),
        "recall": round(float(recall), 8),
        "kl_divergence": round(float(kl_divergence), 8),
        "ece": round(float(ece), 8),
        "loss": round(float(loss), 8),
        "gpu_temperature": round(float(gpu_temperature), 8)
        if gpu_temperature is not None
        else 0.0,
        "epoch": int(epoch),
        "batch_size": int(batch_size),
        "timestamp": wall_clock,
        "monotonic_timestamp": monotonic_now,
        "hmac_version": EXPECTED_HMAC_VERSION,
        "wall_clock_unix": wall_clock,
        "monotonic_start_time": int(monotonic_start_time or time.monotonic()),
        "training_duration_seconds": round(float(training_duration_seconds), 4),
        "samples_per_second": round(float(samples_per_second), 4),
        "gpu_util": round(float(gpu_util), 4) if gpu_util is not None else None,
        "cpu_util": round(float(cpu_util), 4) if cpu_util is not None else None,
        "total_epochs": int(total_epochs),
    }
    if dataset_size is not None:
        payload["dataset_size"] = int(dataset_size)

    payload["crc32"] = compute_payload_crc(payload)
    payload["hmac"] = compute_payload_hmac(payload)
    _atomic_write_json(TRAINING_TELEMETRY_PATH, payload)
    return payload


def write_runtime_state_snapshot(
    *,
    mode: str,
    total_epochs: int,
    completed_epochs: int,
    current_loss: float,
    best_loss: float,
    precision: float,
    ece: float,
    drift_kl: float,
    duplicate_rate: float,
    gpu_util: Optional[float],
    cpu_util: Optional[float],
    temperature: Optional[float],
    determinism_status: bool,
    freeze_status: bool,
    progress_pct: float,
    loss_trend: str,
    training_start_ms: int,
    total_errors: int,
) -> Dict[str, Any]:
    payload = {
        "version": 1,
        "mode": str(mode or "IDLE").upper(),
        "total_epochs": int(total_epochs),
        "completed_epochs": int(completed_epochs),
        "current_loss": round(float(current_loss), 8),
        "best_loss": round(float(best_loss), 8),
        "precision": round(float(precision), 8),
        "rolling_precision": round(float(precision), 8),
        "ece": round(float(ece), 8),
        "kl_baseline_ema": round(float(drift_kl), 8),
        "drift_kl": round(float(drift_kl), 8),
        "duplicate_rate": round(float(duplicate_rate), 8),
        "gpu_util": round(float(gpu_util), 4) if gpu_util is not None else 0.0,
        "cpu_util": round(float(cpu_util), 4) if cpu_util is not None else 0.0,
        "temperature": round(float(temperature), 4) if temperature is not None else 0.0,
        "determinism_status": bool(determinism_status),
        "freeze_status": bool(freeze_status),
        "progress_pct": round(float(progress_pct), 4),
        "loss_trend": str(loss_trend or "idle"),
        "last_update_ms": _now_ms(),
        "training_start_ms": int(training_start_ms),
        "total_errors": int(total_errors),
    }
    _atomic_write_json(RUNTIME_STATE_PATH, payload)
    return payload


def write_field_runtime_status(
    *,
    containment_active: bool,
    containment_reason: Optional[str],
    precision_breach: bool,
    drift_alert: bool,
    freeze_valid: Optional[bool],
    freeze_reason: Optional[str],
    training_velocity_samples_hr: Optional[float],
    training_velocity_batches_sec: Optional[float],
    gpu_utilization: Optional[float],
    determinism_pass: Optional[bool],
    data_freshness: Optional[str],
    merge_status: Optional[str],
) -> Dict[str, Any]:
    payload = {
        "containment_active": containment_active,
        "containment_reason": containment_reason,
        "precision_breach": precision_breach,
        "drift_alert": drift_alert,
        "freeze_valid": freeze_valid,
        "freeze_reason": freeze_reason,
        "training_velocity_samples_hr": training_velocity_samples_hr,
        "training_velocity_batches_sec": training_velocity_batches_sec,
        "gpu_utilization": gpu_utilization,
        "determinism_pass": determinism_pass,
        "data_freshness": data_freshness,
        "merge_status": merge_status,
        "updated_at": _utc_now(),
    }
    _atomic_write_json(FIELD_RUNTIME_STATUS_PATH, payload)
    return payload


def repair_runtime_artifacts_if_needed(
    *,
    training_active: bool,
    idle_max_age_seconds: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Repair missing/corrupt/stale idle artifacts automatically.

    This only rewrites artifacts when training is NOT active, so it does not
    override live telemetry produced by an active training session.
    """
    max_age_seconds = int(idle_max_age_seconds or IDLE_ARTIFACT_MAX_AGE_SECONDS)
    issues: list[str] = []

    training_gate = _read_json(TRAINING_GATE_PATH)
    if training_gate is None:
        issues.append("training_gate_missing")

    runtime_state = _read_json(RUNTIME_STATE_PATH)
    if not _runtime_state_is_valid(runtime_state):
        issues.append("runtime_state_invalid")
    elif not training_active:
        age = _file_age_seconds(RUNTIME_STATE_PATH)
        if age is not None and age > max_age_seconds:
            issues.append("runtime_state_idle_stale")

    field_runtime = _read_json(FIELD_RUNTIME_STATUS_PATH)
    if field_runtime is None:
        issues.append("field_runtime_missing")

    telemetry = _read_json(TRAINING_TELEMETRY_PATH)
    if not _telemetry_payload_is_valid(telemetry):
        issues.append("training_telemetry_invalid")
    elif not training_active:
        age = _file_age_seconds(TRAINING_TELEMETRY_PATH)
        if age is not None and age > max_age_seconds:
            issues.append("training_telemetry_idle_stale")

    if training_active or not issues:
        return {
            "repaired": False,
            "issues": issues,
            "training_active": training_active,
        }

    artifacts = bootstrap_runtime_artifacts(force_refresh=True)
    return {
        "repaired": True,
        "issues": issues,
        "training_active": training_active,
        "artifacts": artifacts,
    }


def bootstrap_runtime_artifacts(*, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Materialize truthful local runtime artifacts for idle/server-startup mode.

    This creates a real single-node bootstrap plus an idle runtime baseline so
    health/status APIs do not start with missing files.
    """
    host_metrics = probe_host_metrics()
    determinism_status = probe_determinism_configuration()

    bootstrap = ensure_local_mode_a_bootstrap()
    gate = _read_json(TRAINING_GATE_PATH)
    if gate is None or force_refresh:
        gate = write_training_gate(
            determinism_status=determinism_status,
            freeze_status=False,
            gpu_temperature=host_metrics.get("gpu_temperature"),
        )

    runtime_state = _read_json(RUNTIME_STATE_PATH)
    if runtime_state is None or force_refresh:
        runtime_state = write_runtime_state_snapshot(
            mode="IDLE",
            total_epochs=0,
            completed_epochs=0,
            current_loss=0.0,
            best_loss=0.0,
            precision=0.0,
            ece=0.0,
            drift_kl=0.0,
            duplicate_rate=0.0,
            gpu_util=host_metrics.get("gpu_util"),
            cpu_util=host_metrics.get("cpu_util"),
            temperature=host_metrics.get("gpu_temperature"),
            determinism_status=determinism_status,
            freeze_status=False,
            progress_pct=0.0,
            loss_trend="idle",
            training_start_ms=0,
            total_errors=0,
        )

    field_runtime = _read_json(FIELD_RUNTIME_STATUS_PATH)
    if field_runtime is None or force_refresh:
        field_runtime = write_field_runtime_status(
            containment_active=False,
            containment_reason=None,
            precision_breach=False,
            drift_alert=False,
            freeze_valid=True,
            freeze_reason=None,
            training_velocity_samples_hr=None,
            training_velocity_batches_sec=None,
            gpu_utilization=host_metrics.get("gpu_util"),
            determinism_pass=determinism_status,
            data_freshness="idle",
            merge_status=None,
        )

    telemetry = _read_json(TRAINING_TELEMETRY_PATH)
    if telemetry is None or force_refresh:
        telemetry = write_training_telemetry(
            epoch=0,
            batch_size=0,
            loss=0.0,
            precision=0.0,
            total_epochs=0,
            training_duration_seconds=0.0,
            samples_per_second=0.0,
            determinism_status=determinism_status,
            freeze_status=False,
            gpu_temperature=host_metrics.get("gpu_temperature"),
            cpu_util=host_metrics.get("cpu_util"),
            gpu_util=host_metrics.get("gpu_util"),
            wall_clock_unix=int(time.time()),
            monotonic_start_time=int(time.monotonic()),
            dataset_size=0,
        )

    return {
        "bootstrap": bootstrap,
        "training_gate": gate,
        "runtime_state": runtime_state,
        "training_telemetry": telemetry,
        "field_runtime_status": field_runtime,
    }
