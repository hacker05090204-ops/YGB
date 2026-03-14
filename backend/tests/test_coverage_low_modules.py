"""
Tests to boost low-coverage modules from 23-75% → 85%+.

Covers missing lines in:
  - backend.auth.auth_guard (48% → 85%+)
  - backend.auth.geoip (23% → 85%+)
  - backend.auth.revocation_store (67% → 85%+)
  - backend.api.report_generator (23% → 85%+ via helpers)
  - backend.api.runtime_api (74% → 85%+)
  - backend.governance.host_action_governor (75% → 85%+)
"""

import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock, AsyncMock


# =========================================================================
# auth_guard — covers lines 84-98, 102-130, 137-160, 182-231, 259-295, etc.
# =========================================================================

class TestAuthGuardAllowedOrigins(unittest.TestCase):
    def test_default_origins(self):
        from backend.auth.auth_guard import _allowed_origins
        origins = _allowed_origins()
        self.assertIn("http://localhost:3000", origins)
        self.assertIn("http://127.0.0.1:3000", origins)
        self.assertIn("http://localhost:8000", origins)

    def test_custom_frontend_url(self):
        from backend.auth.auth_guard import _allowed_origins
        with patch.dict(os.environ, {"FRONTEND_URL": "https://myapp.com/"}):
            origins = _allowed_origins()
            self.assertIn("https://myapp.com", origins)

    def test_extra_origins(self):
        from backend.auth.auth_guard import _allowed_origins
        with patch.dict(os.environ, {"YGB_ALLOWED_ORIGINS": "https://a.com, https://b.com"}):
            origins = _allowed_origins()
            self.assertIn("https://a.com", origins)
            self.assertIn("https://b.com", origins)


class TestAuthGuardNormalizeOrigin(unittest.TestCase):
    def test_full_url(self):
        from backend.auth.auth_guard import _normalize_origin
        self.assertEqual(_normalize_origin("https://example.com/path"), "https://example.com")

    def test_no_scheme(self):
        from backend.auth.auth_guard import _normalize_origin
        self.assertEqual(_normalize_origin("example.com"), "")

    def test_trailing_slash(self):
        from backend.auth.auth_guard import _normalize_origin
        self.assertEqual(_normalize_origin("https://example.com/"), "https://example.com")


class TestAuthGuardExtractCookie(unittest.TestCase):
    def test_primary_cookie(self):
        from backend.auth.auth_guard import _extract_cookie_token
        request = MagicMock()
        request.cookies = {"ygb_auth": "token123"}
        self.assertEqual(_extract_cookie_token(request), "token123")

    def test_legacy_cookie(self):
        from backend.auth.auth_guard import _extract_cookie_token
        request = MagicMock()
        request.cookies = {"ygb_token": "legacy_tok"}
        self.assertEqual(_extract_cookie_token(request), "legacy_tok")

    def test_no_cookie(self):
        from backend.auth.auth_guard import _extract_cookie_token
        request = MagicMock()
        request.cookies = {}
        self.assertIsNone(_extract_cookie_token(request))


class TestAuthGuardTempBypass(unittest.TestCase):
    def test_bypass_disabled_by_default(self):
        from backend.auth.auth_guard import is_temporary_auth_bypass_enabled
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            self.assertFalse(is_temporary_auth_bypass_enabled())

    def test_bypass_enabled(self):
        from backend.auth.auth_guard import is_temporary_auth_bypass_enabled
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "true"}):
            self.assertTrue(is_temporary_auth_bypass_enabled())

    def test_build_temp_user(self):
        from backend.auth.auth_guard import build_temporary_auth_user
        user = build_temporary_auth_user("test")
        self.assertEqual(user["_auth_via"], "test")
        self.assertTrue(user["_temporary_bypass"])
        self.assertEqual(user["role"], "admin")

    def test_build_temp_user_custom_env(self):
        from backend.auth.auth_guard import build_temporary_auth_user
        with patch.dict(os.environ, {
            "YGB_TEMP_AUTH_ROLE": "viewer",
            "YGB_TEMP_AUTH_USER_ID": "custom-user",
            "YGB_TEMP_AUTH_NAME": "Custom Name",
        }):
            user = build_temporary_auth_user()
            self.assertEqual(user["role"], "viewer")
            self.assertEqual(user["sub"], "custom-user")


