# G22: User/Admin Database
"""
User and admin data management for the unified app.

ENTITIES:
- User: id, name, email, bounty_count, targets
- Session: id, user_id, device, ip, start_time
- Admin: id, name, permissions

RULES:
✓ All queries are read-only by default
✓ Writes require validation
✓ Deletions require admin approval
✗ NO unaudited writes
✗ NO bulk deletes without approval
"""

from dataclasses import asdict, dataclass, replace
from enum import Enum
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import uuid
from datetime import datetime, UTC


class UserRole(str, Enum):
    """Closed enum for persisted user roles."""
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    VIEWER = "VIEWER"


class Permission(Enum):
    """CLOSED ENUM - Admin permissions"""
    VIEW_USERS = "VIEW_USERS"
    VIEW_SESSIONS = "VIEW_SESSIONS"
    VIEW_LOGS = "VIEW_LOGS"
    MANAGE_USERS = "MANAGE_USERS"
    MANAGE_ALERTS = "MANAGE_ALERTS"
    APPROVE_EXECUTION = "APPROVE_EXECUTION"


class SessionStatus(Enum):
    """CLOSED ENUM - Session statuses"""
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    EXPIRED = "EXPIRED"
    TERMINATED = "TERMINATED"


@dataclass(frozen=True)
class UserRecord:
    """Persisted user record."""
    user_id: str
    username: str
    role: str
    created_at: str
    last_seen: Optional[str]
    active: bool
    email: Optional[str] = None
    bounty_count: int = 0
    total_earnings: float = 0.0
    current_targets: Tuple[str, ...] = tuple()

    @property
    def name(self) -> str:
        return self.username

    @property
    def last_active(self) -> str:
        return self.last_seen or self.created_at

    @property
    def role_enum(self) -> UserRole:
        return _coerce_user_role(self.role)


User = UserRecord


@dataclass(frozen=True)
class UserSession:
    """User session entity."""
    session_id: str
    user_id: str
    device_id: str
    ip_address: str
    geo_location: Optional[str]
    status: SessionStatus
    started_at: str
    last_activity: str


@dataclass(frozen=True)
class Admin:
    """Admin entity."""
    admin_id: str
    user_id: str
    name: str
    permissions: tuple  # Tuple[Permission, ...]
    created_at: str


@dataclass(frozen=True)
class AuditLog:
    """Audit log entry."""
    log_id: str
    actor_id: str
    action: str
    target_id: Optional[str]
    details: str
    timestamp: str


@dataclass(frozen=True)
class DeleteRequest:
    """Request to delete data (requires approval)."""
    request_id: str
    requestor_id: str
    target_type: str  # "user", "session", "admin"
    target_id: str
    reason: str
    approved: bool
    approver_id: Optional[str]
    timestamp: str


# In-memory stores
_sessions: Dict[str, UserSession] = {}
_admins: Dict[str, Admin] = {}
_audit_logs: List[AuditLog] = []
_delete_requests: Dict[str, DeleteRequest] = {}


def _coerce_user_role(role: Union[UserRole, str]) -> UserRole:
    """Normalize user roles to the governed enum."""
    if isinstance(role, UserRole):
        return role

    normalized = str(role).strip().upper()
    try:
        return UserRole[normalized]
    except KeyError:
        try:
            return UserRole(normalized)
        except ValueError as exc:
            raise ValueError(f"Unknown role: {role}") from exc


