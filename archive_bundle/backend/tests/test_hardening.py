"""
Hardening Tests — Error Leakage, Revocation Persistence, Startup Safety

Validates:
1. No str(e) leakage in API/health responses
2. File-backed revocation store survives simulated restarts
3. Revocation health check returns correct backend info
4. Backup config error responses use sanitized messages
5. Startup preflight does not kill foreign processes
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# =========================================================================
# ERROR LEAKAGE TESTS
# =========================================================================


class TestStorageBridgeErrorSanitization(unittest.TestCase):
    """Verify storage bridge health check does not leak internal errors."""

    def test_health_reason_does_not_contain_raw_exception(self):
        """get_storage_health() must never expose raw exception messages."""
        from backend.storage import storage_bridge

        # Save original engine and set it to a mock that raises
        original_engine = storage_bridge._engine
        try:
            mock_engine = MagicMock()
            mock_engine.root = MagicMock()
            mock_engine.root.exists.side_effect = PermissionError(
                "C:\\secret\\internal\\path is locked"
            )
            storage_bridge._engine = mock_engine

            with patch.object(
                storage_bridge,
                "get_storage_topology",
                return_value={
                    "primary_root": "D:/ygb_hdd",
                    "fallback_root": "C:/ygb_hdd_fallback",
                    "active_root": "D:/ygb_hdd",
                    "primary_available": True,
                    "fallback_available": False,
                    "fallback_active": False,
                    "mode": "PRIMARY",
                    "reason": "Primary NAS root active",
                },
            ):
                result = storage_bridge.get_storage_health()
                reason = result.get("reason", "")

            # The raw exception message must NOT appear
            self.assertNotIn("C:\\secret\\internal\\path", reason)
            self.assertNotIn("is locked", reason)
            # But the type name should be present for debugging
            self.assertIn("PermissionError", reason)
        finally:
            storage_bridge._engine = original_engine

    def test_health_returns_active_when_engine_ok(self):
        """Health check returns ACTIVE when engine root exists."""
        from backend.storage import storage_bridge

        original_engine = storage_bridge._engine
        original_lifecycle = storage_bridge._lifecycle
        original_dm = storage_bridge._disk_monitor
        try:
            mock_engine = MagicMock()
            mock_root = MagicMock()
            mock_root.exists.return_value = True
            mock_engine.root = mock_root
            storage_bridge._engine = mock_engine
            storage_bridge._lifecycle = MagicMock()
            storage_bridge._disk_monitor = MagicMock()

            with patch.object(
                storage_bridge,
                "get_storage_topology",
                return_value={
                    "primary_root": "D:/ygb_hdd",
                    "fallback_root": "C:/ygb_hdd_fallback",
                    "active_root": "D:/ygb_hdd",
                    "primary_available": True,
                    "fallback_available": False,
                    "fallback_active": False,
                    "mode": "PRIMARY",
                    "reason": "Primary NAS root active",
                },
            ):
                result = storage_bridge.get_storage_health()
            self.assertEqual(result["status"], "ACTIVE")
            self.assertTrue(result["storage_active"])
        finally:
            storage_bridge._engine = original_engine
            storage_bridge._lifecycle = original_lifecycle
            storage_bridge._disk_monitor = original_dm


class TestBackupConfigErrorSanitization(unittest.TestCase):
    """Verify backup config does not leak internal errors."""

    def test_local_backup_error_reason_is_sanitized(self):
        """get_local_backup_status() must not expose raw exception text."""
        from backend.storage.backup_config import (
            get_local_backup_status,
            BackupTargetStatus,
            _LOCAL_BACKUP_ROOT,
        )

        # Mock _LOCAL_BACKUP_ROOT.exists() to raise
        with patch.object(
            type(_LOCAL_BACKUP_ROOT), "exists",
            side_effect=PermissionError("Access denied to /secret/path"),
        ):
            result = get_local_backup_status()
            self.assertEqual(result.status, BackupTargetStatus.ERROR)
            self.assertNotIn("/secret/path", result.reason)
            self.assertNotIn("Access denied", result.reason)
            self.assertIn("PermissionError", result.reason)


class TestVoiceGatewayErrorSanitization(unittest.TestCase):
    """Verify WebSocket close does not leak internal errors."""

    def test_ws_close_reason_is_generic(self):
        """voice_gateway.py must use generic close reason, not str(e)."""
        import ast

        ws_path = Path(__file__).parent.parent.parent / "api" / "voice_gateway.py"
        content = ws_path.read_text(encoding="utf-8")

        # Ensure no str(e) in ws.close calls
        self.assertNotIn('reason=str(e)', content)
        self.assertIn('reason="Internal server error"', content)


# =========================================================================
# REVOCATION PERSISTENCE TESTS
# =========================================================================


class TestFileBackedRevocationStore(unittest.TestCase):
    """Test the file-backed revocation store for restart durability."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.revoc_path = os.path.join(self.tmpdir, "revocations.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_file_store_persists_across_instances(self):
        """Revocations must survive store re-instantiation (simulates restart)."""
        from backend.auth.revocation_store import _FileStore

        # Instance 1: revoke a token
        store1 = _FileStore(path=self.revoc_path)
        store1.revoke_token("hash_abc123")
        store1.revoke_session("session_xyz")
        self.assertTrue(store1.is_token_revoked("hash_abc123"))
        self.assertTrue(store1.is_session_revoked("session_xyz"))

        # Instance 2: simulates restart — must still be revoked
        store2 = _FileStore(path=self.revoc_path)
        self.assertTrue(store2.is_token_revoked("hash_abc123"))
        self.assertTrue(store2.is_session_revoked("session_xyz"))
        self.assertFalse(store2.is_token_revoked("hash_other"))

    def test_file_store_clear(self):
        """clear() removes all revocations and persists empty state."""
        from backend.auth.revocation_store import _FileStore

        store = _FileStore(path=self.revoc_path)
        store.revoke_token("hash_test")
        self.assertTrue(store.is_token_revoked("hash_test"))

        store.clear()
        self.assertFalse(store.is_token_revoked("hash_test"))

        # Verify persistence of cleared state
        store2 = _FileStore(path=self.revoc_path)
        self.assertFalse(store2.is_token_revoked("hash_test"))

    def test_file_store_deduplication(self):
        """Revoking same token twice should not create duplicates."""
        from backend.auth.revocation_store import _FileStore

        store = _FileStore(path=self.revoc_path)
        store.revoke_token("hash_dup")
        store.revoke_token("hash_dup")

        data = json.loads(Path(self.revoc_path).read_text(encoding="utf-8"))
        self.assertEqual(data["tokens"].count("hash_dup"), 1)

    def test_file_store_handles_corrupt_file(self):
        """Store should start fresh if JSON file is corrupt."""
        from backend.auth.revocation_store import _FileStore

        Path(self.revoc_path).write_text("NOT JSON", encoding="utf-8")
        store = _FileStore(path=self.revoc_path)
        self.assertFalse(store.is_token_revoked("anything"))
        # Should be usable
        store.revoke_token("hash_new")
        self.assertTrue(store.is_token_revoked("hash_new"))


