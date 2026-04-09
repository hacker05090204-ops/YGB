"""Unified leader DDP training entrypoint.

Leader-mode orchestration is routed through the canonical training core rather
than maintaining a second standalone training implementation.
"""

from __future__ import annotations

import json
import logging
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.expert_task_queue import (
    DEFAULT_STATUS_PATH,
    ExpertTaskQueue,
    STATUS_COMPLETED,
    STATUS_FAILED,
)
from training_core.entrypoints import run_leader_ddp_main


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class LeaderDDPConfig:
    leader_node: str = "RTX2050"
    follower_node: str = "RTX3050"
    rank: int = 0
    world_size: int = 2
    backend: str = "nccl"
    master_addr: str = "127.0.0.1"
    master_port: int = 29500
    input_dim: int = 256
    hidden_dim: int = 512
    num_classes: int = 2
    num_epochs: int = 3
    base_batch_size: int = 512
    base_lr: float = 0.001
    gradient_clip: float = 1.0
    seed: int = 42
    num_samples: int = 8000
    cosine_lr: bool = True


def get_master_port() -> int:
    return int(os.getenv("YGB_DDP_PORT", "29500"))


def get_master_addr() -> str:
    return os.getenv("YGB_DDP_ADDR", "127.0.0.1")


def get_status_path() -> Path:
    return Path(os.getenv("YGB_EXPERT_STATUS_PATH", str(DEFAULT_STATUS_PATH)))


def get_worker_id() -> str:
    configured_worker_id = str(os.getenv("YGB_DDP_WORKER_ID", "")).strip()
    if configured_worker_id:
        return configured_worker_id
    return f"ddp-leader@{socket.gethostname()}"


def build_leader_config() -> LeaderDDPConfig:
    return LeaderDDPConfig(
        master_addr=get_master_addr(),
        master_port=get_master_port(),
    )


def _result_to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return result
    if hasattr(result, "__dict__"):
        return dict(vars(result))
    return {}


def _detect_gpu_info() -> tuple[str, float]:
    try:
        import torch
    except ImportError:
        return "CPU", 0.0

    if not torch.cuda.is_available():
        return "CPU", 0.0

    props = torch.cuda.get_device_properties(0)
    return props.name, round(props.total_memory / (1024**3), 2)


def _resolve_checkpoint_path(result: dict[str, Any]) -> str:
    for meta_path in (
        result.get("best_checkpoint_meta_path"),
        result.get("latest_checkpoint_meta_path"),
    ):
        meta_path_text = str(meta_path or "").strip()
        if not meta_path_text or not os.path.exists(meta_path_text):
            continue
        try:
            with open(meta_path_text, "r", encoding="utf-8") as handle:
                meta = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Unable to read checkpoint metadata %s: %s", meta_path_text, exc)
            continue

        model_path = str(meta.get("model_path", "") or "")
        if not model_path:
            shards = meta.get("shards") or []
            if shards and isinstance(shards[0], dict):
                model_path = str(shards[0].get("model_path", "") or "")
        if model_path:
            return model_path
    return ""


def main():
    config = build_leader_config()
    os.environ["MASTER_ADDR"] = config.master_addr
    os.environ["MASTER_PORT"] = str(config.master_port)

    hostname = socket.gethostname()
    gpu_name, vram_gb = _detect_gpu_info()
    logger.info(
        "Leader startup: hostname=%s | gpu=%s | vram_gb=%.2f | master=%s:%s",
        hostname,
        gpu_name,
        vram_gb,
        config.master_addr,
        config.master_port,
    )

    queue = ExpertTaskQueue(status_path=get_status_path())
    logger.info("Current expert queue status:\n%s", queue.render_status())

    worker_id = get_worker_id()
    claimed = queue.claim_next_expert(worker_id)
    if claimed is None:
        logger.info("No expert available for worker_id=%s", worker_id)
        return None

    expert_id = int(claimed["expert_id"])
    field_name = str(claimed["field_name"])
    logger.info(
        "Leader claimed expert_id=%s field_name=%s for worker_id=%s",
        expert_id,
        field_name,
        worker_id,
    )

    result = None
    result_dict: dict[str, Any] = {}
    error_text = ""
    training_failed = False

    try:
        result = run_leader_ddp_main(config)
        result_dict = _result_to_dict(result)
    except Exception as exc:
        training_failed = True
        error_text = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "Leader DDP training failed for expert_id=%s field_name=%s",
            expert_id,
            field_name,
        )
        raise
    finally:
        if result is None and not error_text:
            error_text = "training_result_missing"

        release_status = STATUS_FAILED
        if result_dict and not bool(result_dict.get("drift_aborted")):
            release_status = STATUS_COMPLETED
        if training_failed or result is None:
            release_status = STATUS_FAILED

        checkpoint_path = _resolve_checkpoint_path(result_dict)
        try:
            queue_record = queue.release_expert(
                expert_id,
                worker_id=worker_id,
                status=release_status,
                val_f1=result_dict.get("val_f1"),
                val_precision=result_dict.get("val_precision"),
                val_recall=result_dict.get("val_recall"),
                checkpoint_path=checkpoint_path,
                error=error_text,
            )
            logger.info(
                "Leader released expert_id=%s with status=%s | checkpoint=%s",
                expert_id,
                queue_record.get("status", release_status),
                checkpoint_path or "-",
            )
            logger.info("Queue status after release:\n%s", queue.render_status())
        except Exception as release_exc:
            logger.exception(
                "Failed to release expert_id=%s for worker_id=%s: %s",
                expert_id,
                worker_id,
                release_exc,
            )
            if not training_failed:
                raise

    if result is not None:
        print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
