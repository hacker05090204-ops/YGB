"""
Secure Wipe Engine
==================

Forensic-resistant file deletion for YGB HDD storage.
NO simple os.unlink() allowed.

Procedure:
1) Overwrite with random bytes → fsync
2) Overwrite with zeros → fsync
3) os.unlink()
4) fsync parent directory

Every wipe is logged with proof to /audit/wipe_log.log
"""

import os
import hashlib
import json
import logging
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("secure_wiper")


def _fsync_file(fd: int) -> None:
    """fsync a file descriptor."""
    os.fsync(fd)


def _fsync_directory(dir_path: str) -> None:
    """fsync a directory (Linux) or FlushFileBuffers (Windows)."""
    if platform.system() != "Windows":
        fd = os.open(dir_path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    else:
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            GENERIC_WRITE = 0x40000000
            OPEN_EXISTING = 3
            FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
            handle = kernel32.CreateFileW(
                dir_path, GENERIC_WRITE, 0, None,
                OPEN_EXISTING, FILE_FLAG_BACKUP_SEMANTICS, None,
            )
            if handle != -1:
                kernel32.FlushFileBuffers(handle)
                kernel32.CloseHandle(handle)
        except Exception:
            pass


def secure_wipe(file_path: str, audit_log_dir: str) -> Dict[str, Any]:
    """
    Securely wipe a file with forensic-resistant overwrite.

    Steps:
        1. Read file size
        2. Hash original content (proof of existence)
        3. Overwrite with random bytes → fsync
        4. Hash after random overwrite (proof of overwrite)
        5. Overwrite with zeros → fsync
        6. Hash after zero overwrite (proof of zeroing)
        7. Unlink file
        8. fsync parent directory

    Returns wipe proof record.
    """
    path = Path(file_path)
    if not path.exists():
        return {
            "status": "SKIPPED",
            "reason": "File does not exist",
            "file": file_path,
        }

    parent_dir = str(path.parent)
    file_size = path.stat().st_size

    # Step 1: Hash original content
    original_hash = hashlib.sha256(path.read_bytes()).hexdigest()

    # Step 2: Overwrite with random bytes
    fd = os.open(file_path, os.O_WRONLY, 0o600)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, os.urandom(file_size))
        _fsync_file(fd)
    finally:
        os.close(fd)

    random_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()

    # Step 3: Overwrite with zeros
    fd = os.open(file_path, os.O_WRONLY, 0o600)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, b"\x00" * file_size)
        _fsync_file(fd)
    finally:
        os.close(fd)

    zero_hash = hashlib.sha256(Path(file_path).read_bytes()).hexdigest()

    # Step 4: Unlink
    os.unlink(file_path)

    # Step 5: fsync parent directory
    _fsync_directory(parent_dir)

    # Build wipe proof
    now = datetime.now(timezone.utc).isoformat()
    wipe_proof = {
        "ts": now,
        "action": "SECURE_WIPE",
        "file": file_path,
        "file_size": file_size,
        "original_hash": original_hash,
        "random_overwrite_hash": random_hash,
        "zero_overwrite_hash": zero_hash,
        "verified": (
            random_hash != original_hash and
            zero_hash != original_hash and
            zero_hash != random_hash
        ),
    }

    # Log wipe proof
    _log_wipe_proof(audit_log_dir, wipe_proof)

    logger.info(
        f"SECURE_WIPE: {file_path} "
        f"({file_size} bytes, verified={wipe_proof['verified']})"
    )

    return wipe_proof


def secure_wipe_entity(
    entity_dir: str,
    entity_id: str,
    audit_log_dir: str,
) -> Dict[str, Any]:
    """
    Securely wipe all files for a single entity.
    Wipes: .log, .idx, .meta, .lock
    """
    extensions = [".log", ".idx", ".meta", ".lock"]
    results = []

    for ext in extensions:
        file_path = os.path.join(entity_dir, f"{entity_id}{ext}")
        if os.path.exists(file_path):
            result = secure_wipe(file_path, audit_log_dir)
            results.append(result)

    all_verified = all(r.get("verified", False) for r in results if r.get("status") != "SKIPPED")

    return {
        "entity_id": entity_id,
        "files_wiped": len(results),
        "all_verified": all_verified,
        "details": results,
    }


def _log_wipe_proof(audit_log_dir: str, proof: Dict[str, Any]) -> None:
    """Append wipe proof to the audit wipe log."""
    os.makedirs(audit_log_dir, exist_ok=True)
    log_file = os.path.join(audit_log_dir, "wipe_log.log")

    record_bytes = (json.dumps(proof, separators=(",", ":")) + "\n").encode()

    fd = os.open(log_file, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, record_bytes)
        _fsync_file(fd)
    finally:
        os.close(fd)


def verify_wipe(file_path: str) -> bool:
    """
    Verify a file has been wiped (should not exist).
    Returns True if file is confirmed gone.
    """
    return not os.path.exists(file_path)
