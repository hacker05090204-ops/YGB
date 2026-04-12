from __future__ import annotations


def test_temporary_auth_bypass_remains_disabled_in_production(monkeypatch):
    from backend.auth import auth_guard

    monkeypatch.setenv("YGB_ENV", "production")
    monkeypatch.setenv("YGB_TEMP_AUTH_BYPASS", "true")
    monkeypatch.setenv("YGB_ENABLE_TEST_ONLY_PATHS", "1")

    assert auth_guard.is_temporary_auth_bypass_enabled() is False

    status = auth_guard.get_auth_runtime_status()
    assert status["production_mode"] is True
    assert status["temporary_bypass_requested"] is True
    assert status["temporary_bypass_enabled"] is False
