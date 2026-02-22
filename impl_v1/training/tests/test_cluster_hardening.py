"""
test_cluster_hardening.py — Tests for 9-Phase Cluster Hardening

All tests mock CUDA/NCCL so they run on any machine.
"""

import json
import os
import sys
import tempfile
import time
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 1 — AUTHORITY RESILIENCE
# ===========================================================================

class TestAuthorityStateManager:

    def test_persist_and_reload(self, tmp_path):
        from impl_v1.training.distributed.authority_state_manager import (
            AuthorityState, persist_state, reload_state,
        )
        path = str(tmp_path / "authority_state.json")
        state = AuthorityState(
            dataset_hash="abc123", dataset_locked=True,
            world_size=3, world_size_locked=True,
            last_completed_epoch=5,
        )
        persist_state(state, path)
        reloaded = reload_state(path)

        assert reloaded is not None
        assert reloaded.dataset_hash == "abc123"
        assert reloaded.world_size == 3
        assert reloaded.last_completed_epoch == 5

    def test_lock_dataset(self, tmp_path):
        from impl_v1.training.distributed.authority_state_manager import (
            AuthorityState, lock_dataset,
        )
        os.environ['_AUTH_TEST_PATH'] = str(tmp_path / "state.json")
        state = AuthorityState()
        state = lock_dataset(state, "hash123")
        assert state.dataset_locked is True
        assert state.dataset_hash == "hash123"

    def test_validate_rejoin_missing(self):
        from impl_v1.training.distributed.authority_state_manager import (
            AuthorityState, validate_rejoin,
        )
        state = AuthorityState(
            node_registry={"node_a": {}, "node_b": {}, "node_c": {}},
        )
        result = validate_rejoin(state, ["node_a", "node_b"])
        assert result['valid'] is False
        assert "node_c" in result['missing']

    def test_validate_rejoin_all_present(self):
        from impl_v1.training.distributed.authority_state_manager import (
            AuthorityState, validate_rejoin,
        )
        state = AuthorityState(
            node_registry={"node_a": {}, "node_b": {}},
        )
        result = validate_rejoin(state, ["node_a", "node_b"])
        assert result['valid'] is True
        assert len(result['missing']) == 0

    def test_heartbeat_quorum_ok(self):
        from impl_v1.training.distributed.authority_state_manager import (
            AuthorityState, AuthorityHeartbeat,
        )
        state = AuthorityState(
            node_registry={
                "n1": {"alive": True},
                "n2": {"alive": True},
            },
        )
        hb = AuthorityHeartbeat(state, interval_sec=0.1)
        hb.start()
        time.sleep(0.3)
        hb.stop()
        assert hb.quorum_lost is False


# ===========================================================================
# PHASE 2 — STRICT DETERMINISM LOCK
# ===========================================================================

