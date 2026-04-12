from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_sync_client() -> TestClient:
    from backend.sync import sync_routes

    app = FastAPI()
    app.include_router(sync_routes.sync_router, prefix="/api/v1/sync")
    app.dependency_overrides[sync_routes.require_auth] = lambda: {"sub": "phase5-sync-user"}
    return TestClient(app)


def test_standalone_is_healthy(monkeypatch):
    from backend.sync import sync_engine as se

    monkeypatch.delenv("YGB_SYNC_PEERS", raising=False)
    monkeypatch.delenv("YGB_PEER_NODES", raising=False)

    index = se.get_local_sync_index()
    index.refresh()
    assert index.get_file_count() > 0

    client = _build_sync_client()
    response = client.get("/api/v1/sync/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "STANDALONE"
    assert payload["status"] == "HEALTHY"
    assert payload["local_files"] > 0
    assert payload["stale"] is False
    assert payload["configured"] is False


def test_sync_status_response_has_all_fields(monkeypatch, tmp_path):
    from backend.sync import sync_routes
    from backend.sync.sync_engine import LocalSyncIndex, SyncMode

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "artifact.bin").write_bytes(b"artifact")

    monkeypatch.setattr(LocalSyncIndex, "SCAN_DIRS", [str(data_dir)])
    monkeypatch.setattr(LocalSyncIndex, "INDEX_PATH", tmp_path / "local_sync_index.json")
    index = LocalSyncIndex()
    index.refresh()

    monkeypatch.setattr(sync_routes, "get_local_sync_index", lambda: index)
    monkeypatch.setattr(sync_routes, "get_sync_mode", lambda: SyncMode.STANDALONE)
    monkeypatch.setattr(sync_routes, "get_last_sync_cycle", lambda: None)
    monkeypatch.setattr(sync_routes, "is_sync_configured", lambda: False)
    monkeypatch.setattr(
        sync_routes,
        "get_sync_health",
        lambda: {
            "status": "NOT_CONFIGURED",
            "device_id": "device-a",
            "vector_clock": {},
            "file_count": 0,
            "total_mb": 0.0,
            "last_sync": "",
            "peers": {"total": 0, "online": 0, "offline": 0, "devices": []},
            "gdrive": {"enabled": False, "pending_files": 0},
            "disk": {"usage_pct": 1.0, "warning": False},
            "recent_activity": [],
            "checked_at": "2026-04-08T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(sync_routes, "should_alert", lambda payload: ["sync-healthy"])

    client = _build_sync_client()
    response = client.get("/api/v1/sync/status")

    assert response.status_code == 200
    payload = response.json()
    assert {
        "status",
        "device_id",
        "vector_clock",
        "file_count",
        "total_mb",
        "last_sync",
        "peers",
        "gdrive",
        "disk",
        "recent_activity",
        "checked_at",
        "mode",
        "local_files",
        "local_bytes",
        "message",
        "stale",
        "configured",
        "alerts",
    }.issubset(payload.keys())
    assert payload["mode"] == "STANDALONE"
    assert payload["local_files"] == 1
    assert payload["local_bytes"] > 0
    assert payload["stale"] is False
    assert payload["configured"] is False
    assert payload["alerts"] == ["sync-healthy"]
