"""
runtime_api.py — Authoritative Runtime Status Endpoint

GET /runtime/status

Rules:
  - Reads runtime_state.json (written by C++ training_telemetry)
  - Validates structure (all required fields present)
  - Verifies determinism flag
  - Returns signed response with HMAC
  - If file missing → {"status": "awaiting_data"}
  - No computed values — all from C++ runtime
  - No mock data, no silent fallback
"""

import hashlib
import hmac
import json
import os
import time
import logging

logger = logging.getLogger(__name__)

# Path to the runtime state file written by C++ telemetry
RUNTIME_STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "reports", "runtime_state.json"
)

# HMAC signing key (env or fallback for dev)
SIGNING_KEY = os.environ.get("YGB_RUNTIME_SIGN_KEY", "ygb-runtime-dev-key").encode()

# Required fields in runtime_state.json
REQUIRED_FIELDS = [
    "total_epochs", "completed_epochs", "current_loss",
    "precision", "ece", "drift_kl", "duplicate_rate",
    "gpu_util", "cpu_util", "temperature",
    "determinism_status", "freeze_status",
    "mode", "last_update_ms",
]

# Stale threshold: 60 seconds
STALE_THRESHOLD_MS = 60_000


def _sign_payload(payload: dict) -> str:
    """HMAC-SHA256 signature of the JSON payload."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hmac.new(SIGNING_KEY, raw.encode(), hashlib.sha256).hexdigest()


def _validate_structure(data: dict) -> list:
    """Returns list of missing required fields."""
    return [f for f in REQUIRED_FIELDS if f not in data]


def get_runtime_status() -> dict:
    """
    Read runtime_state.json and return validated, signed status.

    Returns dict suitable for JSON response.
    """
    # Check if file exists
    if not os.path.exists(RUNTIME_STATE_PATH):
        return {
            "status": "awaiting_data",
            "message": "Runtime state not yet available. Training has not started.",
            "timestamp": int(time.time() * 1000),
        }

    # Read file
    try:
        with open(RUNTIME_STATE_PATH, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to read runtime state: %s", e)
        return {
            "status": "error",
            "message": f"Failed to read runtime state: {e}",
            "timestamp": int(time.time() * 1000),
        }

    # Validate structure
    missing = _validate_structure(data)
    if missing:
        return {
            "status": "invalid",
            "message": f"Missing required fields: {', '.join(missing)}",
            "timestamp": int(time.time() * 1000),
        }

    # Check determinism
    determinism_ok = data.get("determinism_status", False)

    # Check staleness
    now_ms = int(time.time() * 1000)
    last_update = data.get("last_update_ms", 0)
    stale = (now_ms - last_update) > STALE_THRESHOLD_MS if last_update > 0 else True

    # Build response payload (all values from C++ runtime, no computation)
    payload = {
        "status": "active",
        "runtime": {
            "total_epochs": data["total_epochs"],
            "completed_epochs": data["completed_epochs"],
            "current_loss": data["current_loss"],
            "precision": data["precision"],
            "ece": data["ece"],
            "drift_kl": data["drift_kl"],
            "duplicate_rate": data["duplicate_rate"],
            "gpu_util": data["gpu_util"],
            "cpu_util": data["cpu_util"],
            "temperature": data["temperature"],
            "determinism_status": data["determinism_status"],
            "freeze_status": data["freeze_status"],
            "mode": data["mode"],
            "progress_pct": data.get("progress_pct", 0.0),
            "loss_trend": data.get("loss_trend", 0.0),
        },
        "determinism_ok": determinism_ok,
        "stale": stale,
        "last_update_ms": last_update,
        "timestamp": now_ms,
    }

    # Sign the response
    payload["signature"] = _sign_payload(payload)

    return payload


def register_runtime_routes(app):
    """Register runtime API routes with a FastAPI or Flask-like app."""
    try:
        # Try FastAPI-style
        from fastapi import APIRouter
        router = APIRouter()

        @router.get("/runtime/status")
        async def runtime_status():
            return get_runtime_status()

        app.include_router(router)
        logger.info("Registered /runtime/status (FastAPI)")
    except ImportError:
        logger.warning("FastAPI not available, skipping runtime route registration")
