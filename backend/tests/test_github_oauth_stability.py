import asyncio
import json

from api import server as server_mod
from backend.storage import storage_bridge as storage_bridge


class _FakeUserEngine:
    def __init__(self, users):
        self.users = users

    def read_entity(self, collection, entity_id):
        if collection != "users":
            return None
        latest = self.users.get(entity_id)
        if latest is None:
            return None
        return {"latest": dict(latest)}

    def list_entities(self, collection, limit=10000):
        if collection != "users":
            return []
        return [{"entity_id": entity_id} for entity_id in self.users]

    def append_record(self, collection, entity_id, data):
        if collection != "users":
            raise AssertionError(f"Unexpected collection: {collection}")
        self.users[entity_id] = dict(data)


def _base_user(email="octocat@example.com"):
    return {
        "name": "Octocat",
        "email": email,
        "role": "hunter",
        "password_hash": None,
        "auth_provider": None,
        "last_login_ip": None,
        "last_geolocation": None,
        "last_auth_provider": None,
        "last_auth_at": None,
        "github_id": None,
        "github_login": None,
        "avatar_url": None,
        "github_profile": {},
        "total_bounties": 0,
        "total_earnings": 0.0,
        "created_at": "2026-03-07T00:00:00+00:00",
        "last_active": "2026-03-07T00:00:00+00:00",
    }


def _install_fake_storage(users):
    original_engine = storage_bridge._engine
    original_email_index = dict(storage_bridge._EMAIL_INDEX)
    original_email_built = storage_bridge._EMAIL_INDEX_BUILT
    original_github_index = dict(storage_bridge._GITHUB_ID_INDEX)
    original_github_built = storage_bridge._GITHUB_ID_INDEX_BUILT

    storage_bridge._engine = _FakeUserEngine(users)
    storage_bridge._EMAIL_INDEX = {}
    storage_bridge._EMAIL_INDEX_BUILT = False
    storage_bridge._GITHUB_ID_INDEX = {}
    storage_bridge._GITHUB_ID_INDEX_BUILT = False

    def restore():
        storage_bridge._engine = original_engine
        storage_bridge._EMAIL_INDEX = original_email_index
        storage_bridge._EMAIL_INDEX_BUILT = original_email_built
        storage_bridge._GITHUB_ID_INDEX = original_github_index
        storage_bridge._GITHUB_ID_INDEX_BUILT = original_github_built

    return restore


def test_update_user_auth_profile_promotes_github_identity_fields():
    users = {"user-1": _base_user()}
    restore = _install_fake_storage(users)
    try:
        storage_bridge.update_user_auth_profile(
            "user-1",
            auth_provider="github",
            ip_address="1.2.3.4",
            geolocation=None,
            github_profile={
                "github_id": "12345",
                "github_login": "octocat",
                "avatar_url": "https://avatars.githubusercontent.com/u/1",
            },
        )

        record = storage_bridge.get_user("user-1")
        assert record["auth_provider"] == "github"
        assert record["github_id"] == "12345"
        assert record["github_login"] == "octocat"
        assert record["avatar_url"] == "https://avatars.githubusercontent.com/u/1"
    finally:
        restore()


def test_get_user_by_github_id_uses_stable_identity_lookup():
    users = {
        "user-1": {
            **_base_user(),
            "auth_provider": "github",
            "last_auth_provider": "github",
            "github_id": "12345",
            "github_login": "octocat",
            "avatar_url": "https://avatars.githubusercontent.com/u/1",
            "github_profile": {
                "github_id": "12345",
                "github_login": "octocat",
                "avatar_url": "https://avatars.githubusercontent.com/u/1",
            },
        }
    }
    restore = _install_fake_storage(users)
    try:
        record = storage_bridge.get_user_by_github_id("12345")
        assert record is not None
        assert record["id"] == "user-1"
        assert record["github_login"] == "octocat"
    finally:
        restore()


def test_resolve_or_create_github_user_prefers_github_id(monkeypatch):
    github_user = {"id": "user-github", "email": "new@example.com", "role": "hunter"}
    email_user = {"id": "user-email", "email": "new@example.com", "role": "hunter"}
    created = []

    monkeypatch.setattr(server_mod, "get_user_by_github_id", lambda github_id: github_user)
    monkeypatch.setattr(server_mod, "get_user_by_email", lambda email: email_user)
    monkeypatch.setattr(
        server_mod,
        "create_user",
        lambda name, email, role: created.append((name, email, role)),
    )

    record, is_new_user = server_mod._resolve_or_create_github_user(
        github_id="12345",
        github_login="octocat",
        effective_email="new@example.com",
    )

    assert record["id"] == "user-github"
    assert is_new_user is False
    assert created == []


def test_auth_me_returns_github_fields_from_storage(monkeypatch):
    monkeypatch.setattr(
        server_mod,
        "get_user",
        lambda user_id: {
            "id": user_id,
            "name": "Octocat",
            "email": "octocat@example.com",
            "role": "hunter",
            "auth_provider": "github",
            "github_id": "12345",
            "github_login": "octocat",
            "avatar_url": "https://avatars.githubusercontent.com/u/1",
        },
    )

    response = asyncio.run(server_mod.auth_me(user={"sub": "user-1", "session_id": "sess-1"}))
    payload = json.loads(response.body.decode())

    assert payload["user_id"] == "user-1"
    assert payload["auth_provider"] == "github"
    assert payload["github_login"] == "octocat"
    assert payload["avatar_url"] == "https://avatars.githubusercontent.com/u/1"
    assert response.headers["Cache-Control"] == "no-store"
