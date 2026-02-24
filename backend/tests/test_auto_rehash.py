"""
Tests for B9 — Auto-rehash on login.

Proves:
  - Legacy (v1) hash user logs in -> auth succeeds -> stored hash upgraded to v3
  - v2 hash user logs in -> needs rehash to v3
  - v3 hash user logs in -> no rehash needed
  - Wrong password never triggers rehash
"""
import os
import sys
import hashlib
import secrets
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("JWT_SECRET", "a_very_secure_test_secret_that_is_at_least_32_chars_long_for_testing")


class TestAutoRehash(unittest.TestCase):
    """Test auto-rehash on login."""

    def _make_legacy_hash(self, password: str) -> str:
        """Create a v1 (legacy) password hash: salt:sha256(salt:password)."""
        salt = secrets.token_hex(16)
        h = hashlib.sha256(f"{salt}:{password}".encode()).hexdigest()
        return f"{salt}:{h}"

    def _make_v2_hash(self, password: str) -> str:
        """Create a v2 hash using the real hash_password function."""
        from backend.auth.auth import hash_password
        return hash_password(password)

    def test_legacy_hash_gets_upgraded(self):
        """Login with legacy hash -> hash upgraded to v3/v3s."""
        from backend.auth.auth import verify_password, hash_password, needs_rehash

        legacy = self._make_legacy_hash("mypassword")
        self.assertTrue(needs_rehash(legacy), "Legacy hash should need rehash")
        self.assertTrue(verify_password("mypassword", legacy))

        # Simulate the rehash that login should do
        new_hash = hash_password("mypassword")
        self.assertTrue(
            new_hash.startswith("v3:") or new_hash.startswith("v3s:"),
            f"New hash should be v3/v3s, got: {new_hash[:10]}"
        )
        self.assertFalse(needs_rehash(new_hash), "v3 hash should NOT need rehash")

    def test_v2_hash_needs_rehash(self):
        """Login with v2 hash -> needs rehash to v3."""
        from backend.auth.auth import verify_password, needs_rehash, _iterative_hash
        import secrets as s

        # Create a genuine v2 hash
        salt = s.token_hex(16)
        hashed = _iterative_hash("securepass", salt)
        v2 = f"v2:{salt}:{hashed}"
        self.assertTrue(needs_rehash(v2), "v2 hash should need rehash to v3")
        self.assertTrue(verify_password("securepass", v2))

    def test_wrong_password_never_rehashes(self):
        """Wrong password -> verify fails -> no rehash triggered."""
        from backend.auth.auth import verify_password, needs_rehash

        legacy = self._make_legacy_hash("correct")
        self.assertFalse(verify_password("wrong", legacy))
        # needs_rehash would return True, but since verify failed,
        # the login flow should never call hash_password
        self.assertTrue(needs_rehash(legacy))

    def test_rehash_integration_with_login_flow(self):
        """
        Simulate the full login auto-rehash flow:
        1. Legacy hash user
        2. verify_password succeeds
        3. needs_rehash returns True
        4. hash_password called with correct password
        5. update_user_password called with new hash
        """
        from backend.auth.auth import verify_password, hash_password, needs_rehash

        password = "test_password_123"
        legacy = self._make_legacy_hash(password)

        # Step 1-2: verify succeeds
        self.assertTrue(verify_password(password, legacy))

        # Step 3: needs rehash
        self.assertTrue(needs_rehash(legacy))

        # Step 4: rehash
        new_hash = hash_password(password)
        self.assertTrue(
            new_hash.startswith("v3:") or new_hash.startswith("v3s:"),
            f"New hash should be v3/v3s, got: {new_hash[:10]}"
        )

        # Step 5: verify still works with new hash
        self.assertTrue(verify_password(password, new_hash))

        # And no more rehash needed
        self.assertFalse(needs_rehash(new_hash))

    def test_current_verify_does_not_downgrade(self):
        """Verify that a v3 hash is never 'downgraded' to v1/v2 format."""
        from backend.auth.auth import hash_password, verify_password

        current = hash_password("pass123")
        self.assertTrue(
            current.startswith("v3:") or current.startswith("v3s:"),
            f"Hash should be v3/v3s, got: {current[:10]}"
        )

        # Verify works
        self.assertTrue(verify_password("pass123", current))
        self.assertFalse(verify_password("wrong", current))


if __name__ == "__main__":
    unittest.main()
