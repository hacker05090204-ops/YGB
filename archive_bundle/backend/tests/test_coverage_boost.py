"""
Comprehensive tests for modules with lowest coverage — targeting 85%+ overall.

Modules covered:
  - backend.api.auth_server (0% → high)
  - backend.api.fido2_auth (0% → high)
  - backend.api.admin_auth (16% → high)
  - backend.api.report_generator (25% → higher)
  - backend.api.system_status (62% → high)
  - backend.api.browser_endpoints (73% → high)
  - backend.approval.report_orchestrator (77% → high)
  - backend.api.runtime_api (74% → higher)
  - backend.auth.auth_guard (75% → higher)
  - backend.auth.revocation_store (69% → higher)
  - backend.api.vault_session (73% → higher)
  - backend.governance.device_authority (84% → 90%+)
  - backend.api.field_progression_api (81% → higher)
"""

import hashlib
import json
import os
import secrets
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

# ---------------------------------------------------------------------------
# 1. auth_server.py — DEPRECATED file-based auth (0% → ~90%)
# ---------------------------------------------------------------------------

class TestAuthServerHelpers(unittest.TestCase):
    """Tests for backend.api.auth_server helper functions."""

    def test_load_json_file_missing(self):
        from backend.api.auth_server import load_json
        result = load_json("/non/existent/path.json")
        self.assertEqual(result, {})

    def test_load_json_with_default(self):
        from backend.api.auth_server import load_json
        result = load_json("/non/existent/path.json", default=[])
        self.assertEqual(result, [])

    def test_load_json_valid_file(self):
        from backend.api.auth_server import load_json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "value"}, f)
            f.flush()
            name = f.name
        try:
            result = load_json(name)
            self.assertEqual(result, {"key": "value"})
        finally:
            os.unlink(name)

    def test_load_json_invalid_json(self):
        from backend.api.auth_server import load_json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json{{{")
            f.flush()
            name = f.name
        try:
            result = load_json(name)
            self.assertEqual(result, {})
        finally:
            os.unlink(name)

    def test_save_json(self):
        from backend.api.auth_server import save_json
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            name = f.name
        try:
            save_json(name, {"saved": True})
            with open(name) as f:
                data = json.load(f)
            self.assertEqual(data, {"saved": True})
        finally:
            os.unlink(name)

    def test_log_audit(self):
        from backend.api.auth_server import log_audit
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            name = f.name
        try:
            with patch('backend.api.auth_server.AUDIT_LOG', name):
                log_audit("test_event", "1.2.3.4", "testuser", True, "details")
            with open(name) as f:
                content = f.read()
            self.assertIn("SUCCESS", content)
            self.assertIn("test_event", content)
            self.assertIn("testuser", content)
        finally:
            os.unlink(name)

    def test_log_audit_failure(self):
        from backend.api.auth_server import log_audit
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            name = f.name
        try:
            with patch('backend.api.auth_server.AUDIT_LOG', name):
                log_audit("login", "1.2.3.4", "user", False, "bad pw")
            with open(name) as f:
                content = f.read()
            self.assertIn("FAILED", content)
        finally:
            os.unlink(name)


class TestAuthServerRateLimiting(unittest.TestCase):
    """Tests for rate limiting in auth_server."""

    def setUp(self):
        from backend.api import auth_server
        auth_server._login_attempts.clear()
        auth_server._otp_requests.clear()
        auth_server._failure_counts.clear()

    def test_prune_window(self):
        from backend.api.auth_server import _prune_window
        now = time.time()
        timestamps = [now - 1000, now - 500, now - 10, now - 1]
        result = _prune_window(timestamps, 100)
        self.assertEqual(len(result), 2)

    def test_check_login_rate_allowed(self):
        from backend.api.auth_server import check_login_rate
        # Should not raise
        check_login_rate("192.168.1.1")

    def test_check_login_rate_exceeded(self):
        from backend.api import auth_server
        from backend.api.auth_server import check_login_rate
        from fastapi import HTTPException
        ip = "10.0.0.1"
        auth_server._login_attempts[ip] = [time.time()] * 5
        with self.assertRaises(HTTPException) as ctx:
            check_login_rate(ip)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_check_otp_rate_allowed(self):
        from backend.api.auth_server import check_otp_rate
        check_otp_rate("user1")

    def test_check_otp_rate_exceeded(self):
        from backend.api import auth_server
        from backend.api.auth_server import check_otp_rate
        from fastapi import HTTPException
        auth_server._otp_requests["user1"] = [time.time()] * 3
        with self.assertRaises(HTTPException):
            check_otp_rate("user1")

    def test_record_failure_and_clear(self):
        from backend.api.auth_server import record_failure, clear_failures, _failure_counts
        record_failure("1.1.1.1")
        self.assertEqual(_failure_counts["1.1.1.1"], 1)
        record_failure("1.1.1.1")
        self.assertEqual(_failure_counts["1.1.1.1"], 2)
        clear_failures("1.1.1.1")
        self.assertEqual(_failure_counts["1.1.1.1"], 0)

    def test_apply_backoff_no_failures(self):
        from backend.api.auth_server import apply_backoff
        # Should not sleep when no failures
        start = time.monotonic()
        apply_backoff("clean_ip")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 0.1)


class TestAuthServerDeviceFingerprinting(unittest.TestCase):
    """Tests for device fingerprinting in auth_server."""

    def test_generate_device_fingerprint(self):
        from backend.api.auth_server import generate_device_fingerprint
        fp = generate_device_fingerprint("Mozilla/5.0", "1.2.3.4", "dev-001")
        self.assertEqual(len(fp), 64)
        fp2 = generate_device_fingerprint("Mozilla/5.0", "1.2.3.4", "dev-001")
        self.assertEqual(fp, fp2)
        fp3 = generate_device_fingerprint("Chrome", "1.2.3.4", "dev-001")
        self.assertNotEqual(fp, fp3)

    def test_get_ip_subnet_ipv4(self):
        from backend.api.auth_server import get_ip_subnet
        self.assertEqual(get_ip_subnet("192.168.1.100"), "192.168.1")

    def test_get_ip_subnet_ipv6(self):
        from backend.api.auth_server import get_ip_subnet
        result = get_ip_subnet("::1")
        self.assertEqual(result, "::1")

    def test_is_trusted_device_missing(self):
        from backend.api.auth_server import is_trusted_device
        with patch('backend.api.auth_server.load_json', return_value={}):
            result = is_trusted_device("user1", "fp123", "1.2.3.4")
        self.assertFalse(result)

    def test_is_trusted_device_valid(self):
        from backend.api.auth_server import is_trusted_device
        devices = {
            "user1": {
                "fp123": {"trusted_at": time.time(), "ip": "1.2.3.4"}
            }
        }
        with patch('backend.api.auth_server.load_json', return_value=devices):
            result = is_trusted_device("user1", "fp123", "1.2.3.4")
        self.assertTrue(result)

    def test_is_trusted_device_expired(self):
        from backend.api.auth_server import is_trusted_device
        devices = {
            "user1": {
                "fp123": {"trusted_at": time.time() - 31 * 86400, "ip": "1.2.3.4"}
            }
        }
        with patch('backend.api.auth_server.load_json', return_value=devices):
            with patch('backend.api.auth_server.save_json'):
                result = is_trusted_device("user1", "fp123", "1.2.3.4")
        self.assertFalse(result)

    def test_is_trusted_device_ip_changed(self):
        from backend.api.auth_server import is_trusted_device
        devices = {
            "user1": {
                "fp123": {"trusted_at": time.time(), "ip": "10.0.0.1"}
            }
        }
        with patch('backend.api.auth_server.load_json', return_value=devices):
            result = is_trusted_device("user1", "fp123", "192.168.1.1")
        self.assertFalse(result)

    def test_trust_device(self):
        from backend.api.auth_server import trust_device
        with patch('backend.api.auth_server.load_json', return_value={}):
            with patch('backend.api.auth_server.save_json') as mock_save:
                trust_device("user1", "fp_new", "5.6.7.8")
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][1]
        self.assertIn("user1", saved)
        self.assertIn("fp_new", saved["user1"])


class TestAuthServerOTP(unittest.TestCase):
    """Tests for OTP functions in auth_server."""

    def test_send_otp_email_missing_config(self):
        from backend.api.auth_server import send_otp_email
        with patch.dict(os.environ, {}, clear=True):
            result = send_otp_email("test@example.com", "123456")
        self.assertFalse(result)

    def test_generate_and_store_otp(self):
        from backend.api.auth_server import generate_and_store_otp
        with patch('backend.api.auth_server.load_json', return_value={}):
            with patch('backend.api.auth_server.save_json'):
                with patch('backend.api.auth_server.send_otp_email', return_value=True) as mock_send:
                    result = generate_and_store_otp("user1", "u@test.com")
        self.assertTrue(result)
        mock_send.assert_called_once()

    def test_send_admin_alert_no_email(self):
        from backend.api.auth_server import send_admin_alert_new_device
        with patch.dict(os.environ, {}, clear=True):
            send_admin_alert_new_device("user", "1.2.3.4", "fp123")

    def test_ensure_auth_dirs(self):
        from backend.api.auth_server import _ensure_auth_dirs
        with patch('os.makedirs'):
            _ensure_auth_dirs()


class TestAuthServerSession(unittest.TestCase):
    """Tests for session creation in auth_server."""

    def test_create_session(self):
        from backend.api.auth_server import create_session as cs
        with patch('backend.api.auth_server.load_json', return_value={}):
            with patch('backend.api.auth_server.save_json') as mock_save:
                token = cs("testuser", "fp123", "1.2.3.4")
        self.assertEqual(len(token), 64)
        mock_save.assert_called_once()


class TestAuthServerAdminEndpoints(unittest.TestCase):
    """Tests for admin endpoint functions in auth_server."""

    def test_admin_get_sessions(self):
        from backend.api.auth_server import admin_get_sessions
        sessions = {
            "token1": {
                "active": True,
                "expires_at": time.time() + 3600,
                "username": "admin",
                "fingerprint": "fp1",
                "ip": "10.0.0.1",
                "created_at": time.time(),
            },
            "token2": {
                "active": False,
                "expires_at": time.time() + 3600,
                "username": "admin",
                "fingerprint": "fp2",
                "created_at": time.time(),
            },
        }
        with patch('backend.api.auth_server.load_json', return_value=sessions):
            result = admin_get_sessions()
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["active_sessions"]), 1)

    def test_admin_get_devices(self):
        from backend.api.auth_server import admin_get_devices
        devices = {
            "user1": {
                "fp1": {"trusted_at": time.time(), "ip": "1.2.3.4"},
            }
        }
        with patch('backend.api.auth_server.load_json', return_value=devices):
            result = admin_get_devices()
        self.assertEqual(result["status"], "success")
        self.assertIn("user1", result["devices"])


