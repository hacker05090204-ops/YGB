import importlib
import sys

import pytest


def _reload_auth_guard(monkeypatch, **overrides):
    defaults = {
        "JWT_SECRET": "a" * 64,
        "YGB_HMAC_SECRET": "b" * 64,
        "YGB_VIDEO_JWT_SECRET": "c" * 64,
        "YGB_ENV": "development",
        "YGB_TEMP_AUTH_BYPASS": "false",
        "YGB_ENABLE_TEST_ONLY_PATHS": "false",
    }
    defaults.update(overrides)

    for key, value in defaults.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)

    sys.modules.pop("backend.auth.auth_guard", None)
    sys.modules.pop("backend.auth.auth", None)
    return importlib.import_module("backend.auth.auth_guard")


def test_auth_import_fails_closed_without_strong_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("YGB_HMAC_SECRET", "b" * 64)
    monkeypatch.setenv("YGB_VIDEO_JWT_SECRET", "c" * 64)
    monkeypatch.setenv("YGB_TEMP_AUTH_BYPASS", "false")

    sys.modules.pop("backend.auth.auth_guard", None)
    sys.modules.pop("backend.auth.auth", None)

    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        importlib.import_module("backend.auth.auth_guard")


def test_temporary_auth_bypass_disabled_in_production(monkeypatch):
    auth_guard = _reload_auth_guard(
        monkeypatch,
        YGB_ENV="production",
        YGB_TEMP_AUTH_BYPASS="true",
        YGB_ENABLE_TEST_ONLY_PATHS="true",
    )

    assert auth_guard.is_temporary_auth_bypass_enabled() is False


def test_storage_bridge_blocks_path_traversal(monkeypatch):
    from backend.storage import storage_bridge as storage_bridge

    result = storage_bridge.store_video("../escape", "session_01", b"video-bytes")

    assert result["success"] is False
    assert "user_id" in result["reason"]


def test_storage_bridge_rejects_unsafe_filename(monkeypatch):
    from backend.storage import storage_bridge as storage_bridge

    result = storage_bridge.get_video_stream_token(
        "user_01",
        "session_01",
        "../secret.webm",
    )

    assert "error" in result
    assert "filename" in result["error"]