class UserStore:
    """Disk-backed user record store."""

    def __init__(
        self,
        storage_path: Optional[Union[str, Path]] = None,
        max_users: int = 50,
    ):
        self.storage_path = (
            Path(storage_path)
            if storage_path is not None
            else Path(__file__).resolve().parents[3] / "data" / "phase49_user_store.json"
        )
        self.max_users = max_users
        self.users: Dict[str, UserRecord] = {}
        self.load_on_startup()

    def load_on_startup(self) -> Dict[str, UserRecord]:
        """Load persisted users from disk if the JSON file exists."""
        self.users.clear()
        if not self.storage_path.exists():
            return self.users

        try:
            payload = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self.users

        users_payload = payload.get("users", payload) if isinstance(payload, dict) else {}
        if isinstance(payload, dict):
            self.max_users = int(payload.get("max_users", self.max_users))

        if not isinstance(users_payload, dict):
            return self.users

        for user_id, raw in users_payload.items():
            if not isinstance(raw, dict):
                continue

            try:
                self.users[user_id] = UserRecord(
                    user_id=user_id,
                    username=str(raw["username"]),
                    role=_coerce_user_role(raw.get("role", UserRole.VIEWER.value)).value,
                    created_at=str(raw["created_at"]),
                    last_seen=raw.get("last_seen"),
                    active=bool(raw.get("active", True)),
                    email=raw.get("email"),
                    bounty_count=int(raw.get("bounty_count", 0)),
                    total_earnings=float(raw.get("total_earnings", 0.0)),
                    current_targets=tuple(raw.get("current_targets", []) or []),
                )
            except (KeyError, TypeError, ValueError):
                continue

        return self.users

    def persist_on_change(self) -> None:
        """Persist the current user map to disk as JSON."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "max_users": self.max_users,
            "users": {
                user_id: self._serialize_user(record)
                for user_id, record in self.users.items()
            },
        }

        temp_path = self.storage_path.with_name(f"{self.storage_path.name}.tmp")
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(self.storage_path)

    def clear(self, remove_file: bool = True) -> None:
        """Clear the store and optionally remove the persisted JSON file."""
        self.users.clear()
        if remove_file and self.storage_path.exists():
            self.storage_path.unlink()
        elif not remove_file:
            self.persist_on_change()

    @staticmethod
    def _serialize_user(record: UserRecord) -> Dict[str, object]:
        payload = asdict(record)
        payload["current_targets"] = list(record.current_targets)
        return payload


class UserManager:
    """Managed user CRUD operations with persistence and validation."""

    def __init__(self, store: Optional[UserStore] = None):
        self.store = store or UserStore()

    def create_user(
        self,
        username: str,
        email: Optional[str] = None,
        role: Union[UserRole, str] = UserRole.VIEWER,
    ) -> UserRecord:
        normalized_role = _coerce_user_role(role)
        lowered_username = username.casefold()

        if any(existing.username.casefold() == lowered_username for existing in self.store.users.values()):
            raise ValueError(f"Username already taken: {username}")
        if len(self.store.users) >= self.store.max_users:
            raise ValueError(f"Maximum user count exceeded: {self.store.max_users}")

        now = datetime.now(UTC).isoformat()
        user = UserRecord(
            user_id=f"USR-{uuid.uuid4().hex[:16].upper()}",
            username=username,
            role=normalized_role.value,
            created_at=now,
            last_seen=now,
            active=True,
            email=email,
        )

        self.store.users[user.user_id] = user
        self.store.persist_on_change()
        _log_action("SYSTEM", "CREATE_USER", user.user_id, f"Created user: {username}")
        return user

    def get_user(self, user_id: str) -> Optional[UserRecord]:
        return self.store.users.get(user_id)

    def get_all_users(self) -> List[UserRecord]:
        return list(self.store.users.values())

    def update_user_bounty(
        self,
        user_id: str,
        bounty_delta: int,
        earnings_delta: float,
    ) -> Optional[UserRecord]:
        user = self.get_user(user_id)
        if not user:
            return None

        updated = replace(
            user,
            bounty_count=user.bounty_count + bounty_delta,
            total_earnings=user.total_earnings + earnings_delta,
            last_seen=datetime.now(UTC).isoformat(),
        )
        self.store.users[user_id] = updated
        self.store.persist_on_change()
        _log_action("SYSTEM", "UPDATE_BOUNTY", user_id, f"Added {bounty_delta} bounties, ${earnings_delta}")
        return updated

    def update_user_targets(self, user_id: str, targets: List[str]) -> Optional[UserRecord]:
        user = self.get_user(user_id)
        if not user:
            return None

        updated = replace(
            user,
            current_targets=tuple(targets),
            last_seen=datetime.now(UTC).isoformat(),
        )
        self.store.users[user_id] = updated
        self.store.persist_on_change()
        _log_action("SYSTEM", "UPDATE_TARGETS", user_id, f"Set targets: {targets}")
        return updated

    def deactivate_user(self, user_id: str) -> bool:
        user = self.get_user(user_id)
        if not user:
            return False

        self.store.users[user_id] = replace(
            user,
            active=False,
            last_seen=datetime.now(UTC).isoformat(),
        )
        self.store.persist_on_change()
        _log_action("SYSTEM", "DEACTIVATE_USER", user_id, f"Deactivated user: {user.username}")
        return True

    def get_active_users(self) -> List[UserRecord]:
        return [user for user in self.store.users.values() if user.active]

    def delete_user(self, user_id: str) -> bool:
        if user_id not in self.store.users:
            return False
        del self.store.users[user_id]
        self.store.persist_on_change()
        return True


_DEFAULT_USER_STORE = UserStore()
_DEFAULT_USER_MANAGER = UserManager(_DEFAULT_USER_STORE)


def clear_database():
    """Clear all data (for testing)."""
    _DEFAULT_USER_STORE.clear()
    _sessions.clear()
    _admins.clear()
    _audit_logs.clear()
    _delete_requests.clear()


def _log_action(actor_id: str, action: str, target_id: Optional[str], details: str):
    """Log an action to audit log."""
    log = AuditLog(
        log_id=f"LOG-{uuid.uuid4().hex[:16].upper()}",
        actor_id=actor_id,
        action=action,
        target_id=target_id,
        details=details,
        timestamp=datetime.now(UTC).isoformat(),
    )
    _audit_logs.append(log)
    return log


# ============================================================
# USER OPERATIONS
# ============================================================

def create_user(
    name: str,
    email: Optional[str] = None,
    role: Union[UserRole, str] = UserRole.VIEWER,
) -> UserRecord:
    """Create a new user."""
    return _DEFAULT_USER_MANAGER.create_user(name, email=email, role=role)


def get_user(user_id: str) -> Optional[UserRecord]:
    """Get user by ID (read-only)."""
    return _DEFAULT_USER_MANAGER.get_user(user_id)


def get_all_users() -> List[UserRecord]:
    """Get all users (read-only)."""
    return _DEFAULT_USER_MANAGER.get_all_users()


def update_user_bounty(
    user_id: str,
    bounty_delta: int,
    earnings_delta: float,
) -> Optional[User]:
    """Update user's bounty count and earnings."""
    return _DEFAULT_USER_MANAGER.update_user_bounty(user_id, bounty_delta, earnings_delta)


