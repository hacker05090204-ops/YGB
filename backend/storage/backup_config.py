"""
Backup Configuration — Storage Strategy

Backup targets (priority order):
  1. Local HDD/C drive structured store (always available)
  2. Peer replication (4-laptop sync/quorum — framework)
  3. Google Drive cloud backup (when credentials present)

Gmail = notification channel ONLY; never used as backup store.

Compression policy:
  - zstd (default) with integrity hash
  - Chunked archives + manifest
  - Restore verification test
"""

import os
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

logger = logging.getLogger("ygb.backup")


# =============================================================================
# BACKUP TARGET STATUS
# =============================================================================

class BackupTargetStatus(Enum):
    ACTIVE = "ACTIVE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    ERROR = "ERROR"
    DEGRADED = "DEGRADED"


class CompressionAlgorithm(Enum):
    ZSTD = "zstd"
    GZIP = "gzip"
    NONE = "none"


@dataclass
class BackupManifest:
    """Manifest for a backup archive."""
    manifest_id: str
    created_at: str
    chunks: List[Dict[str, str]]     # [{"chunk_id": ..., "path": ..., "sha256": ...}]
    total_bytes: int
    compression: str
    source_path: str
    integrity_hash: str              # SHA-256 of all chunk hashes concatenated


@dataclass
class BackupTargetInfo:
    """Status of a single backup target."""
    name: str
    status: BackupTargetStatus
    reason: str
    last_backup_at: Optional[str]
    total_backups: int


# =============================================================================
# LOCAL HDD BACKUP
# =============================================================================

_LOCAL_BACKUP_ROOT = Path(os.environ.get(
    "YGB_BACKUP_ROOT",
    str(Path.home() / "YGB_Backups")
))


def get_local_backup_status() -> BackupTargetInfo:
    """Check local HDD backup target status."""
    try:
        if _LOCAL_BACKUP_ROOT.exists():
            backup_count = len(list(_LOCAL_BACKUP_ROOT.glob("*.manifest.json")))
            return BackupTargetInfo(
                name="local_hdd",
                status=BackupTargetStatus.ACTIVE,
                reason=f"Backup root: {_LOCAL_BACKUP_ROOT}",
                last_backup_at=None,
                total_backups=backup_count,
            )
        else:
            return BackupTargetInfo(
                name="local_hdd",
                status=BackupTargetStatus.NOT_CONFIGURED,
                reason=f"Backup root does not exist: {_LOCAL_BACKUP_ROOT}",
                last_backup_at=None,
                total_backups=0,
            )
    except Exception as e:
        return BackupTargetInfo(
            name="local_hdd",
            status=BackupTargetStatus.ERROR,
            reason=str(e),
            last_backup_at=None,
            total_backups=0,
        )


# =============================================================================
# PEER REPLICATION (FRAMEWORK)
# =============================================================================

def get_peer_replication_status() -> BackupTargetInfo:
    """Check peer replication status (GitHub-ID-based quorum).
    
    Peers identified by GitHub username (network-independent).
    Format: YGB_PEER_NODES=github-user1,github-user2,github-user3
    """
    peers = os.environ.get("YGB_PEER_NODES", "")
    if not peers:
        return BackupTargetInfo(
            name="peer_replication",
            status=BackupTargetStatus.NOT_CONFIGURED,
            reason="YGB_PEER_NODES not set — peer replication disabled",
            last_backup_at=None,
            total_backups=0,
        )

    peer_list = [p.strip() for p in peers.split(",") if p.strip()]
    return BackupTargetInfo(
        name="peer_replication",
        status=BackupTargetStatus.DEGRADED,
        reason=f"{len(peer_list)} peers configured (GitHub: {', '.join(peer_list)}), quorum verification pending",
        last_backup_at=None,
        total_backups=0,
    )


# =============================================================================
# GOOGLE DRIVE BACKUP (FRAMEWORK)
# =============================================================================

