import json


def test_mark_resolved_persists_resolved_status(monkeypatch, tmp_path):
    from backend.sync import recovery as rc

    recovery_log = tmp_path / "recovery_log.json"
    monkeypatch.setattr(rc, "SYNC_META", tmp_path)
    monkeypatch.setattr(rc, "RECOVERY_LOG_PATH", recovery_log)

    rc._append_recovery_event("peer-a", "no_online_peers", resolved=False)
    rc._append_recovery_event("gdrive", "cloud_recovery_failed", resolved=False)

    pending = rc.get_pending_recovery_events()
    assert len(pending) == 2

    target_event = next(event for event in pending if event.peer_id == "peer-a")
    assert rc.mark_resolved(target_event.event_id) is True

    payload = json.loads(recovery_log.read_text(encoding="utf-8"))
    resolved_entry = next(entry for entry in payload if entry["event_id"] == target_event.event_id)
    assert resolved_entry["status"] == "RESOLVED"


def test_get_pending_recovery_events_excludes_resolved_events(monkeypatch, tmp_path):
    from backend.sync import recovery as rc

    recovery_log = tmp_path / "recovery_log.json"
    monkeypatch.setattr(rc, "SYNC_META", tmp_path)
    monkeypatch.setattr(rc, "RECOVERY_LOG_PATH", recovery_log)

    rc._append_recovery_event("peer-a", "no_online_peers", resolved=False)
    rc._append_recovery_event("gdrive", "cloud_recovery_failed", resolved=False)

    first_event = rc.get_pending_recovery_events()[0]
    assert rc.mark_resolved(first_event.event_id) is True

    pending_after = rc.get_pending_recovery_events()
    assert len(pending_after) == 1
    assert all(event.status == "PENDING" for event in pending_after)
    assert pending_after[0].peer_id == "gdrive"
    assert rc.get_unresolved_events()[0].event_id == pending_after[0].event_id


def test_recovery_log_rotation_keeps_unresolved_events(monkeypatch, tmp_path):
    from backend.sync import recovery as rc

    recovery_log = tmp_path / "recovery_log.json"
    monkeypatch.setattr(rc, "SYNC_META", tmp_path)
    monkeypatch.setattr(rc, "RECOVERY_LOG_PATH", recovery_log)
    monkeypatch.setattr(rc, "RECOVERY_LOG_ROTATE_AT", 5)
    monkeypatch.setattr(rc, "RECOVERY_LOG_RETAIN_EVENTS", 3)

    events = [
        rc.RecoveryEvent(
            event_id=f"peer-{i}:resolved:2026-04-04T00:00:0{i}Z",
            timestamp=f"2026-04-04T00:00:0{i}Z",
            peer_id=f"peer-{i}",
            reason="resolved",
            status="RESOLVED",
        )
        for i in range(4)
    ]
    events.extend(
        [
            rc.RecoveryEvent(
                event_id="peer-x:keep-a:2026-04-04T00:00:10Z",
                timestamp="2026-04-04T00:00:10Z",
                peer_id="peer-x",
                reason="keep-a",
                status="PENDING",
            ),
            rc.RecoveryEvent(
                event_id="peer-y:keep-b:2026-04-04T00:00:11Z",
                timestamp="2026-04-04T00:00:11Z",
                peer_id="peer-y",
                reason="keep-b",
                status="PENDING",
            ),
        ]
    )

    rc._persist_recovery_log(events)

    payload = json.loads(recovery_log.read_text(encoding="utf-8"))
    assert len(payload) == 3
    pending_reasons = {entry["reason"] for entry in payload if entry["status"] == "PENDING"}
    assert pending_reasons == {"keep-a", "keep-b"}
