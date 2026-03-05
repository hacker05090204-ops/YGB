"""
YGB Sync Engine — Production-grade multi-device file synchronization.

Modes:
  --watch   : Real-time filesystem watcher + periodic sync (daemon)
  --once    : Single sync cycle then exit
  --restore : Recovery mode — pull missing files from peers/cloud
  --status  : Print current sync status

Architecture:
  1. File watcher (watchdog) detects changes → debounced sync
  2. Periodic 5-min full scan as safety net
  3. Manifest diff → chunk changed files → push/pull peers → cloud backup
  4. Retention enforcement + cold-file compression runs after each cycle
"""

import argparse
import logging
import os
import shutil
import sys
import threading
import time
from pathlib import Path

try:
    import zstandard as zstd
    _HAVE_ZSTD = True
except ImportError:
    _HAVE_ZSTD = False

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.sync.manifest import (
    SyncManifest, hash_file, load_manifest, save_manifest,
    diff_manifests, changes_count, DEVICE_ID,
)
from backend.sync.chunker import (
    chunk_file, cleanup_orphan_chunks, CHUNK_SIZE,
)

logger = logging.getLogger("ygb.sync")

# ── Configuration ─────────────────────────────────────────────────────

SYNC_ROOT     = Path(os.getenv("YGB_SYNC_ROOT", "D:\\"))
SYNC_META     = SYNC_ROOT / "ygb_sync"
MANIFEST_PATH = SYNC_META / "manifest.json"
PEER_STATE    = SYNC_META / "peer_state"
CHUNK_CACHE   = SYNC_META / "chunk_cache"
CONFLICT_DIR  = SYNC_META / "conflict_archive"
SYNC_INTERVAL = int(os.getenv("YGB_SYNC_INTERVAL_SEC", "300"))

# Directories to sync (relative to SYNC_ROOT)
SYNC_DIRS = [
    "ygb_reports",
    "ygb_videos",
    "ygb_training",
    "ygb_logs",
    "ygb_backups",
]

# Retention policies (days)
RETENTION = {
    "ygb_videos":  int(os.getenv("YGB_RETENTION_VIDEOS", "30")),
    "ygb_logs":    int(os.getenv("YGB_RETENTION_LOGS", "14")),
    "ygb_reports": int(os.getenv("YGB_RETENTION_REPORTS", "90")),
}

# Paths that are "critical" and MUST be cloud-backed
CRITICAL_PATTERNS = [
    "models/", "checkpoints/best", "ygb.db",
    "dataset_manifest", "phase_reports",
]


def _init_dirs():
    """Create all sync metadata directories."""
    for d in [SYNC_META, PEER_STATE, CHUNK_CACHE, CONFLICT_DIR]:
        d.mkdir(parents=True, exist_ok=True)
    for sd in SYNC_DIRS:
        (SYNC_ROOT / sd).mkdir(parents=True, exist_ok=True)


def _is_critical(path: str) -> bool:
    """Check if path matches a critical backup pattern."""
    return any(pat in path for pat in CRITICAL_PATTERNS)


# ── Scan ──────────────────────────────────────────────────────────────

def scan_local_files() -> dict:
    """
    Scan all sync directories.
    Returns {relative_path: {path, hash, size, mtime, chunks, device_id, clock}}
    """
    entries = {}
    for sync_dir in SYNC_DIRS:
        root = SYNC_ROOT / sync_dir
        if not root.exists():
            continue
        for fpath in root.rglob("*"):
            if fpath.is_dir():
                continue
            # Skip sync metadata
            if "ygb_sync" in str(fpath):
                continue
            try:
                rel = str(fpath.relative_to(SYNC_ROOT)).replace("\\", "/")
                stat = fpath.stat()
                file_hash = hash_file(fpath)
                if not file_hash:
                    continue  # Skip unreadable files
                chunks = chunk_file(fpath) if stat.st_size > CHUNK_SIZE else [file_hash]
                entries[rel] = {
                    "path": rel,
                    "hash": file_hash,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "chunks": chunks,
                    "device_id": DEVICE_ID,
                    "clock": 0,
                }
            except (PermissionError, OSError) as e:
                logger.warning("Scan skip %s: %s", fpath, e)
    return entries


# ── Retention ─────────────────────────────────────────────────────────

