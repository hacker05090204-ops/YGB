"""
YGB Tiered Storage Manager
===========================
SSD (C:) for hot training data — capped at 110 GB.
HDD (D:) for everything else: videos, logs, user data, backups, overflow.

Policy:
  1. Training artefacts (models, checkpoints, datasets) → SSD first.
  2. When SSD usage exceeds the cap:
     a. Compress oldest cold files (>.5 GB, not accessed in 24 h) with gzip.
     b. If compression frees enough, stay on SSD.
     c. Otherwise, move compressed files to HDD overflow.
  3. Videos, activity logs, session data, user uploads → always HDD.
"""

import gzip
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("tiered_storage")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_GB = 1024 ** 3
_MB = 1024 ** 2

SSD_ROOT = Path(os.environ.get("YGB_SSD_ROOT", "D:/ygb_data"))
HDD_ROOT = Path(os.environ.get("YGB_HDD_ROOT", "D:/ygb_hdd"))
HDD_BACKUP = Path(os.environ.get("DATABASE_BACKUP_PATH", "D:/ygb_data/ygb.db")).parent

SSD_CAP_BYTES = int(float(os.environ.get("YGB_SSD_CAP_GB", "110")) * _GB)

# Sub-directories — training artefacts on SSD, everything else on HDD.
SSD_TRAINING_DIR   = SSD_ROOT / "training"
SSD_CHECKPOINTS    = SSD_ROOT / "checkpoints"
SSD_DATASETS       = SSD_ROOT / "datasets"
SSD_DB             = SSD_ROOT / "ygb.db"

HDD_VIDEOS         = HDD_ROOT / "videos"
HDD_LOGS           = HDD_ROOT / "logs"
HDD_USER_DATA      = HDD_ROOT / "user_data"
HDD_SESSIONS       = HDD_ROOT / "sessions"
HDD_OVERFLOW       = HDD_ROOT / "ssd_overflow"

# Files older than this and bigger than MIN_COMPRESS_SIZE are eligible for
# compression / migration when the SSD cap is hit.
COLD_AGE = timedelta(hours=24)
MIN_COMPRESS_SIZE = 512 * _MB  # 0.5 GB


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class StorageReport:
    ssd_used_bytes: int = 0
    ssd_cap_bytes: int = SSD_CAP_BYTES
    ssd_free_bytes: int = 0
    ssd_usage_pct: float = 0.0
    hdd_used_bytes: int = 0
    compressed_count: int = 0
    migrated_count: int = 0
    migrated_bytes: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return {
            "ssd_used_gb": round(self.ssd_used_bytes / _GB, 2),
            "ssd_cap_gb": round(self.ssd_cap_bytes / _GB, 2),
            "ssd_free_gb": round(self.ssd_free_bytes / _GB, 2),
            "ssd_usage_pct": round(self.ssd_usage_pct, 1),
            "hdd_used_gb": round(self.hdd_used_bytes / _GB, 2),
            "compressed_count": self.compressed_count,
            "migrated_count": self.migrated_count,
            "migrated_gb": round(self.migrated_bytes / _GB, 2),
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _dir_size(path: Path) -> int:
    """Total bytes used by a directory tree."""
    total = 0
    try:
        for entry in path.rglob("*"):
            if entry.is_file():
                total += entry.stat().st_size
    except Exception:
        pass
    return total


def _ssd_usage() -> int:
    return _dir_size(SSD_ROOT)


def _hdd_usage() -> int:
    return _dir_size(HDD_ROOT)


def _cold_files(root: Path) -> list[Path]:
    """
    Return files under *root* that are older than COLD_AGE and bigger than
    MIN_COMPRESS_SIZE, sorted oldest-first.
    """
    cutoff = time.time() - COLD_AGE.total_seconds()
    candidates = []
    try:
        for f in root.rglob("*"):
            if f.is_file() and f.stat().st_size >= MIN_COMPRESS_SIZE:
                if f.stat().st_atime < cutoff:
                    candidates.append(f)
    except Exception:
        pass
    candidates.sort(key=lambda p: p.stat().st_atime)
    return candidates


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------

def compress_file(src: Path) -> Optional[Path]:
    """Gzip-compress *src* in-place.  Returns the .gz path or None on error."""
    dst = src.with_suffix(src.suffix + ".gz")
    if dst.exists():
        return dst  # already compressed
    try:
        with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
            shutil.copyfileobj(fin, fout)
        # Verify the compressed file is smaller
        if dst.stat().st_size < src.stat().st_size:
            src.unlink()
            logger.info("Compressed %s → %s (saved %s)",
                        src.name, dst.name,
                        _human(src.stat().st_size - dst.stat().st_size) if src.exists() else "file removed")
            return dst
        else:
            dst.unlink()  # compression didn't help
            logger.info("Compression ineffective for %s — skipping", src.name)
            return None
    except Exception:
        logger.exception("Failed to compress %s", src)
        if dst.exists():
            dst.unlink()
        return None


def _human(b: int) -> str:
    if b >= _GB:
        return f"{b / _GB:.1f} GB"
    if b >= _MB:
        return f"{b / _MB:.1f} MB"
    return f"{b / 1024:.1f} KB"


# ---------------------------------------------------------------------------
# Migration (SSD → HDD overflow)
# ---------------------------------------------------------------------------

def migrate_to_hdd(src: Path) -> Optional[Path]:
    """Move a file from SSD to HDD overflow, preserving relative path."""
    try:
        rel = src.relative_to(SSD_ROOT)
    except ValueError:
        rel = Path(src.name)
    dst = HDD_OVERFLOW / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dst))
        logger.info("Migrated to HDD: %s → %s (%s)", src.name, dst, _human(dst.stat().st_size))
        return dst
    except Exception:
        logger.exception("Failed to migrate %s → HDD", src)
        return None


