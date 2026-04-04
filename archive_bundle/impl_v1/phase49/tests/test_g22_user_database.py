# test_g22_user_database.py
"""Tests for G22 User/Admin Database."""

import pytest

from impl_v1.phase49.governors.g22_user_database import (
    UserRole,
    Permission,
    SessionStatus,
    User,
    UserSession,
    Admin,
    AuditLog,
    DeleteRequest,
    create_user,
    get_user,
    get_all_users,
    update_user_bounty,
    update_user_targets,
    create_session,
    get_session,
    get_user_sessions,
    get_active_sessions,
    terminate_session,
    create_admin,
    get_admin,
    get_admin_by_user,
    admin_has_permission,
    get_audit_logs,
    get_logs_for_actor,
    request_delete,
    approve_delete,
    can_database_delete_without_approval,
    can_database_bulk_delete,
    can_database_skip_audit,
    clear_database,
)


class TestUserRole:
    """Tests for UserRole enum."""
    
    def test_has_hunter(self):
        assert UserRole.HUNTER.value == "HUNTER"
    
    def test_has_admin(self):
        assert UserRole.ADMIN.value == "ADMIN"
    
    def test_has_owner(self):
        assert UserRole.OWNER.value == "OWNER"


class TestPermission:
    """Tests for Permission enum."""
    
    def test_has_view_users(self):
        assert Permission.VIEW_USERS.value == "VIEW_USERS"
    
    def test_has_manage_users(self):
        assert Permission.MANAGE_USERS.value == "MANAGE_USERS"
    
    def test_has_approve_execution(self):
        assert Permission.APPROVE_EXECUTION.value == "APPROVE_EXECUTION"


class TestCreateUser:
    """Tests for create_user."""
    
    def setup_method(self):
        clear_database()
    
    def test_creates_user(self):
        user = create_user("Hunter1", "hunter1@test.com")
        assert isinstance(user, User)
    
    def test_user_has_id(self):
        user = create_user("Hunter1")
        assert user.user_id.startswith("USR-")
    
    def test_default_role_hunter(self):
        user = create_user("Hunter1")
        assert user.role == UserRole.HUNTER
    
    def test_can_get_user(self):
        user = create_user("Hunter1")
        retrieved = get_user(user.user_id)
        assert retrieved.name == "Hunter1"
    
    def test_get_all_users(self):
        create_user("Hunter1")
        create_user("Hunter2")
        users = get_all_users()
        assert len(users) == 2


class TestUpdateUser:
    """Tests for update_user functions."""
    
    def setup_method(self):
        clear_database()
    
    def test_update_bounty(self):
        user = create_user("Hunter1")
        updated = update_user_bounty(user.user_id, 5, 1000.0)
        assert updated.bounty_count == 5
        assert updated.total_earnings == 1000.0
    
    def test_update_targets(self):
        user = create_user("Hunter1")
        updated = update_user_targets(user.user_id, ["example.com", "test.com"])
        assert len(updated.current_targets) == 2


class TestCreateSession:
    """Tests for create_session."""
    
    def setup_method(self):
        clear_database()
    
    def test_creates_session(self):
        user = create_user("Hunter1")
        session = create_session(user.user_id, "device1", "192.168.1.1")
        assert isinstance(session, UserSession)
    
    def test_session_has_id(self):
        user = create_user("Hunter1")
        session = create_session(user.user_id, "device1", "192.168.1.1")
        assert session.session_id.startswith("SES-")
    
    def test_session_is_active(self):
        user = create_user("Hunter1")
        session = create_session(user.user_id, "device1", "192.168.1.1")
        assert session.status == SessionStatus.ACTIVE
    
    def test_get_user_sessions(self):
        user = create_user("Hunter1")
        create_session(user.user_id, "device1", "1.1.1.1")
        create_session(user.user_id, "device2", "2.2.2.2")
        sessions = get_user_sessions(user.user_id)
        assert len(sessions) == 2
    
    def test_get_active_sessions(self):
        user = create_user("Hunter1")
        create_session(user.user_id, "device1", "1.1.1.1")
        active = get_active_sessions()
        assert len(active) >= 1


