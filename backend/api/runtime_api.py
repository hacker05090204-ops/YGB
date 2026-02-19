"""
runtime_api.py — Backend Runtime Hard Validation API
=====================================================
Endpoint:
  GET  /runtime/status  — Validated runtime state

Before returning runtime data:
  1. Load reports/training_telemetry.json
  2. Validate CRC32 (recompute and match)
  3. Validate schema_version
  4. Validate determinism_status == true
  5. If ANY fail → return {"status": "error", "reason": "runtime_corrupted"}

Never trust partial state.
NO silent fallback. NO telemetry trust without validation.
"""

import os
import json
import struct
import logging

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

TELEMETRY_PATH = os.path.join(PROJECT_ROOT, 'reports', 'training_telemetry.json')
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
# VALIDATION
# =========================================================================

def validate_telemetry() -> dict:
    """
    Load and validate runtime telemetry.
    Returns validated data or error response.
    Never returns partial state.
    """
    # Step 1: Load file
    if not os.path.exists(TELEMETRY_PATH):
        logger.error("Telemetry file missing: %s", TELEMETRY_PATH)
        return {
            "status": "error",
            "reason": "runtime_corrupted",
            "detail": "Telemetry file missing"
        }

    try:
        with open(TELEMETRY_PATH, 'r') as f:
            raw = f.read()
    except Exception as e:
        logger.error("Failed to read telemetry: %s", e)
        return {
            "status": "error",
            "reason": "runtime_corrupted",
            "detail": f"Read failed: {e}"
        }

    # Step 2: Parse JSON
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("Telemetry JSON parse failed: %s", e)
        return {
            "status": "error",
            "reason": "runtime_corrupted",
            "detail": f"JSON parse failed: {e}"
        }

    # Step 3: Validate required fields
    required_fields = ['schema_version', 'determinism_status', 'freeze_status', 'crc32']
    for field in required_fields:
        if field not in data:
            logger.error("Telemetry missing field: %s", field)
            return {
                "status": "error",
                "reason": "runtime_corrupted",
                "detail": f"Missing required field: {field}"
            }

    # Step 4: Validate schema version
    if data['schema_version'] != EXPECTED_SCHEMA_VERSION:
        logger.error(
            "Schema version mismatch: got %s, expected %s",
            data['schema_version'], EXPECTED_SCHEMA_VERSION
        )
        return {
            "status": "error",
            "reason": "runtime_corrupted",
            "detail": f"Schema version mismatch: {data['schema_version']}"
        }

    # Step 5: Validate determinism_status
    if data['determinism_status'] is not True:
        logger.error("determinism_status is not true")
        return {
            "status": "error",
            "reason": "runtime_corrupted",
            "detail": "determinism_status is false"
        }

    # Step 6: Validate CRC32
    stored_crc = data['crc32']
    computed_crc = compute_payload_crc(data)
    if stored_crc != computed_crc:
        logger.error(
            "CRC mismatch: stored=%d computed=%d",
            stored_crc, computed_crc
        )
        return {
            "status": "error",
            "reason": "runtime_corrupted",
            "detail": f"CRC mismatch: stored={stored_crc} computed={computed_crc}"
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
