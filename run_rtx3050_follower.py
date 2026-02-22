"""
run_rtx3050_follower.py — Execute RTX 3050 follower node protocol

Loads telemetry from previous RTX 3050 training session,
runs all 8 steps of the follower protocol, and saves
the result to reports/rtx3050_follower_report.json.
"""

import hashlib
import json
import logging
import os
import sys
import time

import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from impl_v1.training.distributed.cuda_node_rtx3050 import (
    RTX3050Follower,
    FollowerRunResult,
)
from dataclasses import asdict


def load_telemetry():
    """Load RTX 3050 telemetry from previous training session."""
    tel_path = os.path.join('reports', 'speed_telemetry.json')
    if not os.path.exists(tel_path):
        logger.error(f"Telemetry not found: {tel_path}")
        return None

    with open(tel_path, 'r') as f:
        tel = json.load(f)

    logger.info(f"[RUNNER] Loaded telemetry from {tel_path}")
    return tel


def generate_dataset(num_samples=45000, feature_dim=256, num_classes=2, seed=42):
    """Generate deterministic dataset matching leader."""
    rng = np.random.RandomState(seed)
    X = rng.randn(num_samples, feature_dim).astype(np.float32)
    y = rng.randint(0, num_classes, num_samples).astype(np.int64)

    h = hashlib.sha256()
    h.update(X.tobytes())
    h.update(y.tobytes())
    dataset_hash = h.hexdigest()

    logger.info(
        f"[RUNNER] Dataset: {num_samples} samples, dim={feature_dim}, "
        f"hash={dataset_hash[:16]}..."
    )
    return X, y, dataset_hash


def main():
    logger.info("=" * 60)
    logger.info("[RUNNER] RTX 3050 Follower Node — 8-Step Protocol")
    logger.info("=" * 60)

    # Load telemetry
    tel = load_telemetry()

    # Generate dataset (same as leader)
    X, y, dataset_hash = generate_dataset()

    # Extract leader info from telemetry
    cuda_version = None
    driver_version = None
    if tel:
        cuda_version = tel.get('cuda_version')
        driver_version = tel.get('driver_version')

    # Create follower node
    follower = RTX3050Follower(
        X=X,
        y=y,
        expected_dataset_hash=dataset_hash,
        expected_sample_count=45000,
        expected_feature_dim=256,
        leader_term=1,
        leader_cuda_version=cuda_version,
        leader_driver_version=driver_version,
        epochs=1,
        learning_rate=0.001,
        starting_batch=1024,
        input_dim=256,
        num_classes=2,
        gradient_clip=1.0,
    )

    # Run full 8-step protocol
    result = follower.run()

    # Save report
    os.makedirs('reports', exist_ok=True)
    report_path = os.path.join('reports', 'rtx3050_follower_report.json')
    with open(report_path, 'w') as f:
        json.dump(asdict(result), f, indent=2)

    logger.info(f"[RUNNER] Report saved: {report_path}")

    # Summary
    logger.info("=" * 60)
    logger.info("[RUNNER] SUMMARY")
    logger.info("=" * 60)
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
