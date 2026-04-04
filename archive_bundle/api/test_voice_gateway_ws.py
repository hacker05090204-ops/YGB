import os
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("JWT_SECRET", "j" * 64)
os.environ.setdefault("YGB_HMAC_SECRET", "h" * 64)
os.environ.setdefault("YGB_VIDEO_JWT_SECRET", "v" * 64)
os.environ.setdefault("REVOCATION_BACKEND", "memory")
os.environ["YGB_TEMP_AUTH_BYPASS"] = "false"
os.environ["ENABLE_G38_AUTO_TRAINING"] = "false"

from api.server import app
from backend.auth.auth import generate_jwt
from backend.auth.revocation_store import reset_store


@pytest.fixture(scope="module")
def client():
    reset_store()
    with TestClient(app) as test_client:
        yield test_client


def _auth_headers() -> dict[str, str]:
    token = generate_jwt(
        user_id="voice-user",
        email="voice@example.com",
        session_id="voice-session",
        role="hunter",
    )
    return {
        "origin": "http://localhost:3000",
        "cookie": f"ygb_auth={token}",
    }


def test_voice_ws_rejects_missing_auth(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/ws/voice",
            headers={"origin": "http://localhost:3000"},
        ):
            pass
    assert excinfo.value.code == 4401


def test_voice_ws_rejects_disallowed_origin(client: TestClient):
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/ws/voice",
            headers={
                "origin": "https://evil.example",
                "cookie": _auth_headers()["cookie"],
            },
        ):
            pass
    assert excinfo.value.code == 4403


def test_voice_ws_accepts_cookie_auth_on_alias_path(client: TestClient):
    with client.websocket_connect("/ws/voice", headers=_auth_headers()) as websocket:
        websocket.send_text('{"type":"stop"}')
        payload = websocket.receive_json()
    assert payload["type"] == "stopped"
