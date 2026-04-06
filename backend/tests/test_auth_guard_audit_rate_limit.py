import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from backend.auth import auth_guard


def _request(
    path: str = "/auth/check",
    method: str = "GET",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": headers or []})


@pytest.fixture(autouse=True)
def _reset_auth_state(monkeypatch):
    monkeypatch.setenv("YGB_TEMP_AUTH_BYPASS", "false")
    monkeypatch.setattr(auth_guard, "_audit_trail", auth_guard.AuthAuditTrail(max_entries=32, retain_entries=16))
    monkeypatch.setattr(auth_guard, "_subject_rate_limit_windows", {})


@pytest.mark.asyncio
async def test_require_auth_records_allow_audit_entry(monkeypatch):
    monkeypatch.setattr(auth_guard, "is_token_revoked", lambda _token: False)
    monkeypatch.setattr(auth_guard, "is_session_revoked", lambda _session_id: False)
    monkeypatch.setattr(auth_guard, "verify_jwt", lambda _token: {"sub": "user-1", "role": "admin"})

    payload = await auth_guard.require_auth(
        _request(path="/secure"),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-1"),
    )

    entries = auth_guard.get_auth_audit_trail("user-1")
    assert payload["sub"] == "user-1"
    assert len(entries) == 1
    assert entries[0].resource == "/secure"
    assert entries[0].action == "require_auth"
    assert entries[0].decision == "allow"


@pytest.mark.asyncio
async def test_require_auth_records_deny_audit_entry():
    with pytest.raises(HTTPException) as exc:
        await auth_guard.require_auth(_request(path="/denied"), None)

    entries = auth_guard.get_auth_audit_trail()
    assert exc.value.status_code == 401
    assert len(entries) == 1
    assert entries[0].subject == "anonymous"
    assert entries[0].resource == "/denied"
    assert entries[0].decision == "deny"


@pytest.mark.asyncio
async def test_require_auth_rate_limits_on_101st_call(monkeypatch):
    monkeypatch.setattr(auth_guard, "is_token_revoked", lambda _token: False)
    monkeypatch.setattr(auth_guard, "is_session_revoked", lambda _session_id: False)
    monkeypatch.setattr(auth_guard, "verify_jwt", lambda _token: {"sub": "rate-user", "role": "admin"})
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-2")

    for _ in range(100):
        payload = await auth_guard.require_auth(_request(path="/limited"), creds)
        assert payload["sub"] == "rate-user"

    with pytest.raises(HTTPException) as exc:
        await auth_guard.require_auth(_request(path="/limited"), creds)

    entries = auth_guard.get_auth_audit_trail("rate-user")
    assert exc.value.status_code == 429
    assert entries[-1].decision == "deny"
    assert entries[-1].reason == "rate_limited"


def test_auth_audit_trail_rotates_when_capacity_exceeded():
    trail = auth_guard.AuthAuditTrail(max_entries=4, retain_entries=2)

    for idx in range(5):
        trail.append(
            auth_guard.AuthAuditEntry(
                timestamp=str(idx),
                subject=f"user-{idx}",
                resource="resource",
                action="require_auth",
                decision="allow",
                reason="ok",
            )
        )

    entries = trail.get()
    assert [entry.subject for entry in entries] == ["user-3", "user-4"]

