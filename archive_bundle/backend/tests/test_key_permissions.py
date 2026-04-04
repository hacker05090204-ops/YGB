"""
test_key_permissions.py — Key Storage Hardening Tests
=====================================================
Tests for KeyManager hardening:
  - Permission validation (file mode)
  - Fingerprint logging
  - Rotation audit log tracking
  - Strict mode enforcement
  - World-readable key rejection (POSIX)
=====================================================
"""

import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))

from governance.approval_ledger import KeyManager


class TestKeyFingerprint(unittest.TestCase):
    """Test key fingerprint generation."""

    def test_fingerprint_is_16_hex(self):
        """Fingerprint is first 16 hex chars of SHA-256."""
        fp = KeyManager._key_fingerprint(b"test-secret")
        self.assertEqual(len(fp), 16)
        self.assertTrue(all(c in '0123456789abcdef' for c in fp))

    def test_fingerprint_is_deterministic(self):
        """Same key always produces same fingerprint."""
        fp1 = KeyManager._key_fingerprint(b"my-key-v1")
        fp2 = KeyManager._key_fingerprint(b"my-key-v1")
        self.assertEqual(fp1, fp2)

    def test_different_keys_different_fingerprints(self):
        """Different keys produce different fingerprints."""
        fp1 = KeyManager._key_fingerprint(b"key-alpha")
        fp2 = KeyManager._key_fingerprint(b"key-beta")
        self.assertNotEqual(fp1, fp2)

    def test_fingerprint_matches_manual_sha256(self):
        """Fingerprint matches manual SHA-256 truncation."""
        secret = b"verification-test"
        expected = hashlib.sha256(secret).hexdigest()[:16]
        self.assertEqual(KeyManager._key_fingerprint(secret), expected)


