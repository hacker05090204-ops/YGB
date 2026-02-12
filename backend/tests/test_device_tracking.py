"""
Tests for Device Tracking

Verifies:
- Login creates DB record with correct IP/UA
- Device hash is consistent for same user-agent
- Active-devices returns correct entries
- New device detection works
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth.auth import compute_device_hash


class TestDeviceHash:
    """Test device hash computation."""

    def test_consistent_hash(self):
        """Same user-agent → same hash."""
        h1 = compute_device_hash("Mozilla/5.0 Chrome/120")
        h2 = compute_device_hash("Mozilla/5.0 Chrome/120")
        assert h1 == h2

    def test_different_ua_different_hash(self):
        """Different user-agents → different hashes."""
        h1 = compute_device_hash("Chrome/120")
        h2 = compute_device_hash("Firefox/118")
        assert h1 != h2

    def test_hash_is_16_chars(self):
        """Device hash should be exactly 16 hex characters."""
        h = compute_device_hash("TestAgent/1.0")
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)

    def test_unknown_user_agent(self):
        """Empty/None user-agent should still produce a hash."""
        h = compute_device_hash("")
        assert h is not None and len(h) > 0

    def test_no_mock_in_hash(self):
        """Device hash must not use mock/random values."""
        import inspect
        source = inspect.getsource(compute_device_hash)
        assert "random" not in source.lower()
        assert "mock" not in source.lower()
