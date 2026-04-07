import asyncio
import builtins
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException


_ORIGINAL_IMPORT = builtins.__import__


def _block_cryptography_import(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "cryptography" or name.startswith("cryptography."):
        raise ImportError("cryptography unavailable")
    return _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)


def test_auth_bypass_disabled_in_production(monkeypatch):
    from backend.auth import auth_guard as ag

    monkeypatch.setenv("YGB_ENV", "production")
    monkeypatch.setenv("YGB_TEMP_AUTH_BYPASS", "true")
    monkeypatch.setattr(ag, "IS_PRODUCTION", True, raising=False)

    assert ag.is_temporary_auth_bypass_enabled() is False


def test_admin_auth_bypass_disabled_in_production(monkeypatch):
    from backend.api import admin_auth as aa

    monkeypatch.setenv("YGB_ENV", "production")
    monkeypatch.setenv("YGB_TEMP_AUTH_BYPASS", "true")
    monkeypatch.setattr(aa, "IS_PRODUCTION", True, raising=False)

    assert aa._temporary_auth_bypass_enabled() is False
    assert aa.require_auth()["status"] == "unauthorized"


def test_auth_rate_limit_denies_101st_call(monkeypatch):
    from backend.auth import auth_guard as ag

    request = SimpleNamespace(
        url=SimpleNamespace(path="/backend/tests/group5"),
        method="GET",
        cookies={},
        headers={},
    )
    credentials = SimpleNamespace(credentials="group5-token")
    payload = {"sub": "group5-rate-limit-user", "role": "admin"}

    monkeypatch.setenv("YGB_ENV", "development")
    monkeypatch.setenv("YGB_TEMP_AUTH_BYPASS", "false")
    monkeypatch.setattr(ag, "IS_PRODUCTION", False, raising=False)
    monkeypatch.setattr(ag, "_verify_token_or_401", lambda token: payload)

    ag._subject_rate_limit_windows.clear()
    ag._audit_trail._entries.clear()

    async def _exercise_rate_limit():
        for _ in range(100):
            result = await ag.require_auth(request, credentials)
            assert result["sub"] == payload["sub"]

        with pytest.raises(HTTPException) as exc_info:
            await ag.require_auth(request, credentials)

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail["detail"] == "rate_limited"
        assert ag.get_auth_audit_trail(payload["sub"])[-1].reason == "rate_limited"

    try:
        asyncio.run(_exercise_rate_limit())
    finally:
        ag._subject_rate_limit_windows.clear()
        ag._audit_trail._entries.clear()


