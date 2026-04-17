"""
YGB Recovery Engine — Parallel chunk download + file restoration.

Recovery modes:
  1. PEER: Download missing files from online peers (parallel chunks)
  2. CLOUD: Download from Google Drive (disaster recovery)
  3. HYBRID: Try peers first, fall back to cloud for gaps

Priority order for recovery:
  CRITICAL → models, DB, checkpoints/best
  HIGH     → reports, config
  MEDIUM   → datasets, training telemetry
  LOW      → videos, logs, screenshots
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config.storage_config import SYNC_ROOT as DEFAULT_SYNC_ROOT

logger = logging.getLogger("ygb.sync.recovery")

SYNC_ROOT = Path(os.getenv("YGB_SYNC_ROOT", str(DEFAULT_SYNC_ROOT)))
SYNC_META = SYNC_ROOT / "ygb_sync"
DEVICE_ID = os.getenv("YGB_DEVICE_ID", "laptop_a")
RECOVERY_LOG_PATH = SYNC_META / "recovery_log.json"
RECOVERY_LOG_ROTATE_AT = max(1, int(os.getenv("YGB_RECOVERY_LOG_ROTATE_AT", "1000")))
RECOVERY_LOG_RETAIN_EVENTS = max(1, int(os.getenv("YGB_RECOVERY_LOG_RETAIN_EVENTS", "500")))
PEER_RECOVERY_NO_PEERS_REASON = "no_online_peers"
PEER_RECOVERY_INCOMPLETE_REASON = "peer_recovery_incomplete"
CLOUD_RECOVERY_UNAVAILABLE_REASON = "cloud_recovery_unavailable"
CLOUD_RECOVERY_FAILED_REASON = "cloud_recovery_failed"
RECOVERY_STATUS_PENDING = "PENDING"
RECOVERY_STATUS_RESOLVED = "RESOLVED"
RECOVERY_STATUS_FAILED = "FAILED"
VALID_RECOVERY_STATUSES = {
    RECOVERY_STATUS_PENDING,
    RECOVERY_STATUS_RESOLVED,
    RECOVERY_STATUS_FAILED,
}


@dataclass
class RecoveryEvent:
    event_id: str
    timestamp: str
    peer_id: str
    reason: str
    status: str = RECOVERY_STATUS_PENDING

    def __post_init__(self) -> None:
        normalized_status = str(self.status).upper()
        if normalized_status not in VALID_RECOVERY_STATUSES:
            raise ValueError(f"Invalid recovery event status: {self.status}")
        self.status = normalized_status

    @property
    def resolved(self) -> bool:
        return self.status == RECOVERY_STATUS_RESOLVED


def _build_recovery_event_id(timestamp: str, peer_id: str, reason: str) -> str:
    return f"{peer_id}:{reason}:{timestamp}"


def _coerce_recovery_event(entry: dict) -> Optional[RecoveryEvent]:
    timestamp = str(entry.get("timestamp", "")).strip()
    peer_id = str(entry.get("peer_id", "")).strip()
    reason = str(entry.get("reason", "")).strip()
    if not timestamp or not peer_id or not reason:
        return None

    raw_status = entry.get("status")
    if isinstance(raw_status, str) and raw_status.strip().upper() in VALID_RECOVERY_STATUSES:
        status = raw_status.strip().upper()
    else:
        resolved_flag = entry.get("resolved")
        if isinstance(resolved_flag, bool):
            status = RECOVERY_STATUS_RESOLVED if resolved_flag else RECOVERY_STATUS_PENDING
        else:
            logger.warning("Skipping recovery log event with invalid status: %s", entry)
            return None

    event_id = str(entry.get("event_id", "")).strip()
    if not event_id:
        event_id = _build_recovery_event_id(timestamp, peer_id, reason)

    try:
        return RecoveryEvent(
            event_id=event_id,
            timestamp=timestamp,
            peer_id=peer_id,
            reason=reason,
            status=status,
        )
    except ValueError as exc:
        logger.warning("Skipping recovery log event: %s", exc)
        return None


def _rotate_recovery_events(events: list[RecoveryEvent]) -> list[RecoveryEvent]:
    if len(events) <= RECOVERY_LOG_ROTATE_AT:
        return events

    active_events = [event for event in events if event.status != RECOVERY_STATUS_RESOLVED]
    resolved_events = [event for event in events if event.status == RECOVERY_STATUS_RESOLVED]
    keep_active = active_events[-RECOVERY_LOG_RETAIN_EVENTS:]
    remaining_slots = max(0, RECOVERY_LOG_RETAIN_EVENTS - len(keep_active))
    keep_resolved = resolved_events[-remaining_slots:] if remaining_slots else []
    rotated = keep_resolved + keep_active
    rotated.sort(key=lambda event: event.timestamp)
    return rotated


def _load_recovery_log() -> list[RecoveryEvent]:
    if not RECOVERY_LOG_PATH.exists():
        return []
    try:
        payload = json.loads(RECOVERY_LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load recovery log: %s", exc)
        return []
    if not isinstance(payload, list):
        return []
    events: list[RecoveryEvent] = []
    for entry in payload:
        if not isinstance(entry, dict):
            continue
        event = _coerce_recovery_event(entry)
        if event is not None:
            events.append(event)
    return events


def _persist_recovery_log(events: list[RecoveryEvent]) -> None:
    SYNC_META.mkdir(parents=True, exist_ok=True)
    events = _rotate_recovery_events(events)
    temp_path = RECOVERY_LOG_PATH.with_suffix(".tmp")
    temp_path.write_text(
        json.dumps([asdict(event) for event in events], indent=2),
        encoding="utf-8",
    )
    os.replace(temp_path, RECOVERY_LOG_PATH)


def _append_recovery_event(
    peer_id: str,
    reason: str,
    *,
    resolved: bool,
    dedupe_open_events: bool = True,
) -> None:
    events = _load_recovery_log()
    status = RECOVERY_STATUS_RESOLVED if resolved else RECOVERY_STATUS_PENDING
    if dedupe_open_events and status == RECOVERY_STATUS_PENDING:
        for event in events:
            if (
                event.peer_id == peer_id
                and event.reason == reason
                and event.status == RECOVERY_STATUS_PENDING
            ):
                return
    timestamp = datetime.now(timezone.utc).isoformat()
    events.append(
        RecoveryEvent(
            event_id=_build_recovery_event_id(timestamp, peer_id, reason),
            timestamp=timestamp,
            peer_id=peer_id,
            reason=reason,
            status=status,
        )
    )
    _persist_recovery_log(events)


def mark_resolved(event_id: str) -> bool:
    events = _load_recovery_log()
    updated = False
    for event in events:
        if event.event_id != event_id:
            continue
        if event.status != RECOVERY_STATUS_RESOLVED:
            event.status = RECOVERY_STATUS_RESOLVED
            updated = True
        break
    if updated:
        _persist_recovery_log(events)
    return updated


def mark_recovery_events_resolved(peer_id: str, reason: Optional[str] = None) -> int:
    events = _load_recovery_log()
    updated = 0
    for event in events:
        if event.status == RECOVERY_STATUS_RESOLVED:
            continue
        if event.peer_id != peer_id:
            continue
        if reason is not None and event.reason != reason:
            continue
        event.status = RECOVERY_STATUS_RESOLVED
        updated += 1
    if updated:
        _persist_recovery_log(events)
    return updated


def get_pending_recovery_events(
    peer_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> list[RecoveryEvent]:
    events = [
        event
        for event in _load_recovery_log()
        if event.status == RECOVERY_STATUS_PENDING
    ]
    if peer_id is not None:
        events = [event for event in events if event.peer_id == peer_id]
    if reason is not None:
        events = [event for event in events if event.reason == reason]
    events.sort(key=lambda event: event.timestamp)
    return events


def get_unresolved_events(
    peer_id: Optional[str] = None,
    reason: Optional[str] = None,
) -> list[RecoveryEvent]:
    return get_pending_recovery_events(peer_id=peer_id, reason=reason)


# ── Priority Classification ──────────────────────────────────────────

PRIORITY_MAP = {
    "CRITICAL": ["models/", "ygb.db", "checkpoints/best"],
    "HIGH": ["ygb_reports/", "phase_reports/", "audit_reports/"],
    "MEDIUM": ["ygb_training/", "datasets/", "telemetry/"],
    "LOW": ["ygb_videos/", "ygb_logs/", "screenshots/"],
}


def classify_priority(path: str) -> str:
    """Classify a file path by recovery priority."""
    for priority, patterns in PRIORITY_MAP.items():
        if any(pat in path for pat in patterns):
            return priority
    return "MEDIUM"


def _sort_by_priority(file_entries: Dict[str, dict]) -> List[Tuple[str, dict]]:
    """Sort files by recovery priority (CRITICAL first)."""
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    items = list(file_entries.items())
    items.sort(key=lambda x: order.get(classify_priority(x[0]), 2))
    return items


# ── Recovery from Peers ───────────────────────────────────────────────

def recover_from_peers(
    target_manifest: dict,
    max_workers: int = 4,
) -> dict:
    """
    Recover missing files by downloading chunks from online peers.

    Args:
        target_manifest: The manifest we want to restore to
        max_workers: Parallel download threads

    Returns: {recovered: int, failed: int, skipped: int, bytes_downloaded: int}
    """
    from backend.sync.peer_transport import discover_online_peers, parallel_download_chunks
    from backend.sync.chunker import has_chunk, store_chunk, reassemble_file

    peers = discover_online_peers()
    if not peers:
        logger.warning("No online peers for recovery — try cloud")
        _append_recovery_event(
            "peer_mesh",
            PEER_RECOVERY_NO_PEERS_REASON,
            resolved=False,
        )
        return {"recovered": 0, "failed": 0, "skipped": 0, "bytes_downloaded": 0}

    target_files = target_manifest.get("files", {})
    sorted_files = _sort_by_priority(target_files)

    stats = {"recovered": 0, "failed": 0, "skipped": 0, "bytes_downloaded": 0}

    for rel_path, entry in sorted_files:
        dest = SYNC_ROOT / rel_path.replace("/", os.sep)
        if dest.exists():
            stats["skipped"] += 1
            continue

        chunks = entry.get("chunks", [])
        if not chunks:
            continue

        # Find which chunks we need
        needed = [ch for ch in chunks if not has_chunk(ch)]
        if needed:
            logger.info(
                "[%s] Recovering %s (%d chunks, %d needed)",
                classify_priority(rel_path), rel_path, len(chunks), len(needed),
            )
            downloaded = parallel_download_chunks(needed, peers, max_workers)
            for ch, data in downloaded.items():
                if store_chunk(ch, data):
                    stats["bytes_downloaded"] += len(data)

        # All chunks available? Reassemble.
        if all(has_chunk(ch) for ch in chunks):
            if reassemble_file(chunks, dest):
                stats["recovered"] += 1
                logger.info("✓ Recovered: %s", rel_path)
            else:
                stats["failed"] += 1
                logger.error("✗ Reassembly failed: %s", rel_path)
        else:
            stats["failed"] += 1
            missing = [ch[:12] for ch in chunks if not has_chunk(ch)]
            logger.error("✗ Missing chunks for %s: %s", rel_path, missing)

    logger.info(
        "Recovery from peers: %d recovered, %d failed, %d skipped, %.1f MB downloaded",
        stats["recovered"], stats["failed"], stats["skipped"],
        stats["bytes_downloaded"] / 1e6,
    )
    if stats["failed"] > 0:
        _append_recovery_event(
            "peer_mesh",
            PEER_RECOVERY_INCOMPLETE_REASON,
            resolved=False,
        )
    else:
        mark_recovery_events_resolved("peer_mesh", PEER_RECOVERY_NO_PEERS_REASON)
        mark_recovery_events_resolved("peer_mesh", PEER_RECOVERY_INCOMPLETE_REASON)
    return stats


# ── Recovery from Google Drive ────────────────────────────────────────

def recover_from_cloud() -> dict:
    """
    Full disaster recovery from Google Drive.
    Downloads manifest → decrypts → downloads files by priority.
    """
    from backend.sync.gdrive_backup import (
        BackupIntegrityError,
        GDRIVE_ENABLED, STAGING_DIR,
        restore_staged_backup_file,
    )

    if not GDRIVE_ENABLED:
        logger.error("Google Drive not enabled — cannot do cloud recovery")
        _append_recovery_event(
            "gdrive",
            CLOUD_RECOVERY_UNAVAILABLE_REASON,
            resolved=False,
        )
        return {"recovered": 0, "failed": 0, "error": "GDrive not enabled"}

    logger.info("═══ DISASTER RECOVERY FROM CLOUD ═══")
    logger.info("Step 1: Downloading manifest from GDrive...")

    # For now, use rclone to pull
    import subprocess
    try:
        dl_dir = STAGING_DIR / "recovery"
        dl_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [
                "rclone", "copy",
                "ygb-gdrive:YGB_Backups/",
                str(dl_dir),
                "--progress",
                "--transfers", "4",
            ],
            capture_output=True, text=True, timeout=3600,
        )
        if result.returncode != 0:
            logger.error("rclone download failed: %s", result.stderr[:500])
            _append_recovery_event(
                "gdrive",
                CLOUD_RECOVERY_FAILED_REASON,
                resolved=False,
            )
            return {"recovered": 0, "failed": 0, "error": "rclone failed"}

        # Find and decrypt manifest
        manifest_enc = dl_dir / "manifest.json.enc"
        if manifest_enc.exists():
            manifest_bytes, _manifest_meta = restore_staged_backup_file(manifest_enc)
            manifest = json.loads(manifest_bytes.decode("utf-8"))
            logger.info(
                "Manifest recovered: %d files",
                len(manifest.get("files", {})),
            )
        else:
            logger.error("No manifest found in cloud backup")
            _append_recovery_event(
                "gdrive",
                CLOUD_RECOVERY_FAILED_REASON,
                resolved=False,
            )
            return {"recovered": 0, "failed": 0, "error": "No manifest"}

        # Decrypt and restore each file
        stats = {"recovered": 0, "failed": 0}
        for enc_file in dl_dir.iterdir():
            if enc_file.suffix != ".enc" or enc_file.name == "manifest.json.enc":
                continue
            try:
                decompressed, meta = restore_staged_backup_file(enc_file)
                original_name = str(meta.get("original_path", "") or "").replace("\\", "/").lstrip("/")
                if not original_name:
                    raise BackupIntegrityError(
                        f"Backup sidecar missing original_path for {enc_file.name}"
                    )
                dest = SYNC_ROOT / original_name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(decompressed)
                stats["recovered"] += 1
                logger.info("✓ Cloud restored: %s", original_name)
            except Exception as e:
                stats["failed"] += 1
                logger.error("✗ Cloud restore failed for %s: %s", enc_file.name, e)

        logger.info(
            "═══ Cloud recovery done: %d recovered, %d failed ═══",
            stats["recovered"], stats["failed"],
        )
        if stats["failed"] > 0:
            _append_recovery_event(
                "gdrive",
                CLOUD_RECOVERY_FAILED_REASON,
                resolved=False,
            )
        else:
            mark_recovery_events_resolved("gdrive", CLOUD_RECOVERY_UNAVAILABLE_REASON)
            mark_recovery_events_resolved("gdrive", CLOUD_RECOVERY_FAILED_REASON)
        return stats

    except FileNotFoundError:
        logger.error("rclone not installed — cannot do cloud recovery")
        _append_recovery_event(
            "gdrive",
            CLOUD_RECOVERY_UNAVAILABLE_REASON,
            resolved=False,
        )
        return {"recovered": 0, "failed": 0, "error": "rclone not found"}


# ── Hybrid Recovery ───────────────────────────────────────────────────

def full_recovery(source: str = "auto") -> dict:
    """
    Full recovery: try peers first, then cloud for any gaps.

    Args:
        source: 'peers', 'cloud', or 'auto' (try peers → cloud)
    """
    logger.info("═══ FULL RECOVERY MODE [source=%s] ═══", source)

    if source == "cloud":
        return recover_from_cloud()

    # Get target manifest from any peer
    from backend.sync.peer_transport import discover_online_peers, fetch_peer_manifest

    peers = discover_online_peers()
    target_manifest = None

    if peers and source != "cloud":
        for peer in peers:
            m = fetch_peer_manifest(peer["url"])
            if m:
                target_manifest = m
                logger.info("Got target manifest from peer %s", peer["name"])
                break

    if target_manifest:
        stats = recover_from_peers(target_manifest)
        if stats["failed"] > 0 and source == "auto":
            logger.info("Falling back to cloud for %d failed files", stats["failed"])
            cloud_stats = recover_from_cloud()
            stats["recovered"] += cloud_stats.get("recovered", 0)
            stats["cloud_fallback"] = True
        return stats
    elif source == "auto" or source == "cloud":
        logger.info("No peers available — recovering from cloud")
        return recover_from_cloud()
    else:
        logger.error("No peers online and source='peers' — cannot recover")
        return {"recovered": 0, "failed": 0, "error": "No peers online"}