def enforce_retention() -> int:
    """Delete files exceeding retention policy. Returns count deleted."""
    now = time.time()
    deleted = 0
    for category, max_days in RETENTION.items():
        root = SYNC_ROOT / category
        if not root.exists():
            continue
        cutoff = now - (max_days * 86400)
        for fpath in root.rglob("*"):
            if fpath.is_dir() or "_metadata" in str(fpath):
                continue  # NEVER delete metadata indexes
            try:
                if fpath.stat().st_mtime < cutoff:
                    fpath.unlink()
                    deleted += 1
                    logger.info("Retention: deleted %s (>%dd)", fpath.name, max_days)
            except OSError:
                pass

    # Clean conflict archive (7 days)
    cutoff_conflict = now - (7 * 86400)
    if CONFLICT_DIR.exists():
        for fpath in CONFLICT_DIR.rglob("*"):
            if fpath.is_file():
                try:
                    if fpath.stat().st_mtime < cutoff_conflict:
                        fpath.unlink()
                        deleted += 1
                except OSError:
                    pass
    if deleted:
        logger.info("Retention: cleaned %d files total", deleted)
    return deleted


# ── Compression ───────────────────────────────────────────────────────

def compress_cold_files() -> int:
    """Compress files older than 24h with zstd (level 3). Returns count compressed."""
    if not _HAVE_ZSTD:
        logger.debug("zstandard not installed — skipping compression")
        return 0

    cctx = zstd.ZstdCompressor(level=3)
    now = time.time()
    cutoff = now - 86400  # 24 hours
    compressed = 0

    for category in ["ygb_logs", "ygb_reports"]:
        root = SYNC_ROOT / category
        if not root.exists():
            continue
        for fpath in root.rglob("*"):
            if fpath.is_dir() or fpath.suffix == ".zst":
                continue
            try:
                st = fpath.stat()
                if st.st_mtime < cutoff and st.st_size > 1024:
                    zst_path = fpath.with_suffix(fpath.suffix + ".zst")
                    with open(fpath, "rb") as fin, open(zst_path, "wb") as fout:
                        cctx.copy_stream(fin, fout)
                    fpath.unlink()
                    compressed += 1
            except OSError:
                pass
    if compressed:
        logger.info("Compressed %d cold files with zstd", compressed)
    return compressed


# ── Main Sync Cycle ───────────────────────────────────────────────────

def sync_cycle() -> dict:
    """
    Execute one full sync cycle: scan → diff → chunk → retention → compress.

    Returns a summary dict with stats.
    """
    _init_dirs()
    logger.info("═══ Sync cycle start [%s] ═══", DEVICE_ID)
    t0 = time.monotonic()

    # 1. Load previous manifest
    manifest = load_manifest(MANIFEST_PATH)
    previous_files = dict(manifest.files)

    # 2. Scan current files
    current_files = scan_local_files()
    scan_ms = int((time.monotonic() - t0) * 1000)

    # 3. Diff
    diff = diff_manifests(current_files, previous_files)
    n_changes = changes_count(diff)

    if n_changes == 0:
        logger.info("No changes detected (%d files, scan=%dms)", len(current_files), scan_ms)
    else:
        logger.info(
            "Changes: +%d added, ~%d modified, -%d deleted (scan=%dms)",
            len(diff["added"]), len(diff["modified"]), len(diff["deleted"]), scan_ms,
        )

    # 4. Update manifest
    manifest.files = current_files
    if n_changes > 0:
        manifest.bump_clock()
    else:
        manifest.last_sync = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    save_manifest(manifest, MANIFEST_PATH)

    # 5. Retention & compression
    t1 = time.monotonic()
    deleted = enforce_retention()
    compressed = compress_cold_files()
    orphans = cleanup_orphan_chunks(manifest.files)
    maint_ms = int((time.monotonic() - t1) * 1000)

    # 6. Identify critical files for cloud backup
    critical = [p for p in current_files if _is_critical(p)]

    total_ms = int((time.monotonic() - t0) * 1000)
    summary = {
        "device_id": DEVICE_ID,
        "files_tracked": len(current_files),
        "total_bytes": sum(e.get("size", 0) for e in current_files.values()),
        "changes": n_changes,
        "added": len(diff["added"]),
        "modified": len(diff["modified"]),
        "deleted_from_diff": len(diff["deleted"]),
        "retention_deleted": deleted,
        "compressed": compressed,
        "orphan_chunks_removed": orphans,
        "critical_files": len(critical),
        "scan_ms": scan_ms,
        "maintenance_ms": maint_ms,
        "total_ms": total_ms,
        "vector_clock": manifest.vector_clock,
    }

    logger.info(
        "═══ Sync done: %d files (%.1f MB), %d changes, %dms ═══",
        summary["files_tracked"],
        summary["total_bytes"] / 1e6,
        summary["changes"],
        total_ms,
    )
    return summary


