"""
YGB Manifest Manager — File tracking with xxhash, vector clocks, and chunk indexing.

Each device maintains a local manifest.json that records:
  - Every synced file's path, hash, size, mtime, and chunk hashes
  - A vector clock for causality tracking across devices
  - Device identity and last-sync timestamp

Manifests are tiny (~100 KB) and synced first before any chunk transfers.
"""

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

try:
    import xxhash
    _HAVE_XXHASH = True
except ImportError:
    import hashlib
    _HAVE_XXHASH = False

logger = logging.getLogger("ygb.sync.manifest")

DEVICE_ID = os.getenv("YGB_DEVICE_ID", "laptop_a")


# ── Data Structures ───────────────────────────────────────────────────

@dataclass
class FileEntry:
    """A single file tracked in the manifest."""
    path: str              # Relative to SYNC_ROOT (forward slashes)
    hash: str              # xxh3_128 hex digest
    size: int              # Bytes
    mtime: float           # Unix timestamp
    chunks: List[str] = field(default_factory=list)   # Chunk hashes
    device_id: str = ""    # Device that last modified
    clock: int = 0         # Logical clock at last modification

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "FileEntry":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SyncManifest:
    """Full sync manifest for one device."""
    device_id: str = DEVICE_ID
    vector_clock: Dict[str, int] = field(default_factory=dict)
    files: Dict[str, dict] = field(default_factory=dict)
    last_sync: str = ""
    version: int = 1

    def bump_clock(self):
        """Increment this device's logical clock."""
        self.vector_clock[self.device_id] = self.vector_clock.get(self.device_id, 0) + 1
        self.last_sync = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    def file_count(self) -> int:
        return len(self.files)

    def total_bytes(self) -> int:
        return sum(f.get("size", 0) for f in self.files.values())


# ── Hash Functions ────────────────────────────────────────────────────

def hash_file(path: Path) -> str:
    """Fast xxh3_128 hash of file contents. Falls back to SHA-256 if xxhash unavailable."""
    if _HAVE_XXHASH:
        h = xxhash.xxh3_128()
    else:
        h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                block = f.read(1 << 20)  # 1 MB blocks
                if not block:
                    break
                h.update(block)
        return h.hexdigest()
    except (OSError, PermissionError) as e:
        logger.warning("hash_file failed for %s: %s", path, e)
        return ""


def hash_bytes(data: bytes) -> str:
    """Hash raw bytes (for chunks)."""
    if _HAVE_XXHASH:
        return xxhash.xxh3_128(data).hexdigest()
    return hashlib.sha256(data).hexdigest()


# ── Manifest I/O ──────────────────────────────────────────────────────

def load_manifest(path: Path) -> SyncManifest:
    """Load manifest from disk. Returns empty manifest if missing/corrupt."""
    if not path.exists():
        logger.info("No manifest at %s — starting fresh", path)
        return SyncManifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        m = SyncManifest()
        m.device_id = data.get("device_id", DEVICE_ID)
        m.vector_clock = data.get("vector_clock", {})
        m.files = data.get("files", {})
        m.last_sync = data.get("last_sync", "")
        m.version = data.get("version", 1)
        logger.info("Loaded manifest: %d files, clock=%s", m.file_count(), m.vector_clock)
        return m
    except Exception:
        logger.exception("Corrupt manifest at %s — starting fresh", path)
        return SyncManifest()


def save_manifest(manifest: SyncManifest, path: Path):
    """Atomically save manifest (write tmp → rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    payload = {
        "device_id": manifest.device_id,
        "vector_clock": manifest.vector_clock,
        "files": manifest.files,
        "last_sync": manifest.last_sync,
        "version": manifest.version,
    }
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    logger.info("Saved manifest: %d files, %.1f MB",
                manifest.file_count(), manifest.total_bytes() / 1e6)


# ── Diff Engine ───────────────────────────────────────────────────────

def diff_manifests(
    current: Dict[str, dict],
    previous: Dict[str, dict],
) -> Dict[str, Dict[str, dict]]:
    """
    Compute delta between two file dictionaries.
    Returns: {added: {path: entry}, modified: {path: entry}, deleted: {path: entry}}
    """
    added = {k: v for k, v in current.items() if k not in previous}
    deleted = {k: v for k, v in previous.items() if k not in current}
    modified = {
        k: v for k, v in current.items()
        if k in previous and v.get("hash") != previous[k].get("hash")
    }
    return {"added": added, "modified": modified, "deleted": deleted}


def changes_count(diff: Dict[str, Dict[str, dict]]) -> int:
    """Total number of changes in a diff."""
    return len(diff.get("added", {})) + len(diff.get("modified", {})) + len(diff.get("deleted", {}))


# ── Conflict Resolution ──────────────────────────────────────────────

def resolve_conflict(
    local_entry: dict,
    remote_entry: dict,
    conflict_dir: Path,
    sync_root: Path,
) -> dict:
    """
    Last-Writer-Wins conflict resolution.

    - Compare clocks (vector clock value for the owning device).
    - Tie-break on mtime.
    - Archive the loser in conflict_dir with 7-day TTL.
    - Returns the winner entry.
    """
    local_clock = local_entry.get("clock", 0)
    remote_clock = remote_entry.get("clock", 0)

    if local_clock > remote_clock:
        winner, loser = local_entry, remote_entry
    elif remote_clock > local_clock:
        winner, loser = remote_entry, local_entry
    else:
        # Tie — use mtime
        if local_entry.get("mtime", 0) >= remote_entry.get("mtime", 0):
            winner, loser = local_entry, remote_entry
        else:
            winner, loser = remote_entry, local_entry

    # Archive loser
    loser_path = loser.get("path", "unknown")
    ts = time.strftime("%Y%m%d_%H%M%S")
    archive_name = f"{Path(loser_path).stem}__CONFLICT_{ts}{Path(loser_path).suffix}"
    archive_dest = conflict_dir / archive_name

    src = sync_root / loser_path.replace("/", os.sep)
    if src.exists():
        conflict_dir.mkdir(parents=True, exist_ok=True)
        try:
            import shutil
            shutil.copy2(str(src), str(archive_dest))
            logger.warning(
                "CONFLICT: %s — winner=%s (clock=%d), loser archived as %s",
                loser_path, winner.get("device_id", "?"),
                winner.get("clock", 0), archive_name,
            )
        except OSError as e:
            logger.error("Failed to archive conflict file %s: %s", loser_path, e)

    return winner