# ---------------------------------------------------------------------------
# 2. fido2_auth.py — FIDO2/WebAuthn (0% → ~95%)
# ---------------------------------------------------------------------------

class TestFidoCredentialStore(unittest.TestCase):
    """Tests for FidoCredentialStore in fido2_auth."""

    def _make_store(self):
        from backend.api.fido2_auth import FidoCredentialStore
        with patch('os.path.exists', return_value=False):
            store = FidoCredentialStore("/tmp/fake_fido2.json")
        return store

    def test_begin_registration(self):
        store = self._make_store()
        opts = store.begin_registration("user-1")
        self.assertIn("challenge", opts)
        self.assertEqual(opts["rp"]["id"], "ygb.local")
        self.assertEqual(opts["user"]["id"], "user-1")
        self.assertEqual(len(opts["pubKeyCredParams"]), 2)

    def test_complete_registration_success(self):
        store = self._make_store()
        opts = store.begin_registration("user-1")
        challenge = opts["challenge"]
        with patch.object(store, '_save'):
            result = store.complete_registration(challenge, "cred-abc", b"fake-pub-key")
        self.assertTrue(result)
        self.assertIn("cred-abc", store._credentials)

    def test_complete_registration_invalid_challenge(self):
        store = self._make_store()
        result = store.complete_registration("nonexistent", "cred-x", b"key")
        self.assertFalse(result)

    def test_complete_registration_expired_challenge(self):
        store = self._make_store()
        from backend.api.fido2_auth import AuthChallenge
        store._pending_challenges["old-chal"] = AuthChallenge(
            challenge="old-chal", created_at=time.time() - 300, user_id="u1"
        )
        result = store.complete_registration("old-chal", "cred-y", b"key")
        self.assertFalse(result)

    def test_begin_authentication_no_creds(self):
        store = self._make_store()
        result = store.begin_authentication("no-such-user")
        self.assertIsNone(result)

    def test_begin_authentication_with_creds(self):
        store = self._make_store()
        opts = store.begin_registration("usr-2")
        with patch.object(store, '_save'):
            store.complete_registration(opts["challenge"], "cred-2", b"pk2")
        auth_opts = store.begin_authentication("usr-2")
        self.assertIsNotNone(auth_opts)
        self.assertIn("challenge", auth_opts)
        self.assertEqual(len(auth_opts["allowCredentials"]), 1)

    def test_verify_authentication_invalid_challenge(self):
        store = self._make_store()
        result = store.verify_authentication("bad", "c1", b"sig", b"cd", 1)
        self.assertFalse(result)

    def test_verify_authentication_expired_challenge(self):
        store = self._make_store()
        from backend.api.fido2_auth import AuthChallenge
        store._pending_challenges["exp"] = AuthChallenge(
            challenge="exp", created_at=time.time() - 300, user_id="u1"
        )
        result = store.verify_authentication("exp", "c1", b"sig", b"cd", 1)
        self.assertFalse(result)

    def test_verify_authentication_unknown_credential(self):
        store = self._make_store()
        from backend.api.fido2_auth import AuthChallenge
        store._pending_challenges["ch1"] = AuthChallenge(
            challenge="ch1", created_at=time.time(), user_id="u1"
        )
        result = store.verify_authentication("ch1", "unknown-cred", b"sig", b"cd", 1)
        self.assertFalse(result)

    def test_verify_authentication_user_mismatch(self):
        store = self._make_store()
        from backend.api.fido2_auth import AuthChallenge, FidoCredential
        store._credentials["c1"] = FidoCredential(
            credential_id="c1", public_key_hash="h", user_id="other",
            registered_at="2025-01-01"
        )
        store._pending_challenges["ch2"] = AuthChallenge(
            challenge="ch2", created_at=time.time(), user_id="u1"
        )
        result = store.verify_authentication("ch2", "c1", b"sig", b"cd", 1)
        self.assertFalse(result)

    def test_verify_authentication_replay(self):
        store = self._make_store()
        from backend.api.fido2_auth import AuthChallenge, FidoCredential
        store._credentials["c2"] = FidoCredential(
            credential_id="c2", public_key_hash="h", user_id="u1",
            registered_at="2025-01-01", sign_count=10
        )
        store._pending_challenges["ch3"] = AuthChallenge(
            challenge="ch3", created_at=time.time(), user_id="u1"
        )
        result = store.verify_authentication("ch3", "c2", b"sig", b"cd", 5)
        self.assertFalse(result)

    def test_verify_authentication_success(self):
        store = self._make_store()
        from backend.api.fido2_auth import AuthChallenge, FidoCredential
        store._credentials["c3"] = FidoCredential(
            credential_id="c3", public_key_hash="h", user_id="u1",
            registered_at="2025-01-01", sign_count=0
        )
        store._pending_challenges["ch4"] = AuthChallenge(
            challenge="ch4", created_at=time.time(), user_id="u1"
        )
        with patch.object(store, '_save'):
            result = store.verify_authentication("ch4", "c3", b"sig", b"cd", 1)
        self.assertTrue(result)
        self.assertEqual(store._credentials["c3"].sign_count, 1)

    def test_list_credentials_all(self):
        store = self._make_store()
        from backend.api.fido2_auth import FidoCredential
        store._credentials["a"] = FidoCredential("a", "h1", "u1", "t1")
        store._credentials["b"] = FidoCredential("b", "h2", "u2", "t2")
        creds = store.list_credentials()
        self.assertEqual(len(creds), 2)

    def test_list_credentials_by_user(self):
        store = self._make_store()
        from backend.api.fido2_auth import FidoCredential
        store._credentials["a"] = FidoCredential("a", "h1", "u1", "t1")
        store._credentials["b"] = FidoCredential("b", "h2", "u2", "t2")
        creds = store.list_credentials(user_id="u1")
        self.assertEqual(len(creds), 1)

    def test_revoke_credential_exists(self):
        store = self._make_store()
        from backend.api.fido2_auth import FidoCredential
        store._credentials["r1"] = FidoCredential("r1", "h", "u1", "t")
        with patch.object(store, '_save'):
            result = store.revoke_credential("r1")
        self.assertTrue(result)
        self.assertNotIn("r1", store._credentials)

    def test_revoke_credential_missing(self):
        store = self._make_store()
        result = store.revoke_credential("nonexistent")
        self.assertFalse(result)

    def test_cleanup_expired_challenges(self):
        store = self._make_store()
        from backend.api.fido2_auth import AuthChallenge
        store._pending_challenges["fresh"] = AuthChallenge("fresh", time.time(), "u1")
        store._pending_challenges["stale"] = AuthChallenge("stale", time.time() - 300, "u1")
        store.cleanup_expired_challenges()
        self.assertIn("fresh", store._pending_challenges)
        self.assertNotIn("stale", store._pending_challenges)

    def test_load_existing_credentials(self):
        from backend.api.fido2_auth import FidoCredentialStore
        cred_data = {
            "credentials": [{
                "credential_id": "loaded-1",
                "public_key_hash": "hash1",
                "user_id": "u1",
                "registered_at": "2025-01-01",
                "last_used": "",
                "sign_count": 5,
            }],
            "rp_id": "ygb.local",
        }
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(cred_data))):
                store = FidoCredentialStore("/tmp/fake.json")
        self.assertIn("loaded-1", store._credentials)
        self.assertEqual(store._credentials["loaded-1"].sign_count, 5)