def update_user_targets(
    user_id: str,
    targets: List[str],
) -> Optional[User]:
    """Update user's current targets."""
    return _DEFAULT_USER_MANAGER.update_user_targets(user_id, targets)


def deactivate_user(user_id: str) -> bool:
    """Deactivate a user without deleting the persisted record."""
    return _DEFAULT_USER_MANAGER.deactivate_user(user_id)


def get_active_users() -> List[UserRecord]:
    """Return only active users from the persisted store."""
    return _DEFAULT_USER_MANAGER.get_active_users()


# ============================================================
# SESSION OPERATIONS
# ============================================================

def create_session(
    user_id: str,
    device_id: str,
    ip_address: str,
    geo_location: Optional[str] = None,
) -> UserSession:
    """Create a new session."""
    session_id = f"SES-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(UTC).isoformat()
    
    session = UserSession(
        session_id=session_id,
        user_id=user_id,
        device_id=device_id,
        ip_address=ip_address,
        geo_location=geo_location,
        status=SessionStatus.ACTIVE,
        started_at=now,
        last_activity=now,
    )
    
    _sessions[session_id] = session
    _log_action(user_id, "CREATE_SESSION", session_id, f"From IP: {ip_address}")
    return session


def get_session(session_id: str) -> Optional[UserSession]:
    """Get session by ID (read-only)."""
    return _sessions.get(session_id)


def get_user_sessions(user_id: str) -> List[UserSession]:
    """Get all sessions for a user."""
    return [s for s in _sessions.values() if s.user_id == user_id]


def get_active_sessions() -> List[UserSession]:
    """Get all active sessions."""
    return [s for s in _sessions.values() if s.status == SessionStatus.ACTIVE]


def terminate_session(session_id: str, actor_id: str) -> Optional[UserSession]:
    """Terminate a session."""
    session = get_session(session_id)
    if not session:
        return None
    
    new_session = UserSession(
        session_id=session.session_id,
        user_id=session.user_id,
        device_id=session.device_id,
        ip_address=session.ip_address,
        geo_location=session.geo_location,
        status=SessionStatus.TERMINATED,
        started_at=session.started_at,
        last_activity=datetime.now(UTC).isoformat(),
    )
    
    _sessions[session_id] = new_session
    _log_action(actor_id, "TERMINATE_SESSION", session_id, "Session terminated")
    return new_session


# ============================================================
# ADMIN OPERATIONS
# ============================================================

