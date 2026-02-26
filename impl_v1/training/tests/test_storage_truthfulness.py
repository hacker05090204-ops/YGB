"""
Test Storage Truthfulness
==========================

Tests that get_storage_health() in storage_bridge.py returns truthful
status — INACTIVE when engine not initialized, ACTIVE when ready,
DEGRADED when partially available. No fake active states.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

# We need to mock the native HDD engine imports before importing storage_bridge,
# because the module-level imports in storage_bridge.py try to load native libs.
_mock_hdd = MagicMock()
_mock_hdd.LifecycleState = MagicMock()
_mock_hdd.get_engine = MagicMock(return_value=MagicMock())

# Patch native modules before they're imported
sys.modules.setdefault('native', MagicMock())
sys.modules.setdefault('native.hdd_engine', MagicMock())
sys.modules.setdefault('native.hdd_engine.hdd_engine', _mock_hdd)
sys.modules.setdefault('native.hdd_engine.lifecycle_manager', MagicMock())
sys.modules.setdefault('native.hdd_engine.secure_wiper', MagicMock())
sys.modules.setdefault('native.hdd_engine.disk_monitor', MagicMock())
sys.modules.setdefault('native.hdd_engine.video_streamer', MagicMock())


class TestStorageTruthfulness(unittest.TestCase):
    """Ensure storage health reports REAL status only."""

    def _get_bridge(self):
        """Import storage_bridge with native modules mocked."""
        import importlib
        if 'backend.storage.storage_bridge' in sys.modules:
            return sys.modules['backend.storage.storage_bridge']
        import backend.storage.storage_bridge as sb
        return sb

    def test_storage_health_inactive_when_no_engine(self):
        """When _engine is None, get_storage_health() must return INACTIVE."""
        sb = self._get_bridge()

        orig_e = sb._engine
        orig_l = sb._lifecycle
        orig_m = sb._disk_monitor
        try:
            sb._engine = None
            sb._lifecycle = None
            sb._disk_monitor = None

            health = sb.get_storage_health()

            self.assertFalse(health["storage_active"])
            self.assertFalse(health["db_active"])
            self.assertFalse(health["lifecycle_ok"])
            self.assertIn(health["status"], ("INACTIVE", "DEGRADED"))
            self.assertIsNotNone(health["reason"])
            self.assertIn("not initialized", health["reason"])
        finally:
            sb._engine = orig_e
            sb._lifecycle = orig_l
            sb._disk_monitor = orig_m

    def test_storage_health_active_when_engine_ready(self):
        """When engine has valid root, get_storage_health() must return ACTIVE."""
        sb = self._get_bridge()

        orig_e = sb._engine
        orig_l = sb._lifecycle
        orig_m = sb._disk_monitor
        try:
            mock_engine = MagicMock()
            mock_root = MagicMock()
            mock_root.exists.return_value = True
            mock_engine.root = mock_root

            sb._engine = mock_engine
            sb._lifecycle = MagicMock()
            sb._disk_monitor = MagicMock()

            health = sb.get_storage_health()

            self.assertTrue(health["storage_active"])
            self.assertTrue(health["db_active"])
            self.assertTrue(health["lifecycle_ok"])
            self.assertEqual(health["status"], "ACTIVE")
            self.assertIsNone(health["reason"])
        finally:
            sb._engine = orig_e
            sb._lifecycle = orig_l
            sb._disk_monitor = orig_m

    def test_canonical_truth_fields_present(self):
        """Response must contain all canonical truth fields."""
        sb = self._get_bridge()

        orig_e = sb._engine
        try:
            sb._engine = None
            health = sb.get_storage_health()
        finally:
            sb._engine = orig_e

        required_fields = [
            "status", "storage_active", "db_active",
            "lifecycle_ok", "reason", "checked_at",
        ]
        for field in required_fields:
            self.assertIn(field, health, f"Missing field: {field}")

    def test_degraded_when_engine_ok_but_lifecycle_missing(self):
        """DEGRADED status when engine works but lifecycle is missing."""
        sb = self._get_bridge()

        orig_e = sb._engine
        orig_l = sb._lifecycle
        orig_m = sb._disk_monitor
        try:
            mock_engine = MagicMock()
            mock_root = MagicMock()
            mock_root.exists.return_value = True
            mock_engine.root = mock_root

            sb._engine = mock_engine
            sb._lifecycle = None  # Missing!
            sb._disk_monitor = MagicMock()

            health = sb.get_storage_health()

            self.assertTrue(health["storage_active"])
            self.assertFalse(health["lifecycle_ok"])
            self.assertEqual(health["status"], "DEGRADED")
        finally:
            sb._engine = orig_e
            sb._lifecycle = orig_l
            sb._disk_monitor = orig_m


if __name__ == "__main__":
    unittest.main()
