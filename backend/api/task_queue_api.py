from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.auth.auth_guard import require_auth
from scripts.expert_task_queue import (
    DEFAULT_CLAIM_TIMEOUT_SECONDS,
    DEFAULT_STATUS_PATH,
    STATUS_PATH_ENV_VAR,
    ExpertTaskQueue,
)

router = APIRouter(prefix="/api/v1/tasks", tags=["task-queue"])


class ClaimRequest(BaseModel):
    worker_id: str
    claim_timeout_seconds: float = Field(
        default=DEFAULT_CLAIM_TIMEOUT_SECONDS,
        gt=0,
    )


class HeartbeatRequest(BaseModel):
    expert_id: int
    worker_id: str
    claim_timeout_seconds: float = Field(
        default=DEFAULT_CLAIM_TIMEOUT_SECONDS,
        gt=0,
    )


class ReleaseRequest(BaseModel):
    expert_id: int
    worker_id: str | None = None
    status: str
    val_f1: float | None = None
    val_precision: float | None = None
    val_recall: float | None = None
    checkpoint_path: str = ""
    error: str = ""


def _status_path() -> str:
    return os.getenv(STATUS_PATH_ENV_VAR, str(DEFAULT_STATUS_PATH))


def get_task_queue() -> ExpertTaskQueue:
    return ExpertTaskQueue(status_path=_status_path())


def _build_summary(state: Dict[str, Any]) -> Dict[str, int]:
    experts = state.get("experts", [])
    return {
        "available": sum(1 for item in experts if item.get("status") == "AVAILABLE"),
        "claimed": sum(1 for item in experts if item.get("status") == "CLAIMED"),
        "completed": sum(1 for item in experts if item.get("status") == "COMPLETED"),
        "failed": sum(1 for item in experts if item.get("status") == "FAILED"),
        "total": len(experts),
    }


def _queue_status_payload(queue: ExpertTaskQueue) -> Dict[str, Any]:
    state = dict(queue.get_status())
    return {
        "updated_at": state.get("updated_at", ""),
        "summary": _build_summary(state),
        "experts": state.get("experts", []),
    }


def _translate_queue_exception(exc: Exception) -> HTTPException:
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, KeyError):
        message = exc.args[0] if exc.args else str(exc)
        return HTTPException(status_code=404, detail=str(message))
    if isinstance(exc, RuntimeError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, TimeoutError):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


@router.post("/claim")
def claim_task(
    request: ClaimRequest,
    _user=Depends(require_auth),
    queue: ExpertTaskQueue = Depends(get_task_queue),
) -> Dict[str, Any]:
    try:
        task = queue.claim_next_expert(
            request.worker_id,
            claim_timeout_seconds=request.claim_timeout_seconds,
        )
    except Exception as exc:
        raise _translate_queue_exception(exc) from exc

    payload = _queue_status_payload(queue)
    return {
        "status": "ok",
        "claimed": task is not None,
        "task": task,
        **payload,
    }


@router.post("/heartbeat")
def heartbeat_task(
    request: HeartbeatRequest,
    _user=Depends(require_auth),
    queue: ExpertTaskQueue = Depends(get_task_queue),
) -> Dict[str, Any]:
    try:
        task = queue.heartbeat_expert(
            request.expert_id,
            worker_id=request.worker_id,
            claim_timeout_seconds=request.claim_timeout_seconds,
        )
    except Exception as exc:
        raise _translate_queue_exception(exc) from exc

    payload = _queue_status_payload(queue)
    return {
        "status": "ok",
        "task": task,
        **payload,
    }


@router.post("/release")
def release_task(
    request: ReleaseRequest,
    _user=Depends(require_auth),
    queue: ExpertTaskQueue = Depends(get_task_queue),
) -> Dict[str, Any]:
    try:
        task = queue.release_expert(
            request.expert_id,
            worker_id=request.worker_id,
            status=request.status,
            val_f1=request.val_f1,
            val_precision=request.val_precision,
            val_recall=request.val_recall,
            checkpoint_path=request.checkpoint_path,
            error=request.error,
        )
    except Exception as exc:
        raise _translate_queue_exception(exc) from exc

    payload = _queue_status_payload(queue)
    return {
        "status": "ok",
        "task": task,
        **payload,
    }


@router.get("/status")
def task_queue_status(
    _user=Depends(require_auth),
    queue: ExpertTaskQueue = Depends(get_task_queue),
) -> Dict[str, Any]:
    return {
        "status": "ok",
        **_queue_status_payload(queue),
    }


__all__ = ["get_task_queue", "router"]
