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

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

TELEMETRY_PATH = os.path.join(PROJECT_ROOT, 'reports', 'training_telemetry.json')
HMAC_KEY_PATH = os.path.join(PROJECT_ROOT, 'config', 'hmac_secret.key')
LAST_SEEN_PATH = os.path.join(PROJECT_ROOT, 'reports', 'last_seen_timestamp.json')
EXPECTED_SCHEMA_VERSION = 1
EXPECTED_HMAC_VERSION = 1  # Phase 5: HMAC secret versioning


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
    """Load HMAC secret key. Priority: env var > file.

    In CI (CI env var set): raises RuntimeError if no secret found.
    Locally: returns empty bytes on failure (fail closed).
    """
    # Priority 1: Environment variable (works in CI and local)
    env_secret = os.environ.get('YGB_HMAC_SECRET', '').strip()
    if env_secret:
        try:
            return bytes.fromhex(env_secret)
        except ValueError:
            # Treat as raw UTF-8 key if not valid hex
            return env_secret.encode('utf-8')

    # Priority 2: Key file (local development only)
    try:
        with open(HMAC_KEY_PATH, 'r') as f:
            hex_key = f.read().strip()
        if not hex_key:
            raise ValueError("key file empty")
        return bytes.fromhex(hex_key)
    except (FileNotFoundError, ValueError) as e:
        # In CI, this is fatal
        if os.environ.get('CI'):
            raise RuntimeError(
                f"HMAC secret not configured: {e}. "
                "Set YGB_HMAC_SECRET in GitHub Secrets."
            )
        # Locally, log and return empty (fail closed)
        logger.error("HMAC secret not configured: %s", e)
        return b''


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
            "detail": f"Read failed: {e}"
        }

    # Step 2: Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Telemetry JSON parse failed: %s", e)
        return {
            "status": "corrupted",
            "reason": "json_parse_failed",
            "detail": f"JSON parse failed: {e}"
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

    # Step 11: HMAC VERSION CHECK (Phase 5)
    hmac_ver = data.get('hmac_version')
    if hmac_ver is not None and hmac_ver != EXPECTED_HMAC_VERSION:
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

    Returns validated runtime state.
    If corrupted → returns error with reason.
    Never returns partial state.
    """
    result = validate_telemetry()
    return result


# =========================================================================
# FLASK REGISTRATION
# =========================================================================

def register_routes(app):
    """Register runtime API endpoints with Flask app."""
    from functools import wraps

    @app.route('/runtime/status', methods=['GET'])
    def runtime_status_route():
        result = get_runtime_status()
        status_code = 200 if result.get('status') == 'ok' else 500
        return json.dumps(result), status_code, {'Content-Type': 'application/json'}

    logger.info("Registered runtime API routes: /runtime/status")


# =========================================================================
# SELF-TEST
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=== Runtime API Self-Test ===")
    result = get_runtime_status()
    print(json.dumps(result, indent=2))

    if result.get('status') == 'ok':
        print("\n✅ Runtime telemetry validated successfully")
    else:
        print(f"\n⚠️  Runtime telemetry validation failed: {result.get('detail', 'unknown')}")
