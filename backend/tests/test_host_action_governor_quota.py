import logging

from backend.governance import host_action_governor


def test_action_quota_tracker_returns_true_within_limit():
    tracker = host_action_governor.ActionQuotaTracker(
        default_limits={"OPEN_URL": 2},
        time_func=lambda: 1000.0,
    )

    assert tracker.track("OPEN_URL") is True
    assert tracker.track("OPEN_URL") is True

    status = tracker.get_quota_status("OPEN_URL")
    assert status.used == 2
    assert status.limit == 2


def test_action_quota_tracker_returns_false_when_limit_exceeded():
    tracker = host_action_governor.ActionQuotaTracker(
        default_limits={"OPEN_URL": 1},
        time_func=lambda: 1000.0,
    )

    assert tracker.track("OPEN_URL") is True
    assert tracker.track("OPEN_URL") is False


def test_host_action_governor_logs_warning_when_quota_is_exceeded(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "b" * 64)
    monkeypatch.setattr(
        host_action_governor,
        "_quota_tracker",
        host_action_governor.ActionQuotaTracker(default_limits={"LAUNCH_APP": 1}, time_func=lambda: 1000.0),
    )
    monkeypatch.setattr(
        host_action_governor.HostActionGovernor,
        "resolve_app_command",
        classmethod(lambda cls, app_name: [r"C:\Windows\System32\notepad.exe"]),
    )

    governor = host_action_governor.HostActionGovernor(ledger_path=tmp_path / "host_action_ledger.jsonl")
    session = governor.issue_session(
        requested_by="user-1",
        approver_id="admin-1",
        reason="quota test",
        allowed_actions=["LAUNCH_APP"],
        allowed_apps=["notepad"],
    )

    first = governor.validate_request(session.session_id, "LAUNCH_APP", {"app": "notepad"})
    with caplog.at_level(logging.WARNING):
        second = governor.validate_request(session.session_id, "LAUNCH_APP", {"app": "notepad"})

    assert first["allowed"] is True
    assert second["allowed"] is False
    assert second["reason"] == "HOST_ACTION_QUOTA_EXCEEDED"
    assert any("quota exceeded" in record.message.lower() for record in caplog.records)


def test_action_quota_tracker_resets_after_24_hours():
    current_time = [1000.0]
    tracker = host_action_governor.ActionQuotaTracker(
        default_limits={"OPEN_URL": 1},
        time_func=lambda: current_time[0],
    )

    assert tracker.track("OPEN_URL") is True
    assert tracker.track("OPEN_URL") is False

    current_time[0] += 24 * 60 * 60 + 1
    assert tracker.track("OPEN_URL") is True
