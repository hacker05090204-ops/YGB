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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("ygb.sync.recovery")

SYNC_ROOT = Path(os.getenv("YGB_SYNC_ROOT", "D:\\"))
SYNC_META = SYNC_ROOT / "ygb_sync"
DEVICE_ID = os.getenv("YGB_DEVICE_ID", "laptop_a")


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
    return stats


# ── Recovery from Google Drive ────────────────────────────────────────

def recover_from_cloud() -> dict:
    """
    Full disaster recovery from Google Drive.
    Downloads manifest → decrypts → downloads files by priority.
    """
    from backend.sync.gdrive_backup import (
        _decrypt_data, _decompress_data,
        GDRIVE_ENABLED, STAGING_DIR,
    )

    if not GDRIVE_ENABLED:
        logger.error("Google Drive not enabled — cannot do cloud recovery")
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
            return {"recovered": 0, "failed": 0, "error": "rclone failed"}

        # Find and decrypt manifest
        manifest_enc = dl_dir / "manifest.json.enc"
        if manifest_enc.exists():
            data = manifest_enc.read_bytes()
            decrypted = _decrypt_data(data)
            decompressed = _decompress_data(decrypted)
            manifest = json.loads(decompressed.decode("utf-8"))
            logger.info(
                "Manifest recovered: %d files",
                len(manifest.get("files", {})),
            )
        else:
            logger.error("No manifest found in cloud backup")
            return {"recovered": 0, "failed": 0, "error": "No manifest"}

        # Decrypt and restore each file
        stats = {"recovered": 0, "failed": 0}
        for enc_file in dl_dir.iterdir():
            if enc_file.suffix != ".enc" or enc_file.name == "manifest.json.enc":
                continue
            try:
                data = enc_file.read_bytes()
                decrypted = _decrypt_data(data)
                decompressed = _decompress_data(decrypted)

                # Reconstruct original path from filename
                original_name = enc_file.stem.replace(".enc", "").replace("__", "/")
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
        return stats

    except FileNotFoundError:
        logger.error("rclone not installed — cannot do cloud recovery")
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
