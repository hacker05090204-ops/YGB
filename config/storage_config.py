from __future__ import annotations

"""
SSD-first storage configuration.

Hot, latency-sensitive data stays on SSD. Cold/archive data stays on HDD.
All paths are project-relative by default and can be overridden with env vars.
"""

import os
from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _resolve_root(env_name: str, default_relative: str) -> Path:
    raw = os.getenv(env_name, default_relative)
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = _PROJECT_ROOT / candidate
    return candidate.resolve()


# Primary storage — SSD (fast, limited)
SSD_ROOT = _resolve_root("YGB_SSD_PATH", "data/ssd")

# Archive storage — HDD (slow, large)
HDD_ROOT = _resolve_root("YGB_HDD_PATH", "data/hdd")


# Hot paths (SSD)
TRAINING_DIR = SSD_ROOT / "training"
FEATURES_DIR = SSD_ROOT / "features_safetensors"
CHECKPOINTS_DIR = SSD_ROOT / "checkpoints"
DEDUP_DIR = SSD_ROOT / "dedup"
EVIDENCE_DIR = SSD_ROOT / "evidence"
REPORTS_DIR = SSD_ROOT / "reports"
SYNC_ROOT = SSD_ROOT / "sync"
SYNC_META_DIR = SYNC_ROOT / "ygb_sync"
GDRIVE_STAGING_DIR = SSD_ROOT / "gdrive_staging"
ACTIVE_DB = SSD_ROOT / "ygb.db"
NONCE_DB = SSD_ROOT / "nonces.db"


# Cold paths (HDD)
RAW_DATA_DIR = HDD_ROOT / "raw"
ARCHIVE_CHECKPOINTS = HDD_ROOT / "checkpoints_archive"
LOG_DIR = HDD_ROOT / "logs"
OVERFLOW_DIR = HDD_ROOT / "ssd_overflow"


def _ensure_directories() -> None:
    for directory in (
        SSD_ROOT,
        HDD_ROOT,
        TRAINING_DIR,
        FEATURES_DIR,
        CHECKPOINTS_DIR,
        DEDUP_DIR,
        EVIDENCE_DIR,
        REPORTS_DIR,
        SYNC_ROOT,
        SYNC_META_DIR,
        GDRIVE_STAGING_DIR,
        RAW_DATA_DIR,
        ARCHIVE_CHECKPOINTS,
        LOG_DIR,
        OVERFLOW_DIR,
        ACTIVE_DB.parent,
        NONCE_DB.parent,
    ):
        directory.mkdir(parents=True, exist_ok=True)


_ensure_directories()

