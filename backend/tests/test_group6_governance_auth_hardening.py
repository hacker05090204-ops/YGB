from __future__ import annotations

from collections import deque

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.api.runtime_api as runtime_api
from backend.auth import auth_guard
import backend.auth.revocation_store as revocation_store
from backend.governance import approval_ledger


def test_key_manager_status_reports_fallback_and_authority_state(monkeypatch):
    monkeypatch.delenv("YGB_KEY_DIR", raising=False)
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "a" * 64)
    monkeypatch.setenv("YGB_AUTHORITY_KEY", "authority-key-1234567890")
    monkeypatch.setattr(approval_ledger, "last_integrity_report", None)

    manager = approval_ledger.KeyManager(strict=False)
    payload = approval_ledger.get_key_manager_status(
        key_manager=manager,
        run_integrity=False,
    )

    assert payload["available"] is True
    assert payload["status"] == "DEGRADED"
    assert payload["using_env_fallback"] is True
    assert payload["source"] == "env"
    assert payload["active_key_id"] == approval_ledger.KeyManager.DEFAULT_KEY_ID
    assert payload["authority_key_configured"] is True
    assert payload["error"] is None


def test_auth_runtime_status_reports_secret_and_backend_health(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "b" * 64)
    monkeypatch.setenv("YGB_HMAC_SECRET", "c" * 64)
    monkeypatch.setenv("YGB_VIDEO_JWT_SECRET", "d" * 64)
    monkeypatch.setenv("YGB_TEMP_AUTH_BYPASS", "false")
    monkeypatch.setenv("YGB_ENV", "development")
    monkeypatch.setattr(
        auth_guard,
        "_audit_trail",
        auth_guard.AuthAuditTrail(max_entries=32, retain_entries=16),
    )
    monkeypatch.setattr(
        auth_guard,
        "_subject_rate_limit_windows",
        {"user-1": deque([1.0])},
    )
    monkeypatch.setattr(
        revocation_store,
        "get_backend_health",
        lambda: {"status": "healthy", "backend": "memory"},
    )

    auth_guard._append_auth_audit(
        subject="user-1",
        resource="/secure",
        action="require_auth",
        decision="allow",
        reason="ok",
    )
    payload = auth_guard.get_auth_runtime_status()

    assert payload["status"] == "HEALTHY"
    assert payload["available"] is True
    assert payload["temporary_bypass_enabled"] is False
    assert payload["all_required_secrets_present"] is True
    assert payload["audit_entries"] == 1
    assert payload["active_rate_limited_subjects"] == 1
    assert payload["revocation_backend"]["backend"] == "memory"


def test_auth_status_endpoint_returns_runtime_payload(monkeypatch):
    monkeypatch.setattr(
        runtime_api,
        "get_auth_status",
        lambda: {
            "status": "ok",
            "available": True,
            "temporary_bypass_enabled": False,
            "audit_entries": 3,
        },
    )
    app = FastAPI()
    app.include_router(runtime_api.router)
    app.dependency_overrides[runtime_api.require_auth] = lambda: {"sub": "user-1"}
    client = TestClient(app)

    response = client.get("/api/v1/auth/status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "available": True,
        "temporary_bypass_enabled": False,
        "audit_entries": 3,
    }


def test_governance_key_status_endpoint_returns_runtime_payload(monkeypatch):
    monkeypatch.setattr(
        runtime_api,
        "get_governance_key_status",
        lambda: {
            "status": "ok",
            "available": True,
            "active_key_id": "ygb-key-v2",
            "using_env_fallback": False,
        },
    )
    app = FastAPI()
    app.include_router(runtime_api.router)
    app.dependency_overrides[runtime_api.require_admin] = lambda: {
        "sub": "admin-1",
        "role": "admin",
    }
    client = TestClient(app)

    response = client.get("/api/v1/governance/key-status")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "available": True,
        "active_key_id": "ygb-key-v2",
        "using_env_fallback": False,
    }
