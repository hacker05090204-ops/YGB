"""
Coverage boost round 3 — closing the final gap to 85%.

Modules covered:
  - backend.auth.auth (69% → ~90%) — password hash/verify, rate limiter, simple tokens, CSRF
  - backend.auth.revocation_store (69% → ~90%) — all store backends + public API
  - backend.auth.auth_guard (75% → ~90%) — SSRF validation, preflight, WS auth, CSRF
"""

import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import MagicMock, patch, mock_open


# ---------------------------------------------------------------------------
# 1. auth.py — Password hashing, verification, rate limiter, simple tokens
# ---------------------------------------------------------------------------

class TestAuthPasswordHashing(unittest.TestCase):
    """Tests for password hash/verify in auth.py."""

    def test_hash_password_returns_versioned(self):
        from backend.auth.auth import hash_password
        hashed = hash_password("test_password")
        self.assertTrue(hashed.startswith("v3:") or hashed.startswith("v3s:"))

    def test_verify_password_roundtrip(self):
        from backend.auth.auth import hash_password, verify_password
        hashed = hash_password("my_password_123")
        self.assertTrue(verify_password("my_password_123", hashed))
        self.assertFalse(verify_password("wrong_password", hashed))

    def test_verify_password_empty(self):
        from backend.auth.auth import verify_password
        self.assertFalse(verify_password("", "some_hash"))
        self.assertFalse(verify_password("password", ""))

    def test_verify_password_v2_format(self):
        from backend.auth.auth import verify_password, _iterative_hash
        salt = "test_salt"
        pwd = "my_v2_password"
        h = _iterative_hash(pwd, salt)
        stored = f"v2:{salt}:{h}"
        self.assertTrue(verify_password(pwd, stored))
        self.assertFalse(verify_password("wrong", stored))

    def test_verify_password_v2_bad_parts(self):
        from backend.auth.auth import verify_password
        self.assertFalse(verify_password("pwd", "v2:only_salt"))

    def test_verify_password_legacy_v1(self):
        from backend.auth.auth import verify_password
        salt = "legacy_salt"
        pwd = "legacy_pwd"
        h = hashlib.sha256(f"{salt}:{pwd}".encode()).hexdigest()
        stored = f"{salt}:{h}"
        self.assertTrue(verify_password(pwd, stored))
        self.assertFalse(verify_password("wrong", stored))

    def test_verify_password_no_colon(self):
        from backend.auth.auth import verify_password
        self.assertFalse(verify_password("pwd", "no_colon_hash"))

    def test_verify_password_v3s_bad_parts(self):
        from backend.auth.auth import verify_password
        self.assertFalse(verify_password("pwd", "v3s:only_salt"))

    def test_needs_rehash(self):
        from backend.auth.auth import needs_rehash, _HASH_VERSION
        self.assertFalse(needs_rehash(f"{_HASH_VERSION}:something"))
        self.assertTrue(needs_rehash("v1:old_hash"))
        self.assertTrue(needs_rehash("v2:salt:hash"))


class TestAuthRateLimiter(unittest.TestCase):
    """Tests for RateLimiter in auth.py."""

    def test_rate_limiter_not_limited(self):
        from backend.auth.auth import RateLimiter
        rl = RateLimiter(max_attempts=3, window_seconds=60)
        self.assertFalse(rl.is_rate_limited("1.2.3.4"))

    def test_rate_limiter_limited_after_max(self):
        from backend.auth.auth import RateLimiter
        rl = RateLimiter(max_attempts=2, window_seconds=60)
        rl.record_attempt("1.2.3.4")
        rl.record_attempt("1.2.3.4")
        self.assertTrue(rl.is_rate_limited("1.2.3.4"))

    def test_rate_limiter_remaining(self):
        from backend.auth.auth import RateLimiter
        rl = RateLimiter(max_attempts=5, window_seconds=60)
        self.assertEqual(rl.get_remaining("1.2.3.4"), 5)
        rl.record_attempt("1.2.3.4")
        self.assertEqual(rl.get_remaining("1.2.3.4"), 4)

    def test_rate_limiter_reset(self):
        from backend.auth.auth import RateLimiter
        rl = RateLimiter(max_attempts=2, window_seconds=60)
        rl.record_attempt("1.2.3.4")
        rl.record_attempt("1.2.3.4")
        self.assertTrue(rl.is_rate_limited("1.2.3.4"))
        rl.reset("1.2.3.4")
        self.assertFalse(rl.is_rate_limited("1.2.3.4"))


