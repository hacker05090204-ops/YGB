"""
cluster_metrics.py — Cluster Metrics Tracker (Phase 9)

Unified telemetry for training cluster:
- world_size
- cluster_samples_per_sec
- scaling_efficiency
- energy_per_epoch
- merged_weight_hash
- dataset_hash
- leader_term
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

METRICS_DIR = os.path.join('secure_data', 'cluster_metrics')


@dataclass
class EpochMetrics:
    """Metrics for a single epoch."""
    epoch: int
    world_size: int
    cluster_samples_per_sec: float
    scaling_efficiency: float
    merged_weight_hash: str
    dataset_hash: str
    leader_term: int
    energy_wh: float = 0.0       # Watt-hours
    per_node_sps: Dict[str, float] = field(default_factory=dict)
    loss: float = 0.0
    accuracy: float = 0.0
    timestamp: str = ""


@dataclass
class ClusterMetricsReport:
    """Full cluster metrics report."""
    total_epochs: int
    world_size: int
    avg_cluster_sps: float
    avg_efficiency: float
    total_energy_wh: float
    latest_weight_hash: str
    dataset_hash: str
    leader_term: int
    epochs: List[EpochMetrics]
    timestamp: str = ""


class ClusterMetricsTracker:
    """Tracks and persists cluster training metrics."""

    def __init__(self, metrics_dir: str = METRICS_DIR):
        self.metrics_dir = metrics_dir
        self._epochs: List[EpochMetrics] = []
        self._session_id = f"session_{int(time.time())}"

    def record_epoch(
        self,
        epoch: int,
        world_size: int,
        per_node_sps: Dict[str, float],
        baseline_sps_sum: float,
        merged_weight_hash: str,
        dataset_hash: str,
        leader_term: int,
        loss: float = 0.0,
        accuracy: float = 0.0,
        energy_wh: float = 0.0,
    ) -> EpochMetrics:
        """Record metrics for an epoch.

        Args:
            epoch: Epoch number
            world_size: Number of nodes
            per_node_sps: {node_id: samples_per_sec}
            baseline_sps_sum: Sum of single-node baselines
            merged_weight_hash: Hash of merged weights
            dataset_hash: Hash of dataset
            leader_term: Current leader term
            loss: Training loss
            accuracy: Training accuracy
            energy_wh: Energy consumed (Watt-hours)

        Returns:
            EpochMetrics
        """
        cluster_sps = sum(per_node_sps.values())
        efficiency = cluster_sps / max(baseline_sps_sum, 1.0)

        metrics = EpochMetrics(
            epoch=epoch,
            world_size=world_size,
            cluster_samples_per_sec=round(cluster_sps, 2),
            scaling_efficiency=round(efficiency, 4),
            merged_weight_hash=merged_weight_hash,
            dataset_hash=dataset_hash,
            leader_term=leader_term,
            energy_wh=round(energy_wh, 4),
            per_node_sps={k: round(v, 2) for k, v in per_node_sps.items()},
            loss=round(loss, 6),
            accuracy=round(accuracy, 4),
            timestamp=datetime.now().isoformat(),
        )

        self._epochs.append(metrics)

        logger.info(
            f"[METRICS] Epoch {epoch}: sps={cluster_sps:.0f} "
            f"eff={efficiency:.2%} loss={loss:.4f} "
            f"acc={accuracy:.4f}"
        )

        return metrics

    def get_report(self) -> ClusterMetricsReport:
        """Generate full metrics report."""
        if not self._epochs:
            return ClusterMetricsReport(
                total_epochs=0, world_size=0,
                avg_cluster_sps=0, avg_efficiency=0,
                total_energy_wh=0, latest_weight_hash="",
                dataset_hash="", leader_term=0, epochs=[],
                timestamp=datetime.now().isoformat(),
            )

        latest = self._epochs[-1]
        avg_sps = sum(e.cluster_samples_per_sec for e in self._epochs) / len(self._epochs)
        avg_eff = sum(e.scaling_efficiency for e in self._epochs) / len(self._epochs)
        total_energy = sum(e.energy_wh for e in self._epochs)

        return ClusterMetricsReport(
            total_epochs=len(self._epochs),
            world_size=latest.world_size,
            avg_cluster_sps=round(avg_sps, 2),
            avg_efficiency=round(avg_eff, 4),
            total_energy_wh=round(total_energy, 4),
            latest_weight_hash=latest.merged_weight_hash,
            dataset_hash=latest.dataset_hash,
            leader_term=latest.leader_term,
            epochs=self._epochs,
            timestamp=datetime.now().isoformat(),
        )

    def save(self):
        """Persist metrics to disk."""
        os.makedirs(self.metrics_dir, exist_ok=True)
        path = os.path.join(self.metrics_dir, f"{self._session_id}.json")

        report = self.get_report()
        with open(path, 'w') as f:
            json.dump(asdict(report), f, indent=2)

        logger.info(f"[METRICS] Saved: {path}")
        return path

    def estimate_energy(
        self,
        gpu_tdp_watts: float = 75.0,
        epoch_duration_sec: float = 1.0,
    ) -> float:
        """Estimate energy consumption for an epoch.

        Args:
            gpu_tdp_watts: GPU TDP in watts
            epoch_duration_sec: Duration of epoch in seconds

        Returns:
            Energy in Watt-hours
        """
        hours = epoch_duration_sec / 3600.0
        return round(gpu_tdp_watts * hours, 4)