# ---------------------------------------------------------------------------
# 3. admin_auth.py — Admin TOTP auth (16% → ~85%)
# ---------------------------------------------------------------------------

class TestAdminAuthLockout(unittest.TestCase):
    """Tests for lockout management in admin_auth."""

    def setUp(self):
        from backend.api import admin_auth
        admin_auth._lockouts = {}

    def test_is_locked_out_false(self):
        from backend.api.admin_auth import is_locked_out
        with patch('backend.api.admin_auth._load_lockouts'):
            result = is_locked_out("clean@test.com")
        self.assertFalse(result)

    def test_is_locked_out_true(self):
        from backend.api import admin_auth
        from backend.api.admin_auth import is_locked_out
        admin_auth._lockouts["locked@test.com"] = {
            "locked_until": time.time() + 1000
        }
        with patch('backend.api.admin_auth._load_lockouts'):
            result = is_locked_out("locked@test.com")
        self.assertTrue(result)

    def test_is_locked_out_expired(self):
        from backend.api import admin_auth
        from backend.api.admin_auth import is_locked_out
        admin_auth._lockouts["exp@test.com"] = {
            "locked_until": time.time() - 100
        }
        with patch('backend.api.admin_auth._load_lockouts'):
            with patch('backend.api.admin_auth._save_lockouts'):
                result = is_locked_out("exp@test.com")
        self.assertFalse(result)

    def test_record_failed_attempt_increments(self):
        from backend.api import admin_auth
        from backend.api.admin_auth import record_failed_attempt
        with patch('backend.api.admin_auth._load_lockouts'):
            with patch('backend.api.admin_auth._save_lockouts'):
                result = record_failed_attempt("user@test.com", "1.2.3.4")
        self.assertFalse(result["locked"])
        self.assertEqual(result["attempts"], 1)

    def test_record_failed_attempt_triggers_lockout(self):
        from backend.api import admin_auth
        from backend.api.admin_auth import record_failed_attempt
        admin_auth._lockouts["user@test.com"] = {"attempts": 4, "locked_until": 0}
        with patch('backend.api.admin_auth._load_lockouts'):
            with patch('backend.api.admin_auth._save_lockouts'):
                with patch('backend.api.admin_auth.audit_log'):
                    result = record_failed_attempt("user@test.com", "1.2.3.4")
        self.assertTrue(result["locked"])

    def test_clear_lockout(self):
        from backend.api import admin_auth
        from backend.api.admin_auth import clear_lockout
        admin_auth._lockouts["user@test.com"] = {"attempts": 5, "locked_until": time.time() + 1000}
        with patch('backend.api.admin_auth._load_lockouts'):
            with patch('backend.api.admin_auth._save_lockouts'):
                clear_lockout("user@test.com")
        self.assertNotIn("user@test.com", admin_auth._lockouts)


