import os
import sys

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

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

PUBLIC_HTTP_ROUTES = {
    "/api/health",
    "/api/g38/status",
    "/health",
    "/healthz",
    "/readyz",
    "/api/auth/providers",
    "/auth/register",
    "/auth/login",
    "/auth/github",
    "/auth/github/callback",
    "/auth/google",
    "/auth/google/callback",
    "/admin/login",
}

MANUALLY_GUARDED_ROUTES = {
    "/admin/auth/intel",
    "/admin/verify",
    "/admin/vault-unlock",
    "/admin/logout",
}

EXPECTED_401_WITHOUT_AUTH = [
    ("GET", "/metrics/snapshot"),
    ("GET", "/api/system/status"),
    ("GET", "/api/readiness"),
    ("GET", "/api/integration/status"),
    ("GET", "/api/cve/status"),
    ("GET", "/api/cve/scheduler/health"),
    ("GET", "/api/cve/pipeline/status"),
    ("GET", "/api/cve/summary"),
    ("GET", "/api/training/readiness"),
    ("GET", "/api/backup/status"),
    ("GET", "/api/voice/status"),
    ("GET", "/api/voice/metrics"),
    ("GET", "/api/voice/history"),
    ("GET", "/sync/manifest"),
    ("GET", "/sync/status"),
]


def _route_dependency_names(route: APIRoute) -> set[str]:
    return {
        getattr(dependency.call, "__name__", str(dependency.call))
        for dependency in route.dependant.dependencies
    }


NON_PUBLIC_ROUTES = [
    route
    for route in app.routes
    if isinstance(route, APIRoute) and route.path not in PUBLIC_HTTP_ROUTES
]


@pytest.fixture(scope="module")
def client():
    reset_store()
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def valid_auth_header() -> dict[str, str]:
    token = generate_jwt(
        user_id="test-user",
        email="test@example.com",
        session_id="session-1",
        role="admin",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize("route", NON_PUBLIC_ROUTES, ids=lambda route: route.path)
def test_non_public_routes_are_guarded(route: APIRoute):
    if route.path in MANUALLY_GUARDED_ROUTES:
        return
    dependency_names = _route_dependency_names(route)
    assert dependency_names & {"require_auth", "require_admin"}, (
        f"{route.path} is missing require_auth/require_admin"
    )


@pytest.mark.parametrize(("method", "path"), EXPECTED_401_WITHOUT_AUTH)
def test_selected_routes_reject_missing_auth(
    client: TestClient,
    method: str,
    path: str,
):
    response = client.request(method, path)
    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    "path",
    ["/metrics/snapshot", "/api/system/status", "/api/readiness", "/sync/status"],
)
def test_selected_routes_reject_invalid_bearer(client: TestClient, path: str):
    response = client.get(path, headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401, response.text


@pytest.mark.parametrize(
    "path",
    ["/metrics/snapshot", "/api/system/status", "/sync/status"],
)
def test_selected_routes_accept_valid_jwt(
    client: TestClient,
    valid_auth_header: dict[str, str],
    path: str,
):
    response = client.get(path, headers=valid_auth_header)
    assert response.status_code == 200, response.text


def test_public_routes_remain_public(client: TestClient):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/g38/status").status_code == 200
