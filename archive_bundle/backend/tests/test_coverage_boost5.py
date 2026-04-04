"""
Coverage boost round 5 — final push to 90%.

Targeted tests for exact uncovered lines in:
  - auth_server.py: apply_backoff, is_trusted_device, trust_device, send_otp_email, get_ip_subnet
  - auth_guard.py: ws_authenticate (cookie/protocol), require_auth role hydration
  - revocation_store.py: _RedisStore (mocked redis), _get_store singleton, get_backend_health
  - field_progression_api.py: sync_active_field_training, start_training frozen→advance path
"""

import hashlib
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from pathlib import Path


# ---------------------------------------------------------------------------
# 1. auth_server.py — uncovered lines 139-214, 220-247
# ---------------------------------------------------------------------------

class TestAuthServerBackoff(unittest.TestCase):
    """Tests for apply_backoff, record_failure, clear_failures."""

    def test_apply_backoff_no_failures(self):
        from backend.api.auth_server import apply_backoff, _failure_counts
        _failure_counts.clear()
        # Should not sleep when no failures
        apply_backoff("10.0.0.1")

    def test_apply_backoff_with_failures(self):
        from backend.api.auth_server import apply_backoff, record_failure, _failure_counts
        _failure_counts.clear()
        record_failure("10.0.0.2")
        # With 1 failure, delay = min(2^0 * base, 60) — should be small
        with patch('backend.api.auth_server.time') as mock_time:
            mock_time.sleep = MagicMock()
            mock_time.time = time.time
            apply_backoff("10.0.0.2")
            mock_time.sleep.assert_called_once()

    def test_record_and_clear_failures(self):
        from backend.api.auth_server import record_failure, clear_failures, _failure_counts
        _failure_counts.clear()
        record_failure("10.0.0.3")
        record_failure("10.0.0.3")
        self.assertEqual(_failure_counts["10.0.0.3"], 2)
        clear_failures("10.0.0.3")
        self.assertEqual(_failure_counts["10.0.0.3"], 0)


class TestAuthServerDeviceFingerprint(unittest.TestCase):
    """Tests for device fingerprinting functions."""

    def test_generate_device_fingerprint(self):
        from backend.api.auth_server import generate_device_fingerprint
        fp = generate_device_fingerprint("Mozilla/5.0", "1.2.3.4", "dev-1")
        self.assertEqual(len(fp), 64)  # SHA-256 hex
        # Deterministic
        fp2 = generate_device_fingerprint("Mozilla/5.0", "1.2.3.4", "dev-1")
        self.assertEqual(fp, fp2)

    def test_get_ip_subnet_ipv4(self):
        from backend.api.auth_server import get_ip_subnet
        self.assertEqual(get_ip_subnet("192.168.1.100"), "192.168.1")
        self.assertEqual(get_ip_subnet("10.0.0.1"), "10.0.0")

    def test_get_ip_subnet_ipv6(self):
        from backend.api.auth_server import get_ip_subnet
        # IPv6 returns as-is
        self.assertEqual(get_ip_subnet("::1"), "::1")

    def test_is_trusted_device_not_found(self):
        from backend.api.auth_server import is_trusted_device
        with patch('backend.api.auth_server.load_json', return_value={}):
            self.assertFalse(is_trusted_device("user1", "fp-abc", "1.2.3.4"))

    def test_is_trusted_device_valid(self):
        from backend.api.auth_server import is_trusted_device
        devices = {
            "user1": {
                "fp-abc": {"trusted_at": time.time(), "ip": "1.2.3.4"}
            }
        }
        with patch('backend.api.auth_server.load_json', return_value=devices):
            self.assertTrue(is_trusted_device("user1", "fp-abc", "1.2.3.100"))

    def test_is_trusted_device_expired(self):
        from backend.api.auth_server import is_trusted_device, DEVICE_TRUST_TTL
        devices = {
            "user1": {
                "fp-abc": {"trusted_at": time.time() - DEVICE_TRUST_TTL - 100, "ip": "1.2.3.4"}
            }
        }
        with patch('backend.api.auth_server.load_json', return_value=devices):
            with patch('backend.api.auth_server.save_json'):
                self.assertFalse(is_trusted_device("user1", "fp-abc", "1.2.3.4"))

    def test_is_trusted_device_ip_change(self):
        from backend.api.auth_server import is_trusted_device
        devices = {
            "user1": {
                "fp-abc": {"trusted_at": time.time(), "ip": "1.2.3.4"}
            }
        }
        with patch('backend.api.auth_server.load_json', return_value=devices):
            # Different /24 subnet
            self.assertFalse(is_trusted_device("user1", "fp-abc", "10.0.0.1"))

    def test_trust_device_new_user(self):
        from backend.api.auth_server import trust_device
        with patch('backend.api.auth_server.load_json', return_value={}):
            with patch('backend.api.auth_server.save_json') as mock_save:
                trust_device("newuser", "fp-123", "1.2.3.4")
                mock_save.assert_called_once()
                saved_data = mock_save.call_args[0][1]
                self.assertIn("newuser", saved_data)
                self.assertIn("fp-123", saved_data["newuser"])

    def test_trust_device_existing_user(self):
        from backend.api.auth_server import trust_device
        existing = {"olduser": {"old-fp": {"trusted_at": 100, "ip": "1.1.1.1"}}}
        with patch('backend.api.auth_server.load_json', return_value=existing):
            with patch('backend.api.auth_server.save_json') as mock_save:
                trust_device("olduser", "new-fp", "2.2.2.2")
                saved = mock_save.call_args[0][1]
                self.assertIn("new-fp", saved["olduser"])
                self.assertIn("old-fp", saved["olduser"])