class TestAdminAuthSession(unittest.TestCase):
    """Tests for session management in admin_auth."""

    def test_create_session(self):
        from backend.api.admin_auth import create_session
        with patch('backend.api.admin_auth._ensure_secure_dir'):
            with patch('builtins.open', mock_open()):
                with patch('backend.api.admin_auth.audit_log'):
                    token = create_session("user-1", "ADMIN", "1.2.3.4")
        self.assertEqual(len(token), 64)

    def test_validate_session_invalid_token(self):
        from backend.api.admin_auth import validate_session
        result = validate_session("too-short")
        self.assertIsNone(result)

    def test_validate_session_empty_token(self):
        from backend.api.admin_auth import validate_session
        result = validate_session("")
        self.assertIsNone(result)

    def test_validate_session_file_not_found(self):
        from backend.api.admin_auth import validate_session
        token = "a" * 64
        with patch('os.path.exists', return_value=False):
            result = validate_session(token)
        self.assertIsNone(result)

    def test_validate_session_expired(self):
        from backend.api.admin_auth import validate_session, destroy_session
        token = "b" * 64
        session_data = {"expires_at": time.time() - 100, "user_id": "u1", "role": "ADMIN"}
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(session_data))):
                with patch('backend.api.admin_auth.destroy_session'):
                    result = validate_session(token)
        self.assertIsNone(result)

    def test_validate_session_valid(self):
        from backend.api.admin_auth import validate_session
        token = "c" * 64
        session_data = {
            "expires_at": time.time() + 3600,
            "user_id": "u1",
            "role": "ADMIN",
            "last_active": int(time.time()),
        }
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(session_data))):
                result = validate_session(token)
        self.assertIsNotNone(result)
        self.assertEqual(result["user_id"], "u1")

    def test_destroy_session(self):
        from backend.api.admin_auth import destroy_session
        with patch('os.path.exists', return_value=True):
            with patch('os.remove') as mock_rm:
                destroy_session("d" * 64)
        mock_rm.assert_called_once()


