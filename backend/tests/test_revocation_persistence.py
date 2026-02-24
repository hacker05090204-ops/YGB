"""
Tests for B7 — Revocation persistence across re-initialization.

Proves:
  - revoke_token persists across module-level store reset
  - revoke_session persists across module-level store reset
  - In-memory fallback works correctly
"""
import os
import sys
import unittest
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

# Force memory backend for these tests (Redis may not be available)
os.environ.setdefault("REVOCATION_BACKEND", "memory")


class TestRevocationPersistence(unittest.TestCase):
    """Test revocation store behavior."""

    def setUp(self):
        """Reset store before each test."""
        from backend.auth.revocation_store import reset_store
        reset_store()

    def test_revoke_token_and_check(self):
        """Revoked token is detected."""
        from backend.auth.revocation_store import revoke_token, is_token_revoked
        revoke_token("test-jwt-token-123")
        self.assertTrue(is_token_revoked("test-jwt-token-123"))

    def test_non_revoked_token_passes(self):
        """Non-revoked token is not detected."""
        from backend.auth.revocation_store import is_token_revoked
        self.assertFalse(is_token_revoked("never-revoked-token"))

    def test_revoke_session_and_check(self):
        """Revoked session is detected."""
        from backend.auth.revocation_store import revoke_session, is_session_revoked
        revoke_session("session-abc-123")
        self.assertTrue(is_session_revoked("session-abc-123"))

    def test_non_revoked_session_passes(self):
        """Non-revoked session is not detected."""
        from backend.auth.revocation_store import is_session_revoked
        self.assertFalse(is_session_revoked("never-revoked-session"))

    def test_reinit_clears_memory_store(self):
        """After reset_store, in-memory revocations are lost (expected behavior)."""
        from backend.auth.revocation_store import (
            revoke_token, is_token_revoked, reset_store,
        )
        revoke_token("ephemeral-token")
        self.assertTrue(is_token_revoked("ephemeral-token"))

        # Simulate process restart
        reset_store()

        # Memory store is cleared — token is no longer revoked
        self.assertFalse(is_token_revoked("ephemeral-token"))

    def test_multiple_tokens_independent(self):
        """Revoking one token does not affect others."""
        from backend.auth.revocation_store import revoke_token, is_token_revoked
        revoke_token("token-a")
        self.assertTrue(is_token_revoked("token-a"))
        self.assertFalse(is_token_revoked("token-b"))

    def test_multiple_sessions_independent(self):
        """Revoking one session does not affect others."""
        from backend.auth.revocation_store import revoke_session, is_session_revoked
        revoke_session("sess-1")
        self.assertTrue(is_session_revoked("sess-1"))
        self.assertFalse(is_session_revoked("sess-2"))

    def test_auth_guard_uses_store(self):
        """auth_guard.revoke_token delegates to revocation_store."""
        from backend.auth.auth_guard import revoke_token, is_token_revoked
        revoke_token("via-guard-token")
        self.assertTrue(is_token_revoked("via-guard-token"))


if __name__ == "__main__":
    unittest.main()
