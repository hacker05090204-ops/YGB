"""
runtime_api.py — Backend Runtime Hard Validation API with HMAC + Replay Protection
====================================================================================
Endpoint:
  GET  /runtime/status  — Validated runtime state

Before returning runtime data:
  1. Load reports/training_telemetry.json
  2. Validate HMAC-SHA256
  3. Validate CRC32 (recompute and match)
  4. Validate monotonic_timestamp > last_seen (replay protection)
  5. Validate schema_version
  6. Validate determinism_status == true
  7. If ANY fail → return {"status": "corrupted", "reason": "..."}

Never trust partial state.
Never trust unsigned telemetry.
Never expose replayed telemetry.
NO silent fallback.
"""

import os
import json
import hmac
import hashlib
import struct
import logging
import time
import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Response, status as http_status

from backend.auth.auth_guard import require_auth
from backend.training.auto_train_controller import get_auto_train_controller

logger = logging.getLogger(__name__)

router = APIRouter(tags=["runtime"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

TELEMETRY_PATH = os.path.join(PROJECT_ROOT, 'reports', 'training_telemetry.json')
LAST_SEEN_PATH = os.path.join(PROJECT_ROOT, 'reports', 'last_seen_timestamp.json')
EXPECTED_SCHEMA_VERSION = 1
EXPECTED_HMAC_VERSION = 4  # Emergency rotation: previous key exposed in git

# Runtime state file (used by get_runtime_status for non-telemetry state)
RUNTIME_STATE_PATH = os.path.join(PROJECT_ROOT, 'reports', 'runtime_state.json')

# Required fields for valid runtime state
REQUIRED_FIELDS = [
    'total_epochs', 'completed_epochs', 'current_loss', 'best_loss',
    'precision', 'ece', 'drift_kl', 'duplicate_rate',
    'gpu_util', 'cpu_util', 'temperature',
    'determinism_status', 'freeze_status', 'mode',
    'progress_pct', 'loss_trend', 'last_update_ms',
    'training_start_ms', 'total_errors'
]

STALE_THRESHOLD_MS = 30_000  # 30 seconds
_TRUTHY_VALUES = {"1", "true", "yes", "on"}


def _validate_structure(data: dict) -> list:
    """Return list of missing required fields."""
    return [f for f in REQUIRED_FIELDS if f not in data]


def _sign_payload(payload: dict) -> str:
    """Compute deterministic signature for a runtime payload."""
    import hashlib
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _new_trace_id() -> str:
    """Create a short trace identifier for API responses and logs."""
    return str(uuid.uuid4())[:8]


def _serialize_detail(detail):
    """Convert dataclasses/enums into JSON-serializable structures."""
    if is_dataclass(detail):
        return _serialize_detail(asdict(detail))
    if isinstance(detail, dict):
        return {str(key): _serialize_detail(value) for key, value in detail.items()}
    if isinstance(detail, list):
        return [_serialize_detail(item) for item in detail]
    if hasattr(detail, 'value') and not isinstance(
        detail,
        (str, bytes, int, float, bool, type(None)),
    ):
        return _serialize_detail(detail.value)
    return detail


def _finalize_handler_result(handler_name: str, trace_id: str, started_at: float, result: dict) -> dict:
    """Attach trace metadata and emit exit timing logs."""
    payload = dict(result)
    payload.setdefault("trace_id", trace_id)
    duration_ms = round((time.perf_counter() - started_at) * 1000.0, 2)
    logger.info(
        "runtime_api exit handler=%s trace_id=%s duration_ms=%.2f status=%s",
        handler_name,
        trace_id,
        duration_ms,
        payload.get("status", "ok"),
    )
    return payload


def _runtime_error_response(trace_id: str, error, **extras) -> dict:
    """Standardized runtime API error payload."""
    payload = {
        "trace_id": trace_id,
        "status": "error",
        "detail": str(error),
    }
    payload.update(extras)
    return payload


def _component_payload(status: str, detail) -> dict:
    """Build a component status entry for detailed status responses."""
    return {
        "status": status,
        "detail": _serialize_detail(detail),
    }


def _load_circuit_breaker_component() -> dict:
    """Summarize circuit breaker state from CVE pipeline source status."""
    from backend.cve.cve_pipeline import get_pipeline

    source_status = get_pipeline().get_source_status()
    status = "unknown" if not source_status else "ok"
    if any(
        details.get("circuit_breaker") in {"OPEN", "HALF_OPEN"}
        for details in source_status.values()
    ):
        status = "degraded"
    return _component_payload(status, source_status)


def _load_peer_status_component() -> dict:
    """Summarize peer connectivity state."""
    from backend.sync.peer_transport import get_peer_statuses

    peer_statuses = _serialize_detail(get_peer_statuses())
    status = "unknown" if not peer_statuses else "ok"
    if any(value in {"DEGRADED", "UNREACHABLE"} for value in peer_statuses.values()):
        status = "degraded"
    return _component_payload(status, peer_statuses)


def _load_tier_health_component() -> dict:
    """Summarize storage tier health probes."""
    from backend.storage.tiered_storage import get_tier_health

    tiers = _serialize_detail(get_tier_health())
    status = "unknown" if not tiers else "ok"
    if any(
        isinstance(tier, dict)
        and (
            float(tier.get("read_latency_ms", -1.0)) < 0.0
            or float(tier.get("write_latency_ms", -1.0)) < 0.0
        )
        for tier in tiers
    ):
        status = "degraded"
    return _component_payload(status, tiers)


def _load_feature_health_component() -> dict:
    """Summarize feature-bridge health."""
    from backend.training.feature_bridge import FeatureDiversifier

    health = _serialize_detail(FeatureDiversifier().get_health())
    total = int(health.get("total", 0)) if isinstance(health, dict) else 0
    invalid = int(health.get("invalid", 0)) if isinstance(health, dict) else 0
    status = "unknown" if total == 0 else "ok"
    if invalid > 0:
        status = "degraded"
    return _component_payload(status, health)


def _load_last_batch_component() -> dict:
    """Return the most recent bridge ingestion batch summary."""
    from backend.cve.bridge_ingestion_worker import get_bridge_worker

    worker_status = get_bridge_worker().get_status()
    last_batch = worker_status.get("last_batch")
    status = "ok" if last_batch else "unknown"
    return _component_payload(status, last_batch)


# =========================================================================
# SAFE SECRET LOADER (Phase 3: Never access at import time)
# =========================================================================

def get_hmac_secret() -> str:
    """Get HMAC secret. Always requires a real secret — no mock fallback."""
    secret = os.environ.get('YGB_HMAC_SECRET', '').strip()
    if not secret:
        raise RuntimeError(
            "YGB_HMAC_SECRET not set. "
            "Set it via the environment before startup. "
            "No mock/test fallback permitted."
        )
    return secret


# =========================================================================
# CRC32 (must match C++ training_telemetry.cpp implementation)
# =========================================================================

def _crc32_table():
    """Build CRC32 lookup table (same polynomial as C++ impl)."""
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xEDB88320
            else:
                crc >>= 1
        table.append(crc)
    return table

_CRC_TABLE = _crc32_table()


def compute_crc32(data: bytes) -> int:
    """Compute CRC32 matching the C++ implementation."""
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC_TABLE[(crc ^ byte) & 0xFF]
    return crc ^ 0xFFFFFFFF


def compute_payload_crc(payload: dict) -> int:
    """Compute CRC over payload fields (must match C++ format string)."""
    crc_string = (
        f"v{payload.get('schema_version', 0)}"
        f"|det:{1 if payload.get('determinism_status') else 0}"
        f"|frz:{1 if payload.get('freeze_status') else 0}"
        f"|prec:{payload.get('precision', 0.0):.8f}"
        f"|rec:{payload.get('recall', 0.0):.8f}"
        f"|kl:{payload.get('kl_divergence', 0.0):.8f}"
        f"|ece:{payload.get('ece', 0.0):.8f}"
        f"|loss:{payload.get('loss', 0.0):.8f}"
        f"|temp:{payload.get('gpu_temperature', 0.0):.8f}"
        f"|epoch:{payload.get('epoch', 0)}"
        f"|batch:{payload.get('batch_size', 0)}"
        f"|ts:{payload.get('timestamp', 0)}"
        f"|mono:{payload.get('monotonic_timestamp', 0)}"
    )
    return compute_crc32(crc_string.encode('ascii'))


# =========================================================================
# HMAC-SHA256 VALIDATION
# =========================================================================

def load_hmac_key() -> bytes:
    """Load the HMAC secret key from environment variables only."""
    env_secret = os.environ.get('YGB_HMAC_SECRET', '').strip()
    if env_secret:
        try:
            return bytes.fromhex(env_secret)
        except ValueError:
            return env_secret.encode('utf-8')

    raise RuntimeError(
        "HMAC secret not configured. Set YGB_HMAC_SECRET before startup."
    )


def compute_payload_hmac(payload: dict) -> str:
    """Compute HMAC-SHA256 over schema_version|crc32|timestamp."""
    key = load_hmac_key()
    if not key:
        return ''

    msg = f"{payload.get('schema_version', 0)}|{payload.get('crc32', 0)}|{payload.get('timestamp', 0)}"
    digest = hmac.new(key, msg.encode('ascii'), hashlib.sha256).hexdigest()
    return digest


def validate_hmac(payload: dict) -> bool:
    """Validate HMAC-SHA256 signature on telemetry payload."""
    stored_hmac = payload.get('hmac', '')
    if not stored_hmac:
        return False

    expected = compute_payload_hmac(payload)
    if not expected:
        return False

    return hmac.compare_digest(stored_hmac, expected)


# =========================================================================
# MONOTONIC TIMESTAMP REPLAY PROTECTION
# =========================================================================

def load_last_seen_timestamp() -> int:
    """Load last seen monotonic timestamp from persistence."""
    try:
        with open(LAST_SEEN_PATH, 'r') as f:
            data = json.load(f)
        return int(data.get('last_seen', 0))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return 0


def save_last_seen_timestamp(ts: int) -> None:
    """Persist last seen monotonic timestamp atomically."""
    tmp_path = LAST_SEEN_PATH + '.tmp'
    try:
        with open(tmp_path, 'w') as f:
            json.dump({"last_seen": ts}, f)
            f.flush()
            os.fsync(f.fileno())
        # Atomic replace
        if os.path.exists(LAST_SEEN_PATH):
            os.remove(LAST_SEEN_PATH)
        os.rename(tmp_path, LAST_SEEN_PATH)
    except Exception as e:
        logger.error("Failed to save last_seen_timestamp: %s", e)


# =========================================================================
# VALIDATION
# =========================================================================

def validate_telemetry() -> dict:
    """
    Load and validate runtime telemetry.
    Returns validated data or error response.
    Never returns partial state.
    Never trusts unsigned or replayed telemetry.
    """
    # Step 1: Load file
    if not os.path.exists(TELEMETRY_PATH):
        logger.error("Telemetry file missing: %s", TELEMETRY_PATH)
        return {
            "status": "corrupted",
            "reason": "telemetry_missing",
            "detail": "Telemetry file missing"
        }

    try:
        with open(TELEMETRY_PATH, 'r') as f:
            raw = f.read()
    except Exception as e:
        logger.error("Failed to read telemetry: %s", e)
        return {
            "status": "corrupted",
            "reason": "read_failed",
            "detail": "Read failed — check server logs"
        }

    # Step 2: Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Telemetry JSON parse failed: %s", e)
        return {
            "status": "corrupted",
            "reason": "json_parse_failed",
            "detail": "JSON parse failed — check server logs"
        }

    # Step 3: Validate required fields
    required_fields = ['schema_version', 'determinism_status', 'freeze_status',
                       'crc32', 'hmac', 'monotonic_timestamp']
    for field in required_fields:
        if field not in data:
            logger.error("Telemetry missing field: %s", field)
            return {
                "status": "corrupted",
                "reason": "missing_field",
                "detail": f"Missing required field: {field}"
            }

    # Step 4: Validate HMAC (FIRST — reject unsigned telemetry immediately)
    if not validate_hmac(data):
        logger.error("HMAC validation failed — unsigned or tampered telemetry")
        return {
            "status": "corrupted",
            "reason": "hmac_invalid",
            "detail": "HMAC signature invalid or missing"
        }

    # Step 5: Validate CRC32
    stored_crc = data['crc32']
    computed_crc = compute_payload_crc(data)
    if stored_crc != computed_crc:
        logger.error(
            "CRC mismatch: stored=%d computed=%d",
            stored_crc, computed_crc
        )
        return {
            "status": "corrupted",
            "reason": "crc_mismatch",
            "detail": f"CRC mismatch: stored={stored_crc} computed={computed_crc}"
        }

    # Step 6: Validate monotonic_timestamp > last_seen (replay protection)
    monotonic_ts = data.get('monotonic_timestamp', 0)
    last_seen = load_last_seen_timestamp()
    if last_seen > 0 and monotonic_ts <= last_seen:
        logger.error(
            "REPLAY DETECTED: monotonic_timestamp=%d <= last_seen=%d",
            monotonic_ts, last_seen
        )
        return {
            "status": "corrupted",
            "reason": "replay_detected",
            "detail": f"Replay detected: monotonic_timestamp={monotonic_ts} <= last_seen={last_seen}"
        }

    # Step 7: Validate schema version
    if data['schema_version'] != EXPECTED_SCHEMA_VERSION:
        logger.error(
            "Schema version mismatch: got %s, expected %s",
            data['schema_version'], EXPECTED_SCHEMA_VERSION
        )
        return {
            "status": "corrupted",
            "reason": "schema_mismatch",
            "detail": f"Schema version mismatch: {data['schema_version']}"
        }

    # Step 8: Validate determinism_status
    if data['determinism_status'] is not True:
        logger.error("determinism_status is not true")
        return {
            "status": "corrupted",
            "reason": "determinism_failed",
            "detail": "determinism_status is false"
        }

    # Step 9: THERMAL HALT — reject if GPU temperature > 88°C
    gpu_temp = data.get('gpu_temperature', 0.0)
    if isinstance(gpu_temp, (int, float)) and gpu_temp > 88.0:
        logger.error("THERMAL HALT: gpu_temperature=%.1f > 88.0°C", gpu_temp)
        return {
            "status": "corrupted",
            "reason": "thermal_limit",
            "detail": f"GPU temperature {gpu_temp:.1f}°C exceeds 88°C safety limit"
        }

    # Step 10: GOVERNANCE LOCK — reject if freeze_status is active
    if data.get('freeze_status') is True:
        logger.error("GOVERNANCE LOCK ACTIVE: freeze_status=true — training blocked")
        return {
            "status": "corrupted",
            "reason": "governance_lock",
            "detail": "Governance freeze is active — training halted"
        }

    # Step 11: STRICT HMAC VERSION CHECK — no backward compatibility
    hmac_ver = data.get('hmac_version')
    if hmac_ver is None:
        logger.error("HMAC version MISSING from telemetry — strict rejection")
        return {
            "status": "corrupted",
            "reason": "hmac_version_missing",
            "detail": f"hmac_version field required, expected {EXPECTED_HMAC_VERSION}"
        }
    if hmac_ver != EXPECTED_HMAC_VERSION:
        logger.error("HMAC version mismatch: got %s, expected %s",
                     hmac_ver, EXPECTED_HMAC_VERSION)
        return {
            "status": "corrupted",
            "reason": "hmac_version_mismatch",
            "detail": f"HMAC version {hmac_ver} != expected {EXPECTED_HMAC_VERSION}"
        }

    # All checks passed — update last_seen atomically
    if monotonic_ts > last_seen:
        save_last_seen_timestamp(monotonic_ts)

    return {
        "status": "ok",
        "data": data,
        "validated": True
    }


# =========================================================================
# ENDPOINT HANDLERS
# =========================================================================

def get_runtime_status():
    """
    GET /runtime/status

    Returns validated runtime state from RUNTIME_STATE_PATH.
    Falls back to HMAC-validated telemetry only when explicitly enabled.
    Separates storage_engine_status from dataset_readiness_status.
    Blocks 'training ready' if dataset is blocked.
    """
    trace_id = _new_trace_id()
    started_at = time.perf_counter()

    # Determine dataset readiness (strict real mode check)
    strict_real = os.environ.get("YGB_STRICT_REAL_MODE", "true").lower() != "false"
    min_samples = int(os.environ.get("YGB_MIN_REAL_SAMPLES", "125000"))
    dataset_readiness = {
        "status": "BLOCKED_REAL_DATA",
        "strict_real_mode": strict_real,
        "min_samples_required": min_samples,
        "reason": f"Strict real mode active — need {min_samples} verified samples before training"
    }

    try:
        # Try runtime state file first
        if os.path.exists(RUNTIME_STATE_PATH):
            with open(RUNTIME_STATE_PATH, 'r') as f:
                data = json.load(f)

            missing = _validate_structure(data)
            if missing:
                return _finalize_handler_result(
                    "get_runtime_status",
                    trace_id,
                    started_at,
                    {
                        "status": "invalid",
                        "storage_engine_status": "ERROR",
                        "dataset_readiness": dataset_readiness,
                        "message": f"Missing required fields: {', '.join(missing)}",
                        "timestamp": int(time.time() * 1000),
                    },
                )

            now_ms = int(time.time() * 1000)
            last_update = data.get('last_update_ms', 0)
            stale = (now_ms - last_update) > STALE_THRESHOLD_MS

            # Determine storage engine status
            if stale:
                storage_status = "STALE"
            elif data.get('total_errors', 0) > 0:
                storage_status = "DEGRADED"
            else:
                storage_status = "ACTIVE"

            # Block training_ready if dataset is blocked
            training_ready = (
                not stale
                and data.get('determinism_status', False)
                and dataset_readiness["status"] != "BLOCKED_REAL_DATA"
            )

            return _finalize_handler_result(
                "get_runtime_status",
                trace_id,
                started_at,
                {
                    "status": "active",
                    "storage_engine_status": storage_status,
                    "dataset_readiness": dataset_readiness,
                    "training_ready": training_ready,
                    "runtime": data,
                    "signature": _sign_payload(data),
                    "stale": stale,
                    "determinism_ok": data.get('determinism_status', False),
                    "timestamp": now_ms,
                },
            )

        # Optional telemetry fallback for deployments that still expose only the
        # signed telemetry stream. Default is fail-safe awaiting_data because test
        # and cold-start environments often have stale telemetry artifacts.
        telemetry_fallback_enabled = (
            os.environ.get("YGB_RUNTIME_ALLOW_TELEMETRY_FALLBACK", "false")
            .strip()
            .lower()
            in _TRUTHY_VALUES
        )
        if telemetry_fallback_enabled and os.path.exists(TELEMETRY_PATH):
            result = validate_telemetry()
            result["storage_engine_status"] = "ACTIVE" if result.get("status") == "ok" else "ERROR"
            result["dataset_readiness"] = dataset_readiness
            result["training_ready"] = False  # Always blocked until dataset ready
            return _finalize_handler_result(
                "get_runtime_status",
                trace_id,
                started_at,
                result,
            )

        return _finalize_handler_result(
            "get_runtime_status",
            trace_id,
            started_at,
            {
                "status": "awaiting_data",
                "storage_engine_status": "NOT_INITIALIZED",
                "dataset_readiness": dataset_readiness,
                "training_ready": False,
                "message": "No runtime state yet",
                "timestamp": int(time.time() * 1000),
            },
        )
    except json.JSONDecodeError as e:
        logger.warning("runtime_api [%s]: %s", trace_id, repr(e))
        return _finalize_handler_result(
            "get_runtime_status",
            trace_id,
            started_at,
            _runtime_error_response(
                trace_id,
                e,
                message="Corrupt runtime state file",
                storage_engine_status="ERROR",
                dataset_readiness=dataset_readiness,
                timestamp=int(time.time() * 1000),
            ),
        )
    except Exception as e:
        logger.warning("runtime_api [%s]: %s", trace_id, repr(e))
        return _finalize_handler_result(
            "get_runtime_status",
            trace_id,
            started_at,
            _runtime_error_response(
                trace_id,
                e,
                storage_engine_status="ERROR",
                dataset_readiness=dataset_readiness,
                timestamp=int(time.time() * 1000),
            ),
        )


def get_detailed_status() -> dict:
    """Aggregate detailed subsystem health for operator visibility."""
    trace_id = _new_trace_id()
    started_at = time.perf_counter()

    try:
        components = {}
        loaders = {
            "circuit_breaker_stats": _load_circuit_breaker_component,
            "peer_statuses": _load_peer_status_component,
            "tier_health": _load_tier_health_component,
            "feature_health": _load_feature_health_component,
            "last_batch": _load_last_batch_component,
        }
        for component_name, loader in loaders.items():
            try:
                components[component_name] = loader()
            except Exception as e:
                logger.warning("runtime_api [%s]: %s", trace_id, repr(e))
                components[component_name] = _component_payload("error", str(e))

        return _finalize_handler_result(
            "get_detailed_status",
            trace_id,
            started_at,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "components": components,
            },
        )
    except Exception as e:
        logger.warning("runtime_api [%s]: %s", trace_id, repr(e))
        return _finalize_handler_result(
            "get_detailed_status",
            trace_id,
            started_at,
            _runtime_error_response(trace_id, e),
        )


def get_auto_training_status() -> dict[str, object]:
    controller = get_auto_train_controller()
    return {
        "status": "ok",
        **controller.get_status(),
    }


def trigger_auto_training_check() -> dict[str, str]:
    controller = get_auto_train_controller()
    return controller.trigger_check()


@router.get("/api/v1/training/auto/status")
async def auto_training_status(user=Depends(require_auth)) -> dict[str, object]:
    return get_auto_training_status()


@router.post("/api/v1/training/auto/trigger")
async def auto_training_trigger(
    response: Response,
    user=Depends(require_auth),
) -> dict[str, str]:
    payload = trigger_auto_training_check()
    if payload["status"] == "triggered":
        response.status_code = http_status.HTTP_202_ACCEPTED
    else:
        response.status_code = http_status.HTTP_200_OK
    return payload


# =========================================================================
# FLASK REGISTRATION
# =========================================================================

def register_routes(app):
    """Register runtime API endpoints with Flask app."""
    @app.route('/runtime/status', methods=['GET'])
    def runtime_status_route():
        result = get_runtime_status()
        status_code = 200 if result.get('status') == 'ok' else 500
        return json.dumps(result), status_code, {'Content-Type': 'application/json'}

    @app.route('/api/v1/status/detailed', methods=['GET'])
    def detailed_status_route():
        result = get_detailed_status()
        status_code = 500 if result.get('status') == 'error' else 200
        return json.dumps(result), status_code, {'Content-Type': 'application/json'}

    logger.info("Registered runtime API routes: /runtime/status, /api/v1/status/detailed")


# =========================================================================
# RUNTIME INITIALIZATION (Phase 2: Explicit init, never at import)
# =========================================================================

def initialize_runtime():
    """Production startup checks. Only call explicitly, never at import."""
    if os.environ.get('YGB_ENV') != 'production':
        logger.info("Skipping production checks (YGB_ENV != production)")
        return

    # Verify HMAC secret is configured
    secret = os.environ.get('YGB_HMAC_SECRET', '').strip()
    if not secret:
        raise RuntimeError("FATAL: YGB_HMAC_SECRET not set in production")

    # Phase 5: Invalidate old telemetry on version bump
    if os.path.exists(TELEMETRY_PATH):
        try:
            with open(TELEMETRY_PATH, 'r') as f:
                data = json.load(f)
            ver = data.get('hmac_version')
            if ver is not None and ver != EXPECTED_HMAC_VERSION:
                os.remove(TELEMETRY_PATH)
                logger.info("Invalidated old telemetry (version %s != %s)",
                            ver, EXPECTED_HMAC_VERSION)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "Failed to validate existing telemetry version; keeping current file state: %s",
                exc,
                exc_info=True,
            )

    logger.info("Production runtime initialized")


# =========================================================================
# SELF-TEST
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize_runtime()

    print("=== Runtime API Self-Test ===")
    result = get_runtime_status()
    print(json.dumps(result, indent=2))

    if result.get('status') == 'ok':
        print("\n✅ Runtime telemetry validated successfully")
    else:
        print(f"\n⚠️  Runtime telemetry validation failed: {result.get('detail', 'unknown')}")