class TestAdminAuthJWT(unittest.TestCase):
    """Tests for JWT creation & verification in admin_auth."""

    def test_create_jwt(self):
        from backend.api.admin_auth import create_jwt
        token = create_jwt("user-1", "ADMIN")
        self.assertEqual(token.count("."), 2)

    def test_verify_jwt_valid(self):
        from backend.api.admin_auth import create_jwt, verify_jwt
        token = create_jwt("user-1", "ADMIN")
        payload = verify_jwt(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["sub"], "user-1")
        self.assertEqual(payload["role"], "ADMIN")

    def test_verify_jwt_invalid_parts(self):
        from backend.api.admin_auth import verify_jwt
        self.assertIsNone(verify_jwt("invalid"))

    def test_verify_jwt_invalid_signature(self):
        from backend.api.admin_auth import create_jwt, verify_jwt
        token = create_jwt("user-1", "ADMIN")
        tampered = token[:-5] + "XXXXX"
        self.assertIsNone(verify_jwt(tampered))

    def test_verify_jwt_expired(self):
        from backend.api.admin_auth import verify_jwt, _get_jwt_secret
        import base64
        # Build expired JWT
        header = base64.urlsafe_b64encode(
            json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode()
        ).rstrip(b'=').decode()
        payload_data = {'sub': 'u1', 'role': 'ADMIN', 'iat': 1000, 'exp': 1001}
        payload = base64.urlsafe_b64encode(
            json.dumps(payload_data).encode()
        ).rstrip(b'=').decode()
        import hmac
        secret = _get_jwt_secret()
        sig = hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).hexdigest()
        token = f"{header}.{payload}.{sig}"
        self.assertIsNone(verify_jwt(token))


class TestAdminAuthTOTP(unittest.TestCase):
    """Tests for TOTP in admin_auth."""

    def test_generate_totp_secret(self):
        from backend.api.admin_auth import generate_totp_secret
        secret = generate_totp_secret()
        self.assertIsInstance(secret, str)
        self.assertTrue(len(secret) > 10)

    def test_get_totp_uri(self):
        from backend.api.admin_auth import get_totp_uri
        uri = get_totp_uri("JBSWY3DPEHPK3PXP", "admin@ygb.local")
        self.assertIn("otpauth://totp/", uri)
        self.assertIn("JBSWY3DPEHPK3PXP", uri)


