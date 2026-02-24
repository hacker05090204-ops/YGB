"""
Tests for B8 — WebSocket auth gating.

Unit tests for ws_authenticate (always run) and
integration tests for WS endpoints (skip if server dependencies unavailable).
"""
import os
import sys
import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("JWT_SECRET", "a_very_secure_test_secret_that_is_at_least_32_chars_long_for_testing")
os.environ.setdefault("REVOCATION_BACKEND", "memory")


def _valid_token():
    from backend.auth.auth import generate_jwt
    return generate_jwt("ws-test-user", "ws@test.com")


def _run(coro):
    """Run an async function synchronously."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class TestWsAuthenticateUnit(unittest.TestCase):
    """Unit tests for ws_authenticate — no server dependency."""

    def test_returns_none_no_token(self):
        """ws_authenticate returns None when no token provided."""
        from backend.auth.auth_guard import ws_authenticate

        mock_ws = MagicMock()
        mock_ws.query_params = {}
        mock_ws.headers = {}

        result = _run(ws_authenticate(mock_ws))
        self.assertIsNone(result)

    def test_returns_none_invalid_token(self):
        """ws_authenticate returns None for invalid JWT."""
        from backend.auth.auth_guard import ws_authenticate

        mock_ws = MagicMock()
        mock_ws.query_params = {"token": "invalid.jwt.garbage"}
        mock_ws.headers = {}

        result = _run(ws_authenticate(mock_ws))
        self.assertIsNone(result)

    def test_returns_payload_valid_token(self):
        """ws_authenticate returns payload for valid token."""
        from backend.auth.auth_guard import ws_authenticate

        token = _valid_token()
        mock_ws = MagicMock()
        mock_ws.query_params = {"token": token}
        mock_ws.headers = {}

        result = _run(ws_authenticate(mock_ws))
        self.assertIsNotNone(result)
        self.assertEqual(result["sub"], "ws-test-user")

    def test_rejects_revoked_token(self):
        """ws_authenticate returns None for revoked token."""
        from backend.auth.auth_guard import ws_authenticate
        from backend.auth.revocation_store import revoke_token, reset_store

        reset_store()
        token = _valid_token()
        revoke_token(token)

        mock_ws = MagicMock()
        mock_ws.query_params = {"token": token}
        mock_ws.headers = {}

        result = _run(ws_authenticate(mock_ws))
        self.assertIsNone(result)

    def test_extracts_from_protocol_header(self):
        """ws_authenticate extracts token from Sec-WebSocket-Protocol."""
        from backend.auth.auth_guard import ws_authenticate
        from backend.auth.revocation_store import reset_store

        reset_store()
        token = _valid_token()
        mock_ws = MagicMock()
        mock_ws.query_params = {}
        mock_ws.headers = {"sec-websocket-protocol": f"bearer.{token}"}

        result = _run(ws_authenticate(mock_ws))
        self.assertIsNotNone(result)
        self.assertEqual(result["sub"], "ws-test-user")


if __name__ == "__main__":
    unittest.main()
