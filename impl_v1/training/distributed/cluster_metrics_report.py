"""
cluster_metrics_report.py — Full Metric Reporting (Phase 9)

After training, emit comprehensive JSON:

{
  world_size,
  cuda_nodes,
  mps_nodes,
  cluster_sps,
  scaling_efficiency,
  merged_weight_hash,
  dataset_hash,
  determinism_match,
  final_accuracy,
  overfit_gap
}
"""

import json
import logging
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

REPORT_PATH = os.path.join('reports', 'cluster_training_report.json')


# =============================================================================
# TYPES
# =============================================================================

@dataclass
class ClusterMetrics:
    """Comprehensive cluster training metrics."""
    # Topology
    world_size: int
    cuda_nodes: int
    mps_nodes: int

    # Performance
    cluster_sps: float
    scaling_efficiency: float
    per_node_sps: Dict[str, float]

    # Integrity
    merged_weight_hash: str
    dataset_hash: str
    determinism_match: bool

    # Quality
    final_accuracy: float
    overfit_gap: float        # train_acc - val_acc

    # Meta
    total_epochs: int
    total_time_sec: float
    timestamp: str

    # Authority
    checkpoint_consensus: bool
    authority_healthy: bool


# =============================================================================
# BUILDER
# =============================================================================

def build_cluster_report(
    # Topology
    world_size: int,
    cuda_node_ids: List[str],
    mps_node_ids: List[str],
    # Performance
    cluster_sps: float,
    scaling_efficiency: float,
    per_node_sps: Optional[Dict[str, float]] = None,
    # Integrity
    merged_weight_hash: str = "",
    dataset_hash: str = "",
    determinism_match: bool = True,
    # Quality
    final_accuracy: float = 0.0,
    train_accuracy: float = 0.0,
    val_accuracy: float = 0.0,
    # Meta
    total_epochs: int = 0,
    total_time_sec: float = 0.0,
    # Authority
    checkpoint_consensus: bool = True,
    authority_healthy: bool = True,
) -> ClusterMetrics:
    """Build a comprehensive cluster metrics report.

    Args:
        world_size: Total nodes.
        cuda_node_ids: List of CUDA node IDs.
        mps_node_ids: List of MPS node IDs.
        cluster_sps: Aggregate cluster throughput.
        scaling_efficiency: Cluster / single-node ratio.
        per_node_sps: Per-node throughput.
        merged_weight_hash: SHA-256 of merged weights.
        dataset_hash: SHA-256 of dataset.
        determinism_match: All nodes deterministic.
        final_accuracy: Best validation accuracy.
        train_accuracy: Final training accuracy.
        val_accuracy: Final validation accuracy.
        total_epochs: Epochs completed.
        total_time_sec: Total wall time.
        checkpoint_consensus: All checkpoints confirmed.
        authority_healthy: Authority heartbeat ok.

    Returns:
        ClusterMetrics.
    """
    overfit_gap = round(train_accuracy - val_accuracy, 6)
    if final_accuracy == 0.0 and val_accuracy > 0:
        final_accuracy = val_accuracy

    report = ClusterMetrics(
        world_size=world_size,
        cuda_nodes=len(cuda_node_ids),
        mps_nodes=len(mps_node_ids),
        cluster_sps=round(cluster_sps, 2),
        scaling_efficiency=round(scaling_efficiency, 4),
        per_node_sps=per_node_sps or {},
        merged_weight_hash=merged_weight_hash,
        dataset_hash=dataset_hash,
        determinism_match=determinism_match,
        final_accuracy=round(final_accuracy, 6),
        overfit_gap=overfit_gap,
        total_epochs=total_epochs,
        total_time_sec=round(total_time_sec, 3),
        timestamp=datetime.now().isoformat(),
        checkpoint_consensus=checkpoint_consensus,
        authority_healthy=authority_healthy,
    )

    return report


# =============================================================================
# OUTPUT
# =============================================================================

def emit_report(
    report: ClusterMetrics,
    path: str = REPORT_PATH,
) -> dict:
    """Emit the report as JSON to logger and file.

    Args:
        report: ClusterMetrics to emit.
        path: Output file path.

    Returns:
        Dict representation of the report.
    """
    report_dict = asdict(report)

    # Log
    logger.info(f"[METRICS] FINAL REPORT: {json.dumps(report_dict, indent=2)}")

    # Save to file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(report_dict, f, indent=2)

    logger.info(f"[METRICS] Report saved to {path}")
    return report_dict


def print_summary(report: ClusterMetrics):
    """Print a human-readable summary to logger."""
    lines = [
        "=" * 60,
        "CLUSTER TRAINING REPORT",
        "=" * 60,
        f"  World size:          {report.world_size}",
        f"  CUDA nodes:          {report.cuda_nodes}",
        f"  MPS nodes:           {report.mps_nodes}",
        f"  Cluster SPS:         {report.cluster_sps:.0f}",
        f"  Scaling efficiency:  {report.scaling_efficiency:.2%}",
        f"  Determinism match:   {'✓' if report.determinism_match else '✗'}",
        f"  Checkpoint consensus:{'✓' if report.checkpoint_consensus else '✗'}",
        f"  Authority healthy:   {'✓' if report.authority_healthy else '✗'}",
        f"  Final accuracy:      {report.final_accuracy:.4f}",
        f"  Overfit gap:         {report.overfit_gap:.4f}",
        f"  Weight hash:         {report.merged_weight_hash[:16]}...",
        f"  Dataset hash:        {report.dataset_hash[:16]}...",
        f"  Epochs:              {report.total_epochs}",
        f"  Time:                {report.total_time_sec:.1f}s",
        "=" * 60,
    ]

    for line in lines:
        logger.info(f"[METRICS] {line}")
