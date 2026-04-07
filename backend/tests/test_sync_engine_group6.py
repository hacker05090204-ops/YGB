import logging
from unittest.mock import MagicMock


def _file_entry(path: str, file_hash: str, *, size: int = 1, mtime: float = 1.0) -> dict:
    return {
        "path": path,
        "hash": file_hash,
        "size": size,
        "mtime": mtime,
        "chunks": [file_hash],
        "device_id": "test-device",
        "clock": 0,
    }


def _patch_sync_cycle_dependencies(monkeypatch, se, *, previous_files: dict, current_files: dict):
    from backend.sync import peer_transport as pt

    manifest = se.SyncManifest()
    manifest.files = dict(previous_files)

    monkeypatch.setattr(se, "_init_dirs", lambda: None)
    monkeypatch.setattr(se, "_SYNC_HISTORY", se.SyncHistory(limit=50))
    monkeypatch.setattr(se, "load_manifest", lambda path: manifest)
    monkeypatch.setattr(se, "scan_local_files", lambda: dict(current_files))
    monkeypatch.setattr(se, "enforce_retention", lambda: 0)
    monkeypatch.setattr(se, "compress_cold_files", lambda: 0)
    monkeypatch.setattr(se, "cleanup_orphan_chunks", lambda files: 0)

    save_manifest = MagicMock()
    monkeypatch.setattr(se, "save_manifest", save_manifest)
    monkeypatch.setattr(pt, "get_peers", lambda: [])
    monkeypatch.setattr(pt, "push_manifest_to_peer", lambda url, payload: True)
    return save_manifest, pt


def test_sync_cycle_continues_when_peer_unreachable(monkeypatch, caplog):
    from backend.sync import sync_engine as se

    current_files = {"report.txt": _file_entry("report.txt", "hash-report")}
    _, pt = _patch_sync_cycle_dependencies(
        monkeypatch,
        se,
        previous_files={},
        current_files=current_files,
    )
    monkeypatch.setattr(
        pt,
        "get_peers",
        lambda: [
            {"name": "peer-a", "url": "http://peer-a", "status": "ONLINE"},
            {"name": "peer-b", "url": "http://peer-b", "status": "OFFLINE"},
        ],
    )
    monkeypatch.setattr(pt, "push_manifest_to_peer", lambda url, payload: url == "http://peer-a")

    with caplog.at_level(logging.WARNING):
        result = se.sync_cycle()

    assert isinstance(result, se.SyncCycleResult)
    assert result.peers_attempted == 2
    assert result.peers_succeeded == 1
    assert any("peer-b" in error for error in result.errors)
    assert "Peer peer-b unreachable" in caplog.text


def test_sync_cycle_updates_manifest_when_files_changed(monkeypatch):
    from backend.sync import sync_engine as se

    previous_files = {"report.txt": _file_entry("report.txt", "hash-old")}
    current_files = {"report.txt": _file_entry("report.txt", "hash-new")}
    save_manifest, _ = _patch_sync_cycle_dependencies(
        monkeypatch,
        se,
        previous_files=previous_files,
        current_files=current_files,
    )

    result = se.sync_cycle()

    assert result.files_changed == 1
    save_manifest.assert_called_once()
    saved_manifest, saved_path = save_manifest.call_args.args
    assert saved_manifest.files == current_files
    assert saved_path == se.MANIFEST_PATH


def test_sync_cycle_returns_real_counts_and_records_history(monkeypatch):
    from backend.sync import sync_engine as se

    previous_files = {
        "same.txt": _file_entry("same.txt", "hash-same"),
        "changed.txt": _file_entry("changed.txt", "hash-old"),
        "deleted.txt": _file_entry("deleted.txt", "hash-deleted"),
    }
    current_files = {
        "same.txt": _file_entry("same.txt", "hash-same"),
        "changed.txt": _file_entry("changed.txt", "hash-new"),
        "added.txt": _file_entry("added.txt", "hash-added"),
    }
    _patch_sync_cycle_dependencies(
        monkeypatch,
        se,
        previous_files=previous_files,
        current_files=current_files,
    )

    result = se.sync_cycle()
    history = se.get_sync_history()

    assert result.files_scanned == 3
    assert result.files_changed == 3
    assert result.peers_attempted == 0
    assert result.peers_succeeded == 0
    assert result.errors == []
    assert len(history) == 1
    assert history[0] == result