def test_admin_login_raises_when_jwt_creation_fails_in_production(monkeypatch):
    from backend.api import admin_auth as aa

    email = "group5-admin@example.com"
    user = {"user_id": "u-prod", "totp_secret": "secret", "role": aa.ROLE_ADMIN}

    monkeypatch.setenv("YGB_ENV", "production")
    monkeypatch.setattr(aa, "IS_PRODUCTION", True, raising=False)
    monkeypatch.setattr(aa, "is_locked_out", lambda identifier: False)
    monkeypatch.setattr(aa, "get_user", lambda value: user if value == email else None)
    monkeypatch.setattr(aa, "verify_totp", lambda secret, code: True)
    monkeypatch.setattr(aa, "clear_lockout", lambda identifier: None)
    monkeypatch.setattr(aa, "create_session", lambda user_id, role, ip: "s" * 64)
    monkeypatch.setattr(
        aa,
        "_load_users",
        lambda: {"users": {email: {**user, "last_login": 0, "last_ip": ""}}},
    )
    monkeypatch.setattr(aa, "_save_users", lambda data: None)
    monkeypatch.setattr(aa, "destroy_session", lambda token: None)
    monkeypatch.setattr(aa, "audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(aa, "_send_login_notification", lambda *args, **kwargs: None)

    def _raise_jwt_failure(user_id, role):
        raise RuntimeError("jwt signer unavailable")

    monkeypatch.setattr(aa, "create_jwt", _raise_jwt_failure)

    with pytest.raises(
        aa.AuthenticationError,
        match="JWT creation failed in production; session-only fallback is disabled.",
    ):
        aa.login(email, "123456", "1.2.3.4")


def test_admin_login_falls_back_to_session_in_development(monkeypatch):
    from backend.api import admin_auth as aa

    email = "group5-dev@example.com"
    user = {"user_id": "u-dev", "totp_secret": "secret", "role": aa.ROLE_ADMIN}

    monkeypatch.setenv("YGB_ENV", "development")
    monkeypatch.setattr(aa, "IS_PRODUCTION", False, raising=False)
    monkeypatch.setattr(aa, "is_locked_out", lambda identifier: False)
    monkeypatch.setattr(aa, "get_user", lambda value: user if value == email else None)
    monkeypatch.setattr(aa, "verify_totp", lambda secret, code: True)
    monkeypatch.setattr(aa, "clear_lockout", lambda identifier: None)
    monkeypatch.setattr(aa, "create_session", lambda user_id, role, ip: "d" * 64)
    monkeypatch.setattr(
        aa,
        "_load_users",
        lambda: {"users": {email: {**user, "last_login": 0, "last_ip": ""}}},
    )
    monkeypatch.setattr(aa, "_save_users", lambda data: None)
    monkeypatch.setattr(aa, "audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(aa, "_send_login_notification", lambda *args, **kwargs: None)

    def _raise_jwt_failure(user_id, role):
        raise RuntimeError("jwt signer unavailable")

    monkeypatch.setattr(aa, "create_jwt", _raise_jwt_failure)

    result = aa.login(email, "123456", "1.2.3.4")

    assert result["status"] == "ok"
    assert result["session_token"] == "d" * 64
    assert result["jwt_token"] is None


def test_revocation_uses_file_fallback_when_redis_unavailable(monkeypatch, tmp_path):
    from backend.auth import revocation_store as rs

    class _DownRedisStore:
        def __init__(self, redis_url):
            self._url = redis_url
            self._client = None

        def _is_available(self):
            return False

        def revoke_token(self, token_hash, ttl=rs._DEFAULT_TTL):
            raise AssertionError("Redis revoke_token should not run while unavailable")

        def revoke_session(self, session_id, ttl=rs._DEFAULT_TTL):
            raise AssertionError("Redis revoke_session should not run while unavailable")

        def is_token_revoked(self, token_hash):
            raise AssertionError("Redis is_token_revoked should not run while unavailable")

        def is_session_revoked(self, session_id):
            raise AssertionError("Redis is_session_revoked should not run while unavailable")

        def clear(self):
            return None

    revocation_path = tmp_path / "revocations.json"
    monkeypatch.setattr(rs, "_RedisStore", _DownRedisStore)
    monkeypatch.setenv("REVOCATION_BACKEND", "redis")
    monkeypatch.setenv("REVOCATION_FILE_PATH", str(revocation_path))
    rs.reset_store()

    try:
        rs.revoke_token("group5-token")

        assert rs.is_token_revoked("group5-token") is True
        stored_data = json.loads(revocation_path.read_text(encoding="utf-8"))
        assert stored_data["tokens"]
    finally:
        rs.reset_store()


def test_revocation_raises_when_redis_and_file_backends_are_unavailable(monkeypatch):
    from backend.auth import revocation_store as rs

    class _DownRedisStore:
        def __init__(self, redis_url):
            self._url = redis_url
            self._client = None

        def _is_available(self):
            return False

        def revoke_token(self, token_hash, ttl=rs._DEFAULT_TTL):
            raise AssertionError("Redis revoke_token should not run while unavailable")

        def revoke_session(self, session_id, ttl=rs._DEFAULT_TTL):
            raise AssertionError("Redis revoke_session should not run while unavailable")

        def is_token_revoked(self, token_hash):
            raise AssertionError("Redis is_token_revoked should not run while unavailable")

        def is_session_revoked(self, session_id):
            raise AssertionError("Redis is_session_revoked should not run while unavailable")

        def clear(self):
            return None

    class _UnavailableFileStore:
        def __init__(self, path=None):
            raise rs.RevocationUnavailableError("file backend offline")

    monkeypatch.setattr(rs, "_RedisStore", _DownRedisStore)
    monkeypatch.setattr(rs, "_FileStore", _UnavailableFileStore)
    monkeypatch.setenv("REVOCATION_BACKEND", "redis")
    rs.reset_store()

    try:
        with pytest.raises(
            rs.RevocationUnavailableError,
            match="Redis revocation backend is unavailable and file fallback is unavailable",
        ):
            rs.revoke_token("group5-token")
    finally:
        rs.reset_store()


def test_gdrive_missing_crypto_raises_when_encryption_required(monkeypatch, tmp_path):
    from backend.sync import gdrive_backup as gb

    source = tmp_path / "payload.bin"
    source.write_bytes(b"group5-real-bytes")

    staging_dir = tmp_path / "staging"
    pending_dir = staging_dir / "pending"
    uploaded_dir = staging_dir / "uploaded"

    monkeypatch.setattr(gb, "STAGING_DIR", staging_dir)
    monkeypatch.setattr(gb, "PENDING_DIR", pending_dir)
    monkeypatch.setattr(gb, "UPLOADED_DIR", uploaded_dir)
    monkeypatch.setattr(gb, "ENCRYPTION_REQUIRED", True, raising=False)
    monkeypatch.setattr(gb, "ENCRYPTION_KEY", "configured-encryption-key", raising=False)
    monkeypatch.setenv("YGB_REQUIRE_ENCRYPTION", "true")

    with patch("builtins.__import__", side_effect=_block_cryptography_import):
        with pytest.raises(
            gb.EncryptionRequiredError,
            match="Cannot backup without encryption. Install cryptography.",
        ):
            gb.stage_file_for_upload(source, "payload.bin", compress=False, encrypt=True)


def test_gdrive_missing_crypto_allows_plaintext_when_encryption_not_required(monkeypatch, tmp_path):
    from backend.sync import gdrive_backup as gb

    source = tmp_path / "payload.bin"
    source_bytes = b"group5-real-bytes"
    source.write_bytes(source_bytes)

    staging_dir = tmp_path / "staging"
    pending_dir = staging_dir / "pending"
    uploaded_dir = staging_dir / "uploaded"

    monkeypatch.setattr(gb, "STAGING_DIR", staging_dir)
    monkeypatch.setattr(gb, "PENDING_DIR", pending_dir)
    monkeypatch.setattr(gb, "UPLOADED_DIR", uploaded_dir)
    monkeypatch.setattr(gb, "ENCRYPTION_REQUIRED", False, raising=False)
    monkeypatch.setattr(gb, "ENCRYPTION_KEY", "configured-encryption-key", raising=False)
    monkeypatch.setenv("YGB_REQUIRE_ENCRYPTION", "false")

    with patch("builtins.__import__", side_effect=_block_cryptography_import):
        staged_path = gb.stage_file_for_upload(source, "payload.bin", compress=False, encrypt=True)

    assert isinstance(staged_path, Path)
    assert staged_path.read_bytes() == source_bytes