# ---------------------------------------------------------------------------
# Enforce SSD cap
# ---------------------------------------------------------------------------

def enforce_ssd_cap() -> StorageReport:
    """
    Check SSD usage.  If over cap:
      1) Compress cold files.
      2) If still over, migrate oldest compressed files to HDD.
    Returns a StorageReport.
    """
    report = StorageReport()
    used = _ssd_usage()
    report.ssd_used_bytes = used
    report.ssd_cap_bytes = SSD_CAP_BYTES
    report.ssd_free_bytes = max(0, SSD_CAP_BYTES - used)
    report.ssd_usage_pct = (used / SSD_CAP_BYTES * 100) if SSD_CAP_BYTES > 0 else 0.0

    if used <= SSD_CAP_BYTES:
        logger.debug("SSD within cap: %s / %s (%0.1f%%)",
                      _human(used), _human(SSD_CAP_BYTES), report.ssd_usage_pct)
        report.hdd_used_bytes = _hdd_usage()
        return report

    logger.warning("SSD over cap: %s / %s — starting compression",
                    _human(used), _human(SSD_CAP_BYTES))

    # Phase 1: compress cold files
    for cf in _cold_files(SSD_ROOT):
        result = compress_file(cf)
        if result:
            report.compressed_count += 1
        used = _ssd_usage()
        if used <= SSD_CAP_BYTES:
            break

    # Phase 2: migrate if still over
    if used > SSD_CAP_BYTES:
        logger.warning("Still over cap after compression — migrating to HDD")
        # Gather all files sorted by age (oldest first)
        all_files = sorted(
            (f for f in SSD_ROOT.rglob("*") if f.is_file() and f != SSD_DB),
            key=lambda p: p.stat().st_atime,
        )
        for f in all_files:
            if f.name == "ygb.db":
                continue  # never move the live database
            sz = f.stat().st_size
            dst = migrate_to_hdd(f)
            if dst:
                report.migrated_count += 1
                report.migrated_bytes += sz
            used = _ssd_usage()
            if used <= SSD_CAP_BYTES:
                break

    report.ssd_used_bytes = used
    report.ssd_free_bytes = max(0, SSD_CAP_BYTES - used)
    report.ssd_usage_pct = (used / SSD_CAP_BYTES * 100) if SSD_CAP_BYTES > 0 else 0.0
    report.hdd_used_bytes = _hdd_usage()

    logger.info(
        "Enforcement done: SSD %s/%s (%.1f%%), compressed=%d, migrated=%d (%s)",
        _human(report.ssd_used_bytes), _human(SSD_CAP_BYTES),
        report.ssd_usage_pct,
        report.compressed_count, report.migrated_count,
        _human(report.migrated_bytes),
    )
    return report