class TestAuthSimpleToken(unittest.TestCase):
    """Tests for fallback simple token in auth.py."""

    def test_generate_and_verify_simple_token(self):
        from backend.auth.auth import _generate_simple_token, _verify_simple_token
        with patch.dict(os.environ, {"JWT_SECRET": "test_secret_32chars_long_enough!!"}):
            # Need to reload module state
            import backend.auth.auth as auth_mod
            old_secret = auth_mod.JWT_SECRET
            auth_mod.JWT_SECRET = "test_secret_32chars_long_enough!!"
            try:
                token = _generate_simple_token("user-1")
                payload = _verify_simple_token(token)
                self.assertIsNotNone(payload)
                self.assertEqual(payload["sub"], "user-1")
            finally:
                auth_mod.JWT_SECRET = old_secret

    def test_verify_simple_token_invalid_format(self):
        from backend.auth.auth import _verify_simple_token
        self.assertIsNone(_verify_simple_token("invalid-no-colons"))
        self.assertIsNone(_verify_simple_token("a:b"))  # only 2 parts

    def test_verify_simple_token_expired(self):
        from backend.auth.auth import _verify_simple_token
        import backend.auth.auth as auth_mod
        old_secret = auth_mod.JWT_SECRET
        auth_mod.JWT_SECRET = "test_secret"
        try:
            token = f"user1:1000:{hmac.new(b'test_secret', b'user1:1000', hashlib.sha256).hexdigest()}"
            self.assertIsNone(_verify_simple_token(token))
        finally:
            auth_mod.JWT_SECRET = old_secret

    def test_verify_simple_token_bad_sig(self):
        from backend.auth.auth import _verify_simple_token
        future = str(int(time.time()) + 3600)
        self.assertIsNone(_verify_simple_token(f"user1:{future}:bad_signature"))

    def test_verify_simple_token_non_numeric_expiry(self):
        from backend.auth.auth import _verify_simple_token
        self.assertIsNone(_verify_simple_token("user1:not_a_number:sig"))


class TestAuthHelpers(unittest.TestCase):
    """Tests for misc auth helpers."""

    def test_compute_device_hash(self):
        from backend.auth.auth import compute_device_hash
        h1 = compute_device_hash("Mozilla/5.0")
        self.assertEqual(len(h1), 16)
        h2 = compute_device_hash("Mozilla/5.0")
        self.assertEqual(h1, h2)
        h3 = compute_device_hash("Different UA")
        self.assertNotEqual(h1, h3)

    def test_compute_device_hash_empty(self):
        from backend.auth.auth import compute_device_hash
        h = compute_device_hash("")
        self.assertEqual(len(h), 16)

    def test_generate_csrf_token(self):
        from backend.auth.auth import generate_csrf_token
        t = generate_csrf_token()
        self.assertEqual(len(t), 64)

    def test_verify_csrf_token(self):
        from backend.auth.auth import verify_csrf_token
        self.assertTrue(verify_csrf_token("abc", "abc"))
        self.assertFalse(verify_csrf_token("abc", "xyz"))

    def test_get_rate_limiter_singleton(self):
        from backend.auth.auth import get_rate_limiter
        r1 = get_rate_limiter()
        r2 = get_rate_limiter()
        self.assertIs(r1, r2)


# ---------------------------------------------------------------------------
# 2. revocation_store.py — All backends + public API
# ---------------------------------------------------------------------------

class TestMemoryStore(unittest.TestCase):
    """Tests for _MemoryStore."""

    def test_memory_store_lifecycle(self):
        from backend.auth.revocation_store import _MemoryStore
        store = _MemoryStore()
        self.assertFalse(store.is_token_revoked("t1"))
        self.assertFalse(store.is_session_revoked("s1"))
        store.revoke_token("t1")
        store.revoke_session("s1")
        self.assertTrue(store.is_token_revoked("t1"))
        self.assertTrue(store.is_session_revoked("s1"))
        store.clear()
        self.assertFalse(store.is_token_revoked("t1"))
        self.assertFalse(store.is_session_revoked("s1"))


