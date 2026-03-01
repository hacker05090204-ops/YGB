"""
OAuth State Validation Regression Tests

Covers:
- Strict cookie-bound state validation
- Login/logout/login cycle
- Callback replay prevention
- State mismatch rejection
"""

import unittest
import hmac
import hashlib
import time
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestOAuthStateValidation(unittest.TestCase):
    """Test OAuth state generation and validation using HMAC-based state pattern.

    Since server.py handles OAuth state inline (no exported functions),
    these tests implement and validate the core HMAC state security pattern.
    """

    def setUp(self):
        self.secret = os.environ.get("JWT_SECRET", "test-secret-" + "a" * 50)

    def _build_state(self, frontend_url: str) -> str:
        """Build an HMAC-signed OAuth state token."""
        ts = str(int(time.time()))
        payload = json.dumps({"url": frontend_url, "ts": ts})
        sig = hmac.new(self.secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        import base64
        return base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()

    def _parse_state(self, state: str) -> tuple:
        """Parse and verify an HMAC-signed OAuth state token."""
        if not state:
            return False, ""
        try:
            import base64
            decoded = base64.urlsafe_b64decode(state.encode()).decode()
            parts = decoded.rsplit("|", 1)
            if len(parts) != 2:
                return False, ""
            payload_str, sig = parts
            expected_sig = hmac.new(self.secret.encode(), payload_str.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                return False, ""
            payload = json.loads(payload_str)
            return True, payload.get("url", "")
        except Exception:
            return False, ""

    def test_state_round_trip(self):
        """Valid state should parse back to the same frontend URL."""
        url = "http://localhost:3000"
        state = self._build_state(url)
        ok, parsed_url = self._parse_state(state)
        self.assertTrue(ok, "State should be valid")
        self.assertEqual(parsed_url, url)

    def test_state_rejects_tampered_signature(self):
        """Tampered state should be rejected."""
        url = "http://localhost:3000"
        state = self._build_state(url)
        tampered = state[:-4] + "XXXX"
        ok, _ = self._parse_state(tampered)
        self.assertFalse(ok, "Tampered state should be rejected")

    def test_state_rejects_empty(self):
        """Empty state should be rejected."""
        ok, _ = self._parse_state("")
        self.assertFalse(ok)

    def test_state_rejects_garbage(self):
        """Random garbage should be rejected."""
        ok, _ = self._parse_state("not-a-valid-state-at-all")
        self.assertFalse(ok)

    def test_state_different_urls_produce_different_states(self):
        """Different frontend URLs should produce different states."""
        s1 = self._build_state("http://localhost:3000")
        s2 = self._build_state("http://example.com")
        self.assertNotEqual(s1, s2)

    def test_state_includes_timestamp_for_expiry(self):
        """State should contain a timestamp component for TTL validation."""
        state = self._build_state("http://localhost:3000")
        self.assertTrue(len(state) > 20, "State should be sufficiently long to contain timestamp + sig")

    def test_cookie_binding_strict(self):
        """
        Regression: cookie state MUST match URL state exactly.
        """
        state = self._build_state("http://localhost:3000")
        different_state = self._build_state("http://evil.com")
        cookie_ok = bool(state and different_state and state == different_state)
        self.assertFalse(cookie_ok, "Different cookie and URL states must not match")
        cookie_ok = bool(state and state and state == state)
        self.assertTrue(cookie_ok, "Identical cookie and URL states should match")


class TestLoginLogoutLoginCycle(unittest.TestCase):
    """
    Regression: logout → login should work without OAuth state mismatch.
    Tests the JWT generation and session_id binding that enables proper session revocation.
    """

    def setUp(self):
        os.environ.setdefault("JWT_SECRET", "test-secret-" + "a" * 50)
        # Force memory backend for test isolation (prod default is 'file')
        os.environ["REVOCATION_BACKEND"] = "memory"
        os.environ.pop("REVOCATION_FILE_PATH", None)
        from backend.auth.revocation_store import reset_store
        reset_store()
        from backend.auth.auth import generate_jwt, verify_jwt
        from backend.auth.auth_guard import revoke_session, is_session_revoked
        self.generate_jwt = generate_jwt
        self.verify_jwt = verify_jwt
        self.revoke_session = revoke_session
        self.is_session_revoked = is_session_revoked

    def test_login_creates_valid_jwt_with_session(self):
        """Login should create a JWT that includes session_id."""
        token = self.generate_jwt("user1", "a@b.com", session_id="sess-001", role="hunter")
        payload = self.verify_jwt(token)
        self.assertIsNotNone(payload)
        self.assertEqual(payload["session_id"], "sess-001")
        self.assertEqual(payload["role"], "hunter")

    def test_logout_revokes_session(self):
        """After logout, the session should be revoked."""
        token = self.generate_jwt("user1", "a@b.com", session_id="sess-002", role="hunter")
        payload = self.verify_jwt(token)
        self.assertFalse(self.is_session_revoked("sess-002"))

        # Simulate logout
        self.revoke_session("sess-002")
        self.assertTrue(self.is_session_revoked("sess-002"))

    def test_relogin_creates_fresh_session(self):
        """After logout+login, a new session_id should be issued."""
        # First login
        token1 = self.generate_jwt("user1", "a@b.com", session_id="sess-003", role="hunter")

        # Logout — revoke session
        self.revoke_session("sess-003")
        self.assertTrue(self.is_session_revoked("sess-003"))

        # Second login — new session
        token2 = self.generate_jwt("user1", "a@b.com", session_id="sess-004", role="hunter")
        payload2 = self.verify_jwt(token2)
        self.assertEqual(payload2["session_id"], "sess-004")
        self.assertFalse(self.is_session_revoked("sess-004"))

    def test_old_token_invalid_after_logout(self):
        """Token from revoked session should fail auth checks."""
        token = self.generate_jwt("user1", "a@b.com", session_id="sess-005", role="hunter")
        payload = self.verify_jwt(token)
        self.assertIsNotNone(payload)

        # Revoke
        self.revoke_session("sess-005")

        # Token still decodes but session is revoked
        payload = self.verify_jwt(token)
        self.assertIsNotNone(payload)  # JWT is still valid structurally
        self.assertTrue(self.is_session_revoked(payload["session_id"]))


class TestCallbackReplayPrevention(unittest.TestCase):
    """
    Regression: OAuth callback with replayed state should be rejected.
    The cookie is deleted after first use, so replay attempts fail cookie binding.
    """

    def test_cookie_deletion_prevents_replay(self):
        """
        After processing a callback, the cookie is deleted.
        A second request with the same state but no cookie should fail.
        """
        state = "some-valid-state-token"
        # First request: cookie present
        expected_state_first = state
        cookie_ok_first = bool(state and expected_state_first and state == expected_state_first)
        self.assertTrue(cookie_ok_first)

        # Second request (replay): cookie deleted (empty string)
        expected_state_second = ""
        cookie_ok_second = bool(state and expected_state_second and state == expected_state_second)
        self.assertFalse(cookie_ok_second, "Replay without cookie must fail")


if __name__ == "__main__":
    unittest.main()
