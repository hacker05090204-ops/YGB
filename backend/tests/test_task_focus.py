from backend.assistant.task_focus import TaskFocusManager


def test_start_objective_blocks_second_until_completion(tmp_path):
    manager = TaskFocusManager(state_path=tmp_path / "focus.json")

    first = manager.start_objective(
        title="Build the antigravity project",
        requested_by="user-1",
    )
    second = manager.start_objective(
        title="Start a different project",
        requested_by="user-1",
    )

    assert first["status"] == "ok"
    assert second["status"] == "blocked"
    assert "ACTIVE_OBJECTIVE_IN_PROGRESS" in second["message"]


def test_complete_then_start_next_objective(tmp_path):
    manager = TaskFocusManager(state_path=tmp_path / "focus.json")

    manager.start_objective(title="Finish current task", requested_by="user-1")
    complete = manager.complete_active_objective("Task finished")
    next_result = manager.start_objective(
        title="Next task",
        requested_by="user-1",
    )

    assert complete["status"] == "ok"
    assert next_result["status"] == "ok"
    assert next_result["objective"]["title"] == "Next task"


def test_append_step_records_grounded_history(tmp_path):
    manager = TaskFocusManager(state_path=tmp_path / "focus.json")
    manager.start_objective(title="Investigate issue", requested_by="user-1")

    result = manager.append_step(
        kind="QUERY_STATUS",
        summary="Runtime status collected from real backend",
        grounded=True,
        metadata={"source": "runtime"},
    )
    status = manager.status_snapshot()

    assert result["status"] == "ok"
    assert status["active_objective"]["steps"][-1]["grounded"] is True
    assert status["active_objective"]["steps"][-1]["metadata"]["source"] == "runtime"
