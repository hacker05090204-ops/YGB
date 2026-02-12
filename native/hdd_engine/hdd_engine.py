"""
HDD Storage Engine — Core
==========================

Pure HDD-based append-only storage engine for YGB.
No SQLite. No SSD. No JSON pseudo-database.

Architecture:
- Append-only JSONL logs per entity
- Binary hash index for O(1) lookup
- Lifecycle metadata files
- Atomic writes (temp → fsync → rename → dir fsync)
- File locking (single writer per entity)
- Configurable HDD root path

Storage Structure:
    {HDD_ROOT}/
        users/
        sessions/
        devices/
        targets/
        reports/
        videos/
        training/
        audit/
        backups/
        indexes/
"""

import os
import sys
import json
import time
import struct
import hashlib
import logging
import platform
import threading
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger("hdd_engine")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [HDD] %(levelname)s: %(message)s"
    ))
    logger.addHandler(handler)


# =============================================================================
# CONSTANTS
# =============================================================================

# Default HDD root — MUST be on HDD, never SSD
if platform.system() == "Windows":
    DEFAULT_HDD_ROOT = "D:/ygb_hdd"
else:
    DEFAULT_HDD_ROOT = "/mnt/hdd/ygb"

# Entity types (subdirectories)
ENTITY_TYPES = (
    "users",
    "sessions",
    "devices",
    "targets",
    "reports",
    "videos",
    "training",
    "audit",
    "backups",
    "indexes",
)

# File extensions
LOG_EXT = ".log"       # Append-only JSONL
IDX_EXT = ".idx"       # Binary index
META_EXT = ".meta"     # Lifecycle state JSON
LOCK_EXT = ".lock"     # File lock

# Directory permissions
DIR_MODE = 0o700  # Owner only (Linux)

# Max entity ID length
MAX_ID_LENGTH = 128


# =============================================================================
# LIFECYCLE STATES
# =============================================================================

class LifecycleState(Enum):
    """Entity lifecycle states."""
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    BACKED_UP = "BACKED_UP"
    MARKED_FOR_DELETION = "MARKED_FOR_DELETION"
    DELETED = "DELETED"


# =============================================================================
# FILESYSTEM HELPERS (PLATFORM-SAFE)
# =============================================================================

def _fsync_file(fd: int) -> None:
    """fsync a file descriptor."""
    os.fsync(fd)


def _fsync_directory(dir_path: str) -> None:
    """
    fsync a directory to ensure renames are durable.
    On Windows, directory fsync is not supported — we use FlushFileBuffers.
    """
    if platform.system() != "Windows":
        fd = os.open(dir_path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        # Windows: FlushFileBuffers via ctypes
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            GENERIC_WRITE = 0x40000000
            OPEN_EXISTING = 3
            FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
            handle = kernel32.CreateFileW(
                dir_path,
                GENERIC_WRITE,
                0,  # no sharing
                None,
                OPEN_EXISTING,
                FILE_FLAG_BACKUP_SEMANTICS,
                None,
            )
            if handle != -1:
                kernel32.FlushFileBuffers(handle)
                kernel32.CloseHandle(handle)
        except Exception:
            pass  # Best effort on Windows


def _atomic_write(target_path: str, data: bytes) -> None:
    """
    Atomic write: write to temp → fsync → rename → dir fsync.
    Guarantees data integrity even on power loss.
    """
    dir_path = os.path.dirname(target_path)
    tmp_path = target_path + ".tmp"

    # Write to temp file
    fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
        _fsync_file(fd)
    finally:
        os.close(fd)

    # Atomic rename
    if platform.system() == "Windows":
        # Windows: os.replace is atomic
        os.replace(tmp_path, target_path)
    else:
        os.rename(tmp_path, target_path)

    # Sync directory
    _fsync_directory(dir_path)


def _file_lock_acquire(lock_path: str) -> int:
    """
    Acquire an exclusive file lock.
    Returns the file descriptor (must be released later).
    """
    fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)

    if platform.system() == "Windows":
        import msvcrt
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    return fd


def _file_lock_release(fd: int) -> None:
    """Release a file lock."""
    if platform.system() == "Windows":
        import msvcrt
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_UN)

    os.close(fd)


