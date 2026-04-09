from __future__ import annotations

import asyncio
import json
from pathlib import Path


def test_get_sync_mode_returns_standalone_when_no_peers(monkeypatch):
    from backend.sync import sync_engine as se

    monkeypatch.delenv("YGB_SYNC_PEERS", raising=False)
    monkeypatch.delenv("YGB_PEER_NODES", raising=False)

    assert se.get_sync_mode() is se.SyncMode.STANDALONE


def test_sync_mode_values_are_explicit():
    from backend.sync.sync_engine import SyncMode

    assert SyncMode.STANDALONE.value == "STANDALONE"
    assert SyncMode.PEER_SYNC.value == "PEER_SYNC"
    assert SyncMode.DEGRADED.value == "DEGRADED"


def test_local_sync_index_refresh_finds_files_in_data_dir(monkeypatch, tmp_path):
    from backend.sync.sync_engine import LocalSyncIndex

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "sample.txt").write_text("payload", encoding="utf-8")

    monkeypatch.setattr(LocalSyncIndex, "SCAN_DIRS", [str(data_dir)])
    monkeypatch.setattr(LocalSyncIndex, "INDEX_PATH", tmp_path / "local_sync_index.json")

    index = LocalSyncIndex()
    index.refresh()

    assert index.get_file_count() == 1
    assert index.get_total_bytes() > 0


def test_sync_status_response_includes_local_counts_and_standalone_not_stale(monkeypatch, tmp_path):
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
            "stale": True,
            "peers": {"total": 0, "online": 0, "offline": 0, "devices": []},
            "gdrive": {"enabled": False, "pending_files": 0},
            "disk": {"usage_pct": 1.0, "warning": False},
            "recent_activity": [],
            "checked_at": "2026-04-08T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(sync_routes, "should_alert", lambda payload: [])

    payload = asyncio.run(sync_routes.sync_status())

    assert payload["mode"] == "STANDALONE"
    assert payload["local_files"] > 0
    assert payload["local_bytes"] > 0
    assert payload["stale"] is False
    assert payload["message"] == "Single-device mode. Set YGB_SYNC_PEERS for mesh sync."


def test_sync_cycle_returns_real_local_counts(monkeypatch, tmp_path):
    from backend.sync import sync_engine as se

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "sample.txt").write_text("payload", encoding="utf-8")

    monkeypatch.setattr(se.LocalSyncIndex, "SCAN_DIRS", [str(data_dir)])
    monkeypatch.setattr(se.LocalSyncIndex, "INDEX_PATH", tmp_path / "local_sync_index.json")
    se._sync_index = se.LocalSyncIndex()

    manifest = se.SyncManifest()
    monkeypatch.setattr(se, "_init_dirs", lambda: None)
    monkeypatch.setattr(se, "_SYNC_HISTORY", se.SyncHistory(limit=10))
    monkeypatch.setattr(se, "load_manifest", lambda _path: manifest)
    monkeypatch.setattr(se, "scan_local_files", lambda: {})
    monkeypatch.setattr(se, "enforce_retention", lambda: 0)
    monkeypatch.setattr(se, "compress_cold_files", lambda: 0)
    monkeypatch.setattr(se, "cleanup_orphan_chunks", lambda _files: 0)
    monkeypatch.setattr(se, "save_manifest", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(se, "get_sync_mode", lambda: se.SyncMode.STANDALONE)
    monkeypatch.setattr(se, "_sync_manifest_to_peers", lambda _manifest: (0, 0, []))
    status_path = tmp_path / "sync_status.json"
    monkeypatch.setattr(se, "SYNC_STATUS_PATH", status_path)

    result = se.sync_cycle()

    assert result.mode == "STANDALONE"
    assert result.local_files > 0
    assert result.local_bytes > 0
    persisted = json.loads(status_path.read_text(encoding="utf-8"))
    assert persisted["mode"] == "STANDALONE"
    assert persisted["stale"] is False
