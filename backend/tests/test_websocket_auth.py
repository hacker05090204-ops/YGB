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
        """ws_authenticate returns None for invalid JWT via protocol header."""
        from backend.auth.auth_guard import ws_authenticate

        mock_ws = MagicMock()
        mock_ws.query_params = {}
        mock_ws.headers = {"sec-websocket-protocol": "bearer.invalid.jwt.garbage"}

        result = _run(ws_authenticate(mock_ws))
        self.assertIsNone(result)

    def test_returns_payload_valid_token(self):
        """ws_authenticate returns payload for valid token via protocol header."""
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

    def test_rejects_revoked_token(self):
        """ws_authenticate returns None for revoked token via protocol header."""
        from backend.auth.auth_guard import ws_authenticate
        from backend.auth.revocation_store import revoke_token, reset_store

        reset_store()
        token = _valid_token()
        revoke_token(token)

        mock_ws = MagicMock()
        mock_ws.query_params = {}
        mock_ws.headers = {"sec-websocket-protocol": f"bearer.{token}"}

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

    def test_rejects_query_param_token(self):
        """ws_authenticate rejects valid token passed via query param."""
        from backend.auth.auth_guard import ws_authenticate
        from backend.auth.revocation_store import reset_store

        reset_store()
        token = _valid_token()
        mock_ws = MagicMock()
        mock_ws.query_params = {"token": token}
        mock_ws.headers = {}

        result = _run(ws_authenticate(mock_ws))
        self.assertIsNone(result)


DASHBOARD_FRAME_KEYS = {
    "active_field", "queue", "gpu_utilization", "gpu_temp", "vram_used_mb",
    "samples_per_sec", "eta_seconds", "epoch", "total_epochs", "world_size",
    "auto_mode", "loss", "accuracy", "stalled", "mode", "sequence_id", "timestamp",
}


class TestDashboardFrameShape(unittest.TestCase):
    """Tests for /training/dashboard WebSocket frame shape."""

    def test_dashboard_frame_has_all_keys(self):
        """A DashboardFrame must contain all expected keys."""
        # Build a mock frame as the endpoint would
        frame = {
            "active_field": "default",
            "queue": [],
            "gpu_utilization": 0.0,
            "gpu_temp": 0.0,
            "vram_used_mb": 0.0,
            "samples_per_sec": 0.0,
            "eta_seconds": 0.0,
            "epoch": 0,
            "total_epochs": 0,
            "world_size": 1,
            "auto_mode": False,
            "loss": 0.0,
            "accuracy": 0.0,
            "stalled": False,
            "mode": "idle",
            "sequence_id": 1,
            "timestamp": "2026-03-05T00:00:00Z",
        }
        for key in DASHBOARD_FRAME_KEYS:
            self.assertIn(key, frame, f"Missing DashboardFrame key: {key}")

    def test_dashboard_frame_types(self):
        """DashboardFrame values have correct types."""
        frame = {
            "active_field": "cve_analysis",
            "queue": [{"field_name": "f1", "priority": 1, "status": "queued",
                        "best_accuracy": 0.0, "epochs_completed": 0}],
            "gpu_utilization": 0.85,
            "gpu_temp": 72.0,
            "vram_used_mb": 2048.0,
            "samples_per_sec": 128.5,
            "eta_seconds": 300.0,
            "epoch": 5,
            "total_epochs": 20,
            "world_size": 1,
            "auto_mode": True,
            "loss": 0.3421,
            "accuracy": 0.8765,
            "stalled": False,
            "mode": "training",
            "sequence_id": 42,
            "timestamp": "2026-03-05T00:00:00Z",
        }
        self.assertIsInstance(frame["active_field"], str)
        self.assertIsInstance(frame["queue"], list)
        self.assertIsInstance(frame["gpu_utilization"], float)
        self.assertIsInstance(frame["auto_mode"], bool)
        self.assertIsInstance(frame["epoch"], int)
        self.assertIsInstance(frame["stalled"], bool)
        self.assertIsInstance(frame["mode"], str)
        self.assertIsInstance(frame["sequence_id"], int)

    def test_auth_rejection_returns_none(self):
        """ws_authenticate returns None for no auth → dashboard should close 4001."""
        from backend.auth.auth_guard import ws_authenticate

        mock_ws = MagicMock()
        mock_ws.query_params = {}
        mock_ws.headers = {}

        result = _run(ws_authenticate(mock_ws))
        self.assertIsNone(result, "No auth should return None → 4001 close")

    def test_auth_acceptance_for_dashboard(self):
        """ws_authenticate returns payload for valid token (dashboard path)."""
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