# ---------------------------------------------------------------------------
# Path resolution — where should a given data category go?
# ---------------------------------------------------------------------------

def resolve_path(category: str, filename: str = "") -> Path:
    """
    Return the correct storage root for a data category.

    Categories:
        training, checkpoint, dataset → SSD
        video, log, user_data, session, upload, backup → HDD
    """
    _mapping = {
        "training":   SSD_TRAINING_DIR,
        "checkpoint": SSD_CHECKPOINTS,
        "dataset":    SSD_DATASETS,
        "video":      HDD_VIDEOS,
        "log":        HDD_LOGS,
        "user_data":  HDD_USER_DATA,
        "session":    HDD_SESSIONS,
        "upload":     HDD_USER_DATA / "uploads",
        "backup":     HDD_BACKUP,
    }
    base = _mapping.get(category, HDD_ROOT / category)
    base.mkdir(parents=True, exist_ok=True)
    return base / filename if filename else base


def get_storage_report() -> dict:
    """Quick snapshot of SSD/HDD usage for the API."""
    r = StorageReport()
    r.ssd_used_bytes = _ssd_usage()
    r.ssd_free_bytes = max(0, SSD_CAP_BYTES - r.ssd_used_bytes)
    r.ssd_usage_pct = (r.ssd_used_bytes / SSD_CAP_BYTES * 100) if SSD_CAP_BYTES > 0 else 0.0
    r.hdd_used_bytes = _hdd_usage()
    return r.to_dict()


# ---------------------------------------------------------------------------
# Ensure directories exist at import time
# ---------------------------------------------------------------------------

def _init_dirs():
    for d in [
        SSD_TRAINING_DIR, SSD_CHECKPOINTS, SSD_DATASETS,
        HDD_VIDEOS, HDD_LOGS, HDD_USER_DATA, HDD_SESSIONS, HDD_OVERFLOW,
    ]:
        d.mkdir(parents=True, exist_ok=True)


_init_dirs()


# ---------------------------------------------------------------------------
# Background enforcement thread (optional)
# ---------------------------------------------------------------------------

_enforcement_thread: Optional[threading.Thread] = None


def start_enforcement_loop(interval_seconds: int = 300):
    """Start a daemon thread that enforces the SSD cap every N seconds."""
    global _enforcement_thread
    if _enforcement_thread and _enforcement_thread.is_alive():
        logger.info("Enforcement loop already running")
        return

    def _loop():
        logger.info("Storage enforcement loop started (every %ds)", interval_seconds)
        while True:
            try:
                enforce_ssd_cap()
            except Exception:
                logger.exception("Error in storage enforcement loop")
            time.sleep(interval_seconds)

    _enforcement_thread = threading.Thread(target=_loop, daemon=True, name="storage-enforcement")
    _enforcement_thread.start()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [STORAGE] %(message)s")

    if "--enforce" in sys.argv:
        r = enforce_ssd_cap()
        print(json.dumps(r.to_dict(), indent=2))
    elif "--loop" in sys.argv:
        idx = sys.argv.index("--loop")
        interval = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 300
        start_enforcement_loop(interval)
        # Keep main alive
        while True:
            time.sleep(60)
    else:
        print(json.dumps(get_storage_report(), indent=2))
