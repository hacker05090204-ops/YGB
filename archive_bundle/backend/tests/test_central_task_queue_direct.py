import asyncio
import time

from backend.tasks.central_task_queue import FileBackedTaskQueue, TaskPriority, TaskState


def _run(coro):
    return asyncio.run(coro)


def test_queue_requeues_expired_lease_on_reload(tmp_path):
    queue_root = tmp_path / "queue"
    queue = FileBackedTaskQueue(str(queue_root))
    task = _run(
        queue.enqueue(
            "ingest_url",
            {"url": "https://example.com/report/1"},
            priority=TaskPriority.HIGH,
            route="grabber",
        )
    )

    leased = _run(queue.lease("worker-1", ["grabber"], lease_seconds=1))
    assert leased is not None
    _run(queue.heartbeat(task.task_id, "worker-1", lease_seconds=1))
    queue._tasks[task.task_id].state = TaskState.RUNNING.value
    queue._tasks[task.task_id].leased_until = time.time() - 5
    queue._persist_snapshot()

    reloaded = FileBackedTaskQueue(str(queue_root))
    restored = reloaded._tasks[task.task_id]

    assert restored.state == TaskState.QUEUED.value
    assert restored.worker_id == ""
    assert restored.leased_until == 0.0


def test_queue_allows_reenqueue_after_dead_letter(tmp_path):
    queue = FileBackedTaskQueue(str(tmp_path / "queue"))
    payload = {"url": "https://example.com/report/1"}
    first = _run(
        queue.enqueue(
            "ingest_url",
            payload,
            priority=TaskPriority.HIGH,
            route="grabber",
            max_attempts=1,
        )
    )

    leased = _run(queue.lease("worker-1", ["grabber"]))
    assert leased is not None
    finished = _run(queue.finish(first.task_id, "worker-1", ok=False, error="boom"))
    assert finished.state == TaskState.DEAD_LETTER.value

    second = _run(
        queue.enqueue(
            "ingest_url",
            payload,
            priority=TaskPriority.HIGH,
            route="grabber",
            max_attempts=1,
        )
    )

    assert second.task_id != first.task_id


def test_queue_requeues_until_max_attempts_then_dead_letters(tmp_path):
    queue = FileBackedTaskQueue(str(tmp_path / "queue"))
    task = _run(
        queue.enqueue(
            "ingest_url",
            {"url": "https://example.com/report/2"},
            route="grabber",
            max_attempts=2,
        )
    )

    first_lease = _run(queue.lease("worker-1", ["grabber"]))
    assert first_lease is not None
    first_finish = _run(queue.finish(task.task_id, "worker-1", ok=False, error="first"))
    assert first_finish.state == TaskState.QUEUED.value
    assert first_finish.attempts == 1
    assert first_finish.last_error == "first"

    second_lease = _run(queue.lease("worker-2", ["grabber"]))
    assert second_lease is not None
    second_finish = _run(queue.finish(task.task_id, "worker-2", ok=False, error="second"))
    assert second_finish.state == TaskState.DEAD_LETTER.value
    assert second_finish.attempts == 2
    assert second_finish.last_error == "second"


def test_queue_replays_log_when_snapshot_is_missing(tmp_path):
    queue_root = tmp_path / "queue"
    queue = FileBackedTaskQueue(str(queue_root))
    task = _run(
        queue.enqueue(
            "train_expert",
            {"expert": "idor"},
            route="trainer",
            priority=TaskPriority.NORMAL,
        )
    )

    queue.state_path.unlink()
    reloaded = FileBackedTaskQueue(str(queue_root))
    restored = reloaded.list_tasks()

    assert len(restored) == 1
    assert restored[0].task_id == task.task_id
    assert restored[0].payload == {"expert": "idor"}
    assert restored[0].route == "trainer"
    duplicate = _run(
        reloaded.enqueue(
            "train_expert",
            {"expert": "idor"},
            route="trainer",
            priority=TaskPriority.NORMAL,
        )
    )
    assert duplicate.task_id == task.task_id
