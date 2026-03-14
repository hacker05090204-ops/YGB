"""
Coverage boost round 10 — final lines to cross 95%.
Targets:
  - admin_auth.py: session file corruption, TOTP, user CRUD (21 miss)
  - approval_ledger.py: POSIX file perms, key loading, chain verify (11 miss)
  - geoip.py: query_provider internal success path (7 miss)
"""

import hashlib
import json
import os
import secrets
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# 1. admin_auth.py — session file corruption, TOTP, user CRUD
# ---------------------------------------------------------------------------

class TestAdminAuthSessionFile(unittest.TestCase):
    """Cover admin_auth session file handling paths."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_validate_session_corrupted_json(self):
        from backend.api import admin_auth
        session_dir = os.path.join(self.tmp, "sessions")
        os.makedirs(session_dir, exist_ok=True)
        token = "test-corrupted"
        with open(os.path.join(session_dir, f"{token}.json"), "w") as f:
            f.write("{bad json!!!")
        with patch.object(admin_auth, 'SESSION_DIR', session_dir):
            result = admin_auth.validate_session(token)
        self.assertIsNone(result)

    def test_validate_session_expired(self):
        from backend.api import admin_auth
        session_dir = os.path.join(self.tmp, "sessions")
        os.makedirs(session_dir, exist_ok=True)
        token = "test-expired"
        with open(os.path.join(session_dir, f"{token}.json"), "w") as f:
            json.dump({"user_id": "a", "role": "ADMIN",
                       "expires_at": time.time() - 3600}, f)
        with patch.object(admin_auth, 'SESSION_DIR', session_dir):
            with patch.object(admin_auth, 'destroy_session'):
                result = admin_auth.validate_session(token)
        self.assertIsNone(result)

    def test_verify_totp_bad_code(self):
        from backend.api import admin_auth
        result = admin_auth.verify_totp("JBSWY3DPEHPK3PXP", "000000")
        self.assertFalse(result)

    def test_get_totp_uri(self):
        from backend.api import admin_auth
        uri = admin_auth.get_totp_uri("JBSWY3DPEHPK3PXP", "admin@ygb.dev")
        self.assertIn("otpauth://totp/", uri)
        self.assertIn("JBSWY3DPEHPK3PXP", uri)

    def test_load_users_no_file(self):
        from backend.api import admin_auth
        with patch.object(admin_auth, 'USERS_DB_PATH', "/nonexistent/users.json"):
            result = admin_auth._load_users()
        self.assertEqual(result, {"users": {}})

    def test_load_users_corrupted(self):
        from backend.api import admin_auth
        path = os.path.join(self.tmp, "users.json")
        with open(path, "w") as f:
            f.write("{corrupted!")
        with patch.object(admin_auth, 'USERS_DB_PATH', path):
            result = admin_auth._load_users()
        self.assertEqual(result, {"users": {}})


# ---------------------------------------------------------------------------
# 2. approval_ledger.py — key loading, chain verify, POSIX perms
# ---------------------------------------------------------------------------

class TestApprovalLedgerEdgeCases(unittest.TestCase):
    """Cover approval_ledger remaining edge cases."""

    def test_check_file_permissions_windows(self):
        from backend.governance.approval_ledger import KeyManager
        ok, reason = KeyManager._check_file_permissions("some_path")
        self.assertTrue(ok)
        self.assertEqual(reason, "WINDOWS_NTFS")

    def test_key_loading_from_directory(self):
        from backend.governance.approval_ledger import KeyManager
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, "test-key.key"), "wb") as f:
                f.write(secrets.token_bytes(32))
            with patch.dict(os.environ, {"YGB_KEY_DIR": tmp, "YGB_ENV": "dev"}):
                km = KeyManager(strict=False)
            self.assertIn("test-key", km.available_key_ids)
        finally:
            shutil.rmtree(tmp)

    def test_key_loading_with_revocation_list(self):
        from backend.governance.approval_ledger import KeyManager
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, "key-v2.key"), "wb") as f:
                f.write(secrets.token_bytes(32))
            with open(os.path.join(tmp, "revoked_keys.json"), "w") as f:
                json.dump(["key-v1"], f)
            with patch.dict(os.environ, {"YGB_KEY_DIR": tmp}):
                km = KeyManager(strict=False)
            self.assertTrue(km.is_revoked("key-v1"))
            self.assertFalse(km.is_revoked("key-v2"))
        finally:
            shutil.rmtree(tmp)

    def test_append_and_verify_chain(self):
        from backend.governance.approval_ledger import ApprovalLedger
        tmp = tempfile.mkdtemp()
        try:
            with patch.dict(os.environ, {"YGB_APPROVAL_SECRET": secrets.token_hex(32)}):
                ledger = ApprovalLedger(
                    ledger_path=os.path.join(tmp, "ledger.jsonl"))
            token = ledger.sign_approval(42, "reviewer", "looks good")
            ledger.append(token, expected_field_id=42)
            self.assertTrue(ledger.verify_chain())
            self.assertTrue(ledger.has_approval(42))
            self.assertEqual(ledger.entry_count, 1)
        finally:
            shutil.rmtree(tmp)

    def test_token_from_dict_roundtrip(self):
        from backend.governance.approval_ledger import ApprovalToken
        d = {
            "field_id": 7, "approver_id": "admin", "reason": "ok",
            "timestamp": time.time(), "signature": "abc123",
            "nonce": "n1", "model_hash": "m1",
            "expiration_window": 1800.0, "key_id": "k1",
        }
        t = ApprovalToken.from_dict(d)
        self.assertEqual(t.field_id, 7)
        self.assertEqual(t.key_id, "k1")
        back = t.to_dict()
        self.assertEqual(back["field_id"], 7)


# ---------------------------------------------------------------------------
# 3. geoip.py — query_provider mock paths
# ---------------------------------------------------------------------------

class TestGeoIPQueryProvider(unittest.TestCase):
    """Cover geoip _query_provider success internals."""

    def test_query_provider_success(self):
        from backend.auth import geoip
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "city": "London", "region": "England", "country_name": "UK"
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = geoip._query_provider("https://ipapi.co/8.8.8.8/json/")
        self.assertIsNotNone(result)
        self.assertEqual(result["city"], "London")

    def test_query_provider_non_200(self):
        from backend.auth import geoip
        mock_resp = MagicMock()
        mock_resp.status = 503
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = geoip._query_provider("https://ipapi.co/8.8.8.8/json/")
        self.assertIsNone(result)

    def test_query_provider_non_dict(self):
        from backend.auth import geoip
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'"just a string"'
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        with patch('urllib.request.urlopen', return_value=mock_resp):
            result = geoip._query_provider("https://ipapi.co/8.8.8.8/json/")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# 4. auth_guard — require_auth callable check only
# ---------------------------------------------------------------------------

class TestAuthGuardCallable(unittest.TestCase):
    def test_require_auth_returns_callable(self):
        from backend.auth.auth_guard import require_auth
        self.assertTrue(callable(require_auth))


if __name__ == "__main__":
    unittest.main()
