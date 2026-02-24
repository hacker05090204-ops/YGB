"""
Tests for target session lifecycle:
POST /target/start → GET /target/status → POST /target/stop

Verifies the full lifecycle of creating, monitoring, and stopping
target scanning sessions.

All tests use authenticated requests with valid JWT tokens.
"""

import sys
import os

# Add project root and api dir to path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "api"))

# Ensure JWT_SECRET is available for tests
if not os.environ.get("JWT_SECRET"):
    os.environ["JWT_SECRET"] = "test_secret_for_target_lifecycle_tests_that_is_long_enough"

from fastapi.testclient import TestClient
from api.server import app
from backend.auth.auth import generate_jwt

client = TestClient(app)


def _auth_headers():
    """Generate valid auth headers for testing."""
    token = generate_jwt("test-user-target", "test@target.test")
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_target_start_rejected():
    """Unauthenticated target/start requests must return 401/403."""
    res = client.post("/target/start", json={
        "target_url": "example.com",
        "scope_definition": {},
        "mode": "READ_ONLY"
    })
    assert res.status_code in (401, 403)


def test_start_session():
    """Starting a session should return a session_id and started=True."""
    res = client.post("/target/start", json={
        "target_url": "api.example.com",
        "scope_definition": {"include": ["*.example.com"]},
        "mode": "READ_ONLY"
    }, headers=_auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert data["started"] is True
    assert "session_id" in data
    assert data["target_url"] == "api.example.com"
    assert data["mode"] == "READ_ONLY"


def test_start_empty_target_fails():
    """Starting a session with empty target should fail."""
    res = client.post("/target/start", json={
        "target_url": "",
        "scope_definition": {}
    }, headers=_auth_headers())
    data = res.json()
    assert data.get("started") is False
    assert "error" in data


def test_full_lifecycle():
    """Full lifecycle: start → status → stop."""
    headers = _auth_headers()

    # Start
    start_res = client.post("/target/start", json={
        "target_url": "test.example.org",
        "scope_definition": {},
        "mode": "READ_ONLY"
    }, headers=headers)
    start_data = start_res.json()
    session_id = start_data["session_id"]

    # Status — should show active
    status_res = client.get("/target/status", headers=headers)
    status_data = status_res.json()
    active_ids = [s["session_id"] for s in status_data["active_sessions"]]
    assert session_id in active_ids
    assert status_data["total_active"] >= 1

    # Stop
    stop_res = client.post("/target/stop", json={
        "session_id": session_id
    }, headers=headers)
    stop_data = stop_res.json()
    assert stop_data["stopped"] is True
    assert stop_data["session_id"] == session_id

    # Status — should be stopped now
    status_res2 = client.get("/target/status", headers=headers)
    status_data2 = status_res2.json()
    active_ids2 = [s["session_id"] for s in status_data2["active_sessions"]]
    assert session_id not in active_ids2
    stopped_ids = [s["session_id"] for s in status_data2["stopped_sessions"]]
    assert session_id in stopped_ids


def test_stop_nonexistent_session():
    """Stopping a non-existent session should return an error."""
    res = client.post("/target/stop", json={
        "session_id": "FAKE-SESSION-123"
    }, headers=_auth_headers())
    data = res.json()
    assert data.get("stopped") is False
    assert "error" in data


def test_status_returns_structure():
    """Status endpoint should return expected structure."""
    res = client.get("/target/status", headers=_auth_headers())
    assert res.status_code == 200
    data = res.json()
    assert "active_sessions" in data
    assert "stopped_sessions" in data
    assert "total_active" in data
    assert "total_stopped" in data