class TestAuthServerOTP(unittest.TestCase):
    """Tests for OTP email sending."""

    def test_send_otp_email_no_config(self):
        from backend.api.auth_server import send_otp_email
        with patch.dict(os.environ, {'SMTP_USER': '', 'SMTP_PASS': ''}, clear=False):
            result = send_otp_email("user@test.com", "123456")
            self.assertFalse(result)

    def test_send_otp_email_smtp_failure(self):
        from backend.api.auth_server import send_otp_email
        env = {'SMTP_USER': 'test@smtp.com', 'SMTP_PASS': 'pass', 'ALERT_EMAIL_FROM': 'from@test.com'}
        with patch.dict(os.environ, env, clear=False):
            with patch('backend.api.auth_server.smtplib.SMTP', side_effect=Exception("Connection refused")):
                result = send_otp_email("user@test.com", "123456")
                self.assertFalse(result)

    def test_send_otp_email_success(self):
        from backend.api.auth_server import send_otp_email
        env = {'SMTP_USER': 'test@smtp.com', 'SMTP_PASS': 'pass', 'ALERT_EMAIL_FROM': 'from@test.com'}
        with patch.dict(os.environ, env, clear=False):
            mock_smtp = MagicMock()
            mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
            mock_smtp.__exit__ = MagicMock(return_value=False)
            with patch('backend.api.auth_server.smtplib.SMTP', return_value=mock_smtp):
                result = send_otp_email("user@test.com", "654321")
                self.assertTrue(result)


class TestAuthServerCheckOTPRate(unittest.TestCase):
    """Tests for OTP rate limiting."""

    def test_check_otp_rate_normal(self):
        from backend.api.auth_server import check_otp_rate, _otp_requests
        _otp_requests.clear()
        check_otp_rate("testuser")  # Should not raise

    def test_check_otp_rate_exceeded(self):
        from backend.api.auth_server import check_otp_rate, _otp_requests, OTP_RATE_LIMIT
        from fastapi import HTTPException
        _otp_requests.clear()
        _otp_requests["rateuser"] = [time.time()] * OTP_RATE_LIMIT
        with self.assertRaises(HTTPException) as ctx:
            check_otp_rate("rateuser")
        self.assertEqual(ctx.exception.status_code, 429)


# ---------------------------------------------------------------------------
# 2. revocation_store.py — RedisStore (mocked), _get_store, health
# ---------------------------------------------------------------------------