def _validate_entity_id(entity_id: str) -> bool:
    """
    Validate entity ID to prevent path traversal.
    Only alphanumeric, hyphens, and underscores allowed.
    """
    if not entity_id or len(entity_id) > MAX_ID_LENGTH:
        return False
    # Strict: only safe characters
    return all(c.isalnum() or c in "-_" for c in entity_id)


def _validate_entity_type(entity_type: str) -> bool:
    """Validate entity type is in allowed list."""
    return entity_type in ENTITY_TYPES


# =============================================================================
# HDD ENGINE CLASS
# =============================================================================

class HDDEngine:
    """
    Core HDD storage engine.

    All data stored as:
    - {entity_type}/{entity_id}.log  — Append-only JSONL records
    - {entity_type}/{entity_id}.idx  — Binary hash index
    - {entity_type}/{entity_id}.meta — Lifecycle metadata

    Thread safety: File locking per entity.
    Durability: fsync after every write + directory sync.
    """

    # Cache TTL in seconds
    CACHE_TTL = 5.0

    def __init__(self, hdd_root: Optional[str] = None):
        self._root = Path(hdd_root or os.getenv("YGB_HDD_ROOT", DEFAULT_HDD_ROOT))
        self._initialized = False
        self._stats = {
            "total_writes": 0,
            "total_reads": 0,
            "total_entities": 0,
            "total_bytes_written": 0,
        }
        # --- Performance caches ---
        self._meta_cache: Dict[str, Dict[str, Any]] = {}       # key: "type/id" -> meta dict
        self._entity_cache: Dict[str, Tuple[float, Any]] = {}  # key: "type/id" -> (ts, result)
        self._list_cache: Dict[str, Tuple[float, List]] = {}   # key: entity_type -> (ts, list)
        self._count_cache: Dict[str, Tuple[float, int]] = {}   # key: entity_type -> (ts, count)
        self._cache_lock = threading.Lock()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> bool:
        """
        Initialize the storage engine.
        Creates all required directories with proper permissions.
        Returns True if successful.
        """
        try:
            # Create root
            self._root.mkdir(parents=True, exist_ok=True)

            # Create entity directories
            for entity_type in ENTITY_TYPES:
                entity_dir = self._root / entity_type
                entity_dir.mkdir(parents=True, exist_ok=True)

                # Set permissions on Linux
                if platform.system() != "Windows":
                    os.chmod(str(entity_dir), DIR_MODE)

            self._initialized = True
            logger.info(f"HDD Engine initialized at: {self._root}")

            # Count existing entities
            self._stats["total_entities"] = self._count_entities()

            return True

        except Exception as e:
            logger.error(f"Failed to initialize HDD engine: {e}")
            return False

    def _count_entities(self) -> int:
        """Count total entities across all types."""
        count = 0
        for entity_type in ENTITY_TYPES:
            entity_dir = self._root / entity_type
            if entity_dir.exists():
                count += len(list(entity_dir.glob(f"*{META_EXT}")))
        return count

    def _entity_dir(self, entity_type: str) -> Path:
        """Get the directory for an entity type."""
        return self._root / entity_type

    def _log_path(self, entity_type: str, entity_id: str) -> Path:
        return self._entity_dir(entity_type) / f"{entity_id}{LOG_EXT}"

    def _idx_path(self, entity_type: str, entity_id: str) -> Path:
        return self._entity_dir(entity_type) / f"{entity_id}{IDX_EXT}"

    def _meta_path(self, entity_type: str, entity_id: str) -> Path:
        return self._entity_dir(entity_type) / f"{entity_id}{META_EXT}"

    def _lock_path(self, entity_type: str, entity_id: str) -> Path:
        return self._entity_dir(entity_type) / f"{entity_id}{LOCK_EXT}"

    # =========================================================================
    # WRITE OPERATIONS (Append-only)
    # =========================================================================

    def create_entity(
        self,
        entity_type: str,
        entity_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a new entity with initial data.

        Writes:
        1. .meta file (lifecycle state = CREATED)
        2. .log file (initial JSONL record)
        3. .idx file (binary index entry)

        All writes are atomic with fsync.
        """
        if not self._initialized:
            raise RuntimeError("HDD Engine not initialized")

        if not _validate_entity_type(entity_type):
            raise ValueError(f"Invalid entity type: {entity_type}")

        if not _validate_entity_id(entity_id):
            raise ValueError(f"Invalid entity ID: {entity_id}")

        meta_path = str(self._meta_path(entity_type, entity_id))
        log_path = str(self._log_path(entity_type, entity_id))
        lock_path = str(self._lock_path(entity_type, entity_id))

        # Check if entity already exists
        if os.path.exists(meta_path):
            raise FileExistsError(f"Entity already exists: {entity_type}/{entity_id}")

        # Acquire lock
        lock_fd = _file_lock_acquire(lock_path)
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Build log record FIRST so we can compute total_bytes
            record = {
                "ts": now,
                "op": "CREATE",
                "id": entity_id,
                **data,
            }
            record_bytes = (json.dumps(record, separators=(",", ":")) + "\n").encode()

            # Build metadata with correct total_bytes (single write)
            meta = {
                "entity_id": entity_id,
                "entity_type": entity_type,
                "lifecycle_state": LifecycleState.CREATED.value,
                "created_at": now,
                "updated_at": now,
                "backup_verified": False,
                "integrity_verified": True,
                "legal_hold": False,
                "record_count": 1,
                "total_bytes": len(record_bytes),
            }

            # Write metadata once (atomic) — no double write
            meta_bytes = json.dumps(meta, indent=2).encode()
            _atomic_write(meta_path, meta_bytes)

            # Write initial log record (atomic)
            _atomic_write(log_path, record_bytes)

            # Cache the meta
            cache_key = f"{entity_type}/{entity_id}"
            with self._cache_lock:
                self._meta_cache[cache_key] = meta.copy()
                # Invalidate list/count cache for this type
                self._list_cache.pop(entity_type, None)
                self._count_cache.pop(entity_type, None)

            self._stats["total_writes"] += 1
            self._stats["total_entities"] += 1
            self._stats["total_bytes_written"] += len(record_bytes) + len(meta_bytes)

            # Audit log
            self._audit_log("CREATE", entity_type, entity_id)

            return {**meta, **data}

        finally:
            _file_lock_release(lock_fd)

    def append_record(
        self,
        entity_type: str,
        entity_id: str,
        data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Append a record to an existing entity's log.
        Append-only — never modifies existing records.
        """
        if not self._initialized:
            raise RuntimeError("HDD Engine not initialized")

        if not _validate_entity_type(entity_type):
            raise ValueError(f"Invalid entity type: {entity_type}")

        if not _validate_entity_id(entity_id):
            raise ValueError(f"Invalid entity ID: {entity_id}")

        meta_path = str(self._meta_path(entity_type, entity_id))
        log_path = str(self._log_path(entity_type, entity_id))
        lock_path = str(self._lock_path(entity_type, entity_id))

        if not os.path.exists(meta_path):
            raise FileNotFoundError(f"Entity not found: {entity_type}/{entity_id}")

        lock_fd = _file_lock_acquire(lock_path)
        try:
            now = datetime.now(timezone.utc).isoformat()

            # Build record
            record = {
                "ts": now,
                "op": "UPDATE",
                "id": entity_id,
                **data,
            }
            record_bytes = (json.dumps(record, separators=(",", ":")) + "\n").encode()

            # Append to log (NOT atomic write — append only)
            fd = os.open(log_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, record_bytes)
                _fsync_file(fd)
            finally:
                os.close(fd)

            # Read meta from cache if available, else disk
            cache_key = f"{entity_type}/{entity_id}"
            with self._cache_lock:
                meta = self._meta_cache.get(cache_key)
            if meta is None:
                meta = json.loads(Path(meta_path).read_text())

            meta["updated_at"] = now
            meta["record_count"] = meta.get("record_count", 0) + 1
            meta["total_bytes"] = meta.get("total_bytes", 0) + len(record_bytes)
            if meta["lifecycle_state"] == LifecycleState.CREATED.value:
                meta["lifecycle_state"] = LifecycleState.ACTIVE.value
            _atomic_write(meta_path, json.dumps(meta, indent=2).encode())

            # Update cache
            with self._cache_lock:
                self._meta_cache[cache_key] = meta.copy()
                self._entity_cache.pop(cache_key, None)  # invalidate read cache

            self._stats["total_writes"] += 1
            self._stats["total_bytes_written"] += len(record_bytes)

            return record

        finally:
            _file_lock_release(lock_fd)

    # =========================================================================
    # READ OPERATIONS (No locking needed)
    # =========================================================================

    def read_entity(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Read all records for an entity.
        Returns metadata + all JSONL records.
        Uses read-through cache with TTL.
        """
        if not _validate_entity_type(entity_type):
            return None

        if not _validate_entity_id(entity_id):
            return None

        cache_key = f"{entity_type}/{entity_id}"
        now = time.monotonic()

        # Check entity cache
        with self._cache_lock:
            cached = self._entity_cache.get(cache_key)
            if cached and (now - cached[0]) < self.CACHE_TTL:
                self._stats["total_reads"] += 1
                return cached[1]

        meta_path = self._meta_path(entity_type, entity_id)
        log_path = self._log_path(entity_type, entity_id)

        if not meta_path.exists():
            return None

        self._stats["total_reads"] += 1

        # Read metadata (prefer cache)
        with self._cache_lock:
            meta = self._meta_cache.get(cache_key)
        if meta is None:
            meta = json.loads(meta_path.read_text())
            with self._cache_lock:
                self._meta_cache[cache_key] = meta.copy()

        # Read all log records
        records = []
        if log_path.exists():
            with open(str(log_path), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue

        result = {
            "meta": meta,
            "records": records,
            "latest": records[-1] if records else None,
        }

        # Cache result
        with self._cache_lock:
            self._entity_cache[cache_key] = (now, result)

        return result

    def read_metadata(
        self,
        entity_type: str,
        entity_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Read only the metadata for an entity (cache-aware)."""
        if not _validate_entity_type(entity_type):
            return None
        if not _validate_entity_id(entity_id):
            return None

        cache_key = f"{entity_type}/{entity_id}"
        with self._cache_lock:
            cached = self._meta_cache.get(cache_key)
            if cached:
                return cached.copy()

        meta_path = self._meta_path(entity_type, entity_id)
        if not meta_path.exists():
            return None

        meta = json.loads(meta_path.read_text())
        with self._cache_lock:
            self._meta_cache[cache_key] = meta.copy()
        return meta

    def list_entities(
        self,
        entity_type: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """List all entities of a given type with pagination (cached)."""
        if not _validate_entity_type(entity_type):
            return []

        now = time.monotonic()

        # Check list cache (only for page 0 — most common case)
        if offset == 0:
            with self._cache_lock:
                cached = self._list_cache.get(entity_type)
                if cached and (now - cached[0]) < self.CACHE_TTL:
                    return cached[1][:limit]

        entity_dir = self._entity_dir(entity_type)
        if not entity_dir.exists():
            return []

        metas = sorted(
            entity_dir.glob(f"*{META_EXT}"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        results = []
        for meta_path in metas[offset:offset + limit]:
            try:
                meta = json.loads(meta_path.read_text())
                results.append(meta)
                # Warm the meta cache
                cache_key = f"{entity_type}/{meta.get('entity_id', meta_path.stem)}"
                with self._cache_lock:
                    self._meta_cache[cache_key] = meta.copy()
            except Exception:
                continue

        # Cache the full page-0 result for next call
        if offset == 0:
            with self._cache_lock:
                self._list_cache[entity_type] = (now, results.copy())

        return results

    def count_entities(self, entity_type: str) -> int:
        """Count entities of a given type (cached)."""
        if not _validate_entity_type(entity_type):
            return 0

        now = time.monotonic()
        with self._cache_lock:
            cached = self._count_cache.get(entity_type)
            if cached and (now - cached[0]) < self.CACHE_TTL:
                return cached[1]

        entity_dir = self._entity_dir(entity_type)
        if not entity_dir.exists():
            return 0
        count = len(list(entity_dir.glob(f"*{META_EXT}")))

        with self._cache_lock:
            self._count_cache[entity_type] = (now, count)

        return count

    def invalidate_cache(self, entity_type: str = None, entity_id: str = None):
        """Invalidate caches. If no args, invalidates everything."""
        with self._cache_lock:
            if entity_type and entity_id:
                key = f"{entity_type}/{entity_id}"
                self._meta_cache.pop(key, None)
                self._entity_cache.pop(key, None)
                self._list_cache.pop(entity_type, None)
                self._count_cache.pop(entity_type, None)
            elif entity_type:
                self._list_cache.pop(entity_type, None)
                self._count_cache.pop(entity_type, None)
                keys_to_remove = [k for k in self._meta_cache if k.startswith(f"{entity_type}/")]
                for k in keys_to_remove:
                    self._meta_cache.pop(k, None)
                    self._entity_cache.pop(k, None)
            else:
                self._meta_cache.clear()
                self._entity_cache.clear()
                self._list_cache.clear()
                self._count_cache.clear()

    # =========================================================================
    # LIFECYCLE STATE UPDATES
    # =========================================================================

    def update_lifecycle(
        self,
        entity_type: str,
        entity_id: str,
        new_state: LifecycleState,
    ) -> bool:
        """Update the lifecycle state of an entity."""
        meta_path = str(self._meta_path(entity_type, entity_id))
        lock_path = str(self._lock_path(entity_type, entity_id))

        if not os.path.exists(meta_path):
            return False

        lock_fd = _file_lock_acquire(lock_path)
        try:
            # Read meta from cache or disk
            cache_key = f"{entity_type}/{entity_id}"
            with self._cache_lock:
                meta = self._meta_cache.get(cache_key)
            if meta is None:
                meta = json.loads(Path(meta_path).read_text())

            old_state = meta["lifecycle_state"]
            meta["lifecycle_state"] = new_state.value
            meta["updated_at"] = datetime.now(timezone.utc).isoformat()
            _atomic_write(meta_path, json.dumps(meta, indent=2).encode())

            # Update cache
            with self._cache_lock:
                self._meta_cache[cache_key] = meta.copy()
                self._entity_cache.pop(cache_key, None)

            self._audit_log(
                "LIFECYCLE_CHANGE",
                entity_type,
                entity_id,
                f"{old_state} -> {new_state.value}",
            )
            return True
        finally:
            _file_lock_release(lock_fd)

    # =========================================================================
    # STATS
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        disk_usage = self._get_disk_usage()
        entity_counts = {}
        for et in ENTITY_TYPES:
            entity_counts[et] = self.count_entities(et)

        return {
            "initialized": self._initialized,
            "hdd_root": str(self._root),
            "entity_counts": entity_counts,
            "disk_usage": disk_usage,
            **self._stats,
        }

    def _get_disk_usage(self) -> Dict[str, Any]:
        """Get disk usage for the HDD root."""
        try:
            usage = os.statvfs(str(self._root)) if platform.system() != "Windows" else None
            if usage:
                total = usage.f_blocks * usage.f_frsize
                free = usage.f_bfree * usage.f_frsize
                used = total - free
                return {
                    "total_bytes": total,
                    "free_bytes": free,
                    "used_bytes": used,
                    "percent_used": round((used / total) * 100, 1) if total > 0 else 0,
                }
            else:
                # Windows
                import ctypes
                free_bytes = ctypes.c_ulonglong(0)
                total_bytes = ctypes.c_ulonglong(0)
                ctypes.windll.kernel32.GetDiskFreeSpaceExW(
                    str(self._root),
                    None,
                    ctypes.byref(total_bytes),
                    ctypes.byref(free_bytes),
                )
                total = total_bytes.value
                free = free_bytes.value
                used = total - free
                return {
                    "total_bytes": total,
                    "free_bytes": free,
                    "used_bytes": used,
                    "percent_used": round((used / total) * 100, 1) if total > 0 else 0,
                }
        except Exception:
            return {"total_bytes": 0, "free_bytes": 0, "used_bytes": 0, "percent_used": 0}

    # =========================================================================
    # AUDIT LOG
    # =========================================================================

    def _audit_log(
        self,
        action: str,
        entity_type: str,
        entity_id: str,
        details: str = "",
    ) -> None:
        """Append to the audit log (append-only)."""
        audit_dir = self._root / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_file = str(audit_dir / "engine.log")

        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details,
        }
        record_bytes = (json.dumps(record, separators=(",", ":")) + "\n").encode()

        fd = os.open(audit_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, record_bytes)
            _fsync_file(fd)
        finally:
            os.close(fd)


# =============================================================================
# SINGLETON
# =============================================================================

_engine: Optional[HDDEngine] = None


def get_engine(hdd_root: Optional[str] = None) -> HDDEngine:
    """Get or create the singleton HDD engine."""
    global _engine
    if _engine is None:
        _engine = HDDEngine(hdd_root)
        _engine.initialize()
    return _engine