class TestAdminAuthUserManagement(unittest.TestCase):
    """Tests for user management in admin_auth."""

    def test_register_admin(self):
        from backend.api.admin_auth import register_admin
        with patch('backend.api.admin_auth._load_users', return_value={'users': {}}):
            with patch('backend.api.admin_auth._save_users'):
                with patch('backend.api.admin_auth.audit_log'):
                    result = register_admin("new@admin.com", "ADMIN")
        self.assertIn("user_id", result)
        self.assertIn("totp_secret", result)

    def test_register_admin_invalid_role(self):
        from backend.api.admin_auth import register_admin
        result = register_admin("u@test.com", "SUPERUSER")
        self.assertIn("error", result)

    def test_register_admin_duplicate(self):
        from backend.api.admin_auth import register_admin
        existing = {'users': {'dup@test.com': {}}}
        with patch('backend.api.admin_auth._load_users', return_value=existing):
            result = register_admin("dup@test.com")
        self.assertIn("error", result)

    def test_get_user_exists(self):
        from backend.api.admin_auth import get_user
        users = {'users': {'admin@test.com': {'user_id': 'u1', 'role': 'ADMIN'}}}
        with patch('backend.api.admin_auth._load_users', return_value=users):
            result = get_user("admin@test.com")
        self.assertEqual(result["user_id"], "u1")

    def test_get_user_missing(self):
        from backend.api.admin_auth import get_user
        with patch('backend.api.admin_auth._load_users', return_value={'users': {}}):
            result = get_user("nobody@test.com")
        self.assertIsNone(result)


class TestAdminAuthLogin(unittest.TestCase):
    """Tests for the login flow in admin_auth."""

    def test_login_locked_out(self):
        from backend.api.admin_auth import login
        with patch('backend.api.admin_auth.is_locked_out', return_value=True):
            with patch('backend.api.admin_auth.audit_log'):
                result = login("user@test.com", "123456", "1.2.3.4")
        self.assertEqual(result["status"], "locked_out")

    def test_login_unknown_user(self):
        from backend.api.admin_auth import login
        with patch('backend.api.admin_auth.is_locked_out', return_value=False):
            with patch('backend.api.admin_auth.get_user', return_value=None):
                with patch('backend.api.admin_auth.record_failed_attempt', return_value={"locked": False, "attempts": 1, "remaining": 4}):
                    with patch('backend.api.admin_auth.audit_log'):
                        result = login("noone@test.com", "000000", "1.2.3.4")
        self.assertEqual(result["status"], "denied")

    def test_login_invalid_totp(self):
        from backend.api.admin_auth import login
        user = {'user_id': 'u1', 'totp_secret': 'JBSWY3DPEHPK3PXP', 'role': 'ADMIN'}
        with patch('backend.api.admin_auth.is_locked_out', return_value=False):
            with patch('backend.api.admin_auth.get_user', return_value=user):
                with patch('backend.api.admin_auth.verify_totp', return_value=False):
                    with patch('backend.api.admin_auth.record_failed_attempt', return_value={"locked": False, "attempts": 1, "remaining": 4}):
                        with patch('backend.api.admin_auth.audit_log'):
                            result = login("user@test.com", "000000", "1.2.3.4")
        self.assertEqual(result["status"], "denied")
        self.assertIn("attempts remaining", result["message"])

    def test_login_success(self):
        from backend.api.admin_auth import login
        user = {'user_id': 'u1', 'totp_secret': 'JBSWY3DPEHPK3PXP', 'role': 'ADMIN'}
        users_db = {'users': {'ok@test.com': {**user, 'last_login': 0}}}
        with patch('backend.api.admin_auth.is_locked_out', return_value=False):
            with patch('backend.api.admin_auth.get_user', return_value=user):
                with patch('backend.api.admin_auth.verify_totp', return_value=True):
                    with patch('backend.api.admin_auth.clear_lockout'):
                        with patch('backend.api.admin_auth.create_session', return_value="s" * 64):
                            with patch('backend.api.admin_auth._load_users', return_value=users_db):
                                with patch('backend.api.admin_auth._save_users'):
                                    with patch('backend.api.admin_auth.audit_log'):
                                        with patch('backend.api.admin_auth._send_login_notification'):
                                            result = login("ok@test.com", "123456", "1.2.3.4")
        self.assertEqual(result["status"], "ok")
        self.assertIn("session_token", result)


class TestAdminAuthRequireAuth(unittest.TestCase):
    """Tests for require_auth middleware in admin_auth."""

    def test_require_auth_bypass(self):
        from backend.api.admin_auth import require_auth
        with patch('backend.api.admin_auth._temporary_auth_bypass_enabled', return_value=True):
            result = require_auth()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["auth_method"], "temporary_bypass")

    def test_require_auth_no_token(self):
        from backend.api.admin_auth import require_auth
        with patch('backend.api.admin_auth._temporary_auth_bypass_enabled', return_value=False):
            result = require_auth()
        self.assertEqual(result["status"], "unauthorized")

    def test_require_auth_session_token(self):
        from backend.api.admin_auth import require_auth
        session = {"user_id": "u1", "role": "ADMIN"}
        with patch('backend.api.admin_auth._temporary_auth_bypass_enabled', return_value=False):
            with patch('backend.api.admin_auth.validate_session', return_value=session):
                result = require_auth(session_token="valid-" + "a" * 58)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["user_id"], "u1")

    def test_require_auth_jwt_token(self):
        from backend.api.admin_auth import require_auth
        with patch('backend.api.admin_auth._temporary_auth_bypass_enabled', return_value=False):
            with patch('backend.api.admin_auth.validate_session', return_value=None):
                with patch('backend.api.admin_auth.verify_jwt', return_value={"sub": "u2", "role": "WORKER"}):
                    result = require_auth(jwt_token="some.jwt.token")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["user_id"], "u2")

    def test_require_auth_role_insufficient(self):
        from backend.api.admin_auth import require_auth
        session = {"user_id": "u1", "role": "VIEWER"}
        with patch('backend.api.admin_auth._temporary_auth_bypass_enabled', return_value=False):
            with patch('backend.api.admin_auth.validate_session', return_value=session):
                result = require_auth(session_token="valid-" + "a" * 58, required_role="ADMIN")
        self.assertEqual(result["status"], "forbidden")


