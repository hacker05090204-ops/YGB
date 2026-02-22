"""
data_sync_queue.py — Offline-Tolerant Data Sync Queue (Phase 4)

If target drive offline:
  1. Queue updates locally
  2. On reconnect: validate version, push, verify checksum
  3. No overwrite without version match
"""

import hashlib
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

QUEUE_DIR = os.path.join('secure_data', 'sync_queue')


@dataclass
class SyncEntry:
    """A queued sync entry."""
    entry_id: str
    source_path: str
    target_path: str
    version: int
    checksum: str
    queued_at: str
    synced: bool = False
    synced_at: str = ""


@dataclass
class SyncQueue:
    """Queue of pending sync operations."""
    entries: List[dict] = field(default_factory=list)
    last_sync: str = ""


def compute_file_checksum(path: str) -> str:
    """SHA-256 of a file."""
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def is_drive_online(path: str) -> bool:
    """Check if a target path is accessible."""
    try:
        return os.path.exists(os.path.dirname(path) or path)
    except Exception:
        return False


def queue_update(
    source_path: str,
    target_path: str,
    version: int,
    queue_dir: str = QUEUE_DIR,
) -> SyncEntry:
    """Queue a file for sync when target is offline.

    Args:
        source_path: Local file to sync.
        target_path: Target destination.
        version: Version number for conflict detection.
        queue_dir: Queue directory.

    Returns:
        SyncEntry.
    """
    os.makedirs(queue_dir, exist_ok=True)

    checksum = compute_file_checksum(source_path)
    entry = SyncEntry(
        entry_id=f"sync_{int(time.time())}_{version}",
        source_path=source_path,
        target_path=target_path,
        version=version,
        checksum=checksum,
        queued_at=datetime.now().isoformat(),
    )

    # Save entry metadata
    meta_path = os.path.join(queue_dir, f"{entry.entry_id}.json")
    with open(meta_path, 'w') as f:
        json.dump(asdict(entry), f, indent=2)

    logger.info(
        f"[SYNC] Queued: {source_path} → {target_path} "
        f"v{version} checksum={checksum[:16]}..."
    )
    return entry


def get_pending_entries(queue_dir: str = QUEUE_DIR) -> List[SyncEntry]:
    """Get all pending (unsynced) entries."""
    if not os.path.exists(queue_dir):
        return []

    entries = []
    for fname in sorted(os.listdir(queue_dir)):
        if not fname.endswith('.json'):
            continue
        try:
            with open(os.path.join(queue_dir, fname), 'r') as f:
                data = json.load(f)
            entry = SyncEntry(**data)
            if not entry.synced:
                entries.append(entry)
        except Exception:
            continue

    return entries


def sync_entry(
    entry: SyncEntry,
    queue_dir: str = QUEUE_DIR,
) -> Tuple[bool, str]:
    """Sync a single entry to its target.

    Validates:
      1. Target is accessible
      2. If target exists, check version (no overwrite without match)
      3. Copy file
      4. Verify checksum

    Returns:
        (success, reason)
    """
    # Check target accessible
    target_dir = os.path.dirname(entry.target_path)
    if not is_drive_online(target_dir):
        return False, f"Target offline: {target_dir}"

    # Check source still exists
    if not os.path.exists(entry.source_path):
        return False, f"Source missing: {entry.source_path}"

    # Version check: if target exists, verify version in metadata
    if os.path.exists(entry.target_path):
        meta = entry.target_path + ".version"
        if os.path.exists(meta):
            try:
                with open(meta, 'r') as f:
                    existing_ver = int(f.read().strip())
                if existing_ver >= entry.version:
                    return False, (
                        f"Version conflict: target v{existing_ver} "
                        f">= source v{entry.version}"
                    )
            except Exception:
                pass

    # Copy
    os.makedirs(target_dir, exist_ok=True)
    shutil.copy2(entry.source_path, entry.target_path)

    # Verify checksum
    target_checksum = compute_file_checksum(entry.target_path)
    if target_checksum != entry.checksum:
        os.remove(entry.target_path)
        return False, (
            f"Checksum mismatch: {target_checksum[:16]} "
            f"!= {entry.checksum[:16]}"
        )

    # Write version marker
    with open(entry.target_path + ".version", 'w') as f:
        f.write(str(entry.version))

    # Mark synced
    entry.synced = True
    entry.synced_at = datetime.now().isoformat()

    # Update queue metadata
    meta_path = os.path.join(queue_dir, f"{entry.entry_id}.json")
    if os.path.exists(meta_path):
        with open(meta_path, 'w') as f:
            json.dump(asdict(entry), f, indent=2)

    logger.info(
        f"[SYNC] Synced: {entry.source_path} → {entry.target_path} "
        f"v{entry.version}"
    )
    return True, "Synced successfully"


def sync_all_pending(queue_dir: str = QUEUE_DIR) -> dict:
    """Sync all pending entries.

    Returns:
        {synced: int, failed: int, errors: list}
    """
    entries = get_pending_entries(queue_dir)
    synced = 0
    failed = 0
    errors = []

    for entry in entries:
        ok, reason = sync_entry(entry, queue_dir)
        if ok:
            synced += 1
        else:
            failed += 1
            errors.append(f"{entry.entry_id}: {reason}")

    logger.info(f"[SYNC] Batch: {synced} synced, {failed} failed")
    return {'synced': synced, 'failed': failed, 'errors': errors}


def clear_synced_entries(queue_dir: str = QUEUE_DIR) -> int:
    """Remove synced entries from queue. Returns count removed."""
    if not os.path.exists(queue_dir):
        return 0

    removed = 0
    for fname in os.listdir(queue_dir):
        if not fname.endswith('.json'):
            continue
        path = os.path.join(queue_dir, fname)
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            if data.get('synced', False):
                os.remove(path)
                removed += 1
        except Exception:
            continue

    logger.info(f"[SYNC] Cleared {removed} synced entries")
    return removed
