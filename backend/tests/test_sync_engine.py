from __future__ import annotations


def test_standalone_mode_when_no_peers_env(monkeypatch):
    from backend.sync import sync_engine as se

    monkeypatch.delenv("YGB_SYNC_PEERS", raising=False)
    monkeypatch.delenv("YGB_PEER_NODES", raising=False)

    assert se.get_sync_mode() is se.SyncMode.STANDALONE


def test_local_sync_index_finds_files(monkeypatch, tmp_path):
    from backend.sync.sync_engine import LocalSyncIndex

    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = data_dir / "sample.txt"
    payload.write_text("payload", encoding="utf-8")

    monkeypatch.setattr(LocalSyncIndex, "SCAN_DIRS", [str(data_dir)])
    monkeypatch.setattr(LocalSyncIndex, "INDEX_PATH", tmp_path / "local_sync_index.json")

    index = LocalSyncIndex()
    index.refresh()

    assert index.get_file_count() == 1
    assert index.get_total_bytes() == payload.stat().st_size


def test_stale_false_in_standalone():
    from backend.sync import sync_engine as se

    assert se.is_sync_stale(
        mode=se.SyncMode.STANDALONE,
        last_completed_at="2000-01-01T00:00:00+00:00",
    ) is False