def get_google_drive_status() -> BackupTargetInfo:
    """Check Google Drive backup status."""
    creds = os.environ.get("GOOGLE_DRIVE_CREDENTIALS", "")
    if not creds:
        return BackupTargetInfo(
            name="google_drive",
            status=BackupTargetStatus.NOT_CONFIGURED,
            reason="GOOGLE_DRIVE_CREDENTIALS not set",
            last_backup_at=None,
            total_backups=0,
        )

    # Real verification: check file exists and is valid service account JSON
    creds_path = Path(creds)
    if not creds_path.exists():
        return BackupTargetInfo(
            name="google_drive",
            status=BackupTargetStatus.ERROR,
            reason=f"Credentials file not found: {creds}",
            last_backup_at=None,
            total_backups=0,
        )

    try:
        with open(creds_path, "r", encoding="utf-8") as f:
            key_data = json.load(f)
        required_fields = ["type", "project_id", "private_key", "client_email"]
        missing = [k for k in required_fields if k not in key_data]
        if missing:
            return BackupTargetInfo(
                name="google_drive",
                status=BackupTargetStatus.ERROR,
                reason=f"Service account key missing fields: {', '.join(missing)}",
                last_backup_at=None,
                total_backups=0,
            )
        if key_data.get("type") != "service_account":
            return BackupTargetInfo(
                name="google_drive",
                status=BackupTargetStatus.ERROR,
                reason=f"Key type is '{key_data.get('type')}', expected 'service_account'",
                last_backup_at=None,
                total_backups=0,
            )
        return BackupTargetInfo(
            name="google_drive",
            status=BackupTargetStatus.DEGRADED,
            reason=f"Credentials verified (project: {key_data['project_id']}, email: {key_data['client_email']}), API connection not tested",
            last_backup_at=None,
            total_backups=0,
        )
    except json.JSONDecodeError:
        return BackupTargetInfo(
            name="google_drive",
            status=BackupTargetStatus.ERROR,
            reason=f"Credentials file is not valid JSON: {creds}",
            last_backup_at=None,
            total_backups=0,
        )
    except Exception as e:
        return BackupTargetInfo(
            name="google_drive",
            status=BackupTargetStatus.ERROR,
            reason=f"Failed to read credentials: {e}",
            last_backup_at=None,
            total_backups=0,
        )


# =============================================================================
# COMPRESSION POLICY
# =============================================================================

def compute_integrity_hash(chunk_hashes: List[str]) -> str:
    """Compute integrity hash from all chunk hashes."""
    combined = "|".join(sorted(chunk_hashes))
    return hashlib.sha256(combined.encode()).hexdigest()


def create_manifest(
    source_path: str,
    chunks: List[Dict[str, str]],
    total_bytes: int,
    compression: str = "zstd",
) -> BackupManifest:
    """Create a backup manifest for chunked archive."""
    chunk_hashes = [c["sha256"] for c in chunks]
    import uuid
    return BackupManifest(
        manifest_id=f"BKP-{uuid.uuid4().hex[:16].upper()}",
        created_at=datetime.now(timezone.utc).isoformat(),
        chunks=chunks,
        total_bytes=total_bytes,
        compression=compression,
        source_path=source_path,
        integrity_hash=compute_integrity_hash(chunk_hashes),
    )


def verify_manifest_integrity(manifest: BackupManifest) -> Tuple[bool, str]:
    """Verify that manifest integrity hash matches chunk hashes."""
    chunk_hashes = [c["sha256"] for c in manifest.chunks]
    expected = compute_integrity_hash(chunk_hashes)
    if expected != manifest.integrity_hash:
        return False, f"INTEGRITY_MISMATCH: expected {expected[:16]}..., got {manifest.integrity_hash[:16]}..."
    return True, "Integrity verified"


# =============================================================================
# OVERALL STATUS
# =============================================================================

def get_backup_status() -> Dict[str, Any]:
    """Get comprehensive backup status across all targets."""
    local = get_local_backup_status()
    peer = get_peer_replication_status()
    gdrive = get_google_drive_status()

    targets = [local, peer, gdrive]
    active_count = sum(1 for t in targets if t.status == BackupTargetStatus.ACTIVE)
    configured_count = sum(1 for t in targets if t.status != BackupTargetStatus.NOT_CONFIGURED)

    if active_count == 0:
        overall = "NO_BACKUP"
    elif active_count < configured_count:
        overall = "DEGRADED"
    else:
        overall = "ACTIVE"

    return {
        "status": overall,
        "targets_active": active_count,
        "targets_configured": configured_count,
        "targets_total": len(targets),
        "compression_default": CompressionAlgorithm.ZSTD.value,
        "targets": {
            t.name: {
                "status": t.status.value,
                "reason": t.reason,
                "last_backup_at": t.last_backup_at,
                "total_backups": t.total_backups,
            }
            for t in targets
        },
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
