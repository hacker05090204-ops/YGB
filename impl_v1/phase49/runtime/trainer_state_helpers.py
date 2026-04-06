from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
import uuid


def write_worker_status(trainer: Any, logger) -> None:
    try:
        payload = trainer.get_status()
        trainer._atomic_write_json(trainer._worker_status_path, payload)
    except Exception as exc:
        logger.debug("Worker status write skipped: %s", exc)


def emit_training_event(
    trainer: Any,
    event_cls,
    logger,
    event_type: str,
    details: str,
    idle_seconds: int = 0,
    gpu_used: bool = False,
    epoch: Optional[int] = None,
):
    event = event_cls(
        event_id=f"EVT-{uuid.uuid4().hex[:12].upper()}",
        event_type=event_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        details=details,
        idle_seconds=idle_seconds,
        gpu_used=gpu_used,
        epoch=epoch,
    )

    trainer._events.append(event)
    if len(trainer._events) > 1000:
        trainer._events = trainer._events[-500:]
    if event_type == "ERROR":
        trainer._last_error = details

    log_msg = f"[{event_type}] {details}"
    if event_type in (
        "TRAINING_STARTED",
        "IDLE_DETECTED",
        "TRAINING_STOPPED",
        "CHECKPOINT_SAVED",
    ):
        logger.info(log_msg)
    elif event_type in ("TRAINING_ABORTED", "GUARD_BLOCKED"):
        logger.warning(log_msg)
    elif event_type == "ERROR":
        logger.error(log_msg)
    else:
        logger.debug(log_msg)

    if trainer._on_event_callback:
        try:
            trainer._on_event_callback(event)
        except Exception as exc:
            logger.debug("Training event callback failed: %s", exc)

    if trainer._telegram_notifier is not None:
        try:
            trainer._telegram_notifier.notify(event, trainer.get_status())
        except Exception as exc:
            logger.warning("Telegram notifier skipped: %s", exc)

    try:
        write_worker_status(trainer, logger)
    except Exception as exc:
        logger.debug("Worker status write skipped after event emission: %s", exc)

    return event


def session_duration_seconds(current_session: Any) -> float:
    if not current_session:
        return 0.0
    try:
        started = datetime.fromisoformat(current_session.started_at)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
    except ValueError:
        return 0.0


def build_trainer_status(
    trainer: Any,
    conditions: Any,
    *,
    torch_available: bool,
    torch_module: Any,
    pytorch_available: bool,
    safetensors_available: bool,
    amp_available: bool,
) -> dict:
    current_state = trainer.state
    is_continuous = getattr(trainer, "_continuous_mode", False)

    if trainer.is_training and is_continuous:
        real_progress = round(trainer._last_accuracy * 100)
        current_epoch = trainer._session_epoch
        target = 0
    elif trainer.is_training and trainer._target_epochs > 0:
        real_progress = round((trainer._session_epoch / trainer._target_epochs) * 100)
        current_epoch = trainer._session_epoch
        target = trainer._target_epochs
    elif trainer._last_target_epochs > 0:
        real_progress = 100
        current_epoch = trainer._last_completed_epochs
        target = trainer._last_target_epochs
    else:
        real_progress = 0
        current_epoch = 0
        target = 0

    gpu_mem_allocated = 0.0
    gpu_mem_reserved = 0.0
    if torch_available and torch_module.cuda.is_available():
        gpu_mem_allocated = torch_module.cuda.memory_allocated() / 1024 / 1024
        gpu_mem_reserved = torch_module.cuda.memory_reserved() / 1024 / 1024

    return {
        "state": current_state.value,
        "is_training": trainer.is_training,
        "epoch": current_epoch,
        "total_epochs": target,
        "total_completed": trainer._epoch,
        "progress": real_progress,
        "idle_seconds": conditions.idle_seconds,
        "power_connected": conditions.power_connected,
        "scan_active": not conditions.no_active_scan,
        "gpu_available": conditions.gpu_available,
        "events_count": len(trainer._events),
        "last_event": trainer._events[-1].event_type if trainer._events else None,
        "gpu_mem_allocated_mb": round(gpu_mem_allocated, 2),
        "gpu_mem_reserved_mb": round(gpu_mem_reserved, 2),
        "last_loss": round(trainer._last_loss, 6),
        "last_accuracy": round(trainer._last_accuracy, 4),
        "samples_per_sec": round(trainer._samples_per_sec, 1),
        "dataset_size": trainer._gpu_dataset_stats["train"]["total"]
        if trainer._gpu_dataset_stats
        else 0,
        "training_mode": "CONTINUOUS"
        if is_continuous
        else getattr(trainer, "_training_mode_label", "MANUAL"),
        "continuous_mode": is_continuous,
        "last_error": trainer._last_error or None,
        "dependencies": {
            "pytorch": "AVAILABLE" if torch_available else "UNAVAILABLE",
            "pytorch_backend": "AVAILABLE" if pytorch_available else "UNAVAILABLE",
            "safetensors": "AVAILABLE" if safetensors_available else "UNAVAILABLE",
            "cuda": "AVAILABLE"
            if (torch_available and torch_module.cuda.is_available())
            else "UNAVAILABLE",
            "amp": "AVAILABLE" if amp_available else "UNAVAILABLE",
            "numpy": "AVAILABLE",
        },
    }