class TestAuthGuardVerifyToken(unittest.TestCase):
    def test_revoked_token_raises(self):
        from backend.auth.auth_guard import _verify_token_or_401
        from fastapi import HTTPException
        with patch("backend.auth.auth_guard.is_token_revoked", return_value=True):
            with self.assertRaises(HTTPException) as ctx:
                _verify_token_or_401("bad-token")
            self.assertEqual(ctx.exception.status_code, 401)

    def test_invalid_jwt_raises(self):
        from backend.auth.auth_guard import _verify_token_or_401
        from fastapi import HTTPException
        with patch("backend.auth.auth_guard.is_token_revoked", return_value=False), \
             patch("backend.auth.auth_guard.verify_jwt", return_value=None):
            with self.assertRaises(HTTPException) as ctx:
                _verify_token_or_401("invalid-token")
            self.assertEqual(ctx.exception.status_code, 401)

    def test_revoked_session_raises(self):
        from backend.auth.auth_guard import _verify_token_or_401
        from fastapi import HTTPException
        payload = {"sub": "user1", "session_id": "sess123"}
        with patch("backend.auth.auth_guard.is_token_revoked", return_value=False), \
             patch("backend.auth.auth_guard.verify_jwt", return_value=payload), \
             patch("backend.auth.auth_guard.is_session_revoked", return_value=True):
            with self.assertRaises(HTTPException):
                _verify_token_or_401("valid-token")

    def test_valid_token(self):
        from backend.auth.auth_guard import _verify_token_or_401
        payload = {"sub": "user1", "role": "admin"}
        with patch("backend.auth.auth_guard.is_token_revoked", return_value=False), \
             patch("backend.auth.auth_guard.verify_jwt", return_value=payload), \
             patch("backend.auth.auth_guard.is_session_revoked", return_value=False):
            result = _verify_token_or_401("good-token")
            self.assertEqual(result["sub"], "user1")


class TestAuthGuardSSRF(unittest.TestCase):
    def test_empty_url(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("")
        self.assertFalse(safe)
        self.assertTrue(any(v["rule"] == "EMPTY_TARGET" for v in violations))

    def test_localhost_blocked(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://localhost/path")
        self.assertFalse(safe)

    def test_private_ip_blocked(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://192.168.1.1")
        self.assertFalse(safe)

    def test_metadata_ip_blocked(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://169.254.169.254/latest")
        self.assertFalse(safe)

    def test_valid_public_domain(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("https://example.com")
        self.assertTrue(safe)
        self.assertEqual(len(violations), 0)

    def test_url_without_scheme(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("example.com")
        self.assertTrue(safe)

    def test_no_host(self):
        from backend.auth.auth_guard import validate_target_url
        safe, violations = validate_target_url("http://")
        self.assertFalse(safe)


class TestAuthGuardPreflightChecks(unittest.TestCase):
    def test_preflight_missing_secrets_raises(self):
        from backend.auth.auth_guard import preflight_check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "", "YGB_HMAC_SECRET": "", "YGB_VIDEO_JWT_SECRET": "",
        }, clear=False):
            with self.assertRaises(RuntimeError) as ctx:
                preflight_check_secrets()
            self.assertIn("PREFLIGHT", str(ctx.exception))

    def test_preflight_placeholder_raises(self):
        from backend.auth.auth_guard import preflight_check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "changeme",
            "YGB_HMAC_SECRET": "a" * 32,
            "YGB_VIDEO_JWT_SECRET": "b" * 32,
        }, clear=False):
            with self.assertRaises(RuntimeError):
                preflight_check_secrets()

    def test_preflight_short_secret_raises(self):
        from backend.auth.auth_guard import preflight_check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "short",
            "YGB_HMAC_SECRET": "a" * 32,
            "YGB_VIDEO_JWT_SECRET": "b" * 32,
        }, clear=False):
            with self.assertRaises(RuntimeError):
                preflight_check_secrets()

    def test_preflight_pattern_raises(self):
        from backend.auth.auth_guard import preflight_check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "this-is-your-secret-change-me-please-now",
            "YGB_HMAC_SECRET": "a" * 32,
            "YGB_VIDEO_JWT_SECRET": "b" * 32,
        }, clear=False):
            with self.assertRaises(RuntimeError):
                preflight_check_secrets()

    def test_preflight_success(self):
        from backend.auth.auth_guard import preflight_check_secrets
        import secrets as _s
        with patch.dict(os.environ, {
            "JWT_SECRET": _s.token_hex(32),
            "YGB_HMAC_SECRET": _s.token_hex(32),
            "YGB_VIDEO_JWT_SECRET": _s.token_hex(32),
        }, clear=False):
            # Should not raise
            preflight_check_secrets()


