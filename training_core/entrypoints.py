"""Unified training entrypoints.

All public training scripts should route through this module so the backend has a
single execution brain for training orchestration.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any, Optional

from training_core.scheduler import guarded_training_call


def _result_to_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return dict(result)
    if hasattr(result, "__dict__"):
        return dict(vars(result))
    return {}


def _inject_leader_runtime_context(result: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(result)

    expert_id = os.environ.get("YGB_EXPERT_ID", "").strip()
    if expert_id.isdigit():
        enriched.setdefault("expert_id", int(expert_id))

    field_name = os.environ.get("YGB_EXPERT_FIELD_NAME", "").strip()
    if field_name:
        enriched.setdefault("field_name", field_name)

    ddp_role = os.environ.get("YGB_DDP_ROLE", "").strip()
    if ddp_role:
        enriched.setdefault("ddp_role", ddp_role)

    master_addr = os.environ.get("YGB_DDP_ADDR", "").strip()
    if master_addr:
        enriched.setdefault("master_addr", master_addr)

    master_port = os.environ.get("YGB_DDP_PORT", "").strip()
    if master_port.isdigit():
        enriched.setdefault("master_port", int(master_port))

    return enriched


def run_controller_pipeline(config: Optional[Any] = None):
    from training_controller import (
        TrainingControllerConfig,
        logger,
        main as controller_main,
    )

    if config is None:
        return guarded_training_call(None, controller_main)
    if not isinstance(config, TrainingControllerConfig):
        config = TrainingControllerConfig(
            **asdict(config) if hasattr(config, "__dict__") else dict(config)
        )
    return guarded_training_call(None, controller_main, config=config)


def run_real_training_main():
    return run_controller_pipeline()


def run_leader_ddp_main(config: Optional[Any] = None):
    from training_controller import TrainingControllerConfig

    if config is None:
        return run_controller_pipeline()

    mapped = TrainingControllerConfig(
        leader_node=getattr(config, "leader_node", "AUTO_DETECT"),
        follower_node=getattr(config, "follower_node", "AUTO_DETECT"),
        rank=getattr(config, "rank", 0),
        world_size=getattr(config, "world_size", 2),
        backend=getattr(config, "backend", "nccl"),
        master_addr=getattr(config, "master_addr", "127.0.0.1"),
        master_port=getattr(config, "master_port", 29500),
        input_dim=getattr(config, "input_dim", 256),
        hidden_dim=getattr(config, "hidden_dim", 512),
        num_classes=getattr(config, "num_classes", 2),
        num_epochs=getattr(config, "num_epochs", 3),
        base_batch_size=getattr(config, "base_batch_size", 512),
        base_lr=getattr(config, "base_lr", 0.001),
        gradient_clip=getattr(config, "gradient_clip", 1.0),
        seed=getattr(config, "seed", 42),
        cosine_lr=getattr(config, "cosine_lr", True),
        num_samples=getattr(config, "num_samples", 8000),
    )
    result = run_controller_pipeline(mapped)
    if result is None:
        return None

    result_payload = _inject_leader_runtime_context(_result_to_dict(result))
    os.makedirs("secure_data", exist_ok=True)
    report_path = os.path.join("secure_data", "leader_ddp_report.json")
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(result_payload, handle, indent=2)
    return result_payload
