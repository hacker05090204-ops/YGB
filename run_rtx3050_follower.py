"""
run_rtx3050_follower.py — Execute RTX 3050 follower node protocol

Loads real dataset state from the training controller,
runs all 8 steps of the follower protocol, and saves
the result to reports/rtx3050_follower_report.json.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from impl_v1.training.distributed.cuda_node_rtx3050 import (
    RTX3050Follower,
)
from scripts.expert_task_queue import DEFAULT_STATUS_PATH, STATUS_CLAIMED, ExpertTaskQueue
from training_controller import TrainingControllerConfig, phase2_dataset_finalization


def load_telemetry():
    """Load RTX 3050 telemetry from previous training session."""
    tel_path = os.path.join('reports', 'speed_telemetry.json')
    if not os.path.exists(tel_path):
        logger.warning(f"Telemetry not found: {tel_path}")
        return None

    with open(tel_path, 'r', encoding='utf-8') as f:
        tel = json.load(f)

    logger.info(f"[RUNNER] Loaded telemetry from {tel_path}")
    return tel


def get_master_addr() -> str:
    return os.getenv("YGB_DDP_ADDR", "127.0.0.1")


def get_master_port() -> str:
    return str(int(os.getenv("YGB_DDP_PORT", "29500")))


def get_status_path() -> Path:
    return Path(os.getenv("YGB_EXPERT_STATUS_PATH", str(DEFAULT_STATUS_PATH)))


def load_real_dataset():
    """Load the real dataset through the canonical training controller."""
    config = TrainingControllerConfig(
        rank=1,
        world_size=2,
        master_addr=get_master_addr(),
        master_port=int(get_master_port()),
    )
    dataset_state, X, y = phase2_dataset_finalization(config)
    if not dataset_state.trainable:
        raise RuntimeError(
            f"Follower dataset not trainable: {dataset_state.verification_message}"
        )
    return config, dataset_state, X, y


def resolve_claimed_expert(queue: ExpertTaskQueue) -> dict[str, Any]:
    worker_id = str(os.getenv("YGB_DDP_WORKER_ID", "")).strip()
    requested_expert = str(os.getenv("YGB_EXPERT_ID", "")).strip()
    state = queue.load_status()
    claimed_records = [
        dict(item)
        for item in state.get("experts", [])
        if str(item.get("status", "")).upper() == STATUS_CLAIMED
    ]

    if requested_expert.isdigit():
        for record in claimed_records:
            if int(record.get("expert_id", -1)) == int(requested_expert):
                return record

    if worker_id:
        for record in claimed_records:
            if str(record.get("claimed_by", "")).strip() == worker_id:
                return record

    if len(claimed_records) == 1:
        return claimed_records[0]

    if len(claimed_records) > 1:
        claimed_ids = ", ".join(
            str(int(record.get("expert_id", -1))) for record in claimed_records
        )
        raise RuntimeError(
            "Multiple claimed experts found in queue; set YGB_EXPERT_ID or "
            f"YGB_DDP_WORKER_ID to select one explicitly (claimed={claimed_ids})"
        )

    raise RuntimeError(
        f"No claimed expert found in queue {queue.status_path}; "
        "start leader mode first so follower coordination remains honest"
    )


def main():
    logger.info("=" * 60)
    logger.info("[RUNNER] RTX 3050 Follower Node — 8-Step Protocol")
    logger.info("=" * 60)

    tel = load_telemetry()
    queue = ExpertTaskQueue(status_path=get_status_path())
    claimed_expert = resolve_claimed_expert(queue)
    expert_id = int(claimed_expert["expert_id"])
    field_name = str(claimed_expert.get("field_name", ""))
    logger.info("[RUNNER] Queue status:\n%s", queue.render_status())

    _, dataset_state, X, y = load_real_dataset()
    dataset_hash = dataset_state.hash
    logger.info(
        "[RUNNER] Real dataset loaded: samples=%s, dim=%s, source=%s, hash=%s...",
        dataset_state.sample_count,
        dataset_state.feature_dim,
        dataset_state.dataset_source,
        dataset_hash[:16],
    )

    cuda_version = None
    driver_version = None
    if tel:
        cuda_version = tel.get('cuda_version')
        driver_version = tel.get('driver_version')

    master_addr = get_master_addr()
    master_port = get_master_port()
    os.environ["MASTER_ADDR"] = master_addr
    os.environ["MASTER_PORT"] = master_port

    follower = RTX3050Follower(
        X=X,
        y=y,
        expected_dataset_hash=dataset_hash,
        expected_sample_count=dataset_state.sample_count,
        expected_feature_dim=dataset_state.feature_dim,
        leader_term=1,
        leader_cuda_version=cuda_version,
        leader_driver_version=driver_version,
        master_addr=master_addr,
        master_port=master_port,
        epochs=1,
        learning_rate=0.001,
        starting_batch=1024,
        input_dim=dataset_state.feature_dim,
        num_classes=dataset_state.num_classes,
        gradient_clip=1.0,
    )

    result = follower.run()
    if result.leader_connected:
        logger.info("Follower connected to %s:%s for expert %s", master_addr, master_port, expert_id)

    os.makedirs('reports', exist_ok=True)
    report_path = os.path.join('reports', 'rtx3050_follower_report.json')
    report_payload = {
        **asdict(result),
        "expert_id": expert_id,
        "field_name": field_name,
        "master_addr": master_addr,
        "master_port": int(master_port),
        "dataset_source": dataset_state.dataset_source,
        "dataset_verification_code": dataset_state.verification_code,
    }
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report_payload, f, indent=2)

    logger.info(f"[RUNNER] Report saved: {report_path}")

    logger.info("=" * 60)
    logger.info("[RUNNER] SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Expert ID:      {expert_id}")
    logger.info(f"  Field name:     {field_name}")
    logger.info(f"  Node ID:        {result.node_id[:16]}...")
    logger.info(f"  Device:         {result.device_name}")
    logger.info(f"  Rank:           {result.rank}")
    logger.info(f"  CUDA verified:  {result.cuda_verified}")
    logger.info(f"  Leader term:    {result.leader_term}")
    logger.info(f"  Dataset valid:  {result.dataset_valid}")
    logger.info(f"  Optimal batch:  {result.optimal_batch_3050}")
    logger.info(f"  Capacity:       {result.capacity_score}")
    logger.info(f"  Deterministic:  {result.deterministic}")
    logger.info(f"  Epochs:         {result.epochs_completed}")
    logger.info(f"  Final SPS:      {result.final_samples_per_sec:.0f}")
    logger.info(f"  Weight hash:    {result.final_weight_hash[:16]}...")
    logger.info(f"  Dataset hash:   {result.final_dataset_hash[:16]}...")

    if result.errors:
        logger.error(f"  Errors: {result.errors}")

    return result


if __name__ == '__main__':
    main()