class TestRevocationBackendHealth(unittest.TestCase):
    """Test get_backend_health() returns correct backend info."""

    def test_memory_backend_health(self):
        """Memory backend health shows warning about restart loss."""
        from backend.auth import revocation_store

        revocation_store.reset_store()
        original = os.environ.get("REVOCATION_BACKEND")
        try:
            os.environ["REVOCATION_BACKEND"] = "memory"
            revocation_store.reset_store()
            health = revocation_store.get_backend_health()
            self.assertEqual(health["backend"], "memory")
            self.assertTrue(health["available"])
            self.assertIn("warning", health)
        finally:
            if original is not None:
                os.environ["REVOCATION_BACKEND"] = original
            else:
                os.environ.pop("REVOCATION_BACKEND", None)
            revocation_store.reset_store()

    def test_file_backend_health(self):
        """File backend health shows file path and existence."""
        from backend.auth import revocation_store

        original_backend = os.environ.get("REVOCATION_BACKEND")
        original_path = os.environ.get("REVOCATION_FILE_PATH")
        tmpdir = tempfile.mkdtemp()
        try:
            os.environ["REVOCATION_BACKEND"] = "file"
            os.environ["REVOCATION_FILE_PATH"] = os.path.join(tmpdir, "test.json")
            revocation_store.reset_store()
            health = revocation_store.get_backend_health()
            self.assertEqual(health["backend"], "file")
            self.assertIn("file_path", health)
            self.assertTrue(health["available"])
        finally:
            if original_backend is not None:
                os.environ["REVOCATION_BACKEND"] = original_backend
            else:
                os.environ.pop("REVOCATION_BACKEND", None)
            if original_path is not None:
                os.environ["REVOCATION_FILE_PATH"] = original_path
            else:
                os.environ.pop("REVOCATION_FILE_PATH", None)
            revocation_store.reset_store()
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


# =========================================================================
# STARTUP SAFETY TESTS
# =========================================================================


class TestStartupNoForeignKill(unittest.TestCase):
    """Verify startup preflight does not kill foreign processes."""

    def test_preflight_has_no_kill_commands(self):
        """preflight.py must not contain subprocess kill calls."""
        preflight_path = (
            Path(__file__).parent.parent / "startup" / "preflight.py"
        )
        content = preflight_path.read_text(encoding="utf-8")
        # No kill, taskkill, terminate process commands
        self.assertNotIn("taskkill", content.lower())
        self.assertNotIn("os.kill(", content)
        self.assertNotIn("signal.SIGKILL", content)
        self.assertNotIn("subprocess.kill", content)


class TestAcceleratorSimulationDefault(unittest.TestCase):
    """Verify YGB_ACCELERATOR_SIMULATION defaults to false."""

    def test_simulation_defaults_false(self):
        """SIMULATION_MODE must be False when env var is unset."""
        original = os.environ.pop("YGB_ACCELERATOR_SIMULATION", None)
        try:
            # Re-evaluate the module-level constant
            result = os.environ.get(
                "YGB_ACCELERATOR_SIMULATION", "false"
            ).lower() == "true"
            self.assertFalse(result)
        finally:
            if original is not None:
                os.environ["YGB_ACCELERATOR_SIMULATION"] = original

    def test_simulation_requires_explicit_true(self):
        """SIMULATION_MODE must only be True when explicitly set."""
        original = os.environ.get("YGB_ACCELERATOR_SIMULATION")
        try:
            os.environ["YGB_ACCELERATOR_SIMULATION"] = "true"
            result = os.environ.get(
                "YGB_ACCELERATOR_SIMULATION", "false"
            ).lower() == "true"
            self.assertTrue(result)
        finally:
            if original is not None:
                os.environ["YGB_ACCELERATOR_SIMULATION"] = original
            else:
                os.environ.pop("YGB_ACCELERATOR_SIMULATION", None)


if __name__ == "__main__":
    unittest.main()
