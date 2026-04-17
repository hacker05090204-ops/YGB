from __future__ import annotations

import argparse
import errno
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from impl_v1.phase49.moe import EXPERT_FIELDS

STATUS_AVAILABLE = "AVAILABLE"
STATUS_CLAIMED = "CLAIMED"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"

DEFAULT_CLAIM_TIMEOUT_SECONDS = 3600.0
CLAIM_TIMEOUT_SECONDS = DEFAULT_CLAIM_TIMEOUT_SECONDS
STATUS_PATH_ENV_VAR = "YGB_EXPERT_STATUS_PATH"
DEFAULT_STATUS_PATH = (PROJECT_ROOT / "experts_status.json").resolve()
_ALLOWED_STATUSES = {
    STATUS_AVAILABLE,
    STATUS_CLAIMED,
    STATUS_COMPLETED,
    STATUS_FAILED,
}

logger = logging.getLogger(__name__)


class QueueStatus(dict):
    """Mapping-compatible queue status whose [`len()`](scripts/expert_task_queue.py:38) reflects expert count."""

    def __len__(self) -> int:
        experts = self.get("experts")
        if isinstance(experts, list):
            return len(experts)
        return super().__len__()


def _is_lock_contention_error(exc: OSError) -> bool:
    err_no = getattr(exc, "errno", None)
    win_error = getattr(exc, "winerror", None)
    return bool(
        err_no in {errno.EACCES, errno.EAGAIN}
        or win_error in {33}  # ERROR_LOCK_VIOLATION
    )


def _resolve_status_path(status_path: Path | str) -> Path:
    return Path(status_path).resolve()


def _configure_logging(*, verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.WARNING,
        format="%(message)s",
    )


class ExpertTaskQueue:
    """Object-oriented wrapper for the expert task queue state file."""

    def __init__(
        self,
        status_path: Path | str = DEFAULT_STATUS_PATH,
        *,
        claim_timeout_seconds: float = DEFAULT_CLAIM_TIMEOUT_SECONDS,
    ) -> None:
        self.status_path = _resolve_status_path(status_path)
        self.claim_timeout_seconds = float(claim_timeout_seconds)

    def initialize_status_file(self) -> Dict[str, Any]:
        return initialize_status_file(self.status_path)

    def load_status(self) -> Dict[str, Any]:
        return load_status(self.status_path)

    def get_status(self) -> Dict[str, Any]:
        return QueueStatus(self.load_status())

    def render_status(self) -> str:
        return render_status(self.status_path)

    def print_status(self) -> str:
        return print_status(self.status_path)

    def claim_next_expert(
        self,
        worker_id: str,
        *,
        claim_timeout_seconds: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        timeout_seconds = (
            self.claim_timeout_seconds
            if claim_timeout_seconds is None
            else float(claim_timeout_seconds)
        )
        return claim_next_expert(
            worker_id,
            status_path=self.status_path,
            claim_timeout_seconds=timeout_seconds,
        )

    def release_expert(
        self,
        expert_id: int,
        *,
        worker_id: Optional[str] = None,
        status: str,
        val_f1: Optional[float] = None,
        val_precision: Optional[float] = None,
        val_recall: Optional[float] = None,
        checkpoint_path: str = "",
        error: str = "",
    ) -> Dict[str, Any]:
        return release_expert(
            expert_id,
            status_path=self.status_path,
            worker_id=worker_id,
            status=status,
            val_f1=val_f1,
            val_precision=val_precision,
            val_recall=val_recall,
            checkpoint_path=checkpoint_path,
            error=error,
        )


class _FileLock:
    """Cross-platform advisory lock using [msvcrt.locking()](msvcrt:1) on Windows and [fcntl.flock()](fcntl:1) elsewhere."""

    def __init__(
        self,
        lock_path: Path,
        *,
        timeout_seconds: float = 30.0,
        poll_interval: float = 0.05,
    ) -> None:
        self.lock_path = lock_path
        self.timeout_seconds = float(timeout_seconds)
        self.poll_interval = float(poll_interval)
        self._handle = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.lock_path, "a+b")
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() == 0:
            self._handle.write(b"0")
            self._handle.flush()
            os.fsync(self._handle.fileno())
        self._handle.seek(0)

        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out acquiring queue lock: {self.lock_path}")
                time.sleep(self.poll_interval)
                self._handle.seek(0)
            except OSError as exc:
                if not _is_lock_contention_error(exc):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out acquiring queue lock: {self.lock_path}")
                time.sleep(self.poll_interval)
                self._handle.seek(0)

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is None:
            return
        try:
            self._handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _lock_path_for(status_path: Path) -> Path:
    return status_path.with_suffix(status_path.suffix + ".lock")


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(temp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def _default_expert_record(expert_id: int, field_name: str) -> Dict[str, Any]:
    return {
        "expert_id": int(expert_id),
        "field_name": field_name,
        "status": STATUS_AVAILABLE,
        "claimed_by": None,
        "claimed_at": None,
        "claim_expires_at_epoch": None,
        "val_f1": None,
        "val_precision": None,
        "val_recall": None,
        "checkpoint_path": "",
        "best_val_f1": None,
        "best_val_precision": None,
        "best_val_recall": None,
        "best_checkpoint_path": "",
        "last_val_f1": None,
        "last_val_precision": None,
        "last_val_recall": None,
        "last_checkpoint_path": "",
        "last_result_status": None,
        "last_error": "",
        "last_released_at": None,
        "claim_count": 0,
        "completed_count": 0,
        "failed_count": 0,
    }


def _default_state() -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "updated_at": "",
        "experts": [
            _default_expert_record(expert_id, field_name)
            for expert_id, field_name in enumerate(EXPERT_FIELDS)
        ],
    }