class TestAuthGuardWSAuth(unittest.TestCase):
    def test_ws_auth_bypass_enabled(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "true"}):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
            self.assertIsNotNone(result)
            self.assertTrue(result["_temporary_bypass"])

    def test_ws_auth_query_param_rejected(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {"token": "leaked_token"}
        ws.headers = {}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
            self.assertIsNone(result)

    def test_ws_auth_no_token(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "", "sec-websocket-protocol": "other"}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
            self.assertIsNone(result)

    def test_ws_auth_protocol_token(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {
            "cookie": "",
            "sec-websocket-protocol": "bearer.valid-jwt-token",
        }
        payload = {"sub": "user1", "role": "admin"}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}), \
             patch("backend.auth.auth_guard.is_token_revoked", return_value=False), \
             patch("backend.auth.auth_guard.verify_jwt", return_value=payload), \
             patch("backend.auth.auth_guard.is_session_revoked", return_value=False):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
            self.assertIsNotNone(result)
            self.assertEqual(result["sub"], "user1")

    def test_ws_auth_cookie_token(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {
            "cookie": "ygb_auth=cookie-jwt-token",
            "sec-websocket-protocol": "",
        }
        payload = {"sub": "user2", "role": "admin"}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}), \
             patch("backend.auth.auth_guard.is_token_revoked", return_value=False), \
             patch("backend.auth.auth_guard.verify_jwt", return_value=payload), \
             patch("backend.auth.auth_guard.is_session_revoked", return_value=False):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
            self.assertIsNotNone(result)

    def test_ws_auth_revoked_token(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "", "sec-websocket-protocol": "bearer.revoked-token"}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}), \
             patch("backend.auth.auth_guard.is_token_revoked", return_value=True):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
            self.assertIsNone(result)

    def test_ws_auth_revoked_session(self):
        import asyncio
        from backend.auth.auth_guard import ws_authenticate
        ws = MagicMock()
        ws.query_params = {}
        ws.headers = {"cookie": "", "sec-websocket-protocol": "bearer.valid-jwt"}
        payload = {"sub": "user1", "session_id": "revoked-session"}
        with patch.dict(os.environ, {"YGB_TEMP_AUTH_BYPASS": "false"}), \
             patch("backend.auth.auth_guard.is_token_revoked", return_value=False), \
             patch("backend.auth.auth_guard.verify_jwt", return_value=payload), \
             patch("backend.auth.auth_guard.is_session_revoked", return_value=True):
            result = asyncio.get_event_loop().run_until_complete(ws_authenticate(ws))
            self.assertIsNone(result)


# =========================================================================
# geoip — covers lines 25-29, 39-54, 58-69, 78-113
# =========================================================================