class TestFileStore(unittest.TestCase):
    """Tests for _FileStore."""

    def test_file_store_new(self):
        from backend.auth.revocation_store import _FileStore
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "revocations.json")
            store = _FileStore(path)
            self.assertFalse(store.is_token_revoked("t1"))
            store.revoke_token("t1")
            self.assertTrue(store.is_token_revoked("t1"))
            store.revoke_session("s1")
            self.assertTrue(store.is_session_revoked("s1"))
            store.clear()
            self.assertFalse(store.is_token_revoked("t1"))

    def test_file_store_load_existing(self):
        from backend.auth.revocation_store import _FileStore
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "revocations.json")
            existing = {"tokens": ["hash1"], "sessions": ["sess1"]}
            with open(path, "w") as f:
                json.dump(existing, f)
            store = _FileStore(path)
            self.assertTrue(store.is_token_revoked("hash1"))
            self.assertTrue(store.is_session_revoked("sess1"))

    def test_file_store_load_corrupt(self):
        from backend.auth.revocation_store import _FileStore
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "revocations.json")
            with open(path, "w") as f:
                f.write("not json")
            store = _FileStore(path)
            # Should start empty on corrupt file
            self.assertFalse(store.is_token_revoked("anything"))

    def test_file_store_no_duplicate(self):
        from backend.auth.revocation_store import _FileStore
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "revocations.json")
            store = _FileStore(path)
            store.revoke_token("t1")
            store.revoke_token("t1")  # duplicate
            self.assertEqual(store._data["tokens"].count("t1"), 1)


class TestRevocationPublicAPI(unittest.TestCase):
    """Tests for public revocation API functions."""

    def test_revoke_and_check_token(self):
        from backend.auth import revocation_store
        revocation_store.reset_store()
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            revocation_store.revoke_token("my_token")
            self.assertTrue(revocation_store.is_token_revoked("my_token"))
            self.assertFalse(revocation_store.is_token_revoked("other_token"))
        revocation_store.reset_store()

    def test_revoke_and_check_session(self):
        from backend.auth import revocation_store
        revocation_store.reset_store()
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            revocation_store.revoke_session("session-1")
            self.assertTrue(revocation_store.is_session_revoked("session-1"))
        revocation_store.reset_store()

    def test_get_backend_health_memory(self):
        from backend.auth import revocation_store
        revocation_store.reset_store()
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            health = revocation_store.get_backend_health()
            self.assertTrue(health["available"])
            self.assertIn("warning", health)
        revocation_store.reset_store()

    def test_get_store_file_backend(self):
        from backend.auth import revocation_store
        revocation_store.reset_store()
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "rev.json")
            with patch.dict(os.environ, {"REVOCATION_BACKEND": "file", "REVOCATION_FILE_PATH": path}):
                store = revocation_store._get_store()
                self.assertIsInstance(store, revocation_store._FileStore)
        revocation_store.reset_store()


# ---------------------------------------------------------------------------
# 3. auth_guard.py — SSRF validation, preflight, misc helpers
# ---------------------------------------------------------------------------