def _normalize_state(state: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(state, dict):
        state = {}

    existing_records = state.get("experts") if isinstance(state.get("experts"), list) else []
    by_id = {
        int(record.get("expert_id")): record
        for record in existing_records
        if isinstance(record, dict) and str(record.get("expert_id", "")).isdigit()
    }
    by_name = {
        str(record.get("field_name", "")): record
        for record in existing_records
        if isinstance(record, dict) and record.get("field_name")
    }

    experts = []
    for expert_id, field_name in enumerate(EXPERT_FIELDS):
        record = _default_expert_record(expert_id, field_name)
        existing = by_id.get(expert_id) or by_name.get(field_name) or {}
        if isinstance(existing, dict):
            for key, value in existing.items():
                if key in record:
                    record[key] = value
        record["expert_id"] = int(expert_id)
        record["field_name"] = field_name
        status_text = str(record.get("status", STATUS_AVAILABLE) or STATUS_AVAILABLE).upper()
        if status_text not in _ALLOWED_STATUSES:
            status_text = STATUS_AVAILABLE
        record["status"] = status_text
        experts.append(record)

    return {
        "schema_version": 1,
        "updated_at": str(state.get("updated_at", "") or ""),
        "experts": experts,
    }


def _load_state_unlocked(status_path: Path) -> Dict[str, Any]:
    if not status_path.exists():
        state = _default_state()
        _atomic_write_json(status_path, state)
        return state

    with open(status_path, "r", encoding="utf-8") as handle:
        state = json.load(handle)
    normalized = _normalize_state(state)
    if normalized != state:
        _atomic_write_json(status_path, normalized)
    return normalized


def _save_state_unlocked(status_path: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_state(state)
    normalized["updated_at"] = _utc_now_iso()
    _atomic_write_json(status_path, normalized)
    return normalized


def _release_expired_claims_unlocked(state: Dict[str, Any], now_epoch: float) -> bool:
    changed = False
    for record in state.get("experts", []):
        if str(record.get("status", "")).upper() != STATUS_CLAIMED:
            continue
        expires_at = record.get("claim_expires_at_epoch")
        if expires_at is None:
            continue
        try:
            expired = float(expires_at) <= float(now_epoch)
        except (TypeError, ValueError):
            expired = True
        if not expired:
            continue
        record["status"] = STATUS_AVAILABLE
        record["claimed_by"] = None
        record["claimed_at"] = None
        record["claim_expires_at_epoch"] = None
        record["last_result_status"] = STATUS_FAILED
        record["last_error"] = "claim_expired"
        record["last_released_at"] = _utc_now_iso()
        record["failed_count"] = int(record.get("failed_count", 0) or 0) + 1
        changed = True
    return changed


def _claim_priority(record: Dict[str, Any]) -> tuple[int, int]:
    status_text = str(record.get("status", STATUS_AVAILABLE) or STATUS_AVAILABLE).upper()
    priority = 0 if status_text == STATUS_FAILED else 1 if status_text == STATUS_AVAILABLE else 2
    return priority, int(record.get("expert_id", 0) or 0)


def _to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not (numeric == numeric):
        return None
    return numeric


def initialize_status_file(status_path: Path | str = DEFAULT_STATUS_PATH) -> Dict[str, Any]:
    resolved = _resolve_status_path(status_path)
    with _FileLock(_lock_path_for(resolved)):
        state = _load_state_unlocked(resolved)
        return _save_state_unlocked(resolved, state)


def load_status(status_path: Path | str = DEFAULT_STATUS_PATH) -> Dict[str, Any]:
    resolved = _resolve_status_path(status_path)
    with _FileLock(_lock_path_for(resolved)):
        state = _load_state_unlocked(resolved)
        if _release_expired_claims_unlocked(state, time.time()):
            state = _save_state_unlocked(resolved, state)
        return state


def claim_next_expert(
    worker_id: str,
    *,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    claim_timeout_seconds: float = DEFAULT_CLAIM_TIMEOUT_SECONDS,
) -> Optional[Dict[str, Any]]:
    worker_text = str(worker_id or "").strip()
    if not worker_text:
        raise ValueError("worker_id is required")

    resolved = _resolve_status_path(status_path)
    timeout_seconds = max(1e-6, float(claim_timeout_seconds))
    with _FileLock(_lock_path_for(resolved)):
        state = _load_state_unlocked(resolved)
        changed = _release_expired_claims_unlocked(state, time.time())

        candidates = [
            record
            for record in state.get("experts", [])
            if str(record.get("status", "")).upper() in {STATUS_FAILED, STATUS_AVAILABLE}
        ]
        candidates.sort(key=_claim_priority)
        if not candidates:
            if changed:
                _save_state_unlocked(resolved, state)
            return None

        selected = candidates[0]
        selected["status"] = STATUS_CLAIMED
        selected["claimed_by"] = worker_text
        selected["claimed_at"] = _utc_now_iso()
        selected["claim_expires_at_epoch"] = time.time() + timeout_seconds
        selected["last_error"] = ""
        selected["claim_count"] = int(selected.get("claim_count", 0) or 0) + 1
        state = _save_state_unlocked(resolved, state)
        return next(
            dict(record)
            for record in state["experts"]
            if int(record["expert_id"]) == int(selected["expert_id"])
        )


def release_expert(
    expert_id: int,
    *,
    status_path: Path | str = DEFAULT_STATUS_PATH,
    worker_id: Optional[str] = None,
    status: str,
    val_f1: Optional[float] = None,
    val_precision: Optional[float] = None,
    val_recall: Optional[float] = None,
    checkpoint_path: str = "",
    error: str = "",
) -> Dict[str, Any]:
    status_text = str(status or "").upper().strip()
    if status_text not in {STATUS_AVAILABLE, STATUS_COMPLETED, STATUS_FAILED}:
        raise ValueError(f"Unsupported release status: {status}")

    resolved = _resolve_status_path(status_path)
    with _FileLock(_lock_path_for(resolved)):
        state = _load_state_unlocked(resolved)
        _release_expired_claims_unlocked(state, time.time())

        record = next(
            (
                item
                for item in state.get("experts", [])
                if int(item.get("expert_id", -1)) == int(expert_id)
            ),
            None,
        )
        if record is None:
            raise KeyError(f"Unknown expert_id={expert_id}")

        status_value = str(record.get("status", "") or "").upper()
        claimed_by = str(record.get("claimed_by") or "").strip()
        if worker_id is not None:
            worker_text = str(worker_id).strip()
            if not worker_text:
                raise ValueError("worker_id must be non-empty when provided")
            if status_value != STATUS_CLAIMED:
                raise RuntimeError(
                    f"expert_id={expert_id} is not actively claimed; current status={status_value or STATUS_AVAILABLE}"
                )
            if claimed_by != worker_text:
                raise RuntimeError(
                    f"expert_id={expert_id} is claimed by {claimed_by or '-'}, not {worker_text}"
                )

        val_f1_value = _to_float(val_f1)
        val_precision_value = _to_float(val_precision)
        val_recall_value = _to_float(val_recall)

        if val_f1_value is not None:
            record["last_val_f1"] = val_f1_value
        if val_precision_value is not None:
            record["last_val_precision"] = val_precision_value
        if val_recall_value is not None:
            record["last_val_recall"] = val_recall_value
        if checkpoint_path:
            record["last_checkpoint_path"] = str(checkpoint_path)

        best_val_f1 = _to_float(record.get("best_val_f1"))
        improved = bool(
            val_f1_value is not None
            and (best_val_f1 is None or val_f1_value > best_val_f1)
        )
        if improved:
            record["val_f1"] = val_f1_value
            if val_precision_value is not None:
                record["val_precision"] = val_precision_value
            if val_recall_value is not None:
                record["val_recall"] = val_recall_value
            if checkpoint_path:
                record["checkpoint_path"] = str(checkpoint_path)
            record["best_val_f1"] = val_f1_value
            if val_precision_value is not None:
                record["best_val_precision"] = val_precision_value
            if val_recall_value is not None:
                record["best_val_recall"] = val_recall_value
            if checkpoint_path:
                record["best_checkpoint_path"] = str(checkpoint_path)

        record["status"] = status_text
        record["claimed_by"] = None
        record["claimed_at"] = None
        record["claim_expires_at_epoch"] = None
        record["last_result_status"] = status_text
        record["last_error"] = str(error or "")
        record["last_released_at"] = _utc_now_iso()
        if status_text == STATUS_COMPLETED:
            record["completed_count"] = int(record.get("completed_count", 0) or 0) + 1
        elif status_text == STATUS_FAILED:
            record["failed_count"] = int(record.get("failed_count", 0) or 0) + 1

        state = _save_state_unlocked(resolved, state)
        return next(
            dict(item)
            for item in state["experts"]
            if int(item["expert_id"]) == int(expert_id)
        )


def render_status(status_path: Path | str = DEFAULT_STATUS_PATH) -> str:
    state = load_status(status_path)
    experts = state.get("experts", [])
    claimed_count = sum(1 for item in experts if item.get("status") == STATUS_CLAIMED)
    failed_count = sum(1 for item in experts if item.get("status") == STATUS_FAILED)
    completed_count = sum(1 for item in experts if item.get("status") == STATUS_COMPLETED)
    available_count = sum(1 for item in experts if item.get("status") == STATUS_AVAILABLE)
    lines = [
        f"updated_at={state.get('updated_at', '')}",
        (
            f"summary: available={available_count} | claimed={claimed_count} | "
            f"failed={failed_count} | completed={completed_count}"
        ),
    ]
    for item in experts:
        best_val_f1 = item.get("val_f1")
        if best_val_f1 is None:
            best_val_f1 = item.get("best_val_f1")
        best_text = "-" if best_val_f1 is None else f"{float(best_val_f1):.3f}"
        lines.append(
            (
                f"[{int(item['expert_id']):02d}] {item['field_name']}: "
                f"status={item['status']} | claimed_by={item.get('claimed_by') or '-'} | "
                f"best_val_f1={best_text}"
            )
        )
    return "\n".join(lines)


def print_status(status_path: Path | str = DEFAULT_STATUS_PATH) -> str:
    report = render_status(status_path)
    print(report)
    return report


def _default_status_path_text() -> str:
    return os.getenv(STATUS_PATH_ENV_VAR, str(DEFAULT_STATUS_PATH))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Expert task queue management")
    parser.add_argument(
        "--status-path",
        default=_default_status_path_text(),
        help="Path to experts status JSON",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize the queue state file")
    subparsers.add_parser("status", help="Print queue status")

    claim_parser = subparsers.add_parser("claim", help="Claim the next expert")
    claim_parser.add_argument("--worker-id", required=True)
    claim_parser.add_argument(
        "--claim-timeout-seconds",
        type=float,
        default=DEFAULT_CLAIM_TIMEOUT_SECONDS,
    )

    release_parser = subparsers.add_parser("release", help="Release an expert claim")
    release_parser.add_argument("--expert-id", required=True, type=int)
    release_parser.add_argument("--worker-id")
    release_parser.add_argument(
        "--status",
        required=True,
        choices=[STATUS_AVAILABLE, STATUS_COMPLETED, STATUS_FAILED],
    )
    release_parser.add_argument("--val-f1", type=float)
    release_parser.add_argument("--val-precision", type=float)
    release_parser.add_argument("--val-recall", type=float)
    release_parser.add_argument("--checkpoint-path", default="")
    release_parser.add_argument("--error", default="")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_logging(verbose=bool(args.verbose))
    status_path = _resolve_status_path(args.status_path)

    if args.command == "init":
        result = initialize_status_file(status_path)
        logger.debug("Initialized expert task queue at %s", status_path)
    elif args.command in {None, "status"}:
        print_status(status_path)
        return 0
    elif args.command == "claim":
        result = claim_next_expert(
            args.worker_id,
            status_path=status_path,
            claim_timeout_seconds=args.claim_timeout_seconds,
        )
        logger.debug("Claimed next expert for worker_id=%s from %s", args.worker_id, status_path)
    elif args.command == "release":
        result = release_expert(
            args.expert_id,
            status_path=status_path,
            worker_id=args.worker_id,
            status=args.status,
            val_f1=args.val_f1,
            val_precision=args.val_precision,
            val_recall=args.val_recall,
            checkpoint_path=args.checkpoint_path,
            error=args.error,
        )
        logger.debug(
            "Released expert_id=%s with status=%s into %s",
            args.expert_id,
            args.status,
            status_path,
        )
    else:
        raise RuntimeError(f"Unsupported command: {args.command}")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