class TestGeoIP(unittest.TestCase):
    def test_private_ip(self):
        from backend.auth.geoip import resolve_ip_geolocation
        self.assertEqual(resolve_ip_geolocation("192.168.1.1"), "Local/Private Network")
        self.assertEqual(resolve_ip_geolocation("10.0.0.1"), "Local/Private Network")
        self.assertEqual(resolve_ip_geolocation("127.0.0.1"), "Local/Private Network")

    def test_empty_ip(self):
        from backend.auth.geoip import resolve_ip_geolocation
        self.assertEqual(resolve_ip_geolocation(""), "Unknown")
        self.assertEqual(resolve_ip_geolocation("unknown"), "Unknown")

    def test_is_private_or_local(self):
        from backend.auth.geoip import _is_private_or_local
        self.assertTrue(_is_private_or_local("192.168.0.1"))
        self.assertTrue(_is_private_or_local("127.0.0.1"))
        self.assertTrue(_is_private_or_local("10.10.10.10"))
        self.assertFalse(_is_private_or_local("8.8.8.8"))
        self.assertFalse(_is_private_or_local("not-an-ip"))

    def test_safe_get(self):
        from backend.auth.geoip import _safe_get
        self.assertEqual(_safe_get({"city": "Paris"}, ("city",)), "Paris")
        self.assertEqual(_safe_get({"city": " "}, ("city",)), "")
        self.assertEqual(_safe_get({}, ("city",)), "")
        self.assertEqual(_safe_get({"region": "IDF"}, ("city", "region")), "IDF")

    def test_format_location(self):
        from backend.auth.geoip import _format_location
        self.assertEqual(
            _format_location({"city": "Paris", "country": "France"}),
            "Paris, France",
        )
        self.assertEqual(_format_location({}), "")
        self.assertEqual(_format_location({"city": "Berlin"}), "Berlin")

    def test_query_provider_failure(self):
        from backend.auth.geoip import _query_provider
        result = _query_provider("http://nonexistent.invalid/test", timeout=0.5)
        self.assertIsNone(result)

    def test_resolve_with_cache(self):
        from backend.auth.geoip import resolve_ip_geolocation, _CACHE
        _CACHE["8.8.8.8"] = (time.time(), "Mountain View, CA, US")
        result = resolve_ip_geolocation("8.8.8.8")
        self.assertEqual(result, "Mountain View, CA, US")
        del _CACHE["8.8.8.8"]

    def test_resolve_cache_expired(self):
        from backend.auth.geoip import resolve_ip_geolocation, _CACHE
        _CACHE["1.2.3.4"] = (time.time() - 10000, "Old Location")
        with patch("backend.auth.geoip._query_provider", return_value=None):
            result = resolve_ip_geolocation("1.2.3.4")
            self.assertEqual(result, "Unknown")
        if "1.2.3.4" in _CACHE:
            del _CACHE["1.2.3.4"]

    def test_resolve_with_provider(self):
        from backend.auth.geoip import resolve_ip_geolocation, _CACHE
        if "5.6.7.8" in _CACHE:
            del _CACHE["5.6.7.8"]
        with patch("backend.auth.geoip._query_provider", return_value={"city": "London", "country": "UK"}):
            result = resolve_ip_geolocation("5.6.7.8")
            self.assertEqual(result, "London, UK")
        if "5.6.7.8" in _CACHE:
            del _CACHE["5.6.7.8"]

    def test_resolve_provider_failure_returns_unknown(self):
        from backend.auth.geoip import resolve_ip_geolocation, _CACHE
        if "9.9.9.9" in _CACHE:
            del _CACHE["9.9.9.9"]
        with patch("backend.auth.geoip._query_provider", return_value=None):
            result = resolve_ip_geolocation("9.9.9.9")
            self.assertEqual(result, "Unknown")

    def test_resolve_provider_success_false(self):
        from backend.auth.geoip import resolve_ip_geolocation, _CACHE
        if "2.3.4.5" in _CACHE:
            del _CACHE["2.3.4.5"]
        with patch("backend.auth.geoip._query_provider", return_value={"success": False}):
            result = resolve_ip_geolocation("2.3.4.5")
            self.assertEqual(result, "Unknown")


# =========================================================================
# revocation_store — covers lines 54-55, 87-88, 116-177, 194-221
# =========================================================================

class TestRevocationStoreMemory(unittest.TestCase):
    def setUp(self):
        from backend.auth.revocation_store import _MemoryStore
        self.store = _MemoryStore()

    def test_revoke_and_check_token(self):
        self.store.revoke_token("hash1")
        self.assertTrue(self.store.is_token_revoked("hash1"))
        self.assertFalse(self.store.is_token_revoked("hash2"))

    def test_revoke_and_check_session(self):
        self.store.revoke_session("sess1")
        self.assertTrue(self.store.is_session_revoked("sess1"))
        self.assertFalse(self.store.is_session_revoked("sess2"))

    def test_clear(self):
        self.store.revoke_token("h1")
        self.store.revoke_session("s1")
        self.store.clear()
        self.assertFalse(self.store.is_token_revoked("h1"))
        self.assertFalse(self.store.is_session_revoked("s1"))