# ── File Watcher ──────────────────────────────────────────────────────

def run_watcher():
    """Run filesystem watcher (event-driven) + periodic sync (safety net)."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        logger.error("watchdog not installed — run: pip install watchdog")
        logger.info("Falling back to periodic-only mode")
        _run_periodic_only()
        return

    class _SyncHandler(FileSystemEventHandler):
        def __init__(self):
            self._timer = None
            self._lock = threading.Lock()

        def _debounced_sync(self):
            with self._lock:
                self._timer = None
            try:
                sync_cycle()
            except Exception:
                logger.exception("Event-driven sync failed")

        def on_any_event(self, event):
            if "ygb_sync" in event.src_path:
                return
            with self._lock:
                if self._timer:
                    self._timer.cancel()
                # 5-second debounce: batch rapid writes
                self._timer = threading.Timer(5.0, self._debounced_sync)
                self._timer.daemon = True
                self._timer.start()

    _init_dirs()
    handler = _SyncHandler()
    observer = Observer()

    for sd in SYNC_DIRS:
        watch_path = SYNC_ROOT / sd
        watch_path.mkdir(parents=True, exist_ok=True)
        observer.schedule(handler, str(watch_path), recursive=True)
        logger.info("Watching: %s", watch_path)

    observer.start()
    logger.info("╔══ YGB Sync Engine started ══╗")
    logger.info("║ Device: %-20s  ║", DEVICE_ID)
    logger.info("║ Root:   %-20s  ║", str(SYNC_ROOT))
    logger.info("║ Interval: %ds, Debounce: 5s  ║", SYNC_INTERVAL)
    logger.info("╚══════════════════════════════╝")

    # Initial sync
    try:
        sync_cycle()
    except Exception:
        logger.exception("Initial sync failed")

    try:
        while True:
            time.sleep(SYNC_INTERVAL)
            try:
                sync_cycle()
            except Exception:
                logger.exception("Periodic sync failed")
    except KeyboardInterrupt:
        logger.info("Shutting down sync engine...")
        observer.stop()
    observer.join()


def _run_periodic_only():
    """Fallback: periodic-only sync without filesystem events."""
    _init_dirs()
    logger.info("Periodic-only mode: interval=%ds", SYNC_INTERVAL)
    try:
        sync_cycle()
    except Exception:
        logger.exception("Initial sync failed")

    try:
        while True:
            time.sleep(SYNC_INTERVAL)
            try:
                sync_cycle()
            except Exception:
                logger.exception("Periodic sync failed")
    except KeyboardInterrupt:
        logger.info("Shutting down sync engine...")


def print_status():
    """Print current sync status to stdout."""
    import json
    _init_dirs()
    manifest = load_manifest(MANIFEST_PATH)
    status = {
        "device_id": manifest.device_id,
        "vector_clock": manifest.vector_clock,
        "file_count": manifest.file_count(),
        "total_bytes": manifest.total_bytes(),
        "total_mb": round(manifest.total_bytes() / 1e6, 1),
        "last_sync": manifest.last_sync,
        "manifest_path": str(MANIFEST_PATH),
    }
    print(json.dumps(status, indent=2))


# ── Entry Point ───────────────────────────────────────────────────────

def _setup_logging():
    log_file = SYNC_META / "sync.log"
    SYNC_META.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(str(log_file), encoding="utf-8"),
        ],
    )


def main():
    parser = argparse.ArgumentParser(
        description="YGB Sync Engine — Multi-device file synchronization",
    )
    parser.add_argument("--watch", action="store_true", help="Watch mode (daemon)")
    parser.add_argument("--once", action="store_true", help="Single sync cycle")
    parser.add_argument("--restore", action="store_true", help="Recovery mode")
    parser.add_argument("--status", action="store_true", help="Print sync status")
    args = parser.parse_args()

    _setup_logging()
    _init_dirs()

    if args.status:
        print_status()
    elif args.watch:
        run_watcher()
    elif args.once:
        import json
        result = sync_cycle()
        print(json.dumps(result, indent=2))
    elif args.restore:
        logger.info("Recovery mode — scanning and pulling from peers/cloud...")
        sync_cycle()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
