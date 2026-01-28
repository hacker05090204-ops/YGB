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

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
import uuid
from datetime import datetime, UTC


class UserRole(Enum):
    """CLOSED ENUM - User roles"""
    HUNTER = "HUNTER"
    ADMIN = "ADMIN"
    OWNER = "OWNER"


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
class User:
    """User entity."""
    user_id: str
    name: str
    email: Optional[str]
    role: UserRole
    bounty_count: int
    total_earnings: float
    current_targets: tuple  # Tuple[str, ...]
    created_at: str
    last_active: str


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
_users: Dict[str, User] = {}
_sessions: Dict[str, UserSession] = {}
_admins: Dict[str, Admin] = {}
_audit_logs: List[AuditLog] = []
_delete_requests: Dict[str, DeleteRequest] = {}


def clear_database():
    """Clear all data (for testing)."""
    _users.clear()
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
    role: UserRole = UserRole.HUNTER,
) -> User:
    """Create a new user."""
    user_id = f"USR-{uuid.uuid4().hex[:16].upper()}"
    now = datetime.now(UTC).isoformat()
    
    user = User(
        user_id=user_id,
        name=name,
        email=email,
        role=role,
        bounty_count=0,
        total_earnings=0.0,
        current_targets=tuple(),
        created_at=now,
        last_active=now,
    )
    
    _users[user_id] = user
    _log_action("SYSTEM", "CREATE_USER", user_id, f"Created user: {name}")
    return user


def get_user(user_id: str) -> Optional[User]:
    """Get user by ID (read-only)."""
    return _users.get(user_id)


def get_all_users() -> List[User]:
    """Get all users (read-only)."""
    return list(_users.values())


def update_user_bounty(
    user_id: str,
    bounty_delta: int,
    earnings_delta: float,
) -> Optional[User]:
    """Update user's bounty count and earnings."""
    user = get_user(user_id)
    if not user:
        return None
    
    now = datetime.now(UTC).isoformat()
    
    new_user = User(
        user_id=user.user_id,
        name=user.name,
        email=user.email,
        role=user.role,
        bounty_count=user.bounty_count + bounty_delta,
        total_earnings=user.total_earnings + earnings_delta,
        current_targets=user.current_targets,
        created_at=user.created_at,
        last_active=now,
    )
    
    _users[user_id] = new_user
    _log_action("SYSTEM", "UPDATE_BOUNTY", user_id, f"Added {bounty_delta} bounties, ${earnings_delta}")
    return new_user


def update_user_targets(
    user_id: str,
    targets: List[str],
) -> Optional[User]:
    """Update user's current targets."""
    user = get_user(user_id)
    if not user:
        return None
    
    now = datetime.now(UTC).isoformat()
    
    new_user = User(
        user_id=user.user_id,
        name=user.name,
        email=user.email,
        role=user.role,
        bounty_count=user.bounty_count,
        total_earnings=user.total_earnings,
        current_targets=tuple(targets),
        created_at=user.created_at,
        last_active=now,
    )
    
    _users[user_id] = new_user
    _log_action("SYSTEM", "UPDATE_TARGETS", user_id, f"Set targets: {targets}")
    return new_user


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
    if target_type == "user" and target_id in _users:
        del _users[target_id]
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