class TestStrictDeterminism:

    def test_cluster_validation_pass(self):
        from impl_v1.training.distributed.strict_determinism import (
            DeterminismConfig, validate_cluster_determinism,
        )
        auth = DeterminismConfig(
            node_id="auth", cuda_version="12.1",
            cublas_workspace_config=":4096:8",
            allow_tf32=False, cudnn_allow_tf32=False,
            cudnn_deterministic=True, cudnn_benchmark=False,
            deterministic_algorithms=True,
        )
        nodes = {
            "n1": DeterminismConfig(
                node_id="n1", cuda_version="12.1",
                cublas_workspace_config=":4096:8",
                allow_tf32=False, cudnn_allow_tf32=False,
                cudnn_deterministic=True, cudnn_benchmark=False,
                deterministic_algorithms=True,
            ),
        }
        result = validate_cluster_determinism(auth, nodes)
        assert result.passed is True
        assert len(result.rejected_nodes) == 0

    def test_cuda_version_mismatch_rejected(self):
        from impl_v1.training.distributed.strict_determinism import (
            DeterminismConfig, validate_cluster_determinism,
        )
        auth = DeterminismConfig(
            node_id="auth", cuda_version="12.1",
            cublas_workspace_config=":4096:8",
            allow_tf32=False, cudnn_allow_tf32=False,
            cudnn_deterministic=True, cudnn_benchmark=False,
            deterministic_algorithms=True,
        )
        nodes = {
            "bad_node": DeterminismConfig(
                node_id="bad_node", cuda_version="11.8",
                cublas_workspace_config=":4096:8",
                allow_tf32=False, cudnn_allow_tf32=False,
                cudnn_deterministic=True, cudnn_benchmark=False,
                deterministic_algorithms=True,
            ),
        }
        result = validate_cluster_determinism(auth, nodes)
        assert result.passed is False
        assert "bad_node" in result.rejected_nodes

    def test_tf32_enabled_rejected(self):
        from impl_v1.training.distributed.strict_determinism import (
            DeterminismConfig, validate_cluster_determinism,
        )
        auth = DeterminismConfig(
            node_id="auth", cuda_version="12.1",
            cublas_workspace_config=":4096:8",
            allow_tf32=False, cudnn_allow_tf32=False,
            cudnn_deterministic=True, cudnn_benchmark=False,
            deterministic_algorithms=True,
        )
        nodes = {
            "tf32_node": DeterminismConfig(
                node_id="tf32_node", cuda_version="12.1",
                cublas_workspace_config=":4096:8",
                allow_tf32=True, cudnn_allow_tf32=False,
                cudnn_deterministic=True, cudnn_benchmark=False,
                deterministic_algorithms=True,
            ),
        }
        result = validate_cluster_determinism(auth, nodes)
        assert result.passed is False


# ===========================================================================
# PHASE 3 — SCALING EFFICIENCY
# ===========================================================================

class TestScalingEfficiency:

    def test_healthy_efficiency(self):
        from impl_v1.training.distributed.scaling_efficiency import measure_efficiency
        m = measure_efficiency(
            epoch=0, cluster_sps=9000.0,
            per_node_sps={"n1": 5000, "n2": 4000},
            single_node_baselines={"n1": 5500, "n2": 4500},
        )
        assert m.efficiency > 0.7
        assert m.degraded is False

    def test_degraded_efficiency(self):
        from impl_v1.training.distributed.scaling_efficiency import measure_efficiency
        m = measure_efficiency(
            epoch=0, cluster_sps=3000.0,
            per_node_sps={"n1": 2000, "n2": 1000},
            single_node_baselines={"n1": 5000, "n2": 5000},
        )
        assert m.efficiency < 0.7
        assert m.degraded is True

    def test_weakest_node_identified(self):
        from impl_v1.training.distributed.scaling_efficiency import (
            measure_efficiency, should_disable_node,
        )
        m = measure_efficiency(
            epoch=0, cluster_sps=4000.0,
            per_node_sps={"n1": 3500, "n2": 500},
            single_node_baselines={"n1": 5000, "n2": 5000},
        )
        assert m.weakest_node == "n2"
        disable, reason = should_disable_node(m, min_sps_ratio=0.3)
        assert disable is True


# ===========================================================================
# PHASE 5 — DATASET SANITY
# ===========================================================================

class TestDatasetSanity:

    def test_no_leakage(self):
        from impl_v1.training.distributed.dataset_sanity import check_train_test_overlap
        rng = np.random.RandomState(42)
        X_train = rng.randn(100, 10).astype(np.float32)
        X_test = rng.randn(50, 10).astype(np.float32)

        result = check_train_test_overlap(X_train, X_test)
        assert result.passed is True
        assert result.overlap_count == 0

    def test_leakage_detected(self):
        from impl_v1.training.distributed.dataset_sanity import check_train_test_overlap
        rng = np.random.RandomState(42)
        X_train = rng.randn(100, 10).astype(np.float32)
        X_test = X_train[:10].copy()  # Direct copy = leakage

        result = check_train_test_overlap(X_train, X_test)
        assert result.passed is False
        assert result.overlap_count == 10

    def test_combined_sanity_no_test(self):
        from impl_v1.training.distributed.dataset_sanity import run_full_sanity_check
        rng = np.random.RandomState(42)
        X = rng.randn(500, 64).astype(np.float32)
        y = rng.randint(0, 2, 500).astype(np.int64)

        result = run_full_sanity_check(X, y, input_dim=64, batch_size=128)
        # Shuffle test should pass for random data
        assert result.shuffle_test is not None


