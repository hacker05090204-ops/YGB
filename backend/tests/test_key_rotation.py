"""
test_key_rotation.py — Key Rotation & Revocation Tests
=======================================================
Tests:
  - Sign with key A, verify with key A
  - Sign with key A, revoke key A, reject token
  - Sign with key B after key A revoked
  - key_id stored in token and ledger entry
  - Unknown key_id rejected
  - Reload keys from disk preserves revocation
  - Multiple keys active simultaneously
  - Revoked key cannot be used for signing
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..')))

from governance.approval_ledger import ApprovalLedger, ApprovalToken, KeyManager


class TestKeyManager(unittest.TestCase):
    """Test KeyManager multi-key and revocation functionality."""

    def test_default_key_exists(self):
        """Default key should always be available."""
        km = KeyManager()
        key_id, secret = km.get_signing_key()
        self.assertEqual(key_id, KeyManager.DEFAULT_KEY_ID)
        self.assertIsInstance(secret, bytes)
        self.assertTrue(len(secret) > 0)

    def test_add_key(self):
        """Should be able to add new keys."""
        km = KeyManager()
        km.add_key("test-key-v2", b"secret-v2")
        self.assertIn("test-key-v2", km.available_key_ids)
        self.assertEqual(km.get_verification_key("test-key-v2"), b"secret-v2")

    def test_revoke_key(self):
        """Revoked keys should be in the revocation list."""
        km = KeyManager()
        km.add_key("revokeable", b"secret")
        km.revoke_key("revokeable")
        self.assertTrue(km.is_revoked("revokeable"))
        self.assertIn("revokeable", km.revoked_keys)

    def test_unknown_key_returns_none(self):
        """Unknown key_id should return None for verification."""
        km = KeyManager()
        self.assertIsNone(km.get_verification_key("nonexistent-key"))

    def test_revoked_active_key_raises(self):
        """Signing with a revoked active key should raise."""
        km = KeyManager()
        km.revoke_key(km.active_key_id)
        with self.assertRaises(ValueError) as ctx:
            km.get_signing_key()
        self.assertIn("ACTIVE_KEY_REVOKED", str(ctx.exception))

    def test_multiple_keys_active(self):
        """Multiple keys can coexist for verification."""
        km = KeyManager()
        km.add_key("key-a", b"secret-a")
        km.add_key("key-b", b"secret-b")
        self.assertIn("key-a", km.available_key_ids)
        self.assertIn("key-b", km.available_key_ids)
        self.assertEqual(km.get_verification_key("key-a"), b"secret-a")
        self.assertEqual(km.get_verification_key("key-b"), b"secret-b")

    def test_load_keys_from_directory(self):
        """Keys should load from YGB_KEY_DIR filesystem."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write key files
            with open(os.path.join(tmpdir, "prod-key-v1.key"), "wb") as f:
                f.write(b"prod-secret-v1")
            with open(os.path.join(tmpdir, "prod-key-v2.key"), "wb") as f:
                f.write(b"prod-secret-v2")

            # Write revocation list
            with open(os.path.join(tmpdir, "revoked_keys.json"), "w") as f:
                json.dump(["prod-key-v1"], f)

            # Set env and reload
            old_env = os.environ.get("YGB_KEY_DIR", "")
            os.environ["YGB_KEY_DIR"] = tmpdir
            try:
                km = KeyManager()
                self.assertIn("prod-key-v1", km.available_key_ids)
                self.assertIn("prod-key-v2", km.available_key_ids)
                self.assertTrue(km.is_revoked("prod-key-v1"))
                self.assertFalse(km.is_revoked("prod-key-v2"))
                self.assertEqual(
                    km.get_verification_key("prod-key-v1"), b"prod-secret-v1")
            finally:
                if old_env:
                    os.environ["YGB_KEY_DIR"] = old_env
                else:
                    os.environ.pop("YGB_KEY_DIR", None)


