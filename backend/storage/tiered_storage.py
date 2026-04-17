"""
YGB Tiered Storage Manager
===========================
SSD-first storage for hot training data.
HDD archive storage for logs, raw feeds, backups, and overflow.

Policy:
  1. Training artefacts (models, checkpoints, datasets) → SSD first.
  2. When SSD usage exceeds the cap:
     a. Compress oldest cold files (>.5 GB, not accessed in 24 h) with gzip.
     b. If compression frees enough, stay on SSD.
     c. Otherwise, move compressed files to HDD overflow.
  3. Videos, activity logs, session data, user uploads → always HDD.
"""

import asyncio
import gzip
import json
import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from config.storage_config import (
    ACTIVE_DB,
    CHECKPOINTS_DIR,
    FEATURES_DIR,
    HDD_ROOT as CONFIG_HDD_ROOT,
    LOG_DIR,
    OVERFLOW_DIR,
    SSD_ROOT as CONFIG_SSD_ROOT,
    TRAINING_DIR,
)

logger = logging.getLogger("tiered_storage")


class StorageCompletelyUnavailableError(RuntimeError):
    """Raised when neither primary nor fallback storage can be used."""

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_GB = 1024 ** 3
_MB = 1024 ** 2

SSD_ROOT = CONFIG_SSD_ROOT
PRIMARY_HDD_ROOT = CONFIG_HDD_ROOT
FALLBACK_HDD_ROOT = Path(
    os.environ.get("YGB_HDD_FALLBACK_ROOT", str(CONFIG_SSD_ROOT / "archive_fallback"))
)

SSD_CAP_BYTES = int(float(os.environ.get("YGB_SSD_CAP_GB", "110")) * _GB)

# Sub-directories — training artefacts on SSD, everything else on HDD/NAS.
SSD_TRAINING_DIR = TRAINING_DIR
SSD_CHECKPOINTS = CHECKPOINTS_DIR
SSD_DATASETS = FEATURES_DIR
SSD_DB = ACTIVE_DB

# Files older than this and bigger than MIN_COMPRESS_SIZE are eligible for
# compression / migration when the SSD cap is hit.
COLD_AGE = timedelta(hours=24)
MIN_COMPRESS_SIZE = 512 * _MB  # 0.5 GB
STORAGE_TOPOLOGY_CACHE_SECONDS = max(
    1.0,
    float(os.environ.get("YGB_STORAGE_TOPOLOGY_CACHE_SECONDS", "15")),
)

_storage_topology_cache_lock = threading.Lock()
_storage_topology_cache: dict[str, Any] = {
    "checked_at": 0.0,
    "value": None,
}


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
    primary_hdd_root: str = str(PRIMARY_HDD_ROOT)
    fallback_hdd_root: str = str(FALLBACK_HDD_ROOT)
    active_hdd_root: str = ""
    primary_available: bool = False
    fallback_available: bool = False
    fallback_active: bool = False
    topology_reason: str = ""
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
            "primary_hdd_root": self.primary_hdd_root,
            "fallback_hdd_root": self.fallback_hdd_root,
            "active_hdd_root": self.active_hdd_root,
            "primary_available": self.primary_available,
            "fallback_available": self.fallback_available,
            "fallback_active": self.fallback_active,
            "topology_reason": self.topology_reason,
            "timestamp": self.timestamp,
        }


@dataclass
class StorageTierHealth:
    tier_name: str
    available_bytes: int
    used_bytes: int
    read_latency_ms: float
    write_latency_ms: float


STORAGE_WAL_PATH = Path(
    os.environ.get("YGB_STORAGE_WAL_PATH", str(SSD_ROOT / ".wal.jsonl"))
)
_wal_lock = threading.Lock()
_wal_recovery_in_progress = False


def _load_wal_entries() -> list[dict[str, str]]:
    if not STORAGE_WAL_PATH.exists():
        return []

    entries: list[dict[str, str]] = []
    try:
        with open(STORAGE_WAL_PATH, "r", encoding="utf-8") as f:
            for line in f:
                payload = line.strip()
                if not payload:
                    continue
                try:
                    entry = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(entry, dict) and entry.get("op") and entry.get("key"):
                    entries.append(entry)
    except OSError:
        return []
    return entries