class TestRedisStoreMocked(unittest.TestCase):
    """Tests for _RedisStore with mocked redis client."""

    def _make_store(self, available=True):
        from backend.auth.revocation_store import _RedisStore
        store = _RedisStore.__new__(_RedisStore)
        store._client = MagicMock()
        if available:
            store._client.ping.return_value = True
        else:
            store._client.ping.side_effect = Exception("Connection refused")
        return store

    def test_redis_revoke_token(self):
        store = self._make_store(available=True)
        store.revoke_token("hash123", ttl=3600)
        store._client.setex.assert_called_once()

    def test_redis_revoke_session(self):
        store = self._make_store(available=True)
        store.revoke_session("sess-1", ttl=3600)
        store._client.setex.assert_called_once()

    def test_redis_is_token_revoked_true(self):
        store = self._make_store(available=True)
        store._client.exists.return_value = 1
        self.assertTrue(store.is_token_revoked("hash123"))

    def test_redis_is_token_revoked_false(self):
        store = self._make_store(available=True)
        store._client.exists.return_value = 0
        self.assertFalse(store.is_token_revoked("hash123"))

    def test_redis_is_session_revoked_true(self):
        store = self._make_store(available=True)
        store._client.exists.return_value = 1
        self.assertTrue(store.is_session_revoked("sess-1"))

    def test_redis_is_session_revoked_false(self):
        store = self._make_store(available=True)
        store._client.exists.return_value = 0
        self.assertFalse(store.is_session_revoked("sess-1"))

    def test_redis_fail_closed_token(self):
        store = self._make_store(available=False)
        self.assertTrue(store.is_token_revoked("hash123"))

    def test_redis_fail_closed_session(self):
        store = self._make_store(available=False)
        self.assertTrue(store.is_session_revoked("sess-1"))

    def test_redis_unavailable_revoke_token(self):
        store = self._make_store(available=False)
        store.revoke_token("hash123")
        store._client.setex.assert_not_called()

    def test_redis_unavailable_revoke_session(self):
        store = self._make_store(available=False)
        store.revoke_session("sess-1")
        store._client.setex.assert_not_called()

    def test_redis_clear(self):
        store = self._make_store(available=True)
        store._client.scan_iter.return_value = [b"revoked:tok:a", b"revoked:sess:b"]
        store.clear()
        self.assertEqual(store._client.delete.call_count, 2)


class TestGetStoreSingleton(unittest.TestCase):
    """Tests for _get_store singleton factory."""

    def test_get_store_memory(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            store = rs._get_store()
            self.assertIsInstance(store, rs._MemoryStore)
        rs._store = None

    def test_get_store_file(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "file"}):
            store = rs._get_store()
            self.assertIsInstance(store, rs._FileStore)
        rs._store = None

    def test_get_store_redis(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        # Create a pre-built _RedisStore without calling __init__ (which imports redis)
        fake_store = rs._RedisStore.__new__(rs._RedisStore)
        fake_store._client = MagicMock()
        fake_store._client.ping.return_value = True
        fake_store._url = "redis://localhost:6379/0"
        rs._store = fake_store
        store = rs._get_store()
        self.assertIs(store, fake_store)
        rs._store = None

    def test_get_store_cached(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            store1 = rs._get_store()
            store2 = rs._get_store()
            self.assertIs(store1, store2)
        rs._store = None


class TestGetBackendHealth(unittest.TestCase):
    """Tests for get_backend_health."""

    def test_health_memory(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            health = rs.get_backend_health()
            self.assertTrue(health["available"])
            self.assertIn("warning", health)
        rs._store = None

    def test_health_file(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "file"}):
            health = rs.get_backend_health()
            self.assertTrue(health["available"])
            self.assertIn("file_path", health)
        rs._store = None

    def test_health_redis_available(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        # Pre-build _RedisStore with mocked available client
        fake_store = rs._RedisStore.__new__(rs._RedisStore)
        fake_store._client = MagicMock()
        fake_store._client.ping.return_value = True
        rs._store = fake_store
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "redis"}):
            health = rs.get_backend_health()
            self.assertTrue(health["available"])
            self.assertEqual(health["fail_mode"], "closed")
        rs._store = None

    def test_health_redis_unavailable(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        # Pre-build _RedisStore with unavailable client
        fake_store = rs._RedisStore.__new__(rs._RedisStore)
        fake_store._client = MagicMock()
        fake_store._client.ping.side_effect = Exception("down")
        rs._store = fake_store
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "redis"}):
            health = rs.get_backend_health()
            self.assertFalse(health["available"])
        rs._store = None