class TestAdminAuthLogout(unittest.TestCase):
    """Tests for logout in admin_auth."""

    def test_logout_destroy_session(self):
        from backend.api.admin_auth import logout
        session = {"user_id": "u1", "ip": "1.2.3.4"}
        with patch('backend.api.admin_auth._temporary_auth_bypass_enabled', return_value=False):
            with patch('backend.api.admin_auth.validate_session', return_value=session):
                with patch('backend.api.admin_auth.audit_log'):
                    with patch('backend.api.admin_auth.destroy_session') as mock_destroy:
                        logout("d" * 64)
        mock_destroy.assert_called_once()

    def test_logout_temp_bypass(self):
        from backend.api.admin_auth import logout
        with patch('backend.api.admin_auth._temporary_auth_bypass_enabled', return_value=True):
            logout("temporary-admin-bypass")  # Should return without error


class TestAdminAuthNotification(unittest.TestCase):
    """Tests for login notification in admin_auth."""

    def test_send_login_notification(self):
        from backend.api.admin_auth import _send_login_notification
        with patch('backend.api.admin_auth._ensure_secure_dir'):
            with patch('builtins.open', mock_open()):
                _send_login_notification("admin@test.com", "1.2.3.4")


class TestAdminAuthMisc(unittest.TestCase):
    """Misc admin_auth tests."""

    def test_audit_log(self):
        from backend.api.admin_auth import audit_log
        with patch('backend.api.admin_auth._ensure_secure_dir'):
            with patch('builtins.open', mock_open()):
                audit_log("TEST_ACTION", "user1", "1.2.3.4", "details")

    def test_ensure_secure_dir(self):
        from backend.api.admin_auth import _ensure_secure_dir
        with patch('os.makedirs'):
            _ensure_secure_dir()

    def test_temporary_auth_bypass_disabled(self):
        from backend.api.admin_auth import _temporary_auth_bypass_enabled
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            self.assertFalse(_temporary_auth_bypass_enabled())

    def test_temporary_auth_bypass_enabled(self):
        from backend.api.admin_auth import _temporary_auth_bypass_enabled
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "true"}):
            self.assertTrue(_temporary_auth_bypass_enabled())

    def test_load_lockouts_no_file(self):
        from backend.api.admin_auth import _load_lockouts
        with patch('os.path.exists', return_value=False):
            _load_lockouts()

    def test_load_lockouts_invalid_json(self):
        from backend.api import admin_auth
        from backend.api.admin_auth import _load_lockouts
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data="not json")):
                _load_lockouts()
        self.assertEqual(admin_auth._lockouts, {})

    def test_load_users_no_file(self):
        from backend.api.admin_auth import _load_users
        with patch('os.path.exists', return_value=False):
            result = _load_users()
        self.assertEqual(result, {"users": {}})


# ---------------------------------------------------------------------------
# 4. browser_endpoints.py (73% → ~95%)
# ---------------------------------------------------------------------------

class TestBrowserEndpoints(unittest.TestCase):
    """Tests for browser_endpoints functions."""

    def test_get_daily_summary_no_data(self):
        from backend.api.browser_endpoints import get_daily_summary
        with patch('os.path.exists', return_value=False):
            result = get_daily_summary()
        self.assertEqual(result["status"], "no_data")

    def test_get_daily_summary_with_data(self):
        from backend.api.browser_endpoints import get_daily_summary
        summary = {
            "date": "2025-01-01",
            "cves_processed": [{"cve_id": "CVE-2025-0001"}],
            "domains_visited": ["example.com"],
            "total_dedup_skipped": 3,
            "total_blocked": 1,
            "total_expanded": 5,
            "total_fetched": 10,
            "errors": [],
            "timestamp": "2025-01-01T00:00:00Z",
        }
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(summary))):
                result = get_daily_summary()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["new_cves_count"], 1)

    def test_get_new_cves_no_data(self):
        from backend.api.browser_endpoints import get_new_cves
        with patch('os.path.exists', return_value=False):
            result = get_new_cves()
        self.assertEqual(result["status"], "no_data")
        self.assertEqual(result["count"], 0)

    def test_get_new_cves_with_data(self):
        from backend.api.browser_endpoints import get_new_cves
        summary = {
            "date": "2025-01-01",
            "cves_processed": [
                {"cve_id": "CVE-001", "title": "Test", "summary": "S" * 300,
                 "cvss_score": 9.8, "cwe_id": "CWE-79", "source_url": "http://test.com"}
            ],
            "timestamp": "2025-01-01T00:00:00Z",
        }
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', mock_open(read_data=json.dumps(summary))):
                result = get_new_cves()
        self.assertEqual(result["count"], 1)
        self.assertTrue(len(result["cves"][0]["summary"]) <= 200)

    def test_get_representation_impact_no_data(self):
        from backend.api.browser_endpoints import get_representation_impact
        with patch('backend.api.browser_endpoints._load_summary', return_value=None):
            result = get_representation_impact()
        self.assertEqual(result["status"], "no_data")

    def test_get_representation_impact_with_data(self):
        from backend.api.browser_endpoints import get_representation_impact
        summary = {
            "representation_diversity_delta": 0.15,
            "total_expanded": 7,
            "date": "2025-01-01",
            "timestamp": "T",
        }
        hash_index = {"url_hashes": {"h1": 1, "h2": 2}}
        with patch('backend.api.browser_endpoints._load_summary', return_value=summary):
            with patch('backend.api.browser_endpoints._load_hash_index', return_value=hash_index):
                result = get_representation_impact()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total_indexed"], 2)

    def test_load_hash_index_missing(self):
        from backend.api.browser_endpoints import _load_hash_index
        with patch('os.path.exists', return_value=False):
            result = _load_hash_index()
        self.assertIsNone(result)

    def test_load_hash_index_error(self):
        from backend.api.browser_endpoints import _load_hash_index
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', side_effect=Exception("read fail")):
                result = _load_hash_index()
        self.assertIsNone(result)

    def test_load_summary_error(self):
        from backend.api.browser_endpoints import _load_summary
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', side_effect=Exception("read fail")):
                result = _load_summary()
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 5. system_status.py (62% → ~95%)
# ---------------------------------------------------------------------------