class TestAuthGuardSSRF(unittest.TestCase):
    """Tests for validate_target_url in auth_guard."""

    def test_validate_empty_url(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("")
        self.assertFalse(safe)
        self.assertEqual(violations[0]["rule"], "EMPTY_TARGET")

    def test_validate_localhost(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://localhost/admin")
        self.assertFalse(safe)

    def test_validate_private_ip(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://192.168.1.1/secret")
        self.assertFalse(safe)

    def test_validate_metadata_ip(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://169.254.169.254/latest/meta-data")
        self.assertFalse(safe)

    def test_validate_public_domain(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("https://example.com/api")
        self.assertTrue(safe)
        self.assertEqual(len(violations), 0)

    def test_validate_no_scheme(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("example.com/path")
        self.assertTrue(safe)

    def test_validate_wildcard_tld(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://*.com")
        self.assertFalse(safe)

    def test_validate_127_ip(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://127.0.0.1/admin")
        self.assertFalse(safe)


class TestAuthGuardPreflight(unittest.TestCase):
    """Tests for preflight_check_secrets."""

    def test_preflight_missing_secrets(self):
        from backend.auth.auth_guard import preflight_check_secrets
        with patch.dict(os.environ, {"JWT_SECRET": "", "YGB_HMAC_SECRET": "", "YGB_VIDEO_JWT_SECRET": ""}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                preflight_check_secrets()
            self.assertIn("PREFLIGHT", str(ctx.exception))

    def test_preflight_placeholder_secret(self):
        from backend.auth.auth_guard import preflight_check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "changeme",
            "YGB_HMAC_SECRET": "a" * 32,
            "YGB_VIDEO_JWT_SECRET": "b" * 32,
        }, clear=True):
            with self.assertRaises(RuntimeError):
                preflight_check_secrets()

    def test_preflight_short_secret(self):
        from backend.auth.auth_guard import preflight_check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "short",
            "YGB_HMAC_SECRET": "a" * 32,
            "YGB_VIDEO_JWT_SECRET": "b" * 32,
        }, clear=True):
            with self.assertRaises(RuntimeError):
                preflight_check_secrets()

    def test_preflight_all_valid(self):
        from backend.auth.auth_guard import preflight_check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "a" * 32,
            "YGB_HMAC_SECRET": "b" * 32,
            "YGB_VIDEO_JWT_SECRET": "c" * 32,
        }, clear=True):
            preflight_check_secrets()  # Should not raise


class TestAuthGuardHelpers(unittest.TestCase):
    """Tests for auth_guard helper functions."""

    def test_is_temporary_auth_bypass_enabled(self):
        from backend.auth.auth_guard import is_temporary_auth_bypass_enabled
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "true"}):
            self.assertTrue(is_temporary_auth_bypass_enabled())
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            self.assertFalse(is_temporary_auth_bypass_enabled())

    def test_build_temporary_auth_user(self):
        from backend.auth.auth_guard import build_temporary_auth_user
        user = build_temporary_auth_user()
        self.assertEqual(user["sub"], "temp-public-admin")
        self.assertEqual(user["role"], "admin")
        self.assertTrue(user["_temporary_bypass"])

    def test_normalize_origin(self):
        from backend.auth.auth_guard import _normalize_origin
        self.assertEqual(_normalize_origin("https://example.com/path"), "https://example.com")
        self.assertEqual(_normalize_origin(""), "")
        self.assertEqual(_normalize_origin("invalid"), "")

    def test_extract_cookie_token(self):
        from backend.auth.auth_guard import _extract_cookie_token
        request = MagicMock()
        request.cookies = {"ygb_auth": "token123"}
        self.assertEqual(_extract_cookie_token(request), "token123")

    def test_extract_cookie_token_legacy(self):
        from backend.auth.auth_guard import _extract_cookie_token
        request = MagicMock()
        request.cookies = {"ygb_token": "legacy_token"}
        self.assertEqual(_extract_cookie_token(request), "legacy_token")

    def test_extract_cookie_token_none(self):
        from backend.auth.auth_guard import _extract_cookie_token
        request = MagicMock()
        request.cookies = {}
        self.assertIsNone(_extract_cookie_token(request))

    def test_allowed_origins_default(self):
        from backend.auth.auth_guard import _allowed_origins
        with patch.dict(os.environ, {"FRONTEND_URL": "", "YGB_ALLOWED_ORIGINS": ""}):
            origins = _allowed_origins()
        self.assertIn("http://localhost:3000", origins)
        self.assertIn("http://127.0.0.1:3000", origins)

    def test_allowed_origins_custom(self):
        from backend.auth.auth_guard import _allowed_origins
        with patch.dict(os.environ, {
            "FRONTEND_URL": "https://app.example.com",
            "YGB_ALLOWED_ORIGINS": "https://extra.example.com, https://more.example.com",
        }):
            origins = _allowed_origins()
        self.assertIn("https://app.example.com", origins)
        self.assertIn("https://extra.example.com", origins)
        self.assertIn("https://more.example.com", origins)


class TestAuthGuardRequireAdmin(unittest.TestCase):
    """Tests for require_admin."""

    def test_require_admin_success(self):
        import asyncio
        from backend.auth.auth_guard import require_admin
        user = {"sub": "u1", "role": "admin"}
        result = asyncio.get_event_loop().run_until_complete(require_admin(user))
        self.assertEqual(result["sub"], "u1")

    def test_require_admin_forbidden(self):
        import asyncio
        from backend.auth.auth_guard import require_admin
        from fastapi import HTTPException
        user = {"sub": "u1", "role": "viewer"}
        with self.assertRaises(HTTPException) as ctx:
            asyncio.get_event_loop().run_until_complete(require_admin(user))
        self.assertEqual(ctx.exception.status_code, 403)


class TestAuthGuardCSRF(unittest.TestCase):
    """Tests for _enforce_cookie_csrf."""

    def test_csrf_safe_method_skips(self):
        from backend.auth.auth_guard import _enforce_cookie_csrf
        request = MagicMock()
        request.method = "GET"
        _enforce_cookie_csrf(request)  # Should not raise

    def test_csrf_no_origin_no_referer(self):
        from backend.auth.auth_guard import _enforce_cookie_csrf
        from fastapi import HTTPException
        request = MagicMock()
        request.method = "POST"
        request.headers = {}
        with self.assertRaises(HTTPException) as ctx:
            _enforce_cookie_csrf(request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_csrf_bad_origin(self):
        from backend.auth.auth_guard import _enforce_cookie_csrf
        from fastapi import HTTPException
        request = MagicMock()
        request.method = "POST"
        request.headers = {"origin": "https://evil.com"}
        with self.assertRaises(HTTPException) as ctx:
            _enforce_cookie_csrf(request)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_csrf_good_origin_no_token(self):
        from backend.auth.auth_guard import _enforce_cookie_csrf
        from fastapi import HTTPException
        request = MagicMock()
        request.method = "POST"
        request.headers = {"origin": "http://localhost:3000"}
        request.cookies = {}
        with self.assertRaises(HTTPException):
            _enforce_cookie_csrf(request)

    def test_csrf_good_origin_with_valid_token(self):
        from backend.auth.auth_guard import _enforce_cookie_csrf
        request = MagicMock()
        request.method = "POST"
        request.headers = {
            "origin": "http://localhost:3000",
            "x-csrf-token": "matched_token",
        }
        request.cookies = {"ygb_csrf": "matched_token"}
        _enforce_cookie_csrf(request)  # Should not raise

    def test_csrf_uses_referer_when_no_origin(self):
        from backend.auth.auth_guard import _enforce_cookie_csrf
        from fastapi import HTTPException
        request = MagicMock()
        request.method = "POST"
        request.headers = {
            "origin": None,
            "referer": "http://localhost:3000/page",
            "x-csrf-token": "tok",
        }
        request.cookies = {"ygb_csrf": "tok"}
        _enforce_cookie_csrf(request)  # Should not raise (referer is allowed origin)


class TestAuthGuardVerifyToken(unittest.TestCase):
    """Tests for _verify_token_or_401."""

    def test_verify_token_revoked(self):
        from backend.auth.auth_guard import _verify_token_or_401
        from fastapi import HTTPException
        with patch('backend.auth.auth_guard.is_token_revoked', return_value=True):
            with self.assertRaises(HTTPException) as ctx:
                _verify_token_or_401("revoked_token")
            self.assertEqual(ctx.exception.status_code, 401)

    def test_verify_token_invalid_jwt(self):
        from backend.auth.auth_guard import _verify_token_or_401
        from fastapi import HTTPException
        with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
            with patch('backend.auth.auth_guard.verify_jwt', return_value=None):
                with self.assertRaises(HTTPException) as ctx:
                    _verify_token_or_401("invalid_token")
                self.assertEqual(ctx.exception.status_code, 401)

    def test_verify_token_session_revoked(self):
        from backend.auth.auth_guard import _verify_token_or_401
        from fastapi import HTTPException
        with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
            with patch('backend.auth.auth_guard.verify_jwt', return_value={"sub": "u1", "session_id": "s1"}):
                with patch('backend.auth.auth_guard.is_session_revoked', return_value=True):
                    with self.assertRaises(HTTPException) as ctx:
                        _verify_token_or_401("valid_token")
                    self.assertEqual(ctx.exception.status_code, 401)

    def test_verify_token_success(self):
        from backend.auth.auth_guard import _verify_token_or_401
        with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
            with patch('backend.auth.auth_guard.verify_jwt', return_value={"sub": "u1"}):
                result = _verify_token_or_401("valid_token")
                self.assertEqual(result["sub"], "u1")


class TestAuthGuardWSAuth(unittest.TestCase):
    """Tests for ws_authenticate."""

    def test_ws_auth_bypass(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        with patch('backend.auth.auth_guard.is_temporary_auth_bypass_enabled', return_value=True):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
        self.assertEqual(result["sub"], "temp-public-admin")

    def test_ws_auth_query_param_rejected(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {"token": "leaked_token"}
        ws.headers = {}
        with patch('backend.auth.auth_guard.is_temporary_auth_bypass_enabled', return_value=False):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
        self.assertIsNone(result)

    def test_ws_auth_no_token(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "", "sec-websocket-protocol": ""}
        with patch('backend.auth.auth_guard.is_temporary_auth_bypass_enabled', return_value=False):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
        self.assertIsNone(result)

    def test_ws_auth_bearer_protocol(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "", "sec-websocket-protocol": "bearer.valid_token"}
        with patch('backend.auth.auth_guard.is_temporary_auth_bypass_enabled', return_value=False):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
                with patch('backend.auth.auth_guard.verify_jwt', return_value={"sub": "u1"}):
                    result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
        self.assertEqual(result["sub"], "u1")

    def test_ws_auth_cookie(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "ygb_auth=cookie_token", "sec-websocket-protocol": ""}
        with patch('backend.auth.auth_guard.is_temporary_auth_bypass_enabled', return_value=False):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
                with patch('backend.auth.auth_guard.verify_jwt', return_value={"sub": "u2"}):
                    result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
        self.assertEqual(result["sub"], "u2")

    def test_ws_auth_revoked_token(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "", "sec-websocket-protocol": "bearer.revoked"}
        with patch('backend.auth.auth_guard.is_temporary_auth_bypass_enabled', return_value=False):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=True):
                result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
        self.assertIsNone(result)

    def test_ws_auth_revoked_session(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "", "sec-websocket-protocol": "bearer.token"}
        with patch('backend.auth.auth_guard.is_temporary_auth_bypass_enabled', return_value=False):
            with patch('backend.auth.auth_guard.is_token_revoked', return_value=False):
                with patch('backend.auth.auth_guard.verify_jwt', return_value={"sub": "u1", "session_id": "s1"}):
                    with patch('backend.auth.auth_guard.is_session_revoked', return_value=True):
                        result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
        self.assertIsNone(result)


class TestRedisStoreMocked(unittest.TestCase):
    """Tests for _RedisStore with mocked Redis."""

    def test_redis_store_connection_failure(self):
        from backend.auth.revocation_store import _RedisStore
        mock_redis_mod = MagicMock()
        mock_redis_mod.Redis.from_url.return_value.ping.side_effect = Exception("Connection refused")
        with patch.dict('sys.modules', {'redis': mock_redis_mod}):
            store = _RedisStore("redis://fake:6379/0")
        self.assertIsNone(store._client)

    def test_redis_store_unavailable_fail_closed(self):
        from backend.auth.revocation_store import _RedisStore
        mock_redis_mod = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.side_effect = Exception("offline")
        mock_redis_mod.Redis.from_url.return_value = mock_client
        with patch.dict('sys.modules', {'redis': mock_redis_mod}):
            store = _RedisStore("redis://fake:6379/0")
            store._client = mock_client
            # Fail-closed: token treated as revoked when Redis is down
            self.assertTrue(store.is_token_revoked("any"))
            self.assertTrue(store.is_session_revoked("any"))


class TestRevocationBackendHealthFile(unittest.TestCase):
    """Tests for get_backend_health with file backend."""

    def test_backend_health_file(self):
        from backend.auth import revocation_store
        revocation_store.reset_store()
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "rev.json")
            with patch.dict(os.environ, {"REVOCATION_BACKEND": "file", "REVOCATION_FILE_PATH": path}):
                health = revocation_store.get_backend_health()
                self.assertTrue(health["available"])
                self.assertIn("file_path", health)
        revocation_store.reset_store()


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()