class TestRevocationPublicAPI(unittest.TestCase):
    """Tests for public revocation API functions."""

    def test_revoke_and_check_token(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            rs.revoke_token("my-bearer-token")
            self.assertTrue(rs.is_token_revoked("my-bearer-token"))
            self.assertFalse(rs.is_token_revoked("other-token"))
        rs._store = None

    def test_revoke_and_check_session(self):
        from backend.auth import revocation_store as rs
        rs._store = None
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            rs.revoke_session("sess-abc")
            self.assertTrue(rs.is_session_revoked("sess-abc"))
            self.assertFalse(rs.is_session_revoked("sess-xyz"))
        rs._store = None


# ---------------------------------------------------------------------------
# 3. auth_guard.py — ws_authenticate, require_auth role hydration
# ---------------------------------------------------------------------------

class TestWsAuthenticate(unittest.IsolatedAsyncioTestCase):
    """Tests for ws_authenticate covering cookie + protocol paths."""

    async def test_ws_auth_bypass(self):
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "true"}):
            result = await ws_authenticate(ws)
            self.assertIsNotNone(result)

    async def test_ws_auth_query_param_rejected(self):
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {"token": "leaked-token"}
        ws.headers = {}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            result = await ws_authenticate(ws)
            self.assertIsNone(result)

    async def test_ws_auth_no_token(self):
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            result = await ws_authenticate(ws)
            self.assertIsNone(result)

    async def test_ws_auth_via_protocol(self):
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"sec-websocket-protocol": "bearer.valid-jwt-token", "cookie": ""}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
                with patch('backend.auth.auth_guard.verify_jwt', return_value={"sub": "user1", "role": "admin"}):
                    with patch('backend.auth.auth_guard.is_session_revoked', return_value=False):
                        result = await ws_authenticate(ws)
                        self.assertIsNotNone(result)
                        self.assertEqual(result["sub"], "user1")

    async def test_ws_auth_revoked_token(self):
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"sec-websocket-protocol": "bearer.revoked-token", "cookie": ""}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=True):
                result = await ws_authenticate(ws)
                self.assertIsNone(result)

    async def test_ws_auth_invalid_jwt(self):
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"sec-websocket-protocol": "bearer.bad-jwt", "cookie": ""}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
                with patch('backend.auth.auth_guard.verify_jwt', return_value=None):
                    result = await ws_authenticate(ws)
                    self.assertIsNone(result)

    async def test_ws_auth_revoked_session(self):
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"sec-websocket-protocol": "bearer.has-session", "cookie": ""}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
                with patch('backend.auth.auth_guard.verify_jwt', return_value={"sub": "u", "session_id": "s1"}):
                    with patch('backend.auth.auth_guard.is_session_revoked', return_value=True):
                        result = await ws_authenticate(ws)
                        self.assertIsNone(result)

    async def test_ws_auth_via_cookie(self):
        from backend.auth.auth_guard import ws_authenticate, AUTH_COOKIE_NAME
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "%s=cookie-jwt-token" % AUTH_COOKIE_NAME, "sec-websocket-protocol": ""}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
                with patch('backend.auth.auth_guard.verify_jwt', return_value={"sub": "cookieuser", "role": "admin"}):
                    with patch('backend.auth.auth_guard.is_session_revoked', return_value=False):
                        result = await ws_authenticate(ws)
                        self.assertIsNotNone(result)


class TestRequireAuthRoleHydration(unittest.IsolatedAsyncioTestCase):
    """Tests for require_auth role hydration from storage."""

    async def test_role_hydration_from_storage(self):
        from backend.auth.auth_guard import require_auth
        mock_request = MagicMock()
        mock_request.headers = {}
        mock_request.cookies = {}
        mock_creds = MagicMock()
        mock_creds.credentials = "valid-token"
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            with patch('backend.auth.auth_guard._verify_token_or_401', return_value={"sub": "u1"}):
                with patch('backend.storage.storage_bridge.get_user', return_value={"role": "admin"}):
                    result = await require_auth(mock_request, mock_creds)
                    self.assertEqual(result["role"], "admin")

    async def test_role_hydration_storage_failure(self):
        from backend.auth.auth_guard import require_auth
        mock_request = MagicMock()
        mock_creds = MagicMock()
        mock_creds.credentials = "valid-token"
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            with patch('backend.auth.auth_guard._verify_token_or_401', return_value={"sub": "u2"}):
                with patch('backend.storage.storage_bridge.get_user', side_effect=Exception("DB down")):
                    result = await require_auth(mock_request, mock_creds)
                    # Should NOT have role since storage failed
                    self.assertNotIn("role", result)

    async def test_role_already_present(self):
        from backend.auth.auth_guard import require_auth
        mock_request = MagicMock()
        mock_creds = MagicMock()
        mock_creds.credentials = "valid-token"
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            with patch('backend.auth.auth_guard._verify_token_or_401', return_value={"sub": "u3", "role": "viewer"}):
                result = await require_auth(mock_request, mock_creds)
                self.assertEqual(result["role"], "viewer")


# ---------------------------------------------------------------------------
# 4. field_progression_api.py — sync_active_field_training + approve_field
# ---------------------------------------------------------------------------

