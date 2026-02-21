"""
═══════════════════════════════════════════════════════════════════════
  cluster_authority.py — Distributed ML Cluster Authority
═══════════════════════════════════════════════════════════════════════

  ROLE: Cluster authority (Python governance only).
  GOAL: Maintain deterministic, stable training across up to 10 devices.
  C++ handles runtime. Python governance only.

  7 PHASES:
    1. CUDA Verification        — reject mismatched nodes
    2. Dataset Lock              — enforce hash/dim/distribution consensus
    3. World Size Lock           — freeze topology at training start
    4. Scaling Limit             — disable excess nodes if efficiency < 0.7
    5. MPS Safety                — validate MPS weight deltas
    6. Data Quality Enforcement  — block bad datasets
    7. Metric Reporting          — structured epoch telemetry
═══════════════════════════════════════════════════════════════════════
"""

import hashlib
import json
import logging
import math
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════════════

class NodeStatus(str, Enum):
    """Node lifecycle status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ACTIVE = "active"
    DROPPED = "dropped"


@dataclass
class NodeRegistration:
    """Per-node registration data sent during CUDA verification."""
    node_id: str
    gpu_name: str
    cuda_major: int
    cuda_minor: int
    compute_major: int
    compute_minor: int
    fp16_supported: bool
    driver_major: int
    driver_minor: int
    vram_mb: float
    sm_count: int
    optimal_batch: int
    capacity_score: float
    throughput_sps: float
    dataset_hash: str
    sample_count: int
    feature_dim: int
    label_distribution: Dict[str, int]
    status: NodeStatus = NodeStatus.PENDING
    reject_reason: str = ""


@dataclass
class DatasetLock:
    """Locked dataset parameters — all nodes must match."""
    dataset_hash: str
    sample_count: int
    feature_dim: int
    label_distribution: Dict[str, int]
    entropy: float


@dataclass
class EpochMetrics:
    """Metrics reported after each epoch."""
    epoch: int
    world_size: int
    total_cluster_samples_per_sec: float
    per_node_batch: Dict[str, int]
    merged_weight_hash: str
    dataset_hash_consensus: str
    scaling_efficiency: float
    timestamp: str


@dataclass
class AuthorityState:
    """Full authority state."""
    phase: int = 0
    world_size_locked: bool = False
    locked_world_size: int = 0
    training_active: bool = False
    aborted: bool = False
    abort_reason: str = ""


# ═══════════════════════════════════════════════════════════════════════
# THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════

# Phase 1 — CUDA Verification
CUDA_MAJOR_TOLERANCE = 0          # Must match exactly
COMPUTE_CAPABILITY_TOLERANCE = 1  # Minor version ≤1 diff allowed
DRIVER_MINOR_TOLERANCE = 1        # Driver minor diff ≤1 allowed

# Phase 4 — Scaling Limit
SCALING_EFFICIENCY_THRESHOLD = 0.7
MAX_CLUSTER_FOR_SCALING_TEST = 6

# Phase 5 — MPS Safety
MPS_DELTA_NORM_THRESHOLD = 10.0
MPS_LOSS_IMPROVEMENT_MIN = 0.0    # Must not increase
MPS_VAL_ACC_DROP_TOLERANCE = 0.05

# Phase 6 — Data Quality
DATA_DUPLICATE_MAX = 0.20
DATA_IMBALANCE_MAX = 10.0
DATA_ENTROPY_MIN = 0.3
DATA_SANITY_ACC_MIN = 0.40


# ═══════════════════════════════════════════════════════════════════════
# CLUSTER AUTHORITY
# ═══════════════════════════════════════════════════════════════════════

class ClusterAuthority:
    """
    Distributed ML cluster authority.

    Maintains deterministic, stable training across up to 10 devices.
    C++ handles runtime. This is Python governance only.
    """

    MAX_NODES = 10

    def __init__(
        self,
        reference_cuda_major: int = 12,
        reference_compute_major: int = 8,
        reference_compute_minor: int = 6,
        reference_driver_major: int = 8,
        reference_driver_minor: int = 6,
    ):
        self.reference_cuda_major = reference_cuda_major
        self.reference_compute_major = reference_compute_major
        self.reference_compute_minor = reference_compute_minor
        self.reference_driver_major = reference_driver_major
        self.reference_driver_minor = reference_driver_minor

        self.nodes: Dict[str, NodeRegistration] = {}
        self.state = AuthorityState()
        self.dataset_lock: Optional[DatasetLock] = None
        self.epoch_logs: List[EpochMetrics] = []
        self.single_gpu_sps: Optional[float] = None  # For scaling efficiency

        logger.info("[AUTHORITY] Cluster authority initialized")

    # ═══════════════════════════════════════════════════════════════
    # PHASE 1 — CUDA VERIFICATION
    # ═══════════════════════════════════════════════════════════════

    def verify_cuda_node(self, node: NodeRegistration) -> NodeRegistration:
        """
        Verify a CUDA node for cluster participation.

        Reject if:
          - CUDA major version mismatch
          - Compute capability mismatch beyond tolerance
          - FP16 unsupported
          - Driver mismatch > minor difference
        """
        self.state.phase = max(self.state.phase, 1)

        if len(self.nodes) >= self.MAX_NODES:
            node.status = NodeStatus.REJECTED
            node.reject_reason = f"Cluster full ({self.MAX_NODES} nodes max)"
            logger.error(f"[PHASE1] REJECTED {node.node_id}: {node.reject_reason}")
            return node

        if self.state.world_size_locked:
            node.status = NodeStatus.REJECTED
            node.reject_reason = "World size locked — no join mid-training"
            logger.error(f"[PHASE1] REJECTED {node.node_id}: {node.reject_reason}")
            return node

        reasons = []

        # CUDA major version must match exactly
        if node.cuda_major != self.reference_cuda_major:
            reasons.append(
                f"CUDA major mismatch: node={node.cuda_major}, "
                f"ref={self.reference_cuda_major}"
            )

        # Compute capability tolerance
        node_cc = node.compute_major * 10 + node.compute_minor
        ref_cc = self.reference_compute_major * 10 + self.reference_compute_minor
        if abs(node_cc - ref_cc) > COMPUTE_CAPABILITY_TOLERANCE:
            reasons.append(
                f"Compute capability mismatch: node={node.compute_major}.{node.compute_minor}, "
                f"ref={self.reference_compute_major}.{self.reference_compute_minor}"
            )

        # FP16 required
        if not node.fp16_supported:
            reasons.append("FP16 not supported")

        # Driver mismatch
        if node.driver_major != self.reference_driver_major:
            reasons.append(
                f"Driver major mismatch: node={node.driver_major}, "
                f"ref={self.reference_driver_major}"
            )
        elif abs(node.driver_minor - self.reference_driver_minor) > DRIVER_MINOR_TOLERANCE:
            reasons.append(
                f"Driver minor mismatch > {DRIVER_MINOR_TOLERANCE}: "
                f"node={node.driver_major}.{node.driver_minor}, "
                f"ref={self.reference_driver_major}.{self.reference_driver_minor}"
            )

        if reasons:
            node.status = NodeStatus.REJECTED
            node.reject_reason = "; ".join(reasons)
            logger.error(f"[PHASE1] REJECTED {node.node_id}: {node.reject_reason}")
        else:
            node.status = NodeStatus.ACCEPTED
            self.nodes[node.node_id] = node
            logger.info(
                f"[PHASE1] ACCEPTED {node.node_id}: "
                f"{node.gpu_name}, CC={node.compute_major}.{node.compute_minor}, "
                f"VRAM={node.vram_mb:.0f}MB"
            )

        return node

    # ═══════════════════════════════════════════════════════════════
    # PHASE 2 — DATASET LOCK
    # ═══════════════════════════════════════════════════════════════

    def enforce_dataset_lock(self) -> Tuple[bool, str]:
        """
        Lock dataset parameters. All nodes must match:
          - dataset_hash
          - sample_count
          - feature_dim
          - label_distribution
          - entropy threshold

        Returns:
            (passed, reason)
        """
        self.state.phase = max(self.state.phase, 2)

        accepted = self._get_accepted_nodes()
        if not accepted:
            return False, "No accepted nodes"

        # Use first node as reference
        ref = accepted[0]
        mismatches = []

        for node in accepted[1:]:
            if node.dataset_hash != ref.dataset_hash:
                mismatches.append(f"{node.node_id}: hash mismatch")
            if node.sample_count != ref.sample_count:
                mismatches.append(f"{node.node_id}: sample_count mismatch")
            if node.feature_dim != ref.feature_dim:
                mismatches.append(f"{node.node_id}: feature_dim mismatch")
            if node.label_distribution != ref.label_distribution:
                mismatches.append(f"{node.node_id}: label_distribution mismatch")

        if mismatches:
            reason = f"Dataset mismatch — ABORT: {'; '.join(mismatches)}"
            self._abort(reason)
            return False, reason

        # Compute entropy from label distribution
        counts = np.array(list(ref.label_distribution.values()), dtype=float)
        probs = counts / counts.sum()
        max_entropy = np.log2(max(len(probs), 2))
        entropy = float(-np.sum(probs * np.log2(probs + 1e-10)))
        norm_entropy = entropy / max(max_entropy, 1e-10)

        if norm_entropy < DATA_ENTROPY_MIN:
            reason = f"Entropy {norm_entropy:.4f} below threshold {DATA_ENTROPY_MIN}"
            self._abort(reason)
            return False, reason

        self.dataset_lock = DatasetLock(
            dataset_hash=ref.dataset_hash,
            sample_count=ref.sample_count,
            feature_dim=ref.feature_dim,
            label_distribution=ref.label_distribution,
            entropy=round(norm_entropy, 6),
        )

        logger.info(
            f"[PHASE2] Dataset LOCKED: hash={ref.dataset_hash[:16]}, "
            f"samples={ref.sample_count}, dim={ref.feature_dim}, "
            f"entropy={norm_entropy:.4f}"
        )
        return True, "Dataset locked"

    # ═══════════════════════════════════════════════════════════════
    # PHASE 3 — WORLD SIZE LOCK
    # ═══════════════════════════════════════════════════════════════

    def lock_world_size(self) -> Tuple[bool, int]:
        """
        Lock world_size at training start.

        No node join/leave mid-epoch.
        If dropout → abort entire training safely.

        Returns:
            (success, locked_world_size)
        """
        self.state.phase = max(self.state.phase, 3)

        accepted = self._get_accepted_nodes()
        if not accepted:
            return False, 0

        self.state.world_size_locked = True
        self.state.locked_world_size = len(accepted)

        # Mark all accepted nodes as active
        for node in accepted:
            node.status = NodeStatus.ACTIVE

        logger.info(
            f"[PHASE3] World size LOCKED: {self.state.locked_world_size} nodes"
        )
        return True, self.state.locked_world_size

    def check_dropout(self, active_node_ids: List[str]) -> Tuple[bool, str]:
        """
        Check for node dropout during training.

        If any locked node is missing → abort.

        Returns:
            (ok, reason)
        """
        if not self.state.world_size_locked:
            return True, "World size not locked yet"

        active_nodes = self._get_active_nodes()
        expected_ids = {n.node_id for n in active_nodes}
        current_ids = set(active_node_ids)

        missing = expected_ids - current_ids
        if missing:
            reason = (
                f"Node dropout detected: {len(missing)} node(s) missing — "
                f"ABORT. Missing: {list(missing)}"
            )
            self._abort(reason)
            return False, reason

        return True, "All nodes active"

    # ═══════════════════════════════════════════════════════════════
    # PHASE 4 — SCALING LIMIT
    # ═══════════════════════════════════════════════════════════════

    def enforce_scaling_limit(
        self,
        single_gpu_sps: float,
        cluster_sps: float,
    ) -> Tuple[bool, float, List[str]]:
        """
        If cluster size > 6, run scaling efficiency test.

        efficiency = cluster_sps / (single_gpu_sps * world_size)

        If efficiency < 0.7: disable extra nodes.

        Args:
            single_gpu_sps: Single GPU throughput (samples/sec).
            cluster_sps: Measured cluster throughput.

        Returns:
            (passed, efficiency, disabled_node_ids)
        """
        self.state.phase = max(self.state.phase, 4)
        self.single_gpu_sps = single_gpu_sps

        active = self._get_active_nodes()
        world_size = len(active)

        if world_size <= MAX_CLUSTER_FOR_SCALING_TEST:
            logger.info(
                f"[PHASE4] Cluster size {world_size} ≤ {MAX_CLUSTER_FOR_SCALING_TEST} — "
                f"scaling test skipped"
            )
            return True, 1.0, []

        ideal_sps = single_gpu_sps * world_size
        efficiency = cluster_sps / max(ideal_sps, 1e-10)

        if efficiency >= SCALING_EFFICIENCY_THRESHOLD:
            logger.info(
                f"[PHASE4] Scaling efficiency {efficiency:.4f} ≥ "
                f"{SCALING_EFFICIENCY_THRESHOLD} — PASS"
            )
            return True, round(efficiency, 4), []

        # Disable weakest nodes until we're at 6 or efficiency is acceptable
        logger.warning(
            f"[PHASE4] Scaling efficiency {efficiency:.4f} < "
            f"{SCALING_EFFICIENCY_THRESHOLD} — disabling excess nodes"
        )

        # Sort by capacity_score ascending (weakest first)
        sorted_nodes = sorted(active, key=lambda n: n.capacity_score)
        disabled = []

        while len(self._get_active_nodes()) > MAX_CLUSTER_FOR_SCALING_TEST:
            weakest = sorted_nodes.pop(0)
            weakest.status = NodeStatus.DROPPED
            weakest.reject_reason = f"Scaling efficiency {efficiency:.4f} < {SCALING_EFFICIENCY_THRESHOLD}"
            disabled.append(weakest.node_id)
            logger.warning(f"[PHASE4] Disabled node {weakest.node_id}")

        # Update locked world size
        self.state.locked_world_size = len(self._get_active_nodes())

        return False, round(efficiency, 4), disabled

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5 — MPS SAFETY
    # ═══════════════════════════════════════════════════════════════

    def validate_mps_delta(
        self,
        node_id: str,
        delta_norm: float,
        loss_before: float,
        loss_after: float,
        val_acc_before: float,
        val_acc_after: float,
    ) -> Tuple[bool, str]:
        """
        MPS nodes: train shard, send delta.

        Authority checks:
          - delta_norm < threshold
          - loss_improvement > minimum (loss must not increase)
          - validation accuracy drop < tolerance

        If fail: reject merge.

        Returns:
            (accepted, reason)
        """
        self.state.phase = max(self.state.phase, 5)
        reasons = []

        if delta_norm >= MPS_DELTA_NORM_THRESHOLD:
            reasons.append(
                f"delta_norm {delta_norm:.4f} ≥ {MPS_DELTA_NORM_THRESHOLD}"
            )

        loss_improvement = loss_before - loss_after
        if loss_improvement < MPS_LOSS_IMPROVEMENT_MIN:
            reasons.append(
                f"loss increased: {loss_before:.6f} → {loss_after:.6f} "
                f"(improvement={loss_improvement:.6f})"
            )

        val_acc_drop = val_acc_before - val_acc_after
        if val_acc_drop > MPS_VAL_ACC_DROP_TOLERANCE:
            reasons.append(
                f"val_acc dropped {val_acc_drop:.4f} > tolerance "
                f"{MPS_VAL_ACC_DROP_TOLERANCE}"
            )

        if reasons:
            reason = f"MPS delta REJECTED for {node_id}: {'; '.join(reasons)}"
            logger.error(f"[PHASE5] {reason}")
            return False, reason

        logger.info(
            f"[PHASE5] MPS delta ACCEPTED for {node_id}: "
            f"norm={delta_norm:.4f}, loss_imp={loss_improvement:.6f}, "
            f"val_acc_drop={val_acc_drop:.4f}"
        )
        return True, "Delta accepted"

    # ═══════════════════════════════════════════════════════════════
    # PHASE 6 — DATA QUALITY ENFORCEMENT
    # ═══════════════════════════════════════════════════════════════

    def enforce_data_quality(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        sanity_accuracy: float,
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Run dataset_quality_validator before training.

        Block training if:
          - duplicates > 20%
          - imbalance > threshold
          - entropy < threshold
          - validation sanity accuracy < 40%

        Returns:
            (passed, report_dict)
        """
        self.state.phase = max(self.state.phase, 6)
        N = features.shape[0]

        # Duplicate check
        _, unique_counts = np.unique(features, axis=0, return_counts=True)
        duplicates = int(np.sum(unique_counts[unique_counts > 1] - 1))
        dup_ratio = duplicates / max(N, 1)

        # Class imbalance
        unique_labels, counts = np.unique(labels, return_counts=True)
        imbalance = float(counts.max()) / max(float(counts.min()), 1)

        # Entropy
        probs = counts.astype(float) / counts.sum()
        max_entropy = np.log2(max(len(unique_labels), 2))
        entropy = float(-np.sum(probs * np.log2(probs + 1e-10)))
        norm_entropy = entropy / max(max_entropy, 1e-10)

        report = {
            "duplicate_ratio": round(dup_ratio, 4),
            "imbalance_ratio": round(imbalance, 4),
            "entropy": round(norm_entropy, 4),
            "sanity_accuracy": round(sanity_accuracy, 4),
            "samples": N,
            "classes": len(unique_labels),
        }

        block_reasons = []

        if dup_ratio > DATA_DUPLICATE_MAX:
            block_reasons.append(
                f"duplicates {dup_ratio:.1%} > {DATA_DUPLICATE_MAX:.0%}"
            )

        if imbalance > DATA_IMBALANCE_MAX:
            block_reasons.append(
                f"imbalance {imbalance:.1f}x > {DATA_IMBALANCE_MAX:.0f}x"
            )

        if norm_entropy < DATA_ENTROPY_MIN:
            block_reasons.append(
                f"entropy {norm_entropy:.4f} < {DATA_ENTROPY_MIN}"
            )

        if sanity_accuracy < DATA_SANITY_ACC_MIN:
            block_reasons.append(
                f"sanity_acc {sanity_accuracy:.1%} < {DATA_SANITY_ACC_MIN:.0%}"
            )

        if block_reasons:
            report["blocked"] = True
            report["block_reasons"] = block_reasons
            reason = "; ".join(block_reasons)
            logger.error(f"[PHASE6] BLOCKED: {reason}")
            return False, report

        report["blocked"] = False
        report["block_reasons"] = []
        logger.info(
            f"[PHASE6] PASSED: dups={dup_ratio:.1%}, imb={imbalance:.1f}x, "
            f"entropy={norm_entropy:.4f}, sanity={sanity_accuracy:.1%}"
        )
        return True, report

    # ═══════════════════════════════════════════════════════════════
    # PHASE 7 — METRIC REPORTING
    # ═══════════════════════════════════════════════════════════════

    def report_epoch_metrics(
        self,
        epoch: int,
        cluster_sps: float,
        per_node_batch: Dict[str, int],
        merged_weight_hash: str,
        dataset_hash_consensus: str,
        scaling_efficiency: float = 1.0,
    ) -> EpochMetrics:
        """
        After each epoch, authority logs structured metrics.

        Returns:
            EpochMetrics.
        """
        self.state.phase = max(self.state.phase, 7)

        metrics = EpochMetrics(
            epoch=epoch,
            world_size=self.state.locked_world_size or len(self._get_active_nodes()),
            total_cluster_samples_per_sec=round(cluster_sps, 2),
            per_node_batch=per_node_batch,
            merged_weight_hash=merged_weight_hash,
            dataset_hash_consensus=dataset_hash_consensus,
            scaling_efficiency=round(scaling_efficiency, 4),
            timestamp=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        )

        self.epoch_logs.append(metrics)

        logger.info(
            f"[PHASE7] Epoch {epoch}: world_size={metrics.world_size}, "
            f"sps={cluster_sps:.0f}, weight_hash={merged_weight_hash[:16]}, "
            f"dataset_consensus={dataset_hash_consensus[:16]}, "
            f"scaling_eff={scaling_efficiency:.4f}"
        )

        return metrics

    # ═══════════════════════════════════════════════════════════════
    # AUTHORITY LIFECYCLE
    # ═══════════════════════════════════════════════════════════════

    def start_training(self) -> Tuple[bool, str]:
        """
        Finalize authority state and begin training.

        Returns:
            (success, reason)
        """
        if self.state.aborted:
            return False, f"Training aborted: {self.state.abort_reason}"

        active = self._get_active_nodes()
        if not active:
            return False, "No active nodes"

        if not self.dataset_lock:
            return False, "Dataset not locked"

        if not self.state.world_size_locked:
            return False, "World size not locked"

        self.state.training_active = True
        logger.info(
            f"[AUTHORITY] Training STARTED: {len(active)} nodes, "
            f"world_size={self.state.locked_world_size}"
        )
        return True, "Training started"

    def get_shard_proportions(self) -> Dict[str, float]:
        """
        Calculate shard proportions based on capacity scores.

        shard_proportion = capacity / total_capacity
        """
        active = self._get_active_nodes()
        total_cap = sum(n.capacity_score for n in active)

        if total_cap <= 0:
            # Equal split
            n = len(active)
            return {node.node_id: 1.0 / max(n, 1) for node in active}

        return {
            node.node_id: round(node.capacity_score / total_cap, 6)
            for node in active
        }

    def get_full_report(self) -> dict:
        """Return complete authority state as serializable dict."""
        active = self._get_active_nodes()
        all_nodes = list(self.nodes.values())

        return {
            "authority_state": {
                "phase": self.state.phase,
                "world_size_locked": self.state.world_size_locked,
                "locked_world_size": self.state.locked_world_size,
                "training_active": self.state.training_active,
                "aborted": self.state.aborted,
                "abort_reason": self.state.abort_reason,
            },
            "nodes": {
                n.node_id: {
                    "gpu_name": n.gpu_name,
                    "status": n.status.value,
                    "capacity_score": n.capacity_score,
                    "optimal_batch": n.optimal_batch,
                    "vram_mb": n.vram_mb,
                    "reject_reason": n.reject_reason,
                }
                for n in all_nodes
            },
            "dataset_lock": asdict(self.dataset_lock) if self.dataset_lock else None,
            "shard_proportions": self.get_shard_proportions() if active else {},
            "epoch_logs": [asdict(m) for m in self.epoch_logs],
        }

    # ═══════════════════════════════════════════════════════════════
    # INTERNAL HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _get_accepted_nodes(self) -> List[NodeRegistration]:
        return [n for n in self.nodes.values() if n.status == NodeStatus.ACCEPTED]

    def _get_active_nodes(self) -> List[NodeRegistration]:
        return [n for n in self.nodes.values() if n.status == NodeStatus.ACTIVE]

    def _abort(self, reason: str):
        self.state.aborted = True
        self.state.abort_reason = reason
        self.state.training_active = False
        logger.error(f"[AUTHORITY] ABORT: {reason}")
