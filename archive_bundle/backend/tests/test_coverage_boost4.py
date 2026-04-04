"""
Coverage boost round 4 — pushing toward 90%.

Real-data integration tests for:
  - admin_auth.py (lockout, sessions, JWT, TOTP, user mgmt, login, auth middleware)
  - field_progression_api.py (state persistence, runtime status, endpoint handlers)
"""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock

import backend.api.admin_auth as admin_auth_mod


# ---------------------------------------------------------------------------
# Helper: patch admin_auth paths to use temp directory
# ---------------------------------------------------------------------------

def _admin_patches(tmp_dir):
    """Return a list of patch context managers for admin_auth path constants."""
    return [
        patch.object(admin_auth_mod, 'SESSION_DIR', os.path.join(tmp_dir, 'sessions')),
        patch.object(admin_auth_mod, 'AUDIT_LOG_PATH', os.path.join(tmp_dir, 'audit.json')),
        patch.object(admin_auth_mod, 'LOCKOUT_PATH', os.path.join(tmp_dir, 'lockouts.json')),
        patch.object(admin_auth_mod, 'USERS_DB_PATH', os.path.join(tmp_dir, 'users.json')),
        patch.object(admin_auth_mod, 'PROJECT_ROOT', tmp_dir),
    ]


class _AdminAuthTestBase(unittest.TestCase):
    """Base class that sets up temp dir and patches admin_auth paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._patchers = _admin_patches(self.tmp)
        for p in self._patchers:
            p.start()
        # Reset lockouts state
        admin_auth_mod._lockouts = {}

    def tearDown(self):
        for p in self._patchers:
            p.stop()
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# 1. admin_auth.py — Lockout
# ---------------------------------------------------------------------------

class TestAdminAuthLockout(_AdminAuthTestBase):
    """Tests for lockout management using real temp files."""

    def test_not_locked_out_initially(self):
        self.assertFalse(admin_auth_mod.is_locked_out("user@test.com"))

    def test_record_failed_attempts(self):
        result = admin_auth_mod.record_failed_attempt("user@test.com", "1.2.3.4")
        self.assertFalse(result['locked'])
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(result['remaining'], 4)

    def test_lockout_after_max_attempts(self):
        for i in range(5):
            result = admin_auth_mod.record_failed_attempt("locker@test.com", "1.2.3.4")
        self.assertTrue(result['locked'])
        self.assertTrue(admin_auth_mod.is_locked_out("locker@test.com"))

    def test_clear_lockout(self):
        for i in range(5):
            admin_auth_mod.record_failed_attempt("clear@test.com", "1.2.3.4")
        self.assertTrue(admin_auth_mod.is_locked_out("clear@test.com"))
        admin_auth_mod.clear_lockout("clear@test.com")
        self.assertFalse(admin_auth_mod.is_locked_out("clear@test.com"))

    def test_lockout_expired(self):
        admin_auth_mod._ensure_secure_dir()
        admin_auth_mod._lockouts["expired@test.com"] = {
            'attempts': 5,
            'locked_until': time.time() - 10,
        }
        admin_auth_mod._save_lockouts()
        self.assertFalse(admin_auth_mod.is_locked_out("expired@test.com"))

    def test_clear_lockout_nonexistent(self):
        admin_auth_mod.clear_lockout("nobody@test.com")  # Should not raise


# ---------------------------------------------------------------------------
# 2. admin_auth.py — Session Management
# ---------------------------------------------------------------------------

class TestAdminAuthSession(_AdminAuthTestBase):
    """Tests for file-based session management."""

    def test_create_session_returns_token(self):
        token = admin_auth_mod.create_session("user-1", "ADMIN", "192.168.1.1")
        self.assertEqual(len(token), 64)

    def test_validate_session_success(self):
        token = admin_auth_mod.create_session("user-1", "ADMIN", "10.0.0.1")
        session = admin_auth_mod.validate_session(token)
        self.assertIsNotNone(session)
        self.assertEqual(session['user_id'], "user-1")
        self.assertEqual(session['role'], "ADMIN")

    def test_validate_session_bad_token(self):
        self.assertIsNone(admin_auth_mod.validate_session("short"))
        self.assertIsNone(admin_auth_mod.validate_session(""))
        self.assertIsNone(admin_auth_mod.validate_session("a" * 64))

    def test_destroy_session(self):
        token = admin_auth_mod.create_session("u2", "WORKER", "10.0.0.2")
        self.assertIsNotNone(admin_auth_mod.validate_session(token))
        admin_auth_mod.destroy_session(token)
        self.assertIsNone(admin_auth_mod.validate_session(token))

    def test_expired_session(self):
        token = admin_auth_mod.create_session("u3", "VIEWER", "10.0.0.3")
        # Manually expire the session
        session_path = os.path.join(self.tmp, 'sessions', f"{token}.json")
        with open(session_path) as f:
            session = json.load(f)
        session['expires_at'] = int(time.time()) - 100
        with open(session_path, 'w') as f:
            json.dump(session, f)
        self.assertIsNone(admin_auth_mod.validate_session(token))


# ---------------------------------------------------------------------------
# 3. admin_auth.py — JWT
# ---------------------------------------------------------------------------

class TestAdminAuthJWT(_AdminAuthTestBase):
    """Tests for custom JWT creation and verification."""

    def test_create_and_verify_jwt(self):
        token = admin_auth_mod.create_jwt("user-1", "ADMIN")
        self.assertIn('.', token)
        payload = admin_auth_mod.verify_jwt(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload['sub'], "user-1")
        self.assertEqual(payload['role'], "ADMIN")

    def test_verify_jwt_bad_signature(self):
        token = admin_auth_mod.create_jwt("user-1", "ADMIN")
        parts = token.split('.')
        parts[2] = "bad_signature"
        self.assertIsNone(admin_auth_mod.verify_jwt('.'.join(parts)))

    def test_verify_jwt_bad_format(self):
        self.assertIsNone(admin_auth_mod.verify_jwt("not.a.valid.jwt"))
        self.assertIsNone(admin_auth_mod.verify_jwt("no_dots"))

    def test_jwt_secret_auto_generation(self):
        with patch.dict(os.environ, {'YGB_JWT_SECRET': ''}):
            secret = admin_auth_mod._get_jwt_secret()
            self.assertEqual(len(secret), 64)


# ---------------------------------------------------------------------------
# 4. admin_auth.py — TOTP
# ---------------------------------------------------------------------------

class TestAdminAuthTOTP(unittest.TestCase):
    """Tests for TOTP using real crypto."""

    def test_generate_totp_secret(self):
        secret = admin_auth_mod.generate_totp_secret()
        self.assertGreater(len(secret), 10)

    def test_totp_uri_generation(self):
        secret = admin_auth_mod.generate_totp_secret()
        uri = admin_auth_mod.get_totp_uri(secret, "admin@example.com")
        self.assertIn("otpauth://totp/", uri)
        self.assertIn("admin", uri.lower())

    def test_verify_totp_wrong_code(self):
        secret = admin_auth_mod.generate_totp_secret()
        self.assertFalse(admin_auth_mod.verify_totp(secret, "000000"))


# ---------------------------------------------------------------------------
# 5. admin_auth.py — User Management
# ---------------------------------------------------------------------------

class TestAdminAuthUserManagement(_AdminAuthTestBase):
    """Tests for user registration and management."""

    def test_register_admin(self):
        result = admin_auth_mod.register_admin("new@test.com")
        self.assertIn('user_id', result)
        self.assertEqual(result['email'], "new@test.com")
        self.assertEqual(result['role'], "ADMIN")
        self.assertIn('totp_secret', result)
        self.assertIn('totp_uri', result)

    def test_register_duplicate_user(self):
        admin_auth_mod.register_admin("dup@test.com")
        result = admin_auth_mod.register_admin("dup@test.com")
        self.assertIn('error', result)

    def test_register_invalid_role(self):
        result = admin_auth_mod.register_admin("bad@test.com", role="SUPERADMIN")
        self.assertIn('error', result)

    def test_register_worker(self):
        result = admin_auth_mod.register_admin("worker@test.com", role="WORKER")
        self.assertEqual(result['role'], "WORKER")

    def test_get_user(self):
        admin_auth_mod.register_admin("found@test.com", role="WORKER")
        user = admin_auth_mod.get_user("found@test.com")
        self.assertIsNotNone(user)
        self.assertEqual(user['role'], "WORKER")

    def test_get_user_not_found(self):
        self.assertIsNone(admin_auth_mod.get_user("nonexistent@test.com"))

    def test_load_users_empty(self):
        data = admin_auth_mod._load_users()
        self.assertEqual(data, {'users': {}})


# ---------------------------------------------------------------------------
# 6. admin_auth.py — Login
# ---------------------------------------------------------------------------

class TestAdminAuthLogin(_AdminAuthTestBase):
    """Tests for the full login flow."""

    def test_login_unknown_user(self):
        result = admin_auth_mod.login("nobody@test.com", "123456", "1.2.3.4")
        self.assertEqual(result['status'], 'denied')

    def test_login_locked_out(self):
        admin_auth_mod.register_admin("locked@test.com")
        for _ in range(5):
            admin_auth_mod.record_failed_attempt("locked@test.com", "1.2.3.4")
        result = admin_auth_mod.login("locked@test.com", "123456", "1.2.3.4")
        self.assertEqual(result['status'], 'locked_out')

    def test_login_bad_totp(self):
        admin_auth_mod.register_admin("badotp@test.com")
        result = admin_auth_mod.login("badotp@test.com", "000000", "1.2.3.4")
        self.assertEqual(result['status'], 'denied')
        self.assertIn('attempts remaining', result['message'].lower())

    def test_login_prelocked_account(self):
        """Pre-lock account via record_failed_attempt, then verify login blocked."""
        admin_auth_mod.register_admin("lockme@test.com")
        # Pre-record 5 failed attempts to trigger lockout
        for _ in range(5):
            admin_auth_mod.record_failed_attempt("lockme@test.com", "1.2.3.4")
        # Next login should be blocked by lockout check
        result = admin_auth_mod.login("lockme@test.com", "000000", "1.2.3.4")
        self.assertEqual(result['status'], 'locked_out')


# ---------------------------------------------------------------------------
# 7. admin_auth.py — Auth Middleware
# ---------------------------------------------------------------------------

class TestAdminAuthMiddleware(_AdminAuthTestBase):
    """Tests for require_auth middleware."""

    def test_require_auth_bypass(self):
        with patch.dict(os.environ, {'YGB_TEMP_AUTH_BYPASS': 'true'}):
            result = admin_auth_mod.require_auth()
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['role'], 'ADMIN')

    def test_require_auth_session(self):
        token = admin_auth_mod.create_session("u1", "ADMIN", "10.0.0.1")
        with patch.dict(os.environ, {'YGB_TEMP_AUTH_BYPASS': 'false'}):
            result = admin_auth_mod.require_auth(session_token=token)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['user_id'], 'u1')

    def test_require_auth_jwt(self):
        jwt = admin_auth_mod.create_jwt("u2", "WORKER")
        with patch.dict(os.environ, {'YGB_TEMP_AUTH_BYPASS': 'false'}):
            result = admin_auth_mod.require_auth(jwt_token=jwt)
            self.assertEqual(result['status'], 'ok')
            self.assertEqual(result['user_id'], 'u2')

    def test_require_auth_no_creds(self):
        with patch.dict(os.environ, {'YGB_TEMP_AUTH_BYPASS': 'false'}):
            result = admin_auth_mod.require_auth()
            self.assertEqual(result['status'], 'unauthorized')

    def test_require_auth_role_check_pass(self):
        token = admin_auth_mod.create_session("u3", "ADMIN", "10.0.0.1")
        with patch.dict(os.environ, {'YGB_TEMP_AUTH_BYPASS': 'false'}):
            result = admin_auth_mod.require_auth(session_token=token, required_role='WORKER')
            self.assertEqual(result['status'], 'ok')

    def test_require_auth_role_check_fail(self):
        token = admin_auth_mod.create_session("u4", "VIEWER", "10.0.0.1")
        with patch.dict(os.environ, {'YGB_TEMP_AUTH_BYPASS': 'false'}):
            result = admin_auth_mod.require_auth(session_token=token, required_role='ADMIN')
            self.assertEqual(result['status'], 'forbidden')


# ---------------------------------------------------------------------------
# 8. admin_auth.py — Logout
# ---------------------------------------------------------------------------

class TestAdminAuthLogout(_AdminAuthTestBase):
    """Tests for logout."""

    def test_logout_destroys_session(self):
        token = admin_auth_mod.create_session("u5", "ADMIN", "10.0.0.1")
        self.assertIsNotNone(admin_auth_mod.validate_session(token))
        admin_auth_mod.logout(token)
        self.assertIsNone(admin_auth_mod.validate_session(token))

    def test_logout_bypass_mode(self):
        with patch.dict(os.environ, {'YGB_TEMP_AUTH_BYPASS': 'true'}):
            admin_auth_mod.logout('temporary-admin-bypass')

    def test_logout_nonexistent_session(self):
        admin_auth_mod.logout("a" * 64)


# ---------------------------------------------------------------------------
# 9. admin_auth.py — Audit
# ---------------------------------------------------------------------------

class TestAdminAuthAudit(_AdminAuthTestBase):
    """Tests for audit logging."""

    def test_audit_log_writes_to_file(self):
        admin_auth_mod.audit_log("TEST_ACTION", "user-1", "1.2.3.4", "test details")
        path = os.path.join(self.tmp, 'audit.json')
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            line = f.readline()
        entry = json.loads(line)
        self.assertEqual(entry['action'], 'TEST_ACTION')
        self.assertEqual(entry['user_id'], 'user-1')

    def test_audit_log_multiple_entries(self):
        for i in range(3):
            admin_auth_mod.audit_log(f"ACTION_{i}", f"user-{i}", "1.2.3.4")
        path = os.path.join(self.tmp, 'audit.json')
        with open(path) as f:
            lines = f.readlines()
        self.assertEqual(len(lines), 3)


# ---------------------------------------------------------------------------
# 10. field_progression_api.py — State persistence, runtime, handlers
# ---------------------------------------------------------------------------

class TestFieldProgressionStatePersistence(unittest.TestCase):
    """Tests for state save/load with real files."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'field_state.json')

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_and_load_state(self):
        from backend.api.field_progression_api import _default_state, _save_field_state, _load_field_state
        state = _default_state()
        with patch('backend.api.field_progression_api.FIELD_STATE_PATH', self.state_path):
            _save_field_state(state)
            loaded = _load_field_state()
        self.assertEqual(loaded['active_field_id'], 0)
        self.assertEqual(len(loaded['fields']), 23)

    def test_load_state_file_missing(self):
        from backend.api.field_progression_api import _load_field_state
        with patch('backend.api.field_progression_api.FIELD_STATE_PATH', self.state_path + '.missing'):
            state = _load_field_state()
        self.assertEqual(state['active_field_id'], 0)

    def test_load_state_corrupt_file(self):
        from backend.api.field_progression_api import _load_field_state
        with open(self.state_path, 'w') as f:
            f.write("not valid json")
        with patch('backend.api.field_progression_api.FIELD_STATE_PATH', self.state_path):
            state = _load_field_state()
        self.assertEqual(state['active_field_id'], 0)


