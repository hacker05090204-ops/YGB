"""
runtime_api.py — Backend Runtime Hard Validation API with HMAC
=============================================================
Endpoint:
  GET  /runtime/status  — Validated runtime state

Before returning runtime data:
  1. Load reports/training_telemetry.json
  2. Validate HMAC-SHA256
  3. Validate CRC32 (recompute and match)
  4. Validate schema_version
  5. Validate determinism_status == true
  6. If ANY fail → return {"status": "corrupted", "reason": "..."}

Never trust partial state.
Never trust unsigned telemetry.
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
EXPECTED_SCHEMA_VERSION = 1


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
    )
    return compute_crc32(crc_string.encode('ascii'))


# =========================================================================
# HMAC-SHA256 VALIDATION
# =========================================================================

def load_hmac_key() -> bytes:
    """Load HMAC secret key from file. Returns empty bytes if missing."""
    try:
        with open(HMAC_KEY_PATH, 'r') as f:
            hex_key = f.read().strip()
        if not hex_key:
            return b''
        return bytes.fromhex(hex_key)
    except (FileNotFoundError, ValueError) as e:
        logger.error("Failed to load HMAC key: %s", e)
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
# VALIDATION
# =========================================================================

def validate_telemetry() -> dict:
    """
    Load and validate runtime telemetry.
    Returns validated data or error response.
    Never returns partial state.
    Never trusts unsigned telemetry.
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
                       'crc32', 'hmac']
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

    # Step 6: Validate schema version
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

    # Step 7: Validate determinism_status
    if data['determinism_status'] is not True:
        logger.error("determinism_status is not true")
        return {
            "status": "corrupted",
            "reason": "determinism_failed",
            "detail": "determinism_status is false"
        }

    # All checks passed
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