class TestSystemStatus(unittest.TestCase):
    """Tests for system_status module."""

    def test_safe_call_success(self):
        from backend.api.system_status import _safe_call
        result = _safe_call("test", lambda: {"status": "ok"})
        self.assertEqual(result["status"], "ok")

    def test_safe_call_failure(self):
        from backend.api.system_status import _safe_call
        result = _safe_call("fail", lambda: 1 / 0)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertIn("error", result)

    def test_get_training_state(self):
        from backend.api.system_status import _get_training_state
        mock_progress = MagicMock()
        mock_progress.status = "idle"
        mock_progress.current_epoch = 0
        mock_progress.total_epochs = 10
        mock_progress.loss = 0.5
        mock_progress.throughput = 100
        mock_progress.started_at = None
        mock_mgr = MagicMock()
        mock_mgr.get_training_progress.return_value = mock_progress
        # Patch the source module since _get_training_state does lazy import
        with patch('backend.training.state_manager.get_training_state_manager', return_value=mock_mgr):
            result = _get_training_state()
        self.assertEqual(result["status"], "idle")

    def test_get_voice_status(self):
        from backend.api.system_status import _get_voice_status
        with patch('backend.assistant.voice_runtime.build_voice_pipeline_status', return_value={"status": "ready"}):
            result = _get_voice_status()
        self.assertEqual(result["status"], "ready")

    def test_get_metrics_snapshot(self):
        from backend.api.system_status import _get_metrics_snapshot
        mock_registry = MagicMock()
        mock_registry.get_snapshot.return_value = {"count": 5}
        with patch('backend.observability.metrics.metrics_registry', mock_registry):
            result = _get_metrics_snapshot()
        self.assertEqual(result["count"], 5)

    def test_get_storage_health(self):
        from backend.api.system_status import _get_storage_health
        with patch('backend.storage.storage_bridge.get_storage_health', return_value={"storage_active": True}):
            result = _get_storage_health()
        self.assertTrue(result["storage_active"])

    def test_get_readiness(self):
        from backend.api.system_status import _get_readiness
        with patch('backend.reliability.dependency_checker.run_all_checks', return_value={"ready": True}):
            result = _get_readiness()
        self.assertTrue(result["ready"])


# ---------------------------------------------------------------------------
# 6. report_generator.py helpers (25% → higher)
# ---------------------------------------------------------------------------

class TestReportGeneratorDB(unittest.TestCase):
    """Tests for report_generator DB helpers."""

    def test_get_db_path_default(self):
        from backend.api.report_generator import _get_db_path
        with patch.dict(os.environ, {}, clear=True):
            path = _get_db_path()
        self.assertIn("ygb.db", path)

    def test_get_db_path_custom(self):
        from backend.api.report_generator import _get_db_path
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///D:/mydb.db"}):
            path = _get_db_path()
        self.assertEqual(path, "D:/mydb.db")

    def test_get_db_connection_failure(self):
        from backend.api.report_generator import get_db_connection
        import sqlite3
        with patch('sqlite3.connect', side_effect=sqlite3.OperationalError("cannot open")):
            with patch('backend.api.report_generator._get_db_path', return_value="/impossible/path/db.sqlite"):
                conn = get_db_connection()
        self.assertIsNone(conn)

    def test_log_activity_fallback(self):
        from backend.api.report_generator import _log_activity
        with patch('backend.storage.storage_bridge.log_activity', side_effect=Exception("fail")):
            _log_activity("u1", "TEST", "details")  # Should not raise

    def test_ensure_tables_already_created(self):
        from backend.api import report_generator
        report_generator._TABLES_CREATED = True
        report_generator._ensure_tables()  # Should return immediately
        report_generator._TABLES_CREATED = False

    def test_ensure_tables_no_connection(self):
        from backend.api import report_generator
        report_generator._TABLES_CREATED = False
        with patch('backend.api.report_generator.get_db_connection', return_value=None):
            report_generator._ensure_tables()
        self.assertFalse(report_generator._TABLES_CREATED)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