class TestSyncActiveFieldTraining(unittest.TestCase):
    """Tests for sync_active_field_training — the 68-line uncovered function."""

    def _mock_freeze_result(self, freeze_allowed=True, reason=None):
        result = MagicMock()
        result.freeze_allowed = freeze_allowed
        result.reason = reason or "No freeze reason"
        return result

    def _run_sync(self, **kwargs):
        """Run sync_active_field_training with all required mocks."""
        from backend.api.field_progression_api import sync_active_field_training, _default_state
        defaults = {
            'precision': 0.97,
            'fpr': 0.03,
            'dup_detection': 0.90,
            'ece': 0.015,
            'stability_cycles': 10,
            'promotion_ready': False,
            'promotion_frozen': False,
        }
        defaults.update(kwargs)
        freeze_result = self._mock_freeze_result(
            freeze_allowed=kwargs.get('_freeze_allowed', True),
            reason=kwargs.get('_freeze_reason', None)
        )
        mock_validator = MagicMock()
        mock_validator.validate_freeze.return_value = freeze_result
        with patch('backend.api.field_progression_api._load_field_state', return_value=_default_state()):
            with patch('backend.api.field_progression_api._save_field_state'):
                with patch('backend.api.field_progression_api._save_runtime_status'):
                    with patch('backend.api.field_progression_api._signed_approval_status',
                               return_value={'has_signed_approval': kwargs.get('_approved', False), 'chain_valid': True}):
                        with patch('impl_v1.training.distributed.freeze_validator.FreezeValidator', return_value=mock_validator):
                            return sync_active_field_training(**{k: v for k, v in defaults.items() if not k.startswith('_')})

    def test_sync_training_basic(self):
        result = self._run_sync()
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['field_id'], 0)

    def test_sync_promotion_frozen(self):
        result = self._run_sync(promotion_frozen=True, promotion_freeze_reason="drift detected")
        self.assertEqual(result['field_state'], 'TRAINING')
        self.assertTrue(result['promotion_frozen'])

    def test_sync_promotion_ready_no_approval(self):
        result = self._run_sync(promotion_ready=True, _approved=False)
        self.assertEqual(result['field_state'], 'CERTIFICATION_PENDING')

    def test_sync_promotion_ready_approved_freeze_allowed(self):
        result = self._run_sync(promotion_ready=True, _approved=True, _freeze_allowed=True)
        self.assertEqual(result['field_state'], 'FROZEN')
        self.assertTrue(result['freeze_valid'])

    def test_sync_promotion_ready_approved_no_freeze(self):
        result = self._run_sync(promotion_ready=True, _approved=True, _freeze_allowed=False, _freeze_reason="det fail")
        self.assertEqual(result['field_state'], 'CERTIFIED')

    def test_sync_stability_check(self):
        # precision is above threshold and not breached → STABILITY_CHECK
        result = self._run_sync(precision=0.97)
        self.assertEqual(result['field_state'], 'STABILITY_CHECK')

    def test_sync_all_fields_complete(self):
        from backend.api.field_progression_api import sync_active_field_training, _default_state, TOTAL_FIELDS
        state = _default_state()
        state['active_field_id'] = TOTAL_FIELDS
        with patch('backend.api.field_progression_api._load_field_state', return_value=state):
            result = sync_active_field_training(precision=0.97, fpr=0.03)
        self.assertEqual(result['status'], 'error')
        self.assertIn('ALL_FIELDS_COMPLETE', result['message'])


class TestApproveField(unittest.TestCase):
    """Tests for approve_field endpoint handler."""

    def test_approve_missing_approver(self):
        from backend.api.field_progression_api import approve_field
        result = approve_field(0, "", "some reason")
        self.assertEqual(result['status'], 'error')
        self.assertIn('APPROVAL_REJECTED', result['message'])

    def test_approve_missing_reason(self):
        from backend.api.field_progression_api import approve_field
        result = approve_field(0, "admin-1", "")
        self.assertEqual(result['status'], 'error')

    def test_approve_invalid_field_id(self):
        from backend.api.field_progression_api import approve_field
        result = approve_field(-1, "admin-1", "good reason")
        self.assertEqual(result['status'], 'error')
        self.assertIn('INVALID_FIELD_ID', result['message'])

    def test_approve_field_id_too_high(self):
        from backend.api.field_progression_api import approve_field, TOTAL_FIELDS
        result = approve_field(TOTAL_FIELDS + 1, "admin-1", "good reason")
        self.assertEqual(result['status'], 'error')


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
