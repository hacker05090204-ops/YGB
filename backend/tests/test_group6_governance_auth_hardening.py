from __future__ import annotations

from collections import deque
import os

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
    monkeypatch.setenv("YGB_ENV", "development")
    monkeypatch.setattr(approval_ledger, "last_integrity_report", None)

    manager = approval_ledger.KeyManager(strict=False)
    payload = approval_ledger.get_key_manager_status(
        key_manager=manager,
        run_integrity=False,
    )

    assert payload["available"] is True
    assert payload["status"] == "DEGRADED"
    assert payload["key_mode"] == approval_ledger.LedgerKeyMode.ENV_KEY.value
    assert payload["production_mode"] is False
    assert payload["using_env_fallback"] is True
    assert payload["source"] == "env"
    assert payload["key_dir"] is None
    assert payload["key_dir_configured"] is False
    assert payload["active_key_id"] == approval_ledger.KeyManager.DEFAULT_KEY_ID
    assert payload["authority_key_configured"] is True
    assert payload["error"] is None


def test_get_ledger_key_mode_prefers_file_key_resolution(monkeypatch, tmp_path):
    key_dir = tmp_path / "keys"
    key_dir.mkdir()
    key_path = key_dir / "prod-key-v1.key"
    key_path.write_bytes(b"real-approval-secret")

    monkeypatch.setenv("YGB_KEY_DIR", str(key_dir))
    monkeypatch.delenv("YGB_APPROVAL_SECRET", raising=False)
    if os.name != "nt":
        key_path.chmod(0o600)

    assert approval_ledger.get_ledger_key_mode() is approval_ledger.LedgerKeyMode.FILE_KEY


def test_get_key_manager_status_reports_missing_key_mode_safely(monkeypatch, tmp_path):
    empty_key_dir = tmp_path / "empty-keys"
    empty_key_dir.mkdir()

    monkeypatch.setenv("YGB_KEY_DIR", str(empty_key_dir))
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "b" * 64)
    monkeypatch.setenv("YGB_ENV", "production")
    monkeypatch.setattr(approval_ledger, "last_integrity_report", None)

    payload = approval_ledger.get_key_manager_status(run_integrity=False, strict=False)

    assert payload["available"] is False
    assert payload["status"] == "ERROR"
    assert payload["key_mode"] == approval_ledger.LedgerKeyMode.MISSING.value
    assert payload["production_mode"] is True
    assert payload["key_dir"] == "<configured>"
    assert payload["key_dir_configured"] is True
    assert payload["using_env_fallback"] is False
    assert payload["active_key_id"] is None
    assert payload["error"] == "signing_key_unavailable"


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
