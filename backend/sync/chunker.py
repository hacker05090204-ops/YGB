"""
YGB Chunk Engine — Content-addressed chunking for parallel transfers.

Files > CHUNK_SIZE are split into fixed-size chunks, each stored by its
xxh3_128 hash.  This gives automatic deduplication across files and devices.

Chunks are stored in the SSD-backed sync cache as {hash}.chunk.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

from backend.sync.manifest import hash_bytes
from config.storage_config import SYNC_ROOT as DEFAULT_SYNC_ROOT

logger = logging.getLogger("ygb.sync.chunker")

CHUNK_SIZE = int(os.getenv("YGB_CHUNK_SIZE_MB", "64")) * 1024 * 1024  # 64 MB default
SYNC_ROOT = Path(os.getenv("YGB_SYNC_ROOT", str(DEFAULT_SYNC_ROOT)))
CHUNK_CACHE = SYNC_ROOT / "ygb_sync" / "chunk_cache"


def _ensure_cache():
    CHUNK_CACHE.mkdir(parents=True, exist_ok=True)


def chunk_file(path: Path) -> List[str]:
    """
    Split a file into CHUNK_SIZE pieces.

    Returns: list of chunk hashes (content-addressed).
    Each chunk is cached in CHUNK_CACHE/{hash}.chunk
    """
    _ensure_cache()
    chunks: List[str] = []
    try:
        with open(path, "rb") as f:
            while True:
                data = f.read(CHUNK_SIZE)
                if not data:
                    break
                chunk_hash = hash_bytes(data)
                chunk_path = CHUNK_CACHE / f"{chunk_hash}.chunk"
                if not chunk_path.exists():
                    # Atomic write
                    tmp = chunk_path.with_suffix(".tmp")
                    tmp.write_bytes(data)
                    tmp.replace(chunk_path)
                chunks.append(chunk_hash)
    except (OSError, PermissionError) as e:
        logger.error("chunk_file failed for %s: %s", path, e)
    return chunks


def reassemble_file(chunk_hashes: List[str], dest_path: Path) -> bool:
    """
    Reassemble a file from its chunk hashes.

    Args:
        chunk_hashes: Ordered list of chunk hashes
        dest_path: Where to write the reassembled file

    Returns: True if successful, False if any chunk is missing/corrupt
    """
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest_path.with_suffix(dest_path.suffix + ".assembling")

    try:
        with open(tmp, "wb") as out:
            for ch in chunk_hashes:
                chunk_path = CHUNK_CACHE / f"{ch}.chunk"
                if not chunk_path.exists():
                    logger.error("Missing chunk %s for %s", ch, dest_path)
                    tmp.unlink(missing_ok=True)
                    return False
                data = chunk_path.read_bytes()
                # Verify integrity
                actual = hash_bytes(data)
                if actual != ch:
                    logger.error("Chunk integrity fail: expected %s got %s", ch, actual)
                    tmp.unlink(missing_ok=True)
                    return False
                out.write(data)
        tmp.replace(dest_path)
        logger.info("Reassembled %s from %d chunks", dest_path.name, len(chunk_hashes))
        return True
    except OSError as e:
        logger.error("reassemble_file failed for %s: %s", dest_path, e)
        tmp.unlink(missing_ok=True)
        return False


def get_chunk(chunk_hash: str) -> Optional[bytes]:
    """Retrieve a chunk by hash from local cache."""
    chunk_path = CHUNK_CACHE / f"{chunk_hash}.chunk"
    if chunk_path.exists():
        return chunk_path.read_bytes()
    return None


def has_chunk(chunk_hash: str) -> bool:
    """Check if a chunk exists in local cache."""
    return (CHUNK_CACHE / f"{chunk_hash}.chunk").exists()


def store_chunk(chunk_hash: str, data: bytes) -> bool:
    """Store a chunk received from a peer. Verifies integrity."""
    actual = hash_bytes(data)
    if actual != chunk_hash:
        logger.error("store_chunk integrity fail: expected %s got %s", chunk_hash, actual)
        return False
    _ensure_cache()
    chunk_path = CHUNK_CACHE / f"{chunk_hash}.chunk"
    if not chunk_path.exists():
        tmp = chunk_path.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(chunk_path)
    return True


def cleanup_orphan_chunks(manifest_files: dict, max_age_hours: int = 48):
    """
    Remove chunks not referenced by any file in the manifest.
    Only removes chunks older than max_age_hours to avoid race conditions.
    """
    import time
    if not CHUNK_CACHE.exists():
        return 0

    referenced: set = set()
    for entry in manifest_files.values():
        referenced.update(entry.get("chunks", []))

    cutoff = time.time() - (max_age_hours * 3600)
    removed = 0
    for chunk_path in CHUNK_CACHE.glob("*.chunk"):
        chunk_hash = chunk_path.stem
        if chunk_hash not in referenced:
            try:
                if chunk_path.stat().st_mtime < cutoff:
                    chunk_path.unlink()
                    removed += 1
            except OSError as exc:
                logger.debug("Failed to remove orphan chunk %s: %s", chunk_path, exc)
    if removed:
        logger.info("Cleaned %d orphan chunks", removed)
    return removed
