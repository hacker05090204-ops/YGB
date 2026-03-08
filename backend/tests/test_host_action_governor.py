from backend.governance.host_action_governor import HostActionGovernor


def test_issue_session_and_validate_app_launch(tmp_path, monkeypatch):
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "host-action-test-secret")
    ledger_path = tmp_path / "host_action_ledger.jsonl"

    monkeypatch.setattr(
        HostActionGovernor,
        "resolve_app_command",
        classmethod(lambda cls, app_name: [r"C:\Windows\System32\notepad.exe"]),
    )

    governor = HostActionGovernor(ledger_path=ledger_path)
    session = governor.issue_session(
        requested_by="user-1",
        approver_id="admin-1",
        reason="Allow controlled app launch",
        allowed_actions=["LAUNCH_APP"],
        allowed_apps=["notepad"],
    )

    decision = governor.validate_request(
        session.session_id,
        "LAUNCH_APP",
        {"app": "notepad", "host_session_id": session.session_id},
    )

    assert decision["allowed"] is True
    assert decision["canonical_app"] == "notepad"
    assert decision["command"][0].lower().endswith("notepad.exe")


def test_validate_request_rejects_expired_session(tmp_path, monkeypatch):
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "host-action-test-secret")
    ledger_path = tmp_path / "host_action_ledger.jsonl"

    governor = HostActionGovernor(ledger_path=ledger_path)
    session = governor.issue_session(
        requested_by="user-1",
        approver_id="admin-1",
        reason="Short-lived session",
        allowed_actions=["RUN_APPROVED_TASK"],
        allowed_tasks=["antigravity_harness"],
        expiration_window_s=60,
    )

    monkeypatch.setattr(
        "backend.governance.host_action_governor.time.time",
        lambda: session.expires_at + 1,
    )

    decision = governor.validate_request(
        session.session_id,
        "RUN_APPROVED_TASK",
        {"task": "antigravity_harness", "host_session_id": session.session_id},
    )

    assert decision["allowed"] is False
    assert decision["reason"] == "HOST_ACTION_SESSION_EXPIRED"


def test_task_launch_respects_allowed_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("YGB_APPROVAL_SECRET", "host-action-test-secret")
    ledger_path = tmp_path / "host_action_ledger.jsonl"

    governor = HostActionGovernor(ledger_path=ledger_path)
    session = governor.issue_session(
        requested_by="user-1",
        approver_id="admin-1",
        reason="Allow harness inside workspace",
        allowed_actions=["RUN_APPROVED_TASK"],
        allowed_tasks=["antigravity_harness"],
        allowed_roots=[str(tmp_path)],
    )

    denied = governor.validate_request(
        session.session_id,
        "RUN_APPROVED_TASK",
        {
            "task": "antigravity_harness",
            "path": r"C:\Windows\System32",
            "host_session_id": session.session_id,
        },
    )

    allowed = governor.validate_request(
        session.session_id,
        "RUN_APPROVED_TASK",
        {
            "task": "antigravity_harness",
            "path": str(tmp_path / "project"),
            "host_session_id": session.session_id,
        },
    )

    assert denied["allowed"] is False
    assert denied["reason"] == "HOST_ACTION_PATH_OUT_OF_SCOPE"
    assert allowed["allowed"] is True
