import json


def test_recovery_log_filters_and_resolves_unresolved_events(monkeypatch, tmp_path):
    from backend.sync import recovery as rc

    recovery_log = tmp_path / "recovery_log.json"
    monkeypatch.setattr(rc, "SYNC_META", tmp_path)
    monkeypatch.setattr(rc, "RECOVERY_LOG_PATH", recovery_log)

    rc._append_recovery_event("peer-a", "no_online_peers", resolved=False)
    rc._append_recovery_event("peer-a", "no_online_peers", resolved=False)
    rc._append_recovery_event("gdrive", "cloud_recovery_failed", resolved=False)

    unresolved = rc.get_unresolved_events()
    assert len(unresolved) == 2

    resolved_count = rc.mark_recovery_events_resolved("peer-a", "no_online_peers")
    assert resolved_count == 1

    unresolved_after = rc.get_unresolved_events()
    assert len(unresolved_after) == 1
    assert unresolved_after[0].peer_id == "gdrive"


def test_recovery_log_rotation_keeps_unresolved_events(monkeypatch, tmp_path):
    from backend.sync import recovery as rc

    recovery_log = tmp_path / "recovery_log.json"
    monkeypatch.setattr(rc, "SYNC_META", tmp_path)
    monkeypatch.setattr(rc, "RECOVERY_LOG_PATH", recovery_log)
    monkeypatch.setattr(rc, "RECOVERY_LOG_ROTATE_AT", 5)
    monkeypatch.setattr(rc, "RECOVERY_LOG_RETAIN_EVENTS", 3)

    events = [
        rc.RecoveryEvent(timestamp=f"2026-04-04T00:00:0{i}Z", peer_id=f"peer-{i}", reason="resolved", resolved=True)
        for i in range(4)
    ]
    events.extend(
        [
            rc.RecoveryEvent(timestamp="2026-04-04T00:00:10Z", peer_id="peer-x", reason="keep-a", resolved=False),
            rc.RecoveryEvent(timestamp="2026-04-04T00:00:11Z", peer_id="peer-y", reason="keep-b", resolved=False),
        ]
    )

    rc._persist_recovery_log(events)

    payload = json.loads(recovery_log.read_text(encoding="utf-8"))
    assert len(payload) == 3
    unresolved_reasons = {entry["reason"] for entry in payload if entry["resolved"] is False}
    assert unresolved_reasons == {"keep-a", "keep-b"}
