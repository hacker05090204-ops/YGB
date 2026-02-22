"""
═══════════════════════════════════════════════════════════════════════
  test_cluster_authority.py — Comprehensive Tests for Cluster Authority
═══════════════════════════════════════════════════════════════════════

Covers all 7 phases:
  Phase 1: CUDA node acceptance/rejection
  Phase 2: Dataset hash consensus
  Phase 3: World size lock and dropout
  Phase 4: Scaling efficiency
  Phase 5: MPS delta validation
  Phase 6: Data quality gate
  Phase 7: Metric reporting
"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from impl_v1.training.distributed.cluster_authority import (
    ClusterAuthority,
    NodeRegistration,
    NodeStatus,
    SCALING_EFFICIENCY_THRESHOLD,
    MPS_DELTA_NORM_THRESHOLD,
    MPS_VAL_ACC_DROP_TOLERANCE,
    DATA_DUPLICATE_MAX,
    DATA_IMBALANCE_MAX,
    DATA_ENTROPY_MIN,
    DATA_SANITY_ACC_MIN,
)


# ═══════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════

def make_node(
    node_id="RTX3050-test",
    gpu_name="NVIDIA GeForce RTX 3050 Laptop GPU",
    cuda_major=12, cuda_minor=4,
    compute_major=8, compute_minor=6,
    fp16=True,
    driver_major=8, driver_minor=6,
    vram_mb=4096.0, sm_count=16,
    optimal_batch=32768, capacity_score=7.3,
    throughput_sps=115000.0,
    dataset_hash="abc123", sample_count=45000,
    feature_dim=256,
    label_distribution=None,
) -> NodeRegistration:
    if label_distribution is None:
        label_distribution = {"0": 22500, "1": 22500}
    return NodeRegistration(
        node_id=node_id,
        gpu_name=gpu_name,
        cuda_major=cuda_major,
        cuda_minor=cuda_minor,
        compute_major=compute_major,
        compute_minor=compute_minor,
        fp16_supported=fp16,
        driver_major=driver_major,
        driver_minor=driver_minor,
        vram_mb=vram_mb,
        sm_count=sm_count,
        optimal_batch=optimal_batch,
        capacity_score=capacity_score,
        throughput_sps=throughput_sps,
        dataset_hash=dataset_hash,
        sample_count=sample_count,
        feature_dim=feature_dim,
        label_distribution=label_distribution,
    )


def setup_authority_with_nodes(n=2):
    """Create authority with n accepted nodes, dataset locked, world locked."""
    auth = ClusterAuthority()
    for i in range(n):
        node = make_node(node_id=f"node-{i}", capacity_score=5.0 + i)
        auth.verify_cuda_node(node)
    auth.enforce_dataset_lock()
    auth.lock_world_size()
    return auth


# ═══════════════════════════════════════════════════════════════════════
# PHASE 1 — CUDA VERIFICATION
# ═══════════════════════════════════════════════════════════════════════

class TestPhase1CudaVerification:
    """Phase 1: Verify CUDA node acceptance and rejection."""

    def test_accept_matching_node(self):
        auth = ClusterAuthority()
        node = make_node()
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.ACCEPTED
        assert node.node_id in auth.nodes

    def test_reject_cuda_major_mismatch(self):
        auth = ClusterAuthority()
        node = make_node(cuda_major=11)
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.REJECTED
        assert "CUDA major mismatch" in result.reject_reason

    def test_reject_compute_capability_mismatch(self):
        auth = ClusterAuthority()
        node = make_node(compute_major=7, compute_minor=0)
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.REJECTED
        assert "Compute capability mismatch" in result.reject_reason

    def test_accept_minor_compute_difference(self):
        """CC difference of 1 minor version should be accepted."""
        auth = ClusterAuthority()
        node = make_node(compute_major=8, compute_minor=5)
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.ACCEPTED

    def test_reject_no_fp16(self):
        auth = ClusterAuthority()
        node = make_node(fp16=False)
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.REJECTED
        assert "FP16" in result.reject_reason

    def test_reject_driver_major_mismatch(self):
        auth = ClusterAuthority()
        node = make_node(driver_major=7)
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.REJECTED
        assert "Driver major mismatch" in result.reject_reason

    def test_reject_driver_minor_mismatch(self):
        auth = ClusterAuthority()
        node = make_node(driver_minor=10)
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.REJECTED
        assert "Driver minor mismatch" in result.reject_reason

    def test_accept_driver_minor_within_tolerance(self):
        auth = ClusterAuthority()
        node = make_node(driver_minor=7)  # diff of 1
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.ACCEPTED

    def test_reject_multiple_reasons(self):
        auth = ClusterAuthority()
        node = make_node(cuda_major=11, fp16=False)
        result = auth.verify_cuda_node(node)
        assert result.status == NodeStatus.REJECTED
        assert "CUDA major" in result.reject_reason
        assert "FP16" in result.reject_reason

    def test_max_nodes_limit(self):
        auth = ClusterAuthority()
        for i in range(10):
            auth.verify_cuda_node(make_node(node_id=f"node-{i}"))
        overflow = make_node(node_id="overflow")
        result = auth.verify_cuda_node(overflow)
        assert result.status == NodeStatus.REJECTED
        assert "full" in result.reject_reason.lower()

    def test_reject_join_after_world_lock(self):
        auth = setup_authority_with_nodes(2)
        late = make_node(node_id="late-joiner")
        result = auth.verify_cuda_node(late)
        assert result.status == NodeStatus.REJECTED
        assert "locked" in result.reject_reason.lower()


# ═══════════════════════════════════════════════════════════════════════
# PHASE 2 — DATASET LOCK
# ═══════════════════════════════════════════════════════════════════════

class TestPhase2DatasetLock:
    """Phase 2: Enforce dataset consensus."""

    def test_lock_matching_datasets(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="n0"))
        auth.verify_cuda_node(make_node(node_id="n1"))
        passed, reason = auth.enforce_dataset_lock()
        assert passed
        assert auth.dataset_lock is not None
        assert auth.dataset_lock.dataset_hash == "abc123"

    def test_abort_on_hash_mismatch(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="n0", dataset_hash="aaa"))
        auth.verify_cuda_node(make_node(node_id="n1", dataset_hash="bbb"))
        passed, reason = auth.enforce_dataset_lock()
        assert not passed
        assert auth.state.aborted
        assert "hash mismatch" in reason

    def test_abort_on_sample_count_mismatch(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="n0", sample_count=1000))
        auth.verify_cuda_node(make_node(node_id="n1", sample_count=2000))
        passed, reason = auth.enforce_dataset_lock()
        assert not passed
        assert "sample_count mismatch" in reason

    def test_abort_on_feature_dim_mismatch(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="n0", feature_dim=128))
        auth.verify_cuda_node(make_node(node_id="n1", feature_dim=256))
        passed, reason = auth.enforce_dataset_lock()
        assert not passed
        assert "feature_dim mismatch" in reason

    def test_abort_on_label_distribution_mismatch(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="n0", label_distribution={"0": 100, "1": 100}))
        auth.verify_cuda_node(make_node(node_id="n1", label_distribution={"0": 50, "1": 150}))
        passed, reason = auth.enforce_dataset_lock()
        assert not passed
        assert "label_distribution mismatch" in reason

    def test_single_node_locks(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="solo"))
        passed, _ = auth.enforce_dataset_lock()
        assert passed

    def test_no_accepted_nodes(self):
        auth = ClusterAuthority()
        passed, _ = auth.enforce_dataset_lock()
        assert not passed


# ═══════════════════════════════════════════════════════════════════════
# PHASE 3 — WORLD SIZE LOCK
# ═══════════════════════════════════════════════════════════════════════

class TestPhase3WorldSizeLock:
    """Phase 3: World size lock and dropout detection."""

    def test_lock_world_size(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="n0"))
        auth.verify_cuda_node(make_node(node_id="n1"))
        auth.enforce_dataset_lock()
        ok, ws = auth.lock_world_size()
        assert ok
        assert ws == 2
        assert auth.state.world_size_locked

    def test_nodes_become_active(self):
        auth = setup_authority_with_nodes(3)
        active = auth._get_active_nodes()
        assert len(active) == 3
        for n in active:
            assert n.status == NodeStatus.ACTIVE

    def test_dropout_aborts(self):
        auth = setup_authority_with_nodes(3)
        ok, reason = auth.check_dropout(["node-0", "node-1"])  # node-2 missing
        assert not ok
        assert auth.state.aborted
        assert "dropout" in reason.lower()

    def test_no_dropout(self):
        auth = setup_authority_with_nodes(2)
        ok, _ = auth.check_dropout(["node-0", "node-1"])
        assert ok

    def test_lock_prevents_new_nodes(self):
        auth = setup_authority_with_nodes(2)
        late = make_node(node_id="late")
        result = auth.verify_cuda_node(late)
        assert result.status == NodeStatus.REJECTED


# ═══════════════════════════════════════════════════════════════════════
# PHASE 4 — SCALING LIMIT
# ═══════════════════════════════════════════════════════════════════════

class TestPhase4ScalingLimit:
    """Phase 4: Scaling efficiency enforcement."""

    def test_skip_small_cluster(self):
        auth = setup_authority_with_nodes(4)
        passed, eff, disabled = auth.enforce_scaling_limit(
            single_gpu_sps=10000, cluster_sps=35000,
        )
        assert passed
        assert eff == 1.0
        assert disabled == []

    def test_pass_efficient_large_cluster(self):
        auth = setup_authority_with_nodes(8)
        # 80% efficiency with 8 nodes
        passed, eff, disabled = auth.enforce_scaling_limit(
            single_gpu_sps=10000, cluster_sps=64000,
        )
        assert passed
        assert eff >= SCALING_EFFICIENCY_THRESHOLD

    def test_disable_nodes_inefficient_cluster(self):
        auth = setup_authority_with_nodes(8)
        # Very low efficiency
        passed, eff, disabled = auth.enforce_scaling_limit(
            single_gpu_sps=10000, cluster_sps=20000,
        )
        assert not passed
        assert eff < SCALING_EFFICIENCY_THRESHOLD
        assert len(disabled) > 0
        # Should be reduced to 6
        assert len(auth._get_active_nodes()) == 6


# ═══════════════════════════════════════════════════════════════════════
# PHASE 5 — MPS SAFETY
# ═══════════════════════════════════════════════════════════════════════

class TestPhase5MPSSafety:
    """Phase 5: MPS delta validation."""

    def test_accept_good_delta(self):
        auth = ClusterAuthority()
        ok, _ = auth.validate_mps_delta(
            node_id="mps-1",
            delta_norm=2.5,
            loss_before=0.5,
            loss_after=0.4,
            val_acc_before=0.9,
            val_acc_after=0.89,
        )
        assert ok

    def test_reject_high_norm(self):
        auth = ClusterAuthority()
        ok, reason = auth.validate_mps_delta(
            node_id="mps-1",
            delta_norm=15.0,
            loss_before=0.5,
            loss_after=0.4,
            val_acc_before=0.9,
            val_acc_after=0.89,
        )
        assert not ok
        assert "delta_norm" in reason

    def test_reject_loss_increase(self):
        auth = ClusterAuthority()
        ok, reason = auth.validate_mps_delta(
            node_id="mps-1",
            delta_norm=2.0,
            loss_before=0.3,
            loss_after=0.4,
            val_acc_before=0.9,
            val_acc_after=0.89,
        )
        assert not ok
        assert "loss increased" in reason

    def test_reject_val_acc_drop(self):
        auth = ClusterAuthority()
        ok, reason = auth.validate_mps_delta(
            node_id="mps-1",
            delta_norm=2.0,
            loss_before=0.5,
            loss_after=0.4,
            val_acc_before=0.9,
            val_acc_after=0.8,  # 10% drop > 5% tolerance
        )
        assert not ok
        assert "val_acc" in reason

    def test_reject_multiple_failures(self):
        auth = ClusterAuthority()
        ok, reason = auth.validate_mps_delta(
            node_id="mps-1",
            delta_norm=15.0,
            loss_before=0.3,
            loss_after=0.5,
            val_acc_before=0.9,
            val_acc_after=0.7,
        )
        assert not ok
        assert "delta_norm" in reason
        assert "loss increased" in reason
        assert "val_acc" in reason


# ═══════════════════════════════════════════════════════════════════════
# PHASE 6 — DATA QUALITY ENFORCEMENT
# ═══════════════════════════════════════════════════════════════════════

class TestPhase6DataQuality:
    """Phase 6: Data quality gate."""

    def test_pass_good_data(self):
        rng = np.random.RandomState(42)
        features = rng.randn(1000, 16).astype(np.float32)
        labels = rng.randint(0, 2, 1000).astype(np.int64)
        auth = ClusterAuthority()
        passed, report = auth.enforce_data_quality(features, labels, sanity_accuracy=0.65)
        assert passed
        assert not report["blocked"]

    def test_block_high_duplicates(self):
        # Create data with >20% duplicates
        base = np.ones((100, 4), dtype=np.float32)
        features = np.vstack([base] * 5)  # 500 rows, all duplicates
        labels = np.array([0] * 250 + [1] * 250, dtype=np.int64)
        auth = ClusterAuthority()
        passed, report = auth.enforce_data_quality(features, labels, sanity_accuracy=0.65)
        assert not passed
        assert report["duplicate_ratio"] > DATA_DUPLICATE_MAX

    def test_block_high_imbalance(self):
        rng = np.random.RandomState(42)
        features = rng.randn(109, 8).astype(np.float32)
        labels = np.array([0] * 100 + [1] * 9, dtype=np.int64)  # 11.1:1
        auth = ClusterAuthority()
        passed, report = auth.enforce_data_quality(features, labels, sanity_accuracy=0.65)
        assert not passed
        assert report["imbalance_ratio"] > DATA_IMBALANCE_MAX

    def test_block_low_sanity_accuracy(self):
        rng = np.random.RandomState(42)
        features = rng.randn(1000, 16).astype(np.float32)
        labels = rng.randint(0, 2, 1000).astype(np.int64)
        auth = ClusterAuthority()
        passed, report = auth.enforce_data_quality(features, labels, sanity_accuracy=0.30)
        assert not passed
        assert "sanity_acc" in str(report["block_reasons"])


# ═══════════════════════════════════════════════════════════════════════
# PHASE 7 — METRIC REPORTING
# ═══════════════════════════════════════════════════════════════════════

class TestPhase7MetricReporting:
    """Phase 7: Structured epoch metric reporting."""

    def test_report_structure(self):
        auth = setup_authority_with_nodes(2)
        metrics = auth.report_epoch_metrics(
            epoch=1,
            cluster_sps=50000.0,
            per_node_batch={"node-0": 16384, "node-1": 32768},
            merged_weight_hash="abc123def456",
            dataset_hash_consensus="deadbeef",
            scaling_efficiency=0.95,
        )
        assert metrics.epoch == 1
        assert metrics.world_size == 2
        assert metrics.total_cluster_samples_per_sec == 50000.0
        assert metrics.merged_weight_hash == "abc123def456"
        assert metrics.dataset_hash_consensus == "deadbeef"
        assert metrics.scaling_efficiency == 0.95

    def test_metrics_accumulate(self):
        auth = setup_authority_with_nodes(2)
        for ep in range(5):
            auth.report_epoch_metrics(
                epoch=ep + 1,
                cluster_sps=40000 + ep * 1000,
                per_node_batch={"node-0": 16384, "node-1": 32768},
                merged_weight_hash=f"hash_{ep}",
                dataset_hash_consensus="ddd",
            )
        assert len(auth.epoch_logs) == 5
        assert auth.epoch_logs[0].epoch == 1
        assert auth.epoch_logs[4].epoch == 5


# ═══════════════════════════════════════════════════════════════════════
# AUTHORITY LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════

class TestAuthorityLifecycle:
    """Test start_training, shard proportions, full report."""

    def test_start_training(self):
        auth = setup_authority_with_nodes(2)
        ok, _ = auth.start_training()
        assert ok
        assert auth.state.training_active

    def test_start_fails_without_dataset_lock(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="n0"))
        auth.lock_world_size()
        ok, reason = auth.start_training()
        assert not ok
        assert "Dataset" in reason

    def test_shard_proportions(self):
        auth = setup_authority_with_nodes(3)
        props = auth.get_shard_proportions()
        assert len(props) == 3
        total = sum(props.values())
        assert abs(total - 1.0) < 1e-4  # Proportions sum to 1

    def test_full_report_structure(self):
        auth = setup_authority_with_nodes(2)
        auth.start_training()
        auth.report_epoch_metrics(
            epoch=1, cluster_sps=50000,
            per_node_batch={"node-0": 16384, "node-1": 32768},
            merged_weight_hash="h", dataset_hash_consensus="d",
        )
        report = auth.get_full_report()
        assert "authority_state" in report
        assert "nodes" in report
        assert "dataset_lock" in report
        assert "shard_proportions" in report
        assert "epoch_logs" in report

    def test_abort_prevents_start(self):
        auth = ClusterAuthority()
        auth.verify_cuda_node(make_node(node_id="n0", dataset_hash="a"))
        auth.verify_cuda_node(make_node(node_id="n1", dataset_hash="b"))
        auth.enforce_dataset_lock()  # Will abort
        ok, reason = auth.start_training()
        assert not ok
        assert "aborted" in reason.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
