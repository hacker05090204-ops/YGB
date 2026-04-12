from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Sequence


_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on"})
_TEST_ONLY_PATH_ENV = "YGB_ENABLE_TEST_ONLY_PATHS"


def _test_only_paths_enabled() -> bool:
    if "pytest" in sys.modules:
        return True
    return os.environ.get(_TEST_ONLY_PATH_ENV, "").strip().lower() in _TRUTHY_VALUES


def _ensure_test_only_path_allowed(path_name: str) -> None:
    if _test_only_paths_enabled():
        return
    raise RuntimeError(f"{path_name} is disabled outside test-only execution")


def _normalize_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize_json(item) for item in value]
    if isinstance(value, set):
        return sorted(_normalize_json(item) for item in value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return repr(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(_normalize_json(payload), handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def _append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(_normalize_json(payload), sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


class TaskPriority(IntEnum):
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


class TaskState(str, Enum):
    QUEUED = "QUEUED"
    LEASED = "LEASED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEAD_LETTER = "DEAD_LETTER"


@dataclass
class TaskRecord:
    task_id: str
    kind: str
    payload: Dict[str, Any]
    priority: int = int(TaskPriority.NORMAL)
    state: str = TaskState.QUEUED.value
    dedup_key: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    leased_until: float = 0.0
    attempts: int = 0
    max_attempts: int = 5
    route: str = "default"
    worker_id: str = ""
    last_error: str = ""
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex)


Handler = Callable[[TaskRecord], Awaitable[None]]


class FileBackedTaskQueue:
    """Durable file-backed queue with dedup, leasing, and retry support."""

    def __init__(self, root: str = "secure_data/task_queue"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.log_path = self.root / "events.jsonl"
        self.state_path = self.root / "state.json"
        self._lock = asyncio.Lock()
        self._tasks: Dict[str, TaskRecord] = {}
        self._dedup: Dict[str, str] = {}
        self._load_state()
        self._requeue_expired_leases(now=time.time())

    def _load_state(self) -> None:
        payload: Dict[str, Any] = {}
        if self.state_path.exists():
            try:
                payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {}
        elif self.log_path.exists():
            payload = self._replay_log()
        for item in payload.get("tasks", []):
            record = TaskRecord(**item)
            self._tasks[record.task_id] = record
        self._rebuild_dedup()

    def _replay_log(self) -> Dict[str, Any]:
        latest: Dict[str, TaskRecord] = {}
        with open(self.log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                snapshot = {key: value for key, value in payload.items() if key != "event"}
                if not snapshot.get("task_id"):
                    continue
                latest[str(snapshot["task_id"])] = TaskRecord(**snapshot)
        return {"tasks": [asdict(task) for task in latest.values()]}

    def _rebuild_dedup(self) -> None:
        self._dedup = {}
        for task in self._tasks.values():
            if task.dedup_key and task.state != TaskState.DEAD_LETTER.value:
                self._dedup[task.dedup_key] = task.task_id

    def _persist_event(self, event: str, task: TaskRecord) -> None:
        _append_jsonl(self.log_path, {"event": event, **asdict(task)})

    def _persist_snapshot(self) -> None:
        _atomic_write_json(
            self.state_path,
            {"tasks": [asdict(task) for task in self._tasks.values()]},
        )

    def _requeue_expired_leases(self, *, now: float) -> None:
        changed = False
        for task in self._tasks.values():
            if task.state not in {TaskState.LEASED.value, TaskState.RUNNING.value}:
                continue
            if task.leased_until > now:
                continue
            task.state = TaskState.QUEUED.value
            task.worker_id = ""
            task.leased_until = 0.0
            task.updated_at = now
            changed = True
        if changed:
            self._persist_snapshot()

    @staticmethod
    def build_dedup_key(kind: str, payload: Dict[str, Any]) -> str:
        canonical = json.dumps(
            {"kind": kind, "payload": _normalize_json(payload)},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def list_tasks(
        self,
        *,
        states: Optional[Iterable[str]] = None,
        route: Optional[str] = None,
    ) -> List[TaskRecord]:
        state_filter = set(states or [])
        selected: List[TaskRecord] = []
        for task in self._tasks.values():
            if state_filter and task.state not in state_filter:
                continue
            if route is not None and task.route != route:
                continue
            selected.append(task)
        selected.sort(key=lambda item: (item.priority, item.created_at, item.task_id))
        return selected

    async def enqueue(
        self,
        kind: str,
        payload: Dict[str, Any],
        *,
        priority: TaskPriority = TaskPriority.NORMAL,
        route: str = "default",
        max_attempts: int = 5,
        dedup_key: Optional[str] = None,
    ) -> TaskRecord:
        async with self._lock:
            normalized_kind = str(kind or "").strip().lower()
            if normalized_kind.startswith("demo_"):
                _ensure_test_only_path_allowed(f"task kind '{kind}'")
            dedup_key = dedup_key or self.build_dedup_key(kind, payload)
            existing_id = self._dedup.get(dedup_key)
            existing = self._tasks.get(existing_id or "")
            if existing is not None and existing.state != TaskState.DEAD_LETTER.value:
                return existing

            task = TaskRecord(
                task_id=f"tsk_{uuid.uuid4().hex}",
                kind=kind,
                payload=dict(payload),
                priority=int(priority),
                dedup_key=dedup_key,
                max_attempts=max(1, int(max_attempts)),
                route=str(route or "default"),
            )
            self._tasks[task.task_id] = task
            self._dedup[dedup_key] = task.task_id
            self._persist_event("enqueue", task)
            self._persist_snapshot()
            return task

    async def lease(
        self,
        worker_id: str,
        routes: Sequence[str],
        *,
        lease_seconds: int = 60,
    ) -> Optional[TaskRecord]:
        async with self._lock:
            now = time.time()
            self._requeue_expired_leases(now=now)
            route_set = set(routes)
            for task in self.list_tasks(states=(TaskState.QUEUED.value, TaskState.LEASED.value)):
                if task.route not in route_set:
                    continue
                if task.state == TaskState.LEASED.value and task.leased_until > now:
                    continue
                task.state = TaskState.LEASED.value
                task.worker_id = worker_id
                task.leased_until = now + max(1, int(lease_seconds))
                task.updated_at = now
                self._persist_event("lease", task)
                self._persist_snapshot()
                return TaskRecord(**asdict(task))
        return None

    async def heartbeat(
        self,
        task_id: str,
        worker_id: str,
        *,
        lease_seconds: int = 60,
    ) -> TaskRecord:
        async with self._lock:
            task = self._tasks[task_id]
            if task.worker_id != worker_id:
                raise RuntimeError("lease owner mismatch")
            task.state = TaskState.RUNNING.value
            task.leased_until = time.time() + max(1, int(lease_seconds))
            task.updated_at = time.time()
            self._persist_event("heartbeat", task)
            self._persist_snapshot()
            return TaskRecord(**asdict(task))

    async def finish(
        self,
        task_id: str,
        worker_id: str,
        *,
        ok: bool,
        error: str = "",
    ) -> TaskRecord:
        async with self._lock:
            task = self._tasks[task_id]
            if task.worker_id != worker_id:
                raise RuntimeError("finish owner mismatch")
            task.updated_at = time.time()
            task.leased_until = 0.0
            task.worker_id = ""
            if ok:
                task.state = TaskState.SUCCEEDED.value
                task.last_error = ""
            else:
                task.attempts += 1
                task.last_error = str(error)[:4000]
                task.state = (
                    TaskState.DEAD_LETTER.value
                    if task.attempts >= task.max_attempts
                    else TaskState.QUEUED.value
                )
            self._persist_event("finish", task)
            self._persist_snapshot()
            return TaskRecord(**asdict(task))


class TaskAgent:
    def __init__(
        self,
        queue: FileBackedTaskQueue,
        worker_id: str,
        routes: set[str],
        handlers: Dict[str, Handler],
    ):
        self.queue = queue
        self.worker_id = worker_id
        self.routes = set(routes)
        self.handlers = dict(handlers)

    async def run_once(self) -> bool:
        task = await self.queue.lease(self.worker_id, sorted(self.routes))
        if task is None:
            return False
        try:
            await self.queue.heartbeat(task.task_id, self.worker_id)
            handler = self.handlers[task.kind]
            await handler(task)
            await self.queue.finish(task.task_id, self.worker_id, ok=True)
        except Exception as exc:
            await self.queue.finish(task.task_id, self.worker_id, ok=False, error=repr(exc))
        return True

    async def run_forever(self, *, poll_seconds: float = 0.5) -> None:
        while True:
            handled = await self.run_once()
            if not handled:
                await asyncio.sleep(poll_seconds)


async def main() -> None:
    _ensure_test_only_path_allowed("central_task_queue.main()")

    async def _test_only_demo_task_handler(task: TaskRecord) -> None:
        _ensure_test_only_path_allowed("central task queue demo handler")
        await asyncio.sleep(0.01)

    queue = FileBackedTaskQueue()
    await queue.enqueue(
        "demo_ingest",
        {"url": "https://example.com/report/1"},
        priority=TaskPriority.HIGH,
        route="grabber",
    )
    agent = TaskAgent(
        queue,
        "demo-agent",
        {"grabber"},
        {"demo_ingest": _test_only_demo_task_handler},
    )
    while await agent.run_once():
        pass


if __name__ == "__main__":
    asyncio.run(main())