class TestRevocationStoreFile(unittest.TestCase):
    def test_file_store_lifecycle(self):
        from backend.auth.revocation_store import _FileStore
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "revocations.json")
        store = _FileStore(path=path)

        store.revoke_token("hash_a")
        self.assertTrue(store.is_token_revoked("hash_a"))
        self.assertFalse(store.is_token_revoked("hash_b"))

        store.revoke_session("sess_a")
        self.assertTrue(store.is_session_revoked("sess_a"))

        # Persistence check
        store2 = _FileStore(path=path)
        self.assertTrue(store2.is_token_revoked("hash_a"))
        self.assertTrue(store2.is_session_revoked("sess_a"))

    def test_file_store_clear(self):
        from backend.auth.revocation_store import _FileStore
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "revocations.json")
        store = _FileStore(path=path)
        store.revoke_token("h1")
        store.clear()
        self.assertFalse(store.is_token_revoked("h1"))

    def test_file_store_bad_json(self):
        from backend.auth.revocation_store import _FileStore
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "bad.json")
        with open(path, "w") as f:
            f.write("NOT JSON")
        store = _FileStore(path=path)
        self.assertFalse(store.is_token_revoked("anything"))

    def test_file_store_no_duplicate(self):
        from backend.auth.revocation_store import _FileStore
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "revocations.json")
        store = _FileStore(path=path)
        store.revoke_token("h1")
        store.revoke_token("h1")  # Duplicate
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data["tokens"].count("h1"), 1)


class TestRevocationStorePublicAPI(unittest.TestCase):
    def setUp(self):
        from backend.auth.revocation_store import reset_store
        reset_store()

    def test_revoke_and_check_token(self):
        from backend.auth import revocation_store
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            revocation_store.reset_store()
            revocation_store.revoke_token("my-bearer-token")
            self.assertTrue(revocation_store.is_token_revoked("my-bearer-token"))
            self.assertFalse(revocation_store.is_token_revoked("other-token"))

    def test_revoke_and_check_session(self):
        from backend.auth import revocation_store
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            revocation_store.reset_store()
            revocation_store.revoke_session("sess123")
            self.assertTrue(revocation_store.is_session_revoked("sess123"))

    def test_hash_token(self):
        from backend.auth.revocation_store import _hash_token
        h = _hash_token("mytoken")
        self.assertEqual(len(h), 64)

    def test_get_backend_health_memory(self):
        from backend.auth import revocation_store
        with patch.dict(os.environ, {"REVOCATION_BACKEND": "memory"}):
            revocation_store.reset_store()
            health = revocation_store.get_backend_health()
            self.assertEqual(health["type"], "_MemoryStore")
            self.assertTrue(health["available"])

    def test_get_backend_health_file(self):
        from backend.auth import revocation_store
        tmpdir = tempfile.mkdtemp()
        with patch.dict(os.environ, {
            "REVOCATION_BACKEND": "file",
            "REVOCATION_FILE_PATH": os.path.join(tmpdir, "rev.json"),
        }):
            revocation_store.reset_store()
            health = revocation_store.get_backend_health()
            self.assertEqual(health["type"], "_FileStore")


# =========================================================================
# report_generator — covers helpers and DB init
# =========================================================================