# ===========================================================================
# PHASE 6 — CHECKPOINT CONSENSUS
# ===========================================================================

class TestCheckpointConsensus:

    def test_majority_reached(self):
        from impl_v1.training.distributed.checkpoint_consensus import (
            run_epoch_consensus,
        )
        ckpt = run_epoch_consensus(
            epoch=0, dataset_hash="ds_abc",
            merged_weight_hash="wh_123",
            world_size=3,
            shard_proportions={"n1": 0.33, "n2": 0.33, "n3": 0.34},
            node_weight_hashes={
                "n1": "wh_123", "n2": "wh_123", "n3": "wh_123",
            },
        )
        assert ckpt.majority_reached is True
        assert ckpt.confirmed_count == 3

    def test_majority_fails(self):
        from impl_v1.training.distributed.checkpoint_consensus import (
            run_epoch_consensus,
        )
        ckpt = run_epoch_consensus(
            epoch=0, dataset_hash="ds_abc",
            merged_weight_hash="wh_123",
            world_size=3,
            shard_proportions={"n1": 0.33, "n2": 0.33, "n3": 0.34},
            node_weight_hashes={
                "n1": "wh_123", "n2": "WRONG", "n3": "WRONG",
            },
        )
        assert ckpt.majority_reached is False
        assert ckpt.confirmed_count == 1

    def test_consensus_persistence(self, tmp_path):
        from impl_v1.training.distributed.checkpoint_consensus import (
            ConsensusState, persist_consensus_state, load_consensus_state,
        )
        path = str(tmp_path / "consensus.json")
        state = ConsensusState(current_epoch=5)
        persist_consensus_state(state, path)
        loaded = load_consensus_state(path)
        assert loaded.current_epoch == 5


# ===========================================================================
# PHASE 7 — DEVICE LIMIT POLICY
# ===========================================================================

class TestDeviceLimitPolicy:

    def test_below_soft_limit_approved(self):
        from impl_v1.training.distributed.device_limit_policy import (
            evaluate_scale_request, ScaleRequest,
        )
        nodes = [{"id": f"n{i}"} for i in range(3)]
        req = ScaleRequest("n4", "RTX 3050", 4096, 5000)
        decision = evaluate_scale_request(
            nodes, req,
            current_baselines={}, current_cluster_sps=0,
        )
        assert decision.approved is True
        assert decision.benchmark_required is False

    def test_above_hard_limit_denied(self):
        from impl_v1.training.distributed.device_limit_policy import (
            evaluate_scale_request, ScaleRequest,
        )
        nodes = [{"id": f"n{i}"} for i in range(10)]
        req = ScaleRequest("n11", "RTX 3050", 4096, 5000)
        decision = evaluate_scale_request(
            nodes, req,
            current_baselines={}, current_cluster_sps=0,
        )
        assert decision.approved is False

    def test_above_soft_limit_benchmark(self):
        from impl_v1.training.distributed.device_limit_policy import (
            evaluate_scale_request, ScaleRequest,
        )
        nodes = [{"id": f"n{i}"} for i in range(7)]
        req = ScaleRequest("n8", "RTX 2050", 4096, 4000)
        baselines = {f"n{i}": 5000.0 for i in range(7)}
        decision = evaluate_scale_request(
            nodes, req, baselines, current_cluster_sps=30000,
        )
        assert decision.benchmark_required is True


# ===========================================================================
# PHASE 8 — MPS ISOLATION
# ===========================================================================

