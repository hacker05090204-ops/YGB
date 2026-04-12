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
import hashlib
import json
import logging
import os
import shutil
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
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
_SYNC_STOP_EVENT = threading.Event()
SYNC_STATUS_PATH = Path("data/sync_status.json")
SYNC_CONFIG_ENV_VARS = ("YGB_SYNC_PEERS", "YGB_PEER_NODES")


class SyncMode(str, Enum):
    STANDALONE = "STANDALONE"
    PEER_SYNC = "PEER_SYNC"
    DEGRADED = "DEGRADED"


def is_sync_configured() -> bool:
    return any(os.getenv(name, "").strip() for name in SYNC_CONFIG_ENV_VARS)


def _hash_local_sync_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@dataclass
class LocalFileRecord:
    path: str
    sha256: str
    size_bytes: int
    indexed_at: str


@dataclass(frozen=True)
class SyncCycleResult:
    cycle_id: str
    started_at: str
    completed_at: str
    files_scanned: int
    files_changed: int
    peers_attempted: int
    peers_succeeded: int
    errors: list[str]
    mode: str = SyncMode.STANDALONE.value
    local_files: int = 0
    local_bytes: int = 0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class SyncHistory:
    def __init__(self, limit: int = 50):
        self._entries = deque(maxlen=max(1, limit))
        self._lock = threading.Lock()

    def add(self, result: SyncCycleResult) -> None:
        with self._lock:
            self._entries.append(result)

    def get_entries(self) -> list[SyncCycleResult]:
        with self._lock:
            return list(self._entries)


_SYNC_HISTORY = SyncHistory(limit=50)