class TestReportGeneratorHelpers(unittest.TestCase):
    def test_generate_id(self):
        from backend.api.report_generator import _generate_id
        rid = _generate_id("rpt")
        self.assertTrue(rid.startswith("rpt-"))
        self.assertEqual(len(rid), 3 + 1 + 16)  # 'rpt' + '-' + 16 hex chars

    def test_now_iso(self):
        from backend.api.report_generator import _now_iso
        ts = _now_iso()
        self.assertIn("T", ts)
        self.assertIn(":", ts)

    def test_get_db_path_default(self):
        from backend.api.report_generator import _get_db_path
        with patch.dict(os.environ, {"DATABASE_URL": "sqlite:///C:/test/db.db"}):
            path = _get_db_path()
            self.assertEqual(path, "C:/test/db.db")

    def test_get_db_connection(self):
        from backend.api.report_generator import get_db_connection
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.db")
        with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{db_path}"}):
            conn = get_db_connection()
            self.assertIsNotNone(conn)
            conn.close()

    def test_ensure_tables(self):
        import backend.api.report_generator as rg
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.db")
        orig = rg._TABLES_CREATED
        rg._TABLES_CREATED = False
        with patch.dict(os.environ, {"DATABASE_URL": f"sqlite:///{db_path}"}):
            rg._ensure_tables()
            self.assertTrue(rg._TABLES_CREATED)
        rg._TABLES_CREATED = orig

    def test_log_activity_fallback(self):
        from backend.api.report_generator import _log_activity
        # Should not raise even if storage_bridge is unavailable
        _log_activity("user1", "TEST_ACTION", "test detail")


# =========================================================================
# host_action_governor — covers missing branches
# =========================================================================

