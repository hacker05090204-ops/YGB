"""
training_progress.py — Real-Time Training Progress API
=======================================================
Endpoint:
  GET /training/progress — Live training status with stall detection

Reads telemetry JSON written by C++ training_telemetry.cpp.
Returns real timestamps, elapsed time, epoch duration, throughput.
If time hasn't advanced in 60s → stalled = true.

NO mock data. Python is governance only.
"""

import os
import json
import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

TELEMETRY_PATH = os.path.join(PROJECT_ROOT, 'reports', 'training_telemetry.json')

# Stall threshold: if telemetry timestamp hasn't advanced in 60s
STALL_THRESHOLD_SECONDS = 60


def get_training_progress() -> dict:
    """
    Read real-time training progress from telemetry file.

    Returns:
        dict with training visibility fields or error status.
    """
    if not os.path.exists(TELEMETRY_PATH):
        return {
            "status": "awaiting_data",
            "message": "No telemetry data yet — training has not started",
            "stalled": False,
        }

    try:
        with open(TELEMETRY_PATH, 'r') as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to read telemetry: %s", e)
        return {
            "status": "error",
            "message": f"Cannot read telemetry: {e}",
            "stalled": False,
        }

    # Extract timestamps
    wall_clock = data.get('wall_clock_unix', 0)
    mono_start = data.get('monotonic_start_time', 0)
    mono_current = data.get('monotonic_timestamp', 0)
    duration = data.get('training_duration_seconds', 0.0)
    samples_sec = data.get('samples_per_second', 0.0)
    epoch = data.get('epoch', 0)
    loss = data.get('loss', 0.0)
    gpu_temp = data.get('gpu_temperature', 0.0)

    # Format start time as ISO string
    started_at = ""
    if wall_clock > 0:
        started_at = datetime.fromtimestamp(
            wall_clock - duration, tz=timezone.utc
        ).isoformat()

    # Format elapsed time as HH:MM:SS
    elapsed = ""
    if duration >= 0:
        hours = int(duration // 3600)
        mins = int((duration % 3600) // 60)
        secs = int(duration % 60)
        elapsed = f"{hours:02d}:{mins:02d}:{secs:02d}"

    # Stall detection: check if file was modified recently
    stalled = False
    try:
        file_mtime = os.path.getmtime(TELEMETRY_PATH)
        age = time.time() - file_mtime
        if age > STALL_THRESHOLD_SECONDS:
            stalled = True
    except OSError:
        pass

    return {
        "status": "training",
        "started_at": started_at,
        "elapsed": elapsed,
        "training_duration_seconds": duration,
        "epoch": epoch,
        "samples_per_second": samples_sec,
        "loss": loss,
        "gpu_temperature": gpu_temp,
        "stalled": stalled,
        "wall_clock_unix": wall_clock,
        "monotonic_start_time": mono_start,
        "monotonic_current_time": mono_current,
    }


# =========================================================================
# FLASK REGISTRATION
# =========================================================================

def register_routes(app):
    """Register training progress endpoint with Flask app."""
    @app.route('/training/progress', methods=['GET'])
    def training_progress_route():
        result = get_training_progress()
        return json.dumps(result), 200, {'Content-Type': 'application/json'}

    logger.info("Registered training API: /training/progress")


# =========================================================================
# SELF-TEST
# =========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = get_training_progress()
    print(json.dumps(result, indent=2))