class TestKeyRotationInLedger(unittest.TestCase):
    """Test key rotation in the full ledger workflow."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix=".jsonl", delete=False)
        self.tmp.close()
        self.km = KeyManager()
        self.km.add_key("key-alpha", b"secret-alpha")
        self.km.add_key("key-beta", b"secret-beta")
        self.ledger = ApprovalLedger(self.tmp.name, key_manager=self.km)

    def tearDown(self):
        os.unlink(self.tmp.name)

    def test_sign_and_verify_with_key_a(self):
        """Token signed with key A should verify with key A."""
        self.km._active_key_id = "key-alpha"
        token = self.ledger.sign_approval(0, "auditor", "test sign with A")
        self.assertEqual(token.key_id, "key-alpha")
        self.assertTrue(self.ledger.verify_token(token))

    def test_sign_and_verify_with_key_b(self):
        """Token signed with key B should verify with key B."""
        self.km._active_key_id = "key-beta"
        token = self.ledger.sign_approval(0, "auditor", "test sign with B")
        self.assertEqual(token.key_id, "key-beta")
        self.assertTrue(self.ledger.verify_token(token))

    def test_key_id_stored_in_entry(self):
        """key_id should be persisted in ledger entry."""
        self.km._active_key_id = "key-alpha"
        token = self.ledger.sign_approval(0, "auditor", "test key storage")
        entry = self.ledger.append(token)
        self.assertEqual(entry["token"]["key_id"], "key-alpha")

    def test_revoked_key_rejected(self):
        """Tokens signed with revoked key should be rejected."""
        self.km._active_key_id = "key-alpha"
        token = self.ledger.sign_approval(0, "auditor", "before revoke")
        # Revoke key-alpha
        self.km.revoke_key("key-alpha")
        # Validate should fail
        result = self.ledger.validate_anti_replay(token)
        self.assertFalse(result["valid"])
        self.assertIn("KEY_REVOKED", result["reason"])

    def test_sign_with_key_b_after_a_revoked(self):
        """After revoking key A, signing with key B should work."""
        self.km._active_key_id = "key-alpha"
        self.km.revoke_key("key-alpha")
        # Switch to key-beta
        self.km._active_key_id = "key-beta"
        token = self.ledger.sign_approval(0, "auditor", "after rotate to B")
        self.assertEqual(token.key_id, "key-beta")
        self.assertTrue(self.ledger.verify_token(token))
        # Should append successfully
        entry = self.ledger.append(token)
        self.assertEqual(entry["token"]["key_id"], "key-beta")

    def test_unknown_key_id_rejected(self):
        """Token with unknown key_id should fail verification."""
        token = ApprovalToken(
            field_id=0,
            approver_id="hacker",
            reason="fake",
            timestamp=__import__('time').time(),
            signature="fakesig",
            nonce="fakenonce",
            key_id="nonexistent-key",
        )
        self.assertFalse(self.ledger.verify_token(token))
        result = self.ledger.validate_anti_replay(token)
        self.assertFalse(result["valid"])

    def test_both_keys_verify_own_tokens(self):
        """Tokens signed with different keys should each verify correctly."""
        self.km._active_key_id = "key-alpha"
        token_a = self.ledger.sign_approval(0, "auditor", "alpha token")
        self.km._active_key_id = "key-beta"
        token_b = self.ledger.sign_approval(1, "auditor", "beta token")

        self.assertTrue(self.ledger.verify_token(token_a))
        self.assertTrue(self.ledger.verify_token(token_b))

    def test_cross_key_signature_fails(self):
        """Token signed with key A should not verify if key_id claims key C."""
        self.km._active_key_id = "key-alpha"
        token = self.ledger.sign_approval(0, "auditor", "cross test")
        # Tamper — change key_id
        token.key_id = "key-beta"
        self.assertFalse(self.ledger.verify_token(token))

    def test_chain_integrity_after_rotation(self):
        """Hash chain should remain valid across key rotations."""
        self.km._active_key_id = "key-alpha"
        t1 = self.ledger.sign_approval(0, "auditor", "entry one")
        self.ledger.append(t1)

        self.km._active_key_id = "key-beta"
        t2 = self.ledger.sign_approval(1, "auditor", "entry two")
        self.ledger.append(t2)

        self.assertTrue(self.ledger.verify_chain())

    def test_reload_preserves_entries(self):
        """Reloading from disk should preserve all entries and anti-replay."""
        self.km._active_key_id = "key-alpha"
        t1 = self.ledger.sign_approval(0, "auditor", "persist test")
        self.ledger.append(t1)

        # Reload
        ledger2 = ApprovalLedger(self.tmp.name, key_manager=self.km)
        ledger2.load()

        self.assertEqual(ledger2.entry_count, 1)
        self.assertTrue(ledger2.verify_chain())
        # Nonce should be tracked
        self.assertIn(t1.nonce, ledger2._used_nonces)


if __name__ == "__main__":
    unittest.main()
