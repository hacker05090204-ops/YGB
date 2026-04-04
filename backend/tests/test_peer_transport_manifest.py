import json


def test_load_peer_manifest_logs_and_returns_none_on_invalid_json(monkeypatch, tmp_path, caplog):
    from backend.sync import peer_transport as pt

    peer_state = tmp_path / "peer_state"
    peer_state.mkdir(parents=True, exist_ok=True)
    (peer_state / "peer-a.json").write_text("{invalid", encoding="utf-8")
    monkeypatch.setattr(pt, "PEER_STATE", peer_state)

    result = pt.load_peer_manifest("peer-a")

    assert result is None
    assert any("Failed to load cached peer manifest" in record.message for record in caplog.records)


def test_load_peer_manifest_returns_data_when_valid(monkeypatch, tmp_path):
    from backend.sync import peer_transport as pt

    peer_state = tmp_path / "peer_state"
    peer_state.mkdir(parents=True, exist_ok=True)
    payload = {"device_id": "peer-a", "files": 3}
    (peer_state / "peer-a.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(pt, "PEER_STATE", peer_state)

    result = pt.load_peer_manifest("peer-a")

    assert result == payload


def test_get_peers_maps_health_to_transport_status(monkeypatch):
    from backend.sync import peer_transport as pt

    pt._PEER_STATUSES.clear()
    monkeypatch.setattr(
        pt,
        "_parse_peers",
        lambda: [
            {"name": "peer-a", "url": "http://peer-a", "ip": "10.0.0.1", "port": "8000"},
            {"name": "peer-b", "url": "http://peer-b", "ip": "10.0.0.2", "port": "8000"},
        ],
    )
    monkeypatch.setattr(
        pt,
        "check_peer_health",
        lambda url, timeout=2.0: "ONLINE" if "peer-a" in url else "ERROR",
    )

    peers = pt.get_peers()

    assert peers[0]["peer_status"] == pt.PeerStatus.REACHABLE.value
    assert peers[1]["peer_status"] == pt.PeerStatus.DEGRADED.value
    statuses = pt.get_peer_statuses()
    assert statuses["peer-a"] is pt.PeerStatus.REACHABLE
    assert statuses["peer-b"] is pt.PeerStatus.DEGRADED


def test_parallel_download_chunks_uses_backoff_and_recovers_status(monkeypatch):
    from backend.sync import peer_transport as pt

    pt._PEER_STATUSES.clear()
    peers = [{"name": "peer-a", "url": "http://peer-a", "status": "ONLINE"}]
    attempts = {"count": 0}
    delays = []

    def _fetch(_peer_url, _chunk_hash, timeout=30.0):
        attempts["count"] += 1
        if attempts["count"] < 3:
            return None
        return b"chunk-data"

    monkeypatch.setattr(pt, "fetch_chunk_from_peer", _fetch)
    monkeypatch.setattr(pt, "_run_async_backoff_sleep", lambda delay: delays.append(delay))

    downloaded = pt.parallel_download_chunks(["chunk-1"], peers, max_workers=1)

    assert downloaded == {"chunk-1": b"chunk-data"}
    assert attempts["count"] == 3
    assert delays == [1.0, 2.0]
    assert pt.get_peer_statuses()["peer-a"] is pt.PeerStatus.REACHABLE


def test_parallel_download_chunks_marks_unreachable_after_budget_exhaustion(monkeypatch):
    from backend.sync import peer_transport as pt

    pt._PEER_STATUSES.clear()
    peers = [{"name": "peer-a", "url": "http://peer-a", "status": "ONLINE"}]
    delays = []

    monkeypatch.setattr(pt, "fetch_chunk_from_peer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(pt, "_run_async_backoff_sleep", lambda delay: delays.append(delay))

    downloaded = pt.parallel_download_chunks(["chunk-1"], peers, max_workers=1)

    assert downloaded == {}
    assert delays == [1.0, 2.0]
    assert pt.get_peer_statuses()["peer-a"] is pt.PeerStatus.UNREACHABLE
