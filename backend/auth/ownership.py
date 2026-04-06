"""
ownership.py — Centralized resource ownership checks

Provides helpers to enforce that a user can only access resources they own,
unless they have ADMIN role. Used by all endpoints that accept user-controlled
entity IDs (workflow_id, session_id, report_id, etc.).

FAIL CLOSED: if ownership cannot be verified, access is denied.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from fastapi import HTTPException
from threading import RLock
from typing import Dict, Any, Optional


@dataclass(frozen=True)
class TransferRecord:
    timestamp: str
    resource_id: str
    from_owner: str
    to_owner: str
    authorized_by: str


class OwnershipTransferDenied(PermissionError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class OwnershipTransferLog:
    def __init__(self):
        self._records: list[TransferRecord] = []
        self._lock = RLock()

    def record(self, record: TransferRecord) -> None:
        with self._lock:
            self._records.append(record)

    def get_history(self, resource_id: str) -> list[TransferRecord]:
        with self._lock:
            return [record for record in self._records if record.resource_id == resource_id]


_transfer_log = OwnershipTransferLog()


def _transfer_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def transfer_resource_ownership(
    resource: Optional[Dict[str, Any]],
    new_owner: str,
    caller: Dict[str, Any],
    resource_id: str = "",
) -> Dict[str, Any]:
    """Transfer resource ownership when invoked by the current owner or an admin."""
    if resource is None:
        raise OwnershipTransferDenied("resource_not_found")

    current_owner = str(resource.get("owner_id", ""))
    caller_id = str(caller.get("sub", ""))
    caller_role = str(caller.get("role", ""))
    next_owner = str(new_owner).strip()

    if caller_role != "admin" and caller_id != current_owner:
        raise OwnershipTransferDenied("transfer_not_authorized")
    if not next_owner:
        raise ValueError("new_owner is required")

    resolved_resource_id = resource_id or str(resource.get("id", ""))
    resource["owner_id"] = next_owner
    _transfer_log.record(
        TransferRecord(
            timestamp=_transfer_timestamp(),
            resource_id=resolved_resource_id,
            from_owner=current_owner,
            to_owner=next_owner,
            authorized_by=caller_id,
        )
    )
    return resource


def get_transfer_history(resource_id: str) -> list[TransferRecord]:
    return _transfer_log.get_history(resource_id)


def check_resource_owner(
    resource: Optional[Dict[str, Any]],
    user: Dict[str, Any],
    resource_name: str = "resource",
    resource_id: str = "",
) -> None:
    """Verify the authenticated user owns the resource, or is admin.

    Args:
        resource: The resource dict (must contain 'owner_id' key).
        user: The JWT/session payload (must contain 'sub' key).
        resource_name: Human-readable name for error messages.
        resource_id: The ID string for logging.

    Raises:
        HTTPException 404 if resource is None.
        HTTPException 403 if user is not owner and not admin.
    """
    if resource is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "NOT_FOUND",
                "detail": f"{resource_name} '{resource_id}' not found",
            },
        )

    owner_id = resource.get("owner_id", "")
    user_id = user.get("sub", "")
    user_role = user.get("role", "")

    # Admin bypass
    if user_role == "admin":
        return

    # Owner check — fail closed
    if not owner_id or not user_id or owner_id != user_id:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "FORBIDDEN",
                "detail": f"You do not have access to this {resource_name}",
            },
        )


def check_ws_resource_owner(
    resource: Optional[Dict[str, Any]],
    user: Dict[str, Any],
    resource_name: str = "resource",
) -> bool:
    """WebSocket-safe ownership check (no HTTPException).

    Returns True if access is allowed, False otherwise.
    """
    if resource is None:
        return False

    owner_id = resource.get("owner_id", "")
    user_id = user.get("sub", "")
    user_role = user.get("role", "")

    if user_role == "admin":
        return True

    if not owner_id or not user_id or owner_id != user_id:
        return False

    return True