def _write_wal_entries(entries: list[dict[str, str]]) -> None:
    STORAGE_WAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not entries:
        STORAGE_WAL_PATH.unlink(missing_ok=True)
        return

    tmp_path = STORAGE_WAL_PATH.with_suffix(STORAGE_WAL_PATH.suffix + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    os.replace(str(tmp_path), str(STORAGE_WAL_PATH))


def _append_wal_entry(op: str, key: str) -> dict[str, str]:
    entry = {
        "timestamp": datetime.now().isoformat(),
        "op": op,
        "key": key,
    }
    with _wal_lock:
        STORAGE_WAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(STORAGE_WAL_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    return entry


def _complete_wal_entry(entry: dict[str, str]) -> None:
    with _wal_lock:
        removed = False
        filtered: list[dict[str, str]] = []
        for candidate in _load_wal_entries():
            if not removed and candidate == entry:
                removed = True
                continue
            filtered.append(candidate)
        _write_wal_entries(filtered)


def _wal_protected_write(op: str, key: str, action):
    if _wal_recovery_in_progress:
        return action()

    entry = _append_wal_entry(op, key)
    try:
        result = action()
    except Exception:
        raise
    else:
        _complete_wal_entry(entry)
        return result


def _write_probe_file(path: Path, payload: bytes = b"ok") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(payload)


def _ensure_dir(path: Path) -> None:
    _wal_protected_write(
        "ensure_dir",
        str(path),
        lambda: path.mkdir(parents=True, exist_ok=True),
    )


def _replay_wal_entry(entry: dict[str, str]) -> bool:
    op = str(entry.get("op", ""))
    key = str(entry.get("key", ""))
    if not op or not key:
        return False

    path = Path(key)
    if op == "ensure_dir":
        path.mkdir(parents=True, exist_ok=True)
        return True

    if op in {"path_probe", "tier_probe"}:
        _write_probe_file(path)
        path.unlink(missing_ok=True)
        return True

    if op == "compress_file":
        compressed_path = path.with_suffix(path.suffix + ".gz")
        if compressed_path.exists() or not path.exists():
            return True
        return _compress_file_impl(path) is not None

    if op == "migrate_to_hdd":
        try:
            rel = path.relative_to(SSD_ROOT)
        except ValueError:
            rel = Path(path.name)
        expected_dst = _active_hdd_dir("ssd_overflow") / rel
        if expected_dst.exists() or not path.exists():
            return True
        return _migrate_to_hdd_impl(path) is not None

    return False


def _replay_incomplete_wal_entries() -> None:
    global _wal_recovery_in_progress

    pending_entries = _load_wal_entries()
    if not pending_entries:
        return

    logger.info("Replaying %d incomplete storage WAL entries", len(pending_entries))
    remaining_entries: list[dict[str, str]] = []
    _wal_recovery_in_progress = True
    try:
        for entry in pending_entries:
            try:
                if not _replay_wal_entry(entry):
                    remaining_entries.append(entry)
            except Exception:
                remaining_entries.append(entry)
    finally:
        _wal_recovery_in_progress = False

    with _wal_lock:
        _write_wal_entries(remaining_entries)


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
    except Exception as exc:
        logger.debug("Failed to measure directory size for %s: %s", path, exc)
    return total


def _ssd_usage() -> int:
    return _dir_size(SSD_ROOT)


def _path_is_usable(path: Path) -> tuple[bool, str]:
    """Check whether a root is currently writable enough for active storage."""
    try:
        _ensure_dir(path)
        probe = path / ".ygb_probe.tmp"
        _wal_protected_write("path_probe", str(probe), lambda: _write_probe_file(probe))
        probe.unlink(missing_ok=True)
        return True, "ok"
    except Exception as exc:
        return False, type(exc).__name__


def _log_storage_tier_availability(
    primary_ok: bool,
    primary_reason: str,
    fallback_ok: bool,
    fallback_reason: str,
) -> None:
    logger.info(
        "Storage tier availability: primary=%s (%s), fallback=%s (%s)",
        "available" if primary_ok else "unavailable",
        primary_reason,
        "available" if fallback_ok else "unavailable",
        fallback_reason,
    )


def resolve_hdd_root(*, log_availability: bool = False) -> tuple[Path, dict]:
    """
    Resolve the active HDD/NAS root.

    Primary policy:
      1. Use the configured archive root when available.
      2. Fall back to the configured local archive fallback when the primary root is unavailable.
    """
    primary_ok, primary_reason = _path_is_usable(PRIMARY_HDD_ROOT)
    fallback_ok, fallback_reason = _path_is_usable(FALLBACK_HDD_ROOT)

    if log_availability:
        _log_storage_tier_availability(
            primary_ok,
            primary_reason,
            fallback_ok,
            fallback_reason,
        )

    if primary_ok:
        return PRIMARY_HDD_ROOT, {
            "primary_root": str(PRIMARY_HDD_ROOT),
            "fallback_root": str(FALLBACK_HDD_ROOT),
            "active_root": str(PRIMARY_HDD_ROOT),
            "primary_available": True,
            "fallback_available": fallback_ok,
            "fallback_active": False,
            "mode": "PRIMARY",
            "reason": "Primary archive root active",
        }

    if fallback_ok:
        return FALLBACK_HDD_ROOT, {
            "primary_root": str(PRIMARY_HDD_ROOT),
            "fallback_root": str(FALLBACK_HDD_ROOT),
            "active_root": str(FALLBACK_HDD_ROOT),
            "primary_available": False,
            "fallback_available": True,
            "fallback_active": True,
            "mode": "FALLBACK",
            "reason": f"Primary archive root unavailable ({primary_reason}) — using local fallback",
        }

    raise StorageCompletelyUnavailableError("No storage backend available.")


def get_storage_topology(*, force_refresh: bool = False) -> dict:
    """
    Expose the resolved storage topology for API/runtime truth endpoints.

    The underlying probe writes a small file to the active HDD root to confirm
    writability. Caching prevents `/health` polling from repeatedly waking or
    stalling the storage device every few seconds.
    """
    now = time.monotonic()
    if not force_refresh:
        with _storage_topology_cache_lock:
            cached = _storage_topology_cache["value"]
            cached_at = float(_storage_topology_cache["checked_at"] or 0.0)
            if isinstance(cached, dict) and (now - cached_at) < STORAGE_TOPOLOGY_CACHE_SECONDS:
                return dict(cached)

    _, topology = resolve_hdd_root()

    with _storage_topology_cache_lock:
        _storage_topology_cache["checked_at"] = now
        _storage_topology_cache["value"] = dict(topology)

    return dict(topology)


def _active_hdd_root() -> Path:
    return resolve_hdd_root()[0]


def _active_hdd_dir(*parts: str) -> Path:
    return _active_hdd_root().joinpath(*parts)


def _backup_root() -> Path:
    override = os.environ.get("DATABASE_BACKUP_PATH", "").strip()
    if override:
        return Path(override).expanduser().parent
    return _active_hdd_root() / "backups"


def _hdd_usage() -> int:
    return _dir_size(_active_hdd_root())


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
    except Exception as exc:
        logger.warning("Failed to scan compression candidates under %s: %s", root, exc)
    candidates.sort(key=lambda p: p.stat().st_atime)
    return candidates


# ---------------------------------------------------------------------------
# Compression
# ---------------------------------------------------------------------------

def _compress_file_impl(src: Path) -> Optional[Path]:
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


def compress_file(src: Path) -> Optional[Path]:
    return _wal_protected_write("compress_file", str(src), lambda: _compress_file_impl(src))


def _human(b: int) -> str:
    if b >= _GB:
        return f"{b / _GB:.1f} GB"
    if b >= _MB:
        return f"{b / _MB:.1f} MB"
    return f"{b / 1024:.1f} KB"


# ---------------------------------------------------------------------------
# Migration (SSD → HDD overflow)
# ---------------------------------------------------------------------------

def _migrate_to_hdd_impl(src: Path) -> Optional[Path]:
    """Move a file from SSD to HDD overflow, preserving relative path."""
    try:
        rel = src.relative_to(SSD_ROOT)
    except ValueError:
        rel = Path(src.name)
    dst = _active_hdd_dir("ssd_overflow") / rel
    _ensure_dir(dst.parent)
    try:
        shutil.move(str(src), str(dst))
        logger.info("Migrated to HDD: %s → %s (%s)", src.name, dst, _human(dst.stat().st_size))
        return dst
    except Exception:
        logger.exception("Failed to migrate %s → HDD", src)
        return None


def migrate_to_hdd(src: Path) -> Optional[Path]:
    return _wal_protected_write("migrate_to_hdd", str(src), lambda: _migrate_to_hdd_impl(src))


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
    topology = get_storage_topology()
    report.primary_hdd_root = topology["primary_root"]
    report.fallback_hdd_root = topology["fallback_root"]
    report.active_hdd_root = topology["active_root"]
    report.primary_available = topology["primary_available"]
    report.fallback_available = topology["fallback_available"]
    report.fallback_active = topology["fallback_active"]
    report.topology_reason = topology["reason"]
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
        "video":      _active_hdd_dir("videos"),
        "log":        _active_hdd_dir("logs"),
        "user_data":  _active_hdd_dir("user_data"),
        "session":    _active_hdd_dir("sessions"),
        "upload":     _active_hdd_dir("user_data", "uploads"),
        "backup":     _backup_root(),
    }
    base = _mapping.get(category, _active_hdd_dir(category))
    _ensure_dir(base)
    return base / filename if filename else base


def get_storage_report() -> dict:
    """Quick snapshot of SSD/HDD usage for the API."""
    r = StorageReport()
    topology = get_storage_topology()
    r.primary_hdd_root = topology["primary_root"]
    r.fallback_hdd_root = topology["fallback_root"]
    r.active_hdd_root = topology["active_root"]
    r.primary_available = topology["primary_available"]
    r.fallback_available = topology["fallback_available"]
    r.fallback_active = topology["fallback_active"]
    r.topology_reason = topology["reason"]
    r.ssd_used_bytes = _ssd_usage()
    r.ssd_free_bytes = max(0, SSD_CAP_BYTES - r.ssd_used_bytes)
    r.ssd_usage_pct = (r.ssd_used_bytes / SSD_CAP_BYTES * 100) if SSD_CAP_BYTES > 0 else 0.0
    r.hdd_used_bytes = _hdd_usage()
    return r.to_dict()


def _probe_tier_health(root: Path, probe_name: str) -> tuple[float, float]:
    read_latency_ms = -1.0
    write_latency_ms = -1.0
    probe_path = root / probe_name
    payload = f"tier-health:{time.time_ns()}".encode("utf-8")

    try:
        _ensure_dir(root)

        write_start = time.perf_counter()
        _wal_protected_write(
            "tier_probe",
            str(probe_path),
            lambda: _write_probe_file(probe_path, payload),
        )
        write_latency_ms = (time.perf_counter() - write_start) * 1000.0

        read_start = time.perf_counter()
        with open(probe_path, "rb") as f:
            f.read()
        read_latency_ms = (time.perf_counter() - read_start) * 1000.0
    except Exception as exc:
        logger.warning("Tier health probe failed for %s: %s", root, exc)
    finally:
        probe_path.unlink(missing_ok=True)

    return read_latency_ms, write_latency_ms


def get_tier_health() -> list[StorageTierHealth]:
    results: list[StorageTierHealth] = []
    for tier_name, root in [
        ("ssd", SSD_ROOT),
        ("primary_hdd", PRIMARY_HDD_ROOT),
        ("fallback_hdd", FALLBACK_HDD_ROOT),
    ]:
        available_bytes = 0
        used_bytes = 0
        try:
            _ensure_dir(root)
            usage = shutil.disk_usage(root)
            available_bytes = int(usage.free)
            used_bytes = int(usage.used)
        except Exception as exc:
            logger.warning("Disk usage probe failed for %s (%s): %s", tier_name, root, exc)

        read_latency_ms, write_latency_ms = _probe_tier_health(
            root,
            f".{tier_name}.health.tmp",
        )
        results.append(
            StorageTierHealth(
                tier_name=tier_name,
                available_bytes=available_bytes,
                used_bytes=used_bytes,
                read_latency_ms=read_latency_ms,
                write_latency_ms=write_latency_ms,
            )
        )
    return results


# ---------------------------------------------------------------------------
# Ensure directories exist at import time
# ---------------------------------------------------------------------------

def _init_dirs():
    _replay_incomplete_wal_entries()
    try:
        hdd_root, topology = resolve_hdd_root(log_availability=True)
    except StorageCompletelyUnavailableError as exc:
        logger.critical("Storage initialization failed: %s", exc)
        raise
    hdd_dirs = [
        hdd_root / "videos",
        hdd_root / "logs",
        hdd_root / "user_data",
        hdd_root / "sessions",
        hdd_root / "ssd_overflow",
    ]
    if topology["fallback_active"]:
        logger.warning(
            "Primary HDD root unavailable; using fallback root at %s",
            hdd_root,
        )
    for d in [
        SSD_TRAINING_DIR, SSD_CHECKPOINTS, SSD_DATASETS,
        *hdd_dirs,
    ]:
        try:
            _ensure_dir(d)
        except Exception as exc:
            logger.warning("Storage directory init skipped for %s: %s", d, exc)


_init_dirs()


# ---------------------------------------------------------------------------
# Background enforcement thread (optional)
# ---------------------------------------------------------------------------

_enforcement_thread: Optional[threading.Thread] = None
_enforcement_stop_event = threading.Event()


async def _wait_for_stop_signal() -> None:
    stop_signal = asyncio.Event()
    if _enforcement_stop_event.is_set():
        stop_signal.set()
    else:
        loop = asyncio.get_running_loop()

        def _watch_stop() -> None:
            _enforcement_stop_event.wait()
            loop.call_soon_threadsafe(stop_signal.set)

        threading.Thread(
            target=_watch_stop,
            daemon=True,
            name="storage-enforcement-keepalive",
        ).start()

    await stop_signal.wait()


def start_enforcement_loop(interval_seconds: int = 300):
    """Start a daemon thread that enforces the SSD cap every N seconds."""
    global _enforcement_thread
    if _enforcement_thread and _enforcement_thread.is_alive():
        logger.info("Enforcement loop already running")
        return

    _enforcement_stop_event.clear()

    def _loop():
        logger.info("Storage enforcement loop started (every %ds)", interval_seconds)
        MAX_ITERATIONS = 100000  # Loop guard
        LOOP_TIMEOUT = 2592000  # 30 days
        _start = time.time()
        for _i in range(MAX_ITERATIONS):
            if _enforcement_stop_event.is_set():
                logger.info("Storage enforcement loop stopping on stop event")
                break
            if time.time() - _start > LOOP_TIMEOUT:
                logger.warning("Enforcement loop guard: timeout reached")
                break
            try:
                enforce_ssd_cap()
            except Exception:
                logger.exception("Error in storage enforcement loop")
            if _enforcement_stop_event.wait(interval_seconds):
                logger.info("Storage enforcement loop stop event received during wait")
                break
        logger.info("Enforcement loop ended after %d iterations", _i + 1)

    _enforcement_thread = threading.Thread(target=_loop, daemon=True, name="storage-enforcement")
    _enforcement_thread.start()


def stop_enforcement_loop(join_timeout_seconds: float = 5.0) -> None:
    """Signal the background storage enforcement loop to stop."""
    global _enforcement_thread
    _enforcement_stop_event.set()
    if _enforcement_thread and _enforcement_thread.is_alive():
        _enforcement_thread.join(timeout=join_timeout_seconds)
        if _enforcement_thread.is_alive():
            logger.warning("Storage enforcement loop did not stop within timeout")
        else:
            logger.info("Storage enforcement loop stopped")


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
        try:
            asyncio.run(_wait_for_stop_signal())
        finally:
            stop_enforcement_loop()
    else:
        print(json.dumps(get_storage_report(), indent=2))