def create_admin(
    user_id: str,
    name: str,
    permissions: List[Permission],
) -> Admin:
    """Create an admin."""
    admin_id = f"ADM-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(UTC).isoformat()
    
    admin = Admin(
        admin_id=admin_id,
        user_id=user_id,
        name=name,
        permissions=tuple(permissions),
        created_at=now,
    )
    
    _admins[admin_id] = admin
    _log_action("OWNER", "CREATE_ADMIN", admin_id, f"Created admin: {name}")
    return admin


def get_admin(admin_id: str) -> Optional[Admin]:
    """Get admin by ID."""
    return _admins.get(admin_id)


def get_admin_by_user(user_id: str) -> Optional[Admin]:
    """Get admin by user ID."""
    for admin in _admins.values():
        if admin.user_id == user_id:
            return admin
    return None


def admin_has_permission(admin_id: str, permission: Permission) -> bool:
    """Check if admin has a specific permission."""
    admin = get_admin(admin_id)
    if not admin:
        return False
    return permission in admin.permissions


# ============================================================
# AUDIT OPERATIONS
# ============================================================

def get_audit_logs(limit: int = 100) -> List[AuditLog]:
    """Get recent audit logs."""
    return _audit_logs[-limit:]


def get_logs_for_actor(actor_id: str) -> List[AuditLog]:
    """Get logs for a specific actor."""
    return [log for log in _audit_logs if log.actor_id == actor_id]


# ============================================================
# DELETE OPERATIONS (REQUIRES APPROVAL)
# ============================================================

def request_delete(
    requestor_id: str,
    target_type: str,
    target_id: str,
    reason: str,
) -> DeleteRequest:
    """Request deletion (requires admin approval)."""
    request_id = f"DEL-{uuid.uuid4().hex[:16].upper()}"
    
    request = DeleteRequest(
        request_id=request_id,
        requestor_id=requestor_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
        approved=False,
        approver_id=None,
        timestamp=datetime.now(UTC).isoformat(),
    )
    
    _delete_requests[request_id] = request
    _log_action(requestor_id, "REQUEST_DELETE", target_id, f"Type: {target_type}, Reason: {reason}")
    return request


def approve_delete(
    request_id: str,
    approver_id: str,
    approved: bool,
) -> Optional[DeleteRequest]:
    """Approve or reject a delete request."""
    request = _delete_requests.get(request_id)
    if not request:
        return None
    
    # Verify approver is admin with MANAGE_USERS permission
    admin = get_admin_by_user(approver_id)
    if not admin or Permission.MANAGE_USERS not in admin.permissions:
        return None
    
    new_request = DeleteRequest(
        request_id=request.request_id,
        requestor_id=request.requestor_id,
        target_type=request.target_type,
        target_id=request.target_id,
        reason=request.reason,
        approved=approved,
        approver_id=approver_id,
        timestamp=datetime.now(UTC).isoformat(),
    )
    
    _delete_requests[request_id] = new_request
    
    if approved:
        _execute_delete(request.target_type, request.target_id)
        _log_action(approver_id, "APPROVE_DELETE", request.target_id, f"Approved delete of {request.target_type}")
    else:
        _log_action(approver_id, "REJECT_DELETE", request.target_id, f"Rejected delete of {request.target_type}")
    
    return new_request


def _execute_delete(target_type: str, target_id: str):
    """Execute approved deletion."""
    if target_type == "user":
        _DEFAULT_USER_MANAGER.delete_user(target_id)
    elif target_type == "session" and target_id in _sessions:
        del _sessions[target_id]
    elif target_type == "admin" and target_id in _admins:
        del _admins[target_id]


# ============================================================
# CRITICAL SECURITY GUARDS
# ============================================================

def can_database_delete_without_approval() -> tuple:
    """
    Check if database can delete without approval.
    
    Returns (can_delete, reason).
    ALWAYS returns (False, ...).
    """
    return False, "All deletions require admin approval - no unaudited deletes"


def can_database_bulk_delete() -> tuple:
    """
    Check if database can perform bulk deletes.
    
    Returns (can_bulk_delete, reason).
    ALWAYS returns (False, ...).
    """
    return False, "Bulk deletes are FORBIDDEN - individual approval required"


def can_database_skip_audit() -> tuple:
    """
    Check if database operations can skip audit logging.
    
    Returns (can_skip, reason).
    ALWAYS returns (False, ...).
    """
    return False, "All database operations are audited - no skip allowed"