class TestFilePermissions(unittest.TestCase):
    """Test file permission checking."""

    def test_windows_always_passes(self):
        """On Windows, NTFS ACLs are trusted — always passes."""
        if os.name == 'nt':
            with tempfile.NamedTemporaryFile(delete=False) as f:
                f.write(b"test")
                path = f.name
            try:
                ok, reason = KeyManager._check_file_permissions(path)
                self.assertTrue(ok)
                self.assertIn("WINDOWS_NTFS", reason)
            finally:
                os.unlink(path)
        else:
            self.skipTest("Windows-specific test")

    @unittest.skipIf(os.name == 'nt', "POSIX permission test")
    def test_mode_600_passes(self):
        """Mode 0o600 passes permission check."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"secret")
            path = f.name
        try:
            os.chmod(path, 0o600)
            ok, reason = KeyManager._check_file_permissions(path)
            self.assertTrue(ok)
        finally:
            os.unlink(path)

    @unittest.skipIf(os.name == 'nt', "POSIX permission test")
    def test_world_readable_rejected(self):
        """Mode 0o644 (world-readable) is rejected."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"secret")
            path = f.name
        try:
            os.chmod(path, 0o644)
            ok, reason = KeyManager._check_file_permissions(path)
            self.assertFalse(ok)
            self.assertIn("INSECURE_PERMISSIONS", reason)
        finally:
            os.unlink(path)

    @unittest.skipIf(os.name == 'nt', "POSIX permission test")
    def test_group_readable_rejected(self):
        """Mode 0o640 (group-readable) is rejected."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"secret")
            path = f.name
        try:
            os.chmod(path, 0o640)
            ok, reason = KeyManager._check_file_permissions(path)
            self.assertFalse(ok)
            self.assertIn("INSECURE_PERMISSIONS", reason)
        finally:
            os.unlink(path)


class TestAuditLog(unittest.TestCase):
    """Test key rotation audit logging."""

    def test_default_key_logs_fallback(self):
        """Default KeyManager (no YGB_KEY_DIR) logs KEY_FALLBACK."""
        km = KeyManager()
        log = km.audit_log
        self.assertGreater(len(log), 0)
        events = [e["event"] for e in log]
        self.assertIn("KEY_FALLBACK", events)

    def test_add_key_logged(self):
        """Adding a key creates KEY_ADDED audit entry."""
        km = KeyManager()
        km.add_key("test-key", b"secret")
        log = km.audit_log
        events = [e["event"] for e in log]
        self.assertIn("KEY_ADDED", events)
        # Check fingerprint is in detail
        add_entry = [e for e in log if e["event"] == "KEY_ADDED"][0]
        self.assertIn("fingerprint=", add_entry["detail"])

    def test_revoke_key_logged(self):
        """Revoking a key creates KEY_REVOKED audit entry."""
        km = KeyManager()
        km.add_key("rev-key", b"secret")
        km.revoke_key("rev-key")
        log = km.audit_log
        events = [e["event"] for e in log]
        self.assertIn("KEY_REVOKED", events)

    def test_audit_log_immutable(self):
        """Audit log returns a copy, not internal reference."""
        km = KeyManager()
        log1 = km.audit_log
        log1.clear()  # mutate the returned list
        log2 = km.audit_log
        self.assertGreater(len(log2), 0, "Original log should be unaffected")

    def test_audit_entries_have_timestamps(self):
        """Every audit entry has a timestamp."""
        km = KeyManager()
        km.add_key("ts-key", b"secret")
        for entry in km.audit_log:
            self.assertIn("timestamp", entry)
            self.assertIsInstance(entry["timestamp"], float)
            self.assertGreater(entry["timestamp"], 0)

    def test_full_rotation_audit_trail(self):
        """Full rotation cycle generates complete audit trail."""
        km = KeyManager()
        km.add_key("v1", b"secret-v1")
        km.add_key("v2", b"secret-v2")
        km.revoke_key("v1")
        events = [e["event"] for e in km.audit_log]
        self.assertIn("KEY_FALLBACK", events)
        self.assertEqual(events.count("KEY_ADDED"), 2)
        self.assertIn("KEY_REVOKED", events)


class TestStrictMode(unittest.TestCase):
    """Test strict mode key loading."""

    def test_strict_mode_rejects_fallback(self):
        """Strict mode raises ValueError when YGB_KEY_DIR not set."""
        # Ensure YGB_KEY_DIR is not set
        old = os.environ.pop("YGB_KEY_DIR", None)
        try:
            with self.assertRaises(ValueError) as ctx:
                KeyManager(strict=True)
            self.assertIn("KEY_STORAGE_ERROR", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["YGB_KEY_DIR"] = old

    def test_strict_mode_with_valid_dir(self):
        """Strict mode succeeds when YGB_KEY_DIR has valid keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a key file
            key_path = os.path.join(tmpdir, "prod-key-v1.key")
            with open(key_path, "wb") as f:
                f.write(b"production-secret-v1")
            # Set permissions (Windows: NTFS ACLs are trusted)
            if os.name != 'nt':
                os.chmod(key_path, 0o600)

            old = os.environ.get("YGB_KEY_DIR")
            os.environ["YGB_KEY_DIR"] = tmpdir
            try:
                km = KeyManager(strict=True)
                self.assertIn("prod-key-v1", km.available_key_ids)
                self.assertEqual(km.active_key_id, "prod-key-v1")
            finally:
                if old is not None:
                    os.environ["YGB_KEY_DIR"] = old
                else:
                    os.environ.pop("YGB_KEY_DIR", None)

    def test_strict_mode_empty_dir_fails(self):
        """Strict mode fails if YGB_KEY_DIR exists but has no .key files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old = os.environ.get("YGB_KEY_DIR")
            os.environ["YGB_KEY_DIR"] = tmpdir
            try:
                with self.assertRaises(ValueError) as ctx:
                    KeyManager(strict=True)
                self.assertIn("no valid keys", str(ctx.exception))
            finally:
                if old is not None:
                    os.environ["YGB_KEY_DIR"] = old
                else:
                    os.environ.pop("YGB_KEY_DIR", None)


class TestKeyDirLoading(unittest.TestCase):
    """Test loading keys from YGB_KEY_DIR with permission checks."""

    def test_key_loaded_from_dir(self):
        """Keys loaded from directory with fingerprint audit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            key_path = os.path.join(tmpdir, "test-key.key")
            with open(key_path, "wb") as f:
                f.write(b"test-secret-123")
            if os.name != 'nt':
                os.chmod(key_path, 0o600)

            old = os.environ.get("YGB_KEY_DIR")
            os.environ["YGB_KEY_DIR"] = tmpdir
            try:
                km = KeyManager()
                self.assertIn("test-key", km.available_key_ids)
                key_id, secret = km.get_signing_key()
                self.assertEqual(key_id, "test-key")
                self.assertEqual(secret, b"test-secret-123")
                # Verify audit log has KEY_LOADED with fingerprint
                loaded = [e for e in km.audit_log if e["event"] == "KEY_LOADED"]
                self.assertEqual(len(loaded), 1)
                self.assertIn("fingerprint=", loaded[0]["detail"])
            finally:
                if old is not None:
                    os.environ["YGB_KEY_DIR"] = old
                else:
                    os.environ.pop("YGB_KEY_DIR", None)

    def test_revocation_list_loaded(self):
        """Revocation list from directory is loaded and audited."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create key + revocation list
            key_path = os.path.join(tmpdir, "active.key")
            with open(key_path, "wb") as f:
                f.write(b"active-secret")
            if os.name != 'nt':
                os.chmod(key_path, 0o600)

            revoke_path = os.path.join(tmpdir, "revoked_keys.json")
            with open(revoke_path, "w") as f:
                json.dump(["old-key-v1", "old-key-v2"], f)

            old = os.environ.get("YGB_KEY_DIR")
            os.environ["YGB_KEY_DIR"] = tmpdir
            try:
                km = KeyManager()
                self.assertTrue(km.is_revoked("old-key-v1"))
                self.assertTrue(km.is_revoked("old-key-v2"))
                self.assertFalse(km.is_revoked("active"))
                # Verify audit log has revocation entries
                revoked = [e for e in km.audit_log
                           if e["event"] == "KEY_REVOKED_ON_LOAD"]
                self.assertEqual(len(revoked), 2)
            finally:
                if old is not None:
                    os.environ["YGB_KEY_DIR"] = old
                else:
                    os.environ.pop("YGB_KEY_DIR", None)


if __name__ == "__main__":
    unittest.main()