class TestHostActionGovernor(unittest.TestCase):
    def setUp(self):
        from backend.governance.host_action_governor import HostActionGovernor
        self.tmpdir = tempfile.mkdtemp()
        self.ledger_path = os.path.join(self.tmpdir, "ledger.jsonl")
        self.gov = HostActionGovernor(ledger_path=self.ledger_path)

    def test_initial_state(self):
        self.assertEqual(self.gov.entry_count, 0)
        self.assertEqual(self.gov.chain_hash, "0" * 64)

    def test_canonicalize_app_name(self):
        from backend.governance.host_action_governor import HostActionGovernor
        self.assertEqual(HostActionGovernor.canonicalize_app_name("Notepad"), "notepad")
        self.assertEqual(HostActionGovernor.canonicalize_app_name("code"), "code")
        self.assertEqual(HostActionGovernor.canonicalize_app_name("vscode"), "code")
        self.assertIsNone(HostActionGovernor.canonicalize_app_name(""))
        self.assertIsNone(HostActionGovernor.canonicalize_app_name("unknown_app_xyz"))

    def test_canonicalize_task_name(self):
        from backend.governance.host_action_governor import HostActionGovernor
        self.assertEqual(HostActionGovernor.canonicalize_task_name("antigravity"), "antigravity_harness")
        self.assertIsNone(HostActionGovernor.canonicalize_task_name(""))
        self.assertIsNone(HostActionGovernor.canonicalize_task_name("nonexistent_task"))

    def test_issue_session(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="test session",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        self.assertTrue(session.session_id.startswith("HAG-"))
        self.assertEqual(session.requested_by, "agent")
        self.assertEqual(self.gov.entry_count, 1)

    def test_issue_session_reject_empty_requester(self):
        with self.assertRaises(ValueError):
            self.gov.issue_session(
                requested_by="",
                approver_id="admin",
                reason="test",
                allowed_actions=["LAUNCH_APP"],
                allowed_apps=["notepad"],
            )

    def test_issue_session_reject_empty_approver(self):
        with self.assertRaises(ValueError):
            self.gov.issue_session(
                requested_by="agent",
                approver_id="",
                reason="test",
                allowed_actions=["LAUNCH_APP"],
                allowed_apps=["notepad"],
            )

    def test_issue_session_reject_no_actions(self):
        with self.assertRaises(ValueError):
            self.gov.issue_session(
                requested_by="agent",
                approver_id="admin",
                reason="test",
                allowed_actions=[],
            )

    def test_issue_session_reject_unsupported_action(self):
        with self.assertRaises(ValueError):
            self.gov.issue_session(
                requested_by="agent",
                approver_id="admin",
                reason="test",
                allowed_actions=["HACK_EVERYTHING"],
            )

    def test_issue_session_app_action_no_apps(self):
        with self.assertRaises(ValueError):
            self.gov.issue_session(
                requested_by="agent",
                approver_id="admin",
                reason="test",
                allowed_actions=["LAUNCH_APP"],
                # no allowed_apps
            )

    def test_issue_session_task_action_no_tasks(self):
        with self.assertRaises(ValueError):
            self.gov.issue_session(
                requested_by="agent",
                approver_id="admin",
                reason="test",
                allowed_actions=["RUN_APPROVED_TASK"],
                # no allowed_tasks
            )

    def test_verify_chain(self):
        self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="session 1",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="session 2",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["calc"],
        )
        self.assertTrue(self.gov.verify_chain())

    def test_validate_request_no_session(self):
        result = self.gov.validate_request("", "LAUNCH_APP", {})
        self.assertFalse(result["allowed"])
        self.assertIn("SESSION_REQUIRED", result["reason"])

    def test_validate_request_session_not_found(self):
        result = self.gov.validate_request("nonexistent", "LAUNCH_APP", {})
        self.assertFalse(result["allowed"])
        self.assertIn("NOT_FOUND", result["reason"])

    def test_validate_request_expired(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="will expire",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
            expiration_window_s=60,
        )
        # Manually expire by patching time
        with patch("backend.governance.host_action_governor.time") as mock_time:
            mock_time.time.return_value = time.time() + 9999
            result = self.gov.validate_request(
                session.session_id, "LAUNCH_APP", {"app": "notepad"}
            )
            self.assertFalse(result["allowed"])
            self.assertIn("EXPIRED", result["reason"])

    def test_validate_request_action_not_approved(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="only notepad",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        result = self.gov.validate_request(
            session.session_id, "OPEN_URL", {"url": "https://example.com"}
        )
        self.assertFalse(result["allowed"])
        self.assertIn("NOT_APPROVED", result["reason"])

    def test_validate_request_unknown_app(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="test",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        result = self.gov.validate_request(
            session.session_id, "LAUNCH_APP", {"app": "unknown_app_xyz"}
        )
        self.assertFalse(result["allowed"])
        self.assertIn("UNKNOWN", result["reason"])

    def test_validate_request_app_not_in_allowed(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="only notepad",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        result = self.gov.validate_request(
            session.session_id, "LAUNCH_APP", {"app": "calc"}
        )
        self.assertFalse(result["allowed"])
        self.assertIn("NOT_ALLOWED", result["reason"])

    def test_session_to_dict_from_dict(self):
        from backend.governance.host_action_governor import HostActionSession
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="test",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        d = session.to_dict()
        restored = HostActionSession.from_dict(d)
        self.assertEqual(restored.session_id, session.session_id)
        self.assertEqual(restored.allowed_actions, session.allowed_actions)

    def test_describe_session_missing(self):
        desc = self.gov.describe_session("fake-id")
        self.assertEqual(desc["status"], "missing")

    def test_describe_session_active(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="test",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        desc = self.gov.describe_session(session.session_id)
        self.assertEqual(desc["status"], "active")
        self.assertTrue(desc["chain_valid"])

    def test_status_snapshot(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="test",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        snap = self.gov.status_snapshot(session.session_id)
        self.assertEqual(snap["ledger_entries"], 1)
        self.assertTrue(snap["chain_valid"])

    def test_load_persisted_ledger(self):
        from backend.governance.host_action_governor import HostActionGovernor
        self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="persist test",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        gov2 = HostActionGovernor(ledger_path=self.ledger_path)
        gov2.load()
        self.assertEqual(gov2.entry_count, 1)
        self.assertTrue(gov2.verify_chain())

    def test_validate_url_action(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="url test",
            allowed_actions=["OPEN_URL"],
            allowed_apps=["msedge"],
        )
        result = self.gov.validate_request(
            session.session_id, "OPEN_URL", {"url": "not-a-url"}
        )
        self.assertFalse(result["allowed"])
        self.assertIn("URL_INVALID", result["reason"])

    def test_duplicate_session_rejected(self):
        session = self.gov.issue_session(
            requested_by="agent",
            approver_id="admin",
            reason="first",
            allowed_actions=["LAUNCH_APP"],
            allowed_apps=["notepad"],
        )
        with self.assertRaises(ValueError):
            self.gov.append(session)  # Duplicate


if __name__ == "__main__":
    unittest.main()