class TestFieldProgressionRuntimeStatus(unittest.TestCase):
    """Tests for runtime status building."""

    def test_build_runtime_status_default(self):
        from backend.api.field_progression_api import _build_runtime_status, _default_state
        state = _default_state()
        with patch('backend.api.field_progression_api.RUNTIME_STATE_PATH', '/nonexistent/path'):
            runtime = _build_runtime_status(state)
        self.assertFalse(runtime['containment_active'])
        self.assertIsNone(runtime['freeze_valid'])

    def test_build_runtime_status_with_persisted_data(self):
        from backend.api.field_progression_api import _build_runtime_status, _default_state
        state = _default_state()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({'containment_active': True, 'gpu_utilization': 85.5, 'determinism_pass': True}, f)
            path = f.name
        try:
            with patch('backend.api.field_progression_api.RUNTIME_STATE_PATH', path):
                runtime = _build_runtime_status(state)
            self.assertTrue(runtime['containment_active'])
            self.assertEqual(runtime['gpu_utilization'], 85.5)
        finally:
            os.unlink(path)

    def test_build_runtime_status_demoted_field(self):
        from backend.api.field_progression_api import _build_runtime_status, _default_state
        state = _default_state()
        state['fields'][0]['demoted'] = True
        state['fields'][0]['name'] = "Test Field"
        with patch('backend.api.field_progression_api.RUNTIME_STATE_PATH', '/nonexistent'):
            runtime = _build_runtime_status(state)
        self.assertTrue(runtime['containment_active'])
        self.assertIn("Test Field", runtime['containment_reason'])

    def test_build_runtime_corrupt_file(self):
        from backend.api.field_progression_api import _build_runtime_status, _default_state
        state = _default_state()
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not json")
            path = f.name
        try:
            with patch('backend.api.field_progression_api.RUNTIME_STATE_PATH', path):
                runtime = _build_runtime_status(state)
            self.assertFalse(runtime['containment_active'])
        finally:
            os.unlink(path)


