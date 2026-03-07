import sys
import types

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from backend.auth import auth_guard


def _request(method: str = "GET", headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request({"type": "http", "method": method, "headers": headers or []})


def _install_storage_bridge(monkeypatch, get_user_impl):
    fake = types.ModuleType("backend.storage.storage_bridge")
    fake.get_user = get_user_impl
    monkeypatch.setitem(sys.modules, "backend.storage.storage_bridge", fake)


@pytest.mark.asyncio
async def test_require_auth_hydrates_role_from_storage(monkeypatch):
    monkeypatch.setattr(auth_guard, "is_token_revoked", lambda _t: False)
    monkeypatch.setattr(auth_guard, "is_session_revoked", lambda _sid: False)
    monkeypatch.setattr(auth_guard, "verify_jwt", lambda _t: {"sub": "user-1"})
    _install_storage_bridge(
        monkeypatch,
        lambda user_id: {"id": user_id, "role": "admin"},
    )

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-123")
    payload = await auth_guard.require_auth(_request(), creds)

    assert payload["sub"] == "user-1"
    assert payload["role"] == "admin"


@pytest.mark.asyncio
async def test_require_auth_still_succeeds_when_role_lookup_fails(monkeypatch):
    monkeypatch.setattr(auth_guard, "is_token_revoked", lambda _t: False)
    monkeypatch.setattr(auth_guard, "is_session_revoked", lambda _sid: False)
    monkeypatch.setattr(auth_guard, "verify_jwt", lambda _t: {"sub": "user-2"})

    def _raise_lookup(_user_id: str):
        raise RuntimeError("storage unavailable")

    _install_storage_bridge(monkeypatch, _raise_lookup)

    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="token-456")
    payload = await auth_guard.require_auth(_request(), creds)

    assert payload["sub"] == "user-2"
    assert "role" not in payload


@pytest.mark.asyncio
async def test_require_auth_accepts_cookie_auth_on_safe_methods(monkeypatch):
    monkeypatch.setattr(auth_guard, "is_token_revoked", lambda _t: False)
    monkeypatch.setattr(auth_guard, "is_session_revoked", lambda _sid: False)
    monkeypatch.setattr(auth_guard, "verify_jwt", lambda _t: {"sub": "user-cookie"})

    request = _request(headers=[(b"cookie", b"ygb_auth=token-cookie")])
    payload = await auth_guard.require_auth(request, None)

    assert payload["sub"] == "user-cookie"
    assert payload["_auth_via"] == "cookie"


@pytest.mark.asyncio
async def test_require_auth_rejects_cookie_auth_without_csrf(monkeypatch):
    monkeypatch.setattr(auth_guard, "is_token_revoked", lambda _t: False)
    monkeypatch.setattr(auth_guard, "is_session_revoked", lambda _sid: False)
    monkeypatch.setattr(auth_guard, "verify_jwt", lambda _t: {"sub": "user-cookie"})

    request = _request(
        method="POST",
        headers=[
            (b"origin", b"http://localhost:3000"),
            (b"cookie", b"ygb_auth=token-cookie; ygb_csrf=csrf-123"),
        ],
    )

    with pytest.raises(HTTPException) as exc:
        await auth_guard.require_auth(request, None)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_require_auth_accepts_cookie_auth_with_valid_csrf(monkeypatch):
    monkeypatch.setattr(auth_guard, "is_token_revoked", lambda _t: False)
    monkeypatch.setattr(auth_guard, "is_session_revoked", lambda _sid: False)
    monkeypatch.setattr(auth_guard, "verify_jwt", lambda _t: {"sub": "user-cookie"})

    request = _request(
        method="POST",
        headers=[
            (b"origin", b"http://localhost:3000"),
            (b"cookie", b"ygb_auth=token-cookie; ygb_csrf=csrf-123"),
            (b"x-csrf-token", b"csrf-123"),
        ],
    )
    payload = await auth_guard.require_auth(request, None)

    assert payload["sub"] == "user-cookie"
    assert payload["_auth_via"] == "cookie"


@pytest.mark.asyncio
async def test_require_admin_blocks_non_admin():
    with pytest.raises(HTTPException) as exc:
        await auth_guard.require_admin({"role": "hunter"})
    assert exc.value.status_code == 403
