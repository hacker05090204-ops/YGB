from __future__ import annotations


def test_login_raises_when_jwt_creation_fails_in_production(monkeypatch):
    from backend.api import admin_auth

    email = "phase10-admin@example.com"
    user = {
        "user_id": "u-phase10",
        "totp_secret": "secret",
        "role": admin_auth.ROLE_ADMIN,
    }

    monkeypatch.setenv("YGB_ENV", "production")
    monkeypatch.setattr(admin_auth, "IS_PRODUCTION", True, raising=False)
    monkeypatch.setattr(admin_auth, "is_locked_out", lambda identifier: False)
    monkeypatch.setattr(admin_auth, "get_user", lambda value: user if value == email else None)
    monkeypatch.setattr(admin_auth, "verify_totp", lambda secret, code: True)
    monkeypatch.setattr(admin_auth, "clear_lockout", lambda identifier: None)
    monkeypatch.setattr(admin_auth, "create_session", lambda user_id, role, ip: "s" * 64)
    monkeypatch.setattr(
        admin_auth,
        "_load_users",
        lambda: {"users": {email: {**user, "last_login": 0, "last_ip": ""}}},
    )
    monkeypatch.setattr(admin_auth, "_save_users", lambda data: None)
    monkeypatch.setattr(admin_auth, "destroy_session", lambda token: None)
    monkeypatch.setattr(admin_auth, "audit_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(admin_auth, "_send_login_notification", lambda *args, **kwargs: None)

    def _raise_jwt_failure(user_id, role):
        raise RuntimeError("jwt signer unavailable")

    monkeypatch.setattr(admin_auth, "create_jwt", _raise_jwt_failure)

    try:
        admin_auth.login(email, "123456", "1.2.3.4")
    except admin_auth.AuthenticationError as exc:
        assert str(exc) == "JWT creation failed in production; session-only fallback is disabled."
    else:
        raise AssertionError("Expected AuthenticationError when JWT creation fails in production")
