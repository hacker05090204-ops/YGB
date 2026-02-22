"""
storage_policy.py — Storage Architecture Policy (Phase 1)

C Drive (SSD) = active training:
  - model weights, feature dataset, WAL, cluster_state, logs

D Drive (NAS) = archive only:
  - videos, draft reports, temp logs, compressed snapshots
  - NO training data

Health monitoring:
  - Free space threshold
  - SMART alerts (via C++ engine)
  - Path validation
"""

import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Default paths
SSD_ROOT = "C:\\"
NAS_ROOT = "D:\\"
FREE_SPACE_MIN_GB = 10.0


@dataclass
class DriveInfo:
    """Drive info and policy."""
    path: str
    role: str          # "ssd_active" or "nas_archive"
    total_gb: float
    free_gb: float
    healthy: bool
    alert: str = ""


@dataclass
class StoragePolicyResult:
    """Result of storage policy validation."""
    passed: bool
    drives: List[DriveInfo]
    violations: List[str]
    timestamp: str = ""


# Training data markers — files that indicate training data
TRAINING_MARKERS = [
    "cluster_state.json",
    "model_weights.pt",
    "training_data.npz",
    "dataset_features.parquet",
    "authority.wal",
]

# NAS allowed files
NAS_ALLOWED_EXTENSIONS = {
    '.mp4', '.avi', '.mkv',          # videos
    '.pdf', '.docx', '.txt',         # reports
    '.log',                          # logs
    '.zst', '.gz', '.tar', '.zip',   # compressed archives
    '.bak',                          # backups
}


def get_drive_info(path: str, role: str) -> DriveInfo:
    """Get drive information."""
    total_gb = 0.0
    free_gb = 0.0
    healthy = True
    alert = ""

    try:
        usage = shutil.disk_usage(path)
        total_gb = usage.total / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)

        if free_gb < FREE_SPACE_MIN_GB:
            healthy = False
            alert = f"Low space: {free_gb:.1f}GB < {FREE_SPACE_MIN_GB}GB"
    except Exception as e:
        healthy = False
        alert = f"Drive inaccessible: {e}"

    return DriveInfo(
        path=path, role=role,
        total_gb=round(total_gb, 2),
        free_gb=round(free_gb, 2),
        healthy=healthy, alert=alert,
    )


def check_nas_clean(nas_path: str) -> Tuple[bool, List[str]]:
    """Verify no training data on NAS drive.

    Returns:
        (clean, list_of_violations)
    """
    violations = []

    if not os.path.exists(nas_path):
        return True, []

    for root, dirs, files in os.walk(nas_path):
        for fname in files:
            # Check training markers
            if fname in TRAINING_MARKERS:
                violations.append(
                    f"Training data found: {os.path.join(root, fname)}"
                )

            # Check for dataset files in wrong place
            ext = os.path.splitext(fname)[1].lower()
            if ext in ('.pt', '.pth', '.npz', '.npy', '.parquet'):
                # These should NOT be on NAS unless archived
                full = os.path.join(root, fname)
                if 'archive' not in root.lower() and 'snapshot' not in root.lower():
                    violations.append(
                        f"Unarchived data on NAS: {full}"
                    )

        # Limit depth
        if root.count(os.sep) - nas_path.count(os.sep) > 3:
            break

    return len(violations) == 0, violations


def validate_storage_policy(
    ssd_path: str = SSD_ROOT,
    nas_path: str = NAS_ROOT,
) -> StoragePolicyResult:
    """Validate full storage policy.

    Checks:
    1. SSD accessible + healthy
    2. NAS has no active training data
    3. Free space above threshold
    """
    violations = []
    drives = []

    # SSD
    ssd = get_drive_info(ssd_path, "ssd_active")
    drives.append(ssd)
    if not ssd.healthy:
        violations.append(f"SSD unhealthy: {ssd.alert}")

    # NAS
    nas = get_drive_info(nas_path, "nas_archive")
    drives.append(nas)

    if os.path.exists(nas_path):
        clean, nas_violations = check_nas_clean(nas_path)
        if not clean:
            violations.extend(nas_violations)

    passed = len(violations) == 0

    result = StoragePolicyResult(
        passed=passed,
        drives=drives,
        violations=violations,
        timestamp=datetime.now().isoformat(),
    )

    if passed:
        logger.info("[STORAGE_POLICY] ✓ All checks passed")
    else:
        for v in violations:
            logger.error(f"[STORAGE_POLICY] ✗ {v}")

    return result


def get_ssd_training_paths() -> dict:
    """Get standard SSD training paths."""
    base = os.path.join('secure_data')
    return {
        'weights': os.path.join(base, 'model_weights'),
        'features': os.path.join(base, 'features'),
        'wal': os.path.join(base, 'authority.wal'),
        'state': os.path.join(base, 'cluster_state.json'),
        'logs': os.path.join(base, 'experiment_logs'),
        'checkpoints': os.path.join(base, 'versioned_checkpoints'),
    }