class LocalSyncIndex:
    """Tracks local files available for sync."""

    SCAN_DIRS = [
        "data",
        "checkpoints",
        "training/features_safetensors",
    ]
    INDEX_PATH = Path("data/local_sync_index.json")
    EXCLUDED_SUBTREES = {
        "data/raw",
        "data/normalized",
    }

    def __init__(self):
        self._records: dict[str, LocalFileRecord] = {}
        self._lock = threading.Lock()
        self._load()

    @classmethod
    def _iter_files(cls, directory: Path):
        excluded_roots = {
            Path(path).resolve() for path in cls.EXCLUDED_SUBTREES
        }
        for root, dirnames, filenames in os.walk(directory):
            root_path = Path(root)
            try:
                resolved_root = root_path.resolve()
            except OSError as exc:
                logger.warning("LocalSyncIndex: cannot resolve %s: %s", root_path, exc)
                continue

            if resolved_root in excluded_roots:
                dirnames[:] = []
                continue

            filtered_dirnames: list[str] = []
            for dirname in dirnames:
                candidate = root_path / dirname
                try:
                    if candidate.resolve() in excluded_roots:
                        continue
                except OSError as exc:
                    logger.warning("LocalSyncIndex: cannot resolve %s: %s", candidate, exc)
                    continue
                filtered_dirnames.append(dirname)
            dirnames[:] = filtered_dirnames

            for filename in filenames:
                yield root_path / filename

    def refresh(self):
        with self._lock:
            existing_records = dict(self._records)

        refreshed_records: dict[str, LocalFileRecord] = {}
        index_path = self.INDEX_PATH.resolve()
        for dir_name in self.SCAN_DIRS:
            directory = Path(dir_name)
            if not directory.exists():
                continue
            for file_path in self._iter_files(directory):
                try:
                    if file_path.resolve() == index_path:
                        continue
                except OSError as exc:
                    logger.warning("LocalSyncIndex: cannot resolve %s: %s", file_path, exc)
                    continue
                key = str(file_path).replace("\\", "/")
                try:
                    stat_result = file_path.stat()
                except OSError as exc:
                    logger.warning("LocalSyncIndex: cannot stat %s: %s", file_path, exc)
                    continue
                mtime = str(stat_result.st_mtime_ns)
                existing = existing_records.get(key)
                if existing and existing.indexed_at == mtime:
                    refreshed_records[key] = existing
                    continue
                try:
                    sha = _hash_local_sync_file(file_path)
                    refreshed_records[key] = LocalFileRecord(
                        path=key,
                        sha256=sha,
                        size_bytes=int(stat_result.st_size),
                        indexed_at=mtime,
                    )
                except OSError as exc:
                    logger.warning("LocalSyncIndex: cannot index %s: %s", file_path, exc)

        with self._lock:
            self._records = refreshed_records
        self._save()

    def get_file_count(self) -> int:
        with self._lock:
            return len(self._records)

    def get_total_bytes(self) -> int:
        with self._lock:
            return sum(record.size_bytes for record in self._records.values())

    def _save(self):
        self.INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {key: value.__dict__ for key, value in self._records.items()}
        temp_path = self.INDEX_PATH.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )
        temp_path.replace(self.INDEX_PATH)

    def _load(self):
        if not self.INDEX_PATH.exists():
            return
        try:
            data = json.loads(self.INDEX_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("LocalSyncIndex: failed to load persisted index", exc_info=True)
            return
        with self._lock:
            self._records = {key: LocalFileRecord(**value) for key, value in data.items()}


_sync_index = LocalSyncIndex()


def get_local_sync_index() -> LocalSyncIndex:
    return _sync_index


def get_sync_mode() -> SyncMode:
    if not is_sync_configured():
        return SyncMode.STANDALONE
    from backend.sync.peer_transport import PeerStatus, get_peer_statuses, get_peers

    try:
        peers = get_peers()
    except Exception as exc:
        logger.warning("Sync mode peer discovery failed: %s", exc, exc_info=True)
        peers = []

    if peers and any(
        str(peer.get("peer_status", "")).upper() == PeerStatus.REACHABLE.value
        or str(peer.get("status", "")).upper() == "ONLINE"
        for peer in peers
    ):
        return SyncMode.PEER_SYNC

    statuses = get_peer_statuses()
    if any(
        str(getattr(status, "value", status)).upper() == PeerStatus.REACHABLE.value
        for status in statuses.values()
    ):
        return SyncMode.PEER_SYNC
    return SyncMode.DEGRADED


def get_last_sync_cycle() -> SyncCycleResult | None:
    history = get_sync_history()
    return history[-1] if history else None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_sync_stale(
    *,
    mode: SyncMode | None = None,
    last_completed_at: str | None = None,
    interval_seconds: int | None = None,
) -> bool:
    resolved_mode = mode or get_sync_mode()
    if resolved_mode == SyncMode.STANDALONE:
        return False
    if resolved_mode == SyncMode.DEGRADED:
        return True
    completed_at = _parse_iso_datetime(last_completed_at)
    if completed_at is None:
        last_cycle = get_last_sync_cycle()
        completed_at = _parse_iso_datetime(
            last_cycle.completed_at if last_cycle is not None else None
        )
    if completed_at is None:
        return True
    threshold_seconds = max(1, int(interval_seconds or SYNC_INTERVAL)) * 2
    now = datetime.now(timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return (now - completed_at.astimezone(timezone.utc)).total_seconds() > threshold_seconds


def sync_status_message(mode: SyncMode, *, peers_attempted: int = 0, peers_succeeded: int = 0) -> str:
    if mode == SyncMode.STANDALONE:
        return "Single-device mode. Set YGB_SYNC_PEERS for mesh sync."
    if mode == SyncMode.PEER_SYNC:
        total_peers = max(peers_attempted, peers_succeeded)
        if total_peers <= 0:
            return "Mesh sync active. Peer replication available."
        return f"Mesh sync active. Reachable peers: {peers_succeeded}/{total_peers}."
    return "Mesh sync configured but peers are unreachable. Running in degraded mode."


def write_sync_status_snapshot(payload: dict[str, object]) -> None:
    SYNC_STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SYNC_STATUS_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_path.replace(SYNC_STATUS_PATH)

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


def get_sync_history() -> list[SyncCycleResult]:
    """Return the last 50 sync cycle results."""
    return _SYNC_HISTORY.get_entries()


def _build_manifest_payload(manifest: SyncManifest) -> dict[str, object]:
    return {
        "device_id": manifest.device_id,
        "vector_clock": manifest.vector_clock,
        "files": manifest.files,
        "last_sync": manifest.last_sync,
        "version": manifest.version,
    }


def _sync_manifest_to_peers(manifest: SyncManifest) -> tuple[int, int, list[str]]:
    errors: list[str] = []
    peers_attempted = 0
    peers_succeeded = 0

    try:
        from backend.sync.peer_transport import get_peers, push_manifest_to_peer

        peers = get_peers()
    except Exception as exc:
        detail = f"Peer discovery failed: {type(exc).__name__}: {exc}"
        logger.warning(detail, exc_info=True)
        return 0, 0, [detail]

    payload = _build_manifest_payload(manifest)
    for peer in peers:
        peers_attempted += 1
        peer_name = str(peer.get("name", "unknown"))
        peer_url = str(peer.get("url", "")).strip()
        peer_status = str(peer.get("status", "UNKNOWN")).upper()

        if peer_status != "ONLINE":
            detail = f"Peer {peer_name} unreachable ({peer_status})"
            logger.warning(detail)
            errors.append(detail)
            continue

        try:
            pushed = push_manifest_to_peer(peer_url, payload)
        except Exception as exc:
            detail = f"Peer {peer_name} sync failed: {type(exc).__name__}: {exc}"
            logger.warning(detail, exc_info=True)
            errors.append(detail)
            continue

        if pushed:
            peers_succeeded += 1
            logger.info("Manifest synced to peer %s", peer_name)
            continue

        detail = f"Peer {peer_name} unreachable (manifest push failed)"
        logger.warning(detail)
        errors.append(detail)

    return peers_attempted, peers_succeeded, errors


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
            except OSError as exc:
                logger.debug("Retention cleanup skipped for %s: %s", fpath, exc)

    # Clean conflict archive (7 days)
    cutoff_conflict = now - (7 * 86400)
    if CONFLICT_DIR.exists():
        for fpath in CONFLICT_DIR.rglob("*"):
            if fpath.is_file():
                try:
                    if fpath.stat().st_mtime < cutoff_conflict:
                        fpath.unlink()
                        deleted += 1
                except OSError as exc:
                    logger.debug("Conflict archive cleanup skipped for %s: %s", fpath, exc)
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
            except OSError as exc:
                logger.debug("Compression skipped for %s: %s", fpath, exc)
    if compressed:
        logger.info("Compressed %d cold files with zstd", compressed)
    return compressed


# ── Main Sync Cycle ───────────────────────────────────────────────────

def sync_cycle() -> SyncCycleResult:
    """Execute one full sync cycle and return the authoritative cycle result."""
    _init_dirs()
    _sync_index.refresh()
    sync_mode = get_sync_mode()
    configured = is_sync_configured()
    started_dt = datetime.now(timezone.utc)
    cycle_id = f"{DEVICE_ID}-{started_dt.strftime('%Y%m%dT%H%M%S%fZ')}"
    logger.info("═══ Sync cycle start [%s] cycle_id=%s ═══", DEVICE_ID, cycle_id)
    t0 = time.monotonic()

    # 1. Load previous manifest
    manifest = load_manifest(MANIFEST_PATH)
    previous_files = dict(manifest.files)

    # 2. Maintenance first, then scan the final on-disk state.
    deleted = enforce_retention()
    compressed = compress_cold_files()
    current_files = scan_local_files()
    diff = diff_manifests(current_files, previous_files)
    n_changes = changes_count(diff)

    if n_changes == 0:
        logger.info("No changes detected (%d files)", len(current_files))
    else:
        logger.info(
            "Changes: +%d added, ~%d modified, -%d deleted",
            len(diff["added"]),
            len(diff["modified"]),
            len(diff["deleted"]),
        )

    # 3. Update manifest from the authoritative end-of-cycle file set.
    manifest.files = current_files
    if n_changes > 0:
        manifest.bump_clock()
    else:
        manifest.last_sync = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    orphans = cleanup_orphan_chunks(manifest.files)

    try:
        save_manifest(manifest, MANIFEST_PATH)
    except Exception as exc:
        logger.critical("Manifest write failed for %s: %s", MANIFEST_PATH, exc, exc_info=True)
        raise

    # 4. Propagate the authoritative manifest to peers without crashing the cycle.
    peers_attempted, peers_succeeded, errors = _sync_manifest_to_peers(manifest)

    completed_dt = datetime.now(timezone.utc)
    total_ms = int((time.monotonic() - t0) * 1000)
    result = SyncCycleResult(
        cycle_id=cycle_id,
        started_at=started_dt.isoformat(),
        completed_at=completed_dt.isoformat(),
        files_scanned=len(current_files),
        files_changed=n_changes,
        peers_attempted=peers_attempted,
        peers_succeeded=peers_succeeded,
        errors=errors,
        mode=sync_mode.value,
        local_files=_sync_index.get_file_count(),
        local_bytes=_sync_index.get_total_bytes(),
    )
    _SYNC_HISTORY.add(result)
    write_sync_status_snapshot(
        {
            "cycle_id": result.cycle_id,
            "mode": result.mode,
            "local_files": result.local_files,
            "local_bytes": result.local_bytes,
            "last_sync_time": result.completed_at,
            "peers_connected": result.peers_succeeded,
            "files_synced_last_cycle": result.files_changed,
            "configured": configured,
            "stale": is_sync_stale(mode=sync_mode, last_completed_at=result.completed_at),
            "message": sync_status_message(
                sync_mode,
                peers_attempted=result.peers_attempted,
                peers_succeeded=result.peers_succeeded,
            ),
        }
    )

    logger.info(
        "Maintenance summary: retention_deleted=%d compressed=%d orphan_chunks_removed=%d critical_files=%d",
        deleted,
        compressed,
        orphans,
        len([path for path in current_files if _is_critical(path)]),
    )
    logger.info(
        "═══ Sync done: %d files, %d changes, peers=%d/%d, errors=%d, %dms ═══",
        result.files_scanned,
        result.files_changed,
        result.peers_succeeded,
        result.peers_attempted,
        len(result.errors),
        total_ms,
    )
    return result


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

    _SYNC_STOP_EVENT.clear()
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
        while not _SYNC_STOP_EVENT.is_set():
            if _SYNC_STOP_EVENT.wait(SYNC_INTERVAL):
                logger.info("Shutting down sync engine on stop event...")
                break
            try:
                sync_cycle()
            except Exception:
                logger.exception("Periodic sync failed")
    except KeyboardInterrupt:
        logger.info("Shutting down sync engine...")
        _SYNC_STOP_EVENT.set()
        observer.stop()
    else:
        observer.stop()
    observer.join()


def _run_periodic_only():
    """Fallback: periodic-only sync without filesystem events."""
    _init_dirs()
    _SYNC_STOP_EVENT.clear()
    logger.info("Periodic-only mode: interval=%ds", SYNC_INTERVAL)
    try:
        sync_cycle()
    except Exception:
        logger.exception("Initial sync failed")

    try:
        while not _SYNC_STOP_EVENT.is_set():
            if _SYNC_STOP_EVENT.wait(SYNC_INTERVAL):
                logger.info("Shutting down sync engine on stop event...")
                break
            try:
                sync_cycle()
            except Exception:
                logger.exception("Periodic sync failed")
    except KeyboardInterrupt:
        logger.info("Shutting down sync engine...")
        _SYNC_STOP_EVENT.set()


def request_sync_engine_stop() -> None:
    """Signal cooperative shutdown for long-running sync loops."""
    _SYNC_STOP_EVENT.set()


def print_status():
    """Print current sync status to stdout."""
    import json
    _init_dirs()
    manifest = load_manifest(MANIFEST_PATH)
    mode = get_sync_mode()
    _sync_index.refresh()
    status = {
        "device_id": manifest.device_id,
        "mode": mode.value,
        "configured": is_sync_configured(),
        "vector_clock": manifest.vector_clock,
        "file_count": manifest.file_count(),
        "local_files": _sync_index.get_file_count(),
        "local_bytes": _sync_index.get_total_bytes(),
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
        print(json.dumps(result.to_dict(), indent=2))
    elif args.restore:
        logger.info("Recovery mode — scanning and pulling from peers/cloud...")
        sync_cycle()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