class TestTerminateSession:
    """Tests for terminate_session."""
    
    def setup_method(self):
        clear_database()
    
    def test_terminates_session(self):
        user = create_user("Hunter1")
        session = create_session(user.user_id, "device1", "1.1.1.1")
        terminated = terminate_session(session.session_id, user.user_id)
        assert terminated.status == SessionStatus.TERMINATED


class TestCreateAdmin:
    """Tests for create_admin."""
    
    def setup_method(self):
        clear_database()
    
    def test_creates_admin(self):
        user = create_user("Admin1", role=UserRole.ADMIN)
        admin = create_admin(user.user_id, "Admin1", [Permission.VIEW_USERS])
        assert isinstance(admin, Admin)
    
    def test_admin_has_permissions(self):
        user = create_user("Admin1", role=UserRole.ADMIN)
        admin = create_admin(user.user_id, "Admin1", [Permission.VIEW_USERS, Permission.MANAGE_USERS])
        assert admin_has_permission(admin.admin_id, Permission.VIEW_USERS)
        assert admin_has_permission(admin.admin_id, Permission.MANAGE_USERS)
    
    def test_get_admin_by_user(self):
        user = create_user("Admin1", role=UserRole.ADMIN)
        create_admin(user.user_id, "Admin1", [Permission.VIEW_USERS])
        admin = get_admin_by_user(user.user_id)
        assert admin is not None


class TestAuditLogs:
    """Tests for audit log functions."""
    
    def setup_method(self):
        clear_database()
    
    def test_user_creation_logged(self):
        create_user("Hunter1")
        logs = get_audit_logs()
        assert len(logs) >= 1
        assert any("CREATE_USER" in log.action for log in logs)
    
    def test_get_logs_for_actor(self):
        user = create_user("Hunter1")
        session = create_session(user.user_id, "device1", "1.1.1.1")
        logs = get_logs_for_actor(user.user_id)
        assert len(logs) >= 1


class TestDeleteRequest:
    """Tests for delete request and approval."""
    
    def setup_method(self):
        clear_database()
    
    def test_request_delete(self):
        user = create_user("Hunter1")
        request = request_delete("admin1", "user", user.user_id, "Test delete")
        assert request.approved == False
    
    def test_approve_delete_requires_admin(self):
        user = create_user("Hunter1")
        request = request_delete("admin1", "user", user.user_id, "Test")
        
        # Without admin, approval fails
        result = approve_delete(request.request_id, "non-admin", True)
        assert result is None
    
    def test_admin_can_approve_delete(self):
        user = create_user("Hunter1")
        admin_user = create_user("Admin1", role=UserRole.ADMIN)
        admin = create_admin(admin_user.user_id, "Admin1", [Permission.MANAGE_USERS])
        
        request = request_delete("someone", "user", user.user_id, "Test")
        result = approve_delete(request.request_id, admin_user.user_id, True)
        
        assert result is not None
        assert result.approved == True
        
        # User should be deleted
        assert get_user(user.user_id) is None


class TestCanDatabaseDeleteWithoutApproval:
    """Tests for can_database_delete_without_approval guard."""
    
    def test_cannot_delete_without_approval(self):
        can_delete, reason = can_database_delete_without_approval()
        assert can_delete == False
        assert "approval" in reason.lower()


class TestCanDatabaseBulkDelete:
    """Tests for can_database_bulk_delete guard."""
    
    def test_cannot_bulk_delete(self):
        can_bulk, reason = can_database_bulk_delete()
        assert can_bulk == False
        assert "bulk" in reason.lower() or "forbidden" in reason.lower()


class TestCanDatabaseSkipAudit:
    """Tests for can_database_skip_audit guard."""
    
    def test_cannot_skip_audit(self):
        can_skip, reason = can_database_skip_audit()
        assert can_skip == False
        assert "audit" in reason.lower()
