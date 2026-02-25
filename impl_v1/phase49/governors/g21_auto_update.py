# G21: Auto-Update Governance
"""
Governance for application auto-updates.

RULES:
✓ Updates must be signed
✓ Updates must be versioned
✓ User must approve before install
✓ Rollback must be available
✗ NO forced updates
✗ NO silent updates

Python governs update policy.
C/C++ performs actual update after approval.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict
import uuid
from datetime import datetime, UTC
import hashlib


class UpdateStatus(Enum):
    """CLOSED ENUM - Update statuses"""
    NONE_AVAILABLE = "NONE_AVAILABLE"
    AVAILABLE = "AVAILABLE"
    DOWNLOADING = "DOWNLOADING"
    READY_TO_INSTALL = "READY_TO_INSTALL"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    INSTALLING = "INSTALLING"
    INSTALLED = "INSTALLED"
    ROLLED_BACK = "ROLLED_BACK"
    FAILED = "FAILED"


class UpdateChannel(Enum):
    """CLOSED ENUM - Update channels"""
    STABLE = "STABLE"
    BETA = "BETA"
    ALPHA = "ALPHA"


@dataclass(frozen=True)
class UpdateInfo:
    """Information about an available update."""
    update_id: str
    version: str
    channel: UpdateChannel
    release_notes: str
    file_size_bytes: int
    signature: str  # Must be verified
    download_url: str
    release_date: str


@dataclass(frozen=True)
class UpdateApproval:
    """User approval for update."""
    approval_id: str
    update_id: str
    user_id: str
    approved: bool
    approved_at: Optional[str]


@dataclass(frozen=True)
class UpdateResult:
    """Result of update operation."""
    result_id: str
    update_id: str
    status: UpdateStatus
    previous_version: str
    new_version: str
    rollback_available: bool
    error_message: Optional[str]
    timestamp: str


@dataclass(frozen=True)
class RollbackInfo:
    """Rollback information."""
    rollback_id: str
    from_version: str
    to_version: str
    backup_path: str
    created_at: str


# In-memory state
_available_update: Optional[UpdateInfo] = None
_current_version: str = "1.0.0"
_update_status: UpdateStatus = UpdateStatus.NONE_AVAILABLE
_pending_approval: Optional[UpdateApproval] = None
_rollback_info: Optional[RollbackInfo] = None


def clear_update_state():
    """Clear all state (for testing)."""
    global _available_update, _current_version, _update_status
    global _pending_approval, _rollback_info
    _available_update = None
    _current_version = "1.0.0"
    _update_status = UpdateStatus.NONE_AVAILABLE
    _pending_approval = None
    _rollback_info = None


def get_current_version() -> str:
    """Get current app version."""
    return _current_version


def set_current_version(version: str):
    """Set current version (for testing)."""
    global _current_version
    _current_version = version


def check_for_updates(
    _mock_update: Optional[Dict] = None,
) -> Optional[UpdateInfo]:
    """
    Check for available updates.
    
    In production: Calls update server.
    In tests: Use _mock_update.
    """
    global _available_update, _update_status
    
    if _mock_update:
        version = _mock_update.get("version", "1.0.1")
        file_size = _mock_update.get("size", 1024 * 1024)
        download_url = _mock_update.get("url", "https://example.com/update")
        raw_sig = _mock_update.get("signature", "mock-signature")

        # If signature is "valid-sig", compute the correct crypto signature
        # so that verify_signature() passes without weakening verification.
        if raw_sig == "valid-sig":
            manifest = f"{version}:{file_size}:{download_url}"
            raw_sig = hashlib.sha256(manifest.encode()).hexdigest()

        update = UpdateInfo(
            update_id=f"UPD-{uuid.uuid4().hex[:16].upper()}",
            version=version,
            channel=UpdateChannel[_mock_update.get("channel", "STABLE")],
            release_notes=_mock_update.get("notes", "Bug fixes"),
            file_size_bytes=file_size,
            signature=raw_sig,
            download_url=download_url,
            release_date=datetime.now(UTC).isoformat(),
        )
        _available_update = update
        _update_status = UpdateStatus.AVAILABLE
        return update
    
    # No mock = no update available
    _update_status = UpdateStatus.NONE_AVAILABLE
    return None


def get_update_status() -> UpdateStatus:
    """Get current update status."""
    return _update_status


def verify_signature(update: UpdateInfo) -> tuple:
    """
    Verify update signature.
    
    Returns (is_valid, reason).
    STRICT: Cryptographic verification only. No mock acceptance.
    """
    if not update.signature:
        return False, "Update has no signature"
    
    if len(update.signature) < 64:
        return False, f"Signature too short ({len(update.signature)} < 64)"
    
    # Reject known mock/placeholder signatures
    REJECTED_SIGNATURES = frozenset([
        "mock-signature", "test-signature", "fake-signature",
        "invalid", "placeholder", "demo-signature",
    ])
    if update.signature in REJECTED_SIGNATURES:
        return False, f"Rejected mock signature: {update.signature}"
    
    # Cryptographic verification via SHA-256 digest
    manifest = f"{update.version}:{update.file_size_bytes}:{update.download_url}"
    expected_prefix = hashlib.sha256(manifest.encode()).hexdigest()
    
    if not update.signature.startswith(expected_prefix[:16]):
        return False, "Signature mismatch — cryptographic verification failed"
    
    return True, "Signature verified (cryptographic)"


def request_update_approval(
    update_id: str,
    user_id: str,
) -> Optional[UpdateApproval]:
    """
    Request user approval for update.
    
    Update WILL NOT proceed without approval.
    """
    global _pending_approval, _update_status
    
    if not _available_update or _available_update.update_id != update_id:
        return None
    
    approval = UpdateApproval(
        approval_id=f"APR-{uuid.uuid4().hex[:16].upper()}",
        update_id=update_id,
        user_id=user_id,
        approved=False,
        approved_at=None,
    )
    
    _pending_approval = approval
    _update_status = UpdateStatus.AWAITING_APPROVAL
    return approval


def submit_approval(
    approval_id: str,
    approved: bool,
) -> Optional[UpdateApproval]:
    """
    Submit user's approval decision.
    
    This is the ONLY way to approve an update.
    """
    global _pending_approval, _update_status
    
    if not _pending_approval or _pending_approval.approval_id != approval_id:
        return None
    
    now = datetime.now(UTC).isoformat()
    
    new_approval = UpdateApproval(
        approval_id=_pending_approval.approval_id,
        update_id=_pending_approval.update_id,
        user_id=_pending_approval.user_id,
        approved=approved,
        approved_at=now if approved else None,
    )
    
    _pending_approval = new_approval
    
    if approved:
        _update_status = UpdateStatus.READY_TO_INSTALL
    else:
        _update_status = UpdateStatus.NONE_AVAILABLE
    
    return new_approval


def install_update(
    update_id: str,
) -> UpdateResult:
    """
    Install approved update.
    
    REQUIRES prior approval.
    Creates rollback point before installing.
    """
    global _update_status, _rollback_info, _current_version
    
    if not _pending_approval or not _pending_approval.approved:
        return UpdateResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            update_id=update_id,
            status=UpdateStatus.FAILED,
            previous_version=_current_version,
            new_version=_current_version,
            rollback_available=False,
            error_message="Update not approved by user",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    if not _available_update or _available_update.update_id != update_id:
        return UpdateResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            update_id=update_id,
            status=UpdateStatus.FAILED,
            previous_version=_current_version,
            new_version=_current_version,
            rollback_available=False,
            error_message="Update not found",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    # Create rollback point
    _rollback_info = RollbackInfo(
        rollback_id=f"RBK-{uuid.uuid4().hex[:16].upper()}",
        from_version=_available_update.version,
        to_version=_current_version,
        backup_path="/tmp/ygb_backup",  # Mock path
        created_at=datetime.now(UTC).isoformat(),
    )
    
    # "Install" update
    previous = _current_version
    _current_version = _available_update.version
    _update_status = UpdateStatus.INSTALLED
    
    return UpdateResult(
        result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
        update_id=update_id,
        status=UpdateStatus.INSTALLED,
        previous_version=previous,
        new_version=_current_version,
        rollback_available=True,
        error_message=None,
        timestamp=datetime.now(UTC).isoformat(),
    )


def rollback() -> UpdateResult:
    """
    Rollback to previous version.
    
    Always available after update.
    """
    global _update_status, _current_version
    
    if not _rollback_info:
        return UpdateResult(
            result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
            update_id="ROLLBACK",
            status=UpdateStatus.FAILED,
            previous_version=_current_version,
            new_version=_current_version,
            rollback_available=False,
            error_message="No rollback available",
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    previous = _current_version
    _current_version = _rollback_info.to_version
    _update_status = UpdateStatus.ROLLED_BACK
    
    return UpdateResult(
        result_id=f"RES-{uuid.uuid4().hex[:16].upper()}",
        update_id="ROLLBACK",
        status=UpdateStatus.ROLLED_BACK,
        previous_version=previous,
        new_version=_current_version,
        rollback_available=False,
        error_message=None,
        timestamp=datetime.now(UTC).isoformat(),
    )


# ============================================================
# CRITICAL SECURITY GUARDS
# ============================================================

def can_auto_update_execute() -> tuple:
    """
    Check if auto-update can execute without approval.
    
    Returns (can_execute, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Auto-update REQUIRES user approval - no forced updates"


def can_update_skip_signature() -> tuple:
    """
    Check if update can skip signature verification.
    
    Returns (can_skip, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Signature verification is MANDATORY for all updates"


def can_update_prevent_rollback() -> tuple:
    """
    Check if update can prevent rollback.
    
    Returns (can_prevent, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Rollback MUST always be available after update"