class TestFieldProgressionHandlers(unittest.TestCase):
    """Tests for endpoint handler functions."""

    def test_get_active_progress(self):
        from backend.api.field_progression_api import get_active_progress, _default_state
        with patch('backend.api.field_progression_api._load_field_state', return_value=_default_state()):
            result = get_active_progress()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['active_field']['id'], 0)

    def test_get_active_progress_all_complete(self):
        from backend.api.field_progression_api import get_active_progress, _default_state, TOTAL_FIELDS
        state = _default_state()
        state['active_field_id'] = TOTAL_FIELDS
        state['certified_count'] = TOTAL_FIELDS
        with patch('backend.api.field_progression_api._load_field_state', return_value=state):
            result = get_active_progress()
        self.assertEqual(result['status'], 'all_complete')

    def test_signed_approval_status_no_ledger(self):
        from backend.api.field_progression_api import _signed_approval_status
        with patch('backend.api.field_progression_api.APPROVAL_LEDGER_PATH', '/nonexistent/ledger.jsonl'):
            result = _signed_approval_status(0)
        self.assertFalse(result['has_signed_approval'])

    def test_save_runtime_status(self):
        from backend.api.field_progression_api import _save_runtime_status
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'runtime_status.json')
            with patch('backend.api.field_progression_api.RUNTIME_STATE_PATH', path):
                _save_runtime_status({'gpu_utilization': 90.0})
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(data['gpu_utilization'], 90.0)

    def test_advance_past_end(self):
        from backend.api.field_progression_api import _advance_to_next_field, _default_state, TOTAL_FIELDS
        state = _default_state()
        state['active_field_id'] = TOTAL_FIELDS - 1
        result = _advance_to_next_field(state)
        self.assertIsNone(result)

    def test_start_hunt_no_authority(self):
        from backend.api.field_progression_api import start_hunt
        with patch('backend.api.field_progression_api.AuthorityLock') as MockAuth:
            MockAuth.verify_all_locked.return_value = {'all_locked': False, 'violations': ['key1']}
            result = start_hunt()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['gate'], 'AUTHORITY_LOCK')

    def test_start_hunt_not_certified(self):
        from backend.api.field_progression_api import start_hunt, _default_state
        state = _default_state()
        with patch('backend.api.field_progression_api.AuthorityLock') as MockAuth:
            MockAuth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                result = start_hunt()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['gate'], 'CERTIFICATION')

    def test_start_hunt_not_frozen(self):
        from backend.api.field_progression_api import start_hunt, _default_state
        state = _default_state()
        state['fields'][0]['certified'] = True
        state['fields'][0]['frozen'] = False
        with patch('backend.api.field_progression_api.AuthorityLock') as MockAuth:
            MockAuth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                result = start_hunt()
        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['gate'], 'FREEZE')

    def test_start_training_no_authority(self):
        from backend.api.field_progression_api import start_training
        with patch('backend.api.field_progression_api.AuthorityLock') as MockAuth:
            MockAuth.verify_all_locked.return_value = {'all_locked': False, 'violations': ['key1']}
            result = start_training()
        self.assertEqual(result['status'], 'error')
        self.assertIn('AUTHORITY_VIOLATION', result['message'])

    def test_start_training_all_complete(self):
        from backend.api.field_progression_api import start_training, _default_state, TOTAL_FIELDS
        state = _default_state()
        state['active_field_id'] = TOTAL_FIELDS
        with patch('backend.api.field_progression_api.AuthorityLock') as MockAuth:
            MockAuth.verify_all_locked.return_value = {'all_locked': True, 'violations': []}
            with patch('backend.api.field_progression_api._load_field_state', return_value=state):
                result = start_training()
        self.assertEqual(result['status'], 'error')
        self.assertIn('ALL_FIELDS_COMPLETE', result['message'])


if __name__ == "__main__":
    unittest.main()