class TestMPSIsolationGuard:

    def test_valid_delta_accepted(self):
        from impl_v1.training.distributed.mps_isolation_guard import (
            validate_mps_delta, MPSDeltaSubmission,
        )
        sub = MPSDeltaSubmission(
            node_id="mps1", delta={}, delta_norm=2.0,
            loss_before=1.0, loss_after=0.8,
            val_acc_before=0.85, val_acc_after=0.87,
            epoch=0,
        )
        result = validate_mps_delta(sub)
        assert result.accepted is True

    def test_high_norm_rejected(self):
        from impl_v1.training.distributed.mps_isolation_guard import (
            validate_mps_delta, MPSDeltaSubmission,
        )
        sub = MPSDeltaSubmission(
            node_id="mps1", delta={}, delta_norm=50.0,
            loss_before=1.0, loss_after=0.9,
            val_acc_before=0.85, val_acc_after=0.86,
            epoch=0,
        )
        result = validate_mps_delta(sub)
        assert result.accepted is False
        assert result.delta_norm_ok is False

    def test_loss_diverged_rejected(self):
        from impl_v1.training.distributed.mps_isolation_guard import (
            validate_mps_delta, MPSDeltaSubmission,
        )
        sub = MPSDeltaSubmission(
            node_id="mps1", delta={}, delta_norm=2.0,
            loss_before=1.0, loss_after=5.0,
            val_acc_before=0.85, val_acc_after=0.30,
            epoch=0,
        )
        result = validate_mps_delta(sub)
        assert result.accepted is False

    def test_outlier_detection(self):
        from impl_v1.training.distributed.mps_isolation_guard import (
            detect_outlier_deltas, MPSDeltaSubmission,
        )
        subs = [
            MPSDeltaSubmission("n1", {}, 2.0, 1.0, 0.9, 0.85, 0.86, 0),
            MPSDeltaSubmission("n2", {}, 2.0, 1.0, 0.9, 0.85, 0.86, 0),
            MPSDeltaSubmission("n3", {}, 2.0, 1.0, 0.9, 0.85, 0.86, 0),
            MPSDeltaSubmission("n4", {}, 2.0, 1.0, 0.9, 0.85, 0.86, 0),
            MPSDeltaSubmission("n5", {}, 2.0, 1.0, 0.9, 0.85, 0.86, 0),
            MPSDeltaSubmission("outlier", {}, 500.0, 1.0, 0.9, 0.85, 0.86, 0),
        ]
        outliers = detect_outlier_deltas(subs, sigma_threshold=2.0)
        assert "outlier" in outliers

    def test_batch_validation(self):
        from impl_v1.training.distributed.mps_isolation_guard import (
            validate_all_mps_deltas, MPSDeltaSubmission,
        )
        subs = [
            MPSDeltaSubmission("n1", {}, 2.0, 1.0, 0.9, 0.85, 0.86, 0),
            MPSDeltaSubmission("n2", {}, 50.0, 1.0, 5.0, 0.85, 0.30, 0),
        ]
        report = validate_all_mps_deltas(subs, epoch=0)
        assert report.accepted == 1
        assert report.rejected == 1
        assert "n2" in report.rejected_nodes


# ===========================================================================
# PHASE 9 — FULL METRIC REPORTING
# ===========================================================================

class TestClusterMetricsReport:

    def test_build_report(self):
        from impl_v1.training.distributed.cluster_metrics_report import (
            build_cluster_report,
        )
        report = build_cluster_report(
            world_size=4,
            cuda_node_ids=["n1", "n2", "n3"],
            mps_node_ids=["m1"],
            cluster_sps=15200.5,
            scaling_efficiency=0.87,
            merged_weight_hash="abc123",
            dataset_hash="def456",
            determinism_match=True,
            final_accuracy=0.943,
            train_accuracy=0.955,
            val_accuracy=0.943,
            total_epochs=10,
            total_time_sec=120.5,
        )
        assert report.world_size == 4
        assert report.cuda_nodes == 3
        assert report.mps_nodes == 1
        assert report.overfit_gap == round(0.955 - 0.943, 6)

    def test_emit_report(self, tmp_path):
        from impl_v1.training.distributed.cluster_metrics_report import (
            build_cluster_report, emit_report,
        )
        path = str(tmp_path / "report.json")
        report = build_cluster_report(
            world_size=2, cuda_node_ids=["n1", "n2"],
            mps_node_ids=[], cluster_sps=8000, scaling_efficiency=0.9,
            merged_weight_hash="hash1", dataset_hash="hash2",
        )
        d = emit_report(report, path)
        assert os.path.exists(path)
        assert d["world_size"] == 2

        with open(path) as f:
            saved = json.load(f)
        assert saved["cluster_sps"] == 8000
