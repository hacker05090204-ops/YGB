"""
test_production_ddp.py — Tests for 7-Phase Production DDP Hardening

All tests mock CUDA/NCCL so they run on any machine.
"""

import json
import os
import sys
import time
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 1 — CLUSTER AUTHORITY
# ===========================================================================

class TestClusterAuthority:

    def test_fresh_start(self, tmp_path):
        from impl_v1.training.distributed.cluster_authority import ClusterAuthority
        auth = ClusterAuthority(
            authority_id="test",
            state_path=str(tmp_path / "state.json"),
        )
        assert auth.state.epoch_number == -1
        assert auth.state.training_active is False

    def test_persist_and_reload(self, tmp_path):
        from impl_v1.training.distributed.cluster_authority import ClusterAuthority
        path = str(tmp_path / "state.json")

        auth = ClusterAuthority(authority_id="test", state_path=path)
        auth.lock_dataset("hash_abc")
        auth.lock_world_size(2)
        auth.complete_epoch(
            epoch=0, merged_weight_hash="wh_123",
            cluster_sps=8000, per_node_sps={"n1": 4000, "n2": 4000},
            baseline_sum=9000,
        )

        # Reload
        auth2 = ClusterAuthority(state_path=path)
        assert auth2.state.dataset_hash == "hash_abc"
        assert auth2.state.world_size == 2
        assert auth2.state.epoch_number == 0
        assert auth2.state.scaling_efficiency > 0

    def test_lock_prevents_extra_nodes(self, tmp_path):
        from impl_v1.training.distributed.cluster_authority import (
            ClusterAuthority, NodeInfo,
        )
        path = str(tmp_path / "state.json")
        auth = ClusterAuthority(state_path=path)
        auth.lock_world_size(1)

        n1 = NodeInfo("n1", "RTX3050", "cuda", 4096, rank=0)
        assert auth.register_node(n1) is True

        n2 = NodeInfo("n2", "RTX2050", "cuda", 4096, rank=1)
        assert auth.register_node(n2) is False

    def test_quorum_validation(self, tmp_path):
        from impl_v1.training.distributed.cluster_authority import (
            ClusterAuthority, NodeInfo,
        )
        path = str(tmp_path / "state.json")
        auth = ClusterAuthority(state_path=path)
        auth.register_node(NodeInfo("n1", "RTX3050", "cuda", 4096, rank=0))
        auth.register_node(NodeInfo("n2", "RTX2050", "cuda", 4096, rank=1))

        # All rejoin
        result = auth.validate_quorum(["n1", "n2"])
        assert result['valid'] is True

        # One missing
        result = auth.validate_quorum(["n1"])
        assert result['valid'] is False
        assert "n2" in result['missing']

    def test_scaling_efficiency_persisted(self, tmp_path):
        from impl_v1.training.distributed.cluster_authority import ClusterAuthority
        path = str(tmp_path / "state.json")
        auth = ClusterAuthority(state_path=path)
        auth.complete_epoch(
            epoch=0, merged_weight_hash="wh",
            cluster_sps=7000, per_node_sps={"n1": 3500, "n2": 3500},
            baseline_sum=10000,
        )
        assert auth.state.scaling_efficiency == 0.7

    def test_restart_from_state(self, tmp_path):
        from impl_v1.training.distributed.cluster_authority import ClusterAuthority
        path = str(tmp_path / "state.json")
        auth = ClusterAuthority(state_path=path)
        auth.complete_epoch(
            epoch=3, merged_weight_hash="wh",
            cluster_sps=9000, per_node_sps={}, baseline_sum=10000,
            checkpoint_id="ckpt_003",
        )
        ok, msg = auth.restart_from_state()
        assert ok is True
        assert "epoch 4" in msg

    def test_heartbeat_no_abort(self, tmp_path):
        from impl_v1.training.distributed.cluster_authority import (
            ClusterAuthority, NodeInfo,
        )
        path = str(tmp_path / "state.json")
        auth = ClusterAuthority(
            state_path=path, heartbeat_interval=0.1, heartbeat_timeout=5.0,
        )
        auth.register_node(NodeInfo("n1", "GPU", "cuda", 4096, rank=0))
        auth.start_heartbeat()
        time.sleep(0.3)
        auth.stop_heartbeat()
        assert auth.abort_requested is False

    def test_final_report(self, tmp_path):
        from impl_v1.training.distributed.cluster_authority import (
            ClusterAuthority, NodeInfo,
        )
        path = str(tmp_path / "state.json")
        auth = ClusterAuthority(state_path=path)
        auth.register_node(NodeInfo("n1", "RTX3050", "cuda", 4096, rank=0))
        auth.register_node(NodeInfo("m1", "M1", "mps", 8192, rank=1))
        auth.complete_epoch(
            epoch=0, merged_weight_hash="wh123",
            cluster_sps=10000, per_node_sps={"n1": 6000, "m1": 4000},
            baseline_sum=11000,
        )
        report = auth.get_final_report()
        assert report['world_size'] == 0  # Not locked
        assert report['cuda_nodes'] == 1
        assert report['mps_nodes'] == 1


# ===========================================================================
# PHASE 2 — STRICT DETERMINISM (DRIVER VERSION)
# ===========================================================================

class TestStrictDeterminismUpgrade:

    def test_driver_version_match_passes(self):
        from impl_v1.training.distributed.strict_determinism import (
            DeterminismConfig, validate_cluster_determinism,
        )
        auth = DeterminismConfig(
            node_id="auth", cuda_version="12.1",
            cublas_workspace_config=":4096:8",
            allow_tf32=False, cudnn_allow_tf32=False,
            cudnn_deterministic=True, cudnn_benchmark=False,
            deterministic_algorithms=True, driver_version="550.120",
        )
        nodes = {
            "n1": DeterminismConfig(
                node_id="n1", cuda_version="12.1",
                cublas_workspace_config=":4096:8",
                allow_tf32=False, cudnn_allow_tf32=False,
                cudnn_deterministic=True, cudnn_benchmark=False,
                deterministic_algorithms=True, driver_version="550.80",
            ),
        }
        result = validate_cluster_determinism(auth, nodes)
        assert result.passed is True  # Major version 550 matches

    def test_driver_version_mismatch_rejected(self):
        from impl_v1.training.distributed.strict_determinism import (
            DeterminismConfig, validate_cluster_determinism,
        )
        auth = DeterminismConfig(
            node_id="auth", cuda_version="12.1",
            cublas_workspace_config=":4096:8",
            allow_tf32=False, cudnn_allow_tf32=False,
            cudnn_deterministic=True, cudnn_benchmark=False,
            deterministic_algorithms=True, driver_version="550.120",
        )
        nodes = {
            "bad": DeterminismConfig(
                node_id="bad", cuda_version="12.1",
                cublas_workspace_config=":4096:8",
                allow_tf32=False, cudnn_allow_tf32=False,
                cudnn_deterministic=True, cudnn_benchmark=False,
                deterministic_algorithms=True, driver_version="470.80",
            ),
        }
        result = validate_cluster_determinism(auth, nodes)
        assert result.passed is False
        assert "bad" in result.rejected_nodes


# ===========================================================================
# PHASE 4 — SANITY GATE
# ===========================================================================

class TestSanityGate:

    def test_gate_passes_random_data(self, tmp_path):
        from impl_v1.training.distributed.sanity_gate import (
            run_sanity_gate, gate_allows_training,
        )
        rng = np.random.RandomState(42)
        X = rng.randn(500, 64).astype(np.float32)
        y = rng.randint(0, 2, 500).astype(np.int64)

        path = str(tmp_path / "sanity.json")
        result = run_sanity_gate(
            X, y, dataset_hash="test_hash",
            input_dim=64, batch_size=128, result_path=path,
        )
        assert result.passed is True
        assert os.path.exists(path)
        assert gate_allows_training(path) is True

    def test_persistence_and_reload(self, tmp_path):
        from impl_v1.training.distributed.sanity_gate import (
            run_sanity_gate, load_sanity_result,
        )
        rng = np.random.RandomState(42)
        X = rng.randn(500, 64).astype(np.float32)
        y = rng.randint(0, 2, 500).astype(np.int64)

        path = str(tmp_path / "sanity.json")
        run_sanity_gate(X, y, "h", input_dim=64, batch_size=128, result_path=path)

        loaded = load_sanity_result(path)
        assert loaded is not None
        assert loaded.num_samples == 500

    def test_gate_not_run_returns_false(self, tmp_path):
        from impl_v1.training.distributed.sanity_gate import gate_allows_training
        assert gate_allows_training(str(tmp_path / "nonexistent.json")) is False


# ===========================================================================
# PHASE 5 — PRODUCTION DDP LAUNCHER
# ===========================================================================

class TestProductionDDPLauncher:

    def test_setup_env(self):
        from impl_v1.training.distributed.production_ddp_launcher import (
            setup_production_env,
        )
        setup_production_env()
        assert os.environ.get("YGB_CLUSTER_MODE") == "auto"
        assert os.environ.get("YGB_ENV") == "production"
        assert os.environ.get("CUBLAS_WORKSPACE_CONFIG") == ":4096:8"

    def test_single_epoch_cpu(self):
        from impl_v1.training.distributed.production_ddp_launcher import (
            DDPLaunchConfig, run_single_epoch,
        )
        config = DDPLaunchConfig(
            rank=0, world_size=1, input_dim=64,
            num_classes=2, batch_size=128,
        )
        metrics = run_single_epoch(config)
        assert metrics.local_sps > 0
        assert len(metrics.weight_hash) == 64

    def test_deterministic_validation(self):
        from impl_v1.training.distributed.production_ddp_launcher import (
            DDPLaunchConfig, run_deterministic_validation,
        )
        config = DDPLaunchConfig(
            rank=0, world_size=1, input_dim=64,
            num_classes=2, batch_size=128,
            deterministic_runs=3,
        )
        match, hashes = run_deterministic_validation(config, num_runs=3)
        assert match is True
        assert len(hashes) == 3
        assert len(set(hashes)) == 1

    def test_full_report(self):
        from impl_v1.training.distributed.production_ddp_launcher import (
            DDPLaunchConfig, launch_production_ddp,
        )
        config = DDPLaunchConfig(
            rank=0, world_size=1, input_dim=64,
            num_classes=2, batch_size=128,
            deterministic_runs=2,
        )
        report = launch_production_ddp(
            config,
            node0_baseline_sps=5000, node1_baseline_sps=4000,
            authority_resumed=False,
        )
        assert report.world_size == 1
        assert report.determinism_match is True
        assert len(report.merged_weight_hash) == 64


# ===========================================================================
# PHASE 6 — STRICT CHECKPOINT CONSENSUS
# ===========================================================================

class TestStrictCheckpointConsensus:

    def test_strict_all_must_ack(self):
        from impl_v1.training.distributed.checkpoint_consensus import (
            create_consensus_checkpoint, submit_node_ack,
        )
        ckpt = create_consensus_checkpoint(
            epoch=0, dataset_hash="ds",
            merged_weight_hash="wh",
            world_size=3,
            shard_proportions={"n1": 0.33, "n2": 0.33, "n3": 0.34},
            strict=True,
        )
        assert ckpt.required_count == 3

        submit_node_ack(ckpt, "n1", "wh")
        assert ckpt.majority_reached is False  # 1/3

        submit_node_ack(ckpt, "n2", "wh")
        assert ckpt.majority_reached is False  # 2/3

        submit_node_ack(ckpt, "n3", "wh")
        assert ckpt.majority_reached is True   # 3/3

    def test_strict_mismatch_blocks(self):
        from impl_v1.training.distributed.checkpoint_consensus import (
            create_consensus_checkpoint, submit_node_ack, can_advance,
        )
        ckpt = create_consensus_checkpoint(
            epoch=0, dataset_hash="ds",
            merged_weight_hash="wh_correct",
            world_size=2,
            shard_proportions={"n1": 0.5, "n2": 0.5},
            strict=True,
        )
        submit_node_ack(ckpt, "n1", "wh_correct")
        submit_node_ack(ckpt, "n2", "WRONG_HASH")
        assert can_advance(ckpt) is False

    def test_non_strict_majority(self):
        from impl_v1.training.distributed.checkpoint_consensus import (
            create_consensus_checkpoint, submit_node_ack,
        )
        ckpt = create_consensus_checkpoint(
            epoch=0, dataset_hash="ds",
            merged_weight_hash="wh",
            world_size=3,
            shard_proportions={},
            strict=False,
        )
        assert ckpt.required_count == 2  # Majority

        submit_node_ack(ckpt, "n1", "wh")
        submit_node_ack(ckpt, "n2", "wh")
        assert ckpt.majority_reached is True  # 2/3 sufficient


# ===========================================================================
# PHASE 7 — FAILURE RESILIENCE
# ===========================================================================

class TestFailureResilience:

    def test_dropout_detection(self):
        from impl_v1.training.distributed.failure_resilience import (
            NodeDropoutDetector,
        )
        detector = NodeDropoutDetector(timeout_sec=1.0, check_interval=0.3)
        detector.register_node("n1")
        detector.register_node("n2")
        detector.start_monitoring(current_epoch=0)

        # Kill n1
        detector.kill_node("n1", reason="test")
        time.sleep(0.8)

        detector.stop_monitoring()
        assert detector.has_dropouts is True
        assert any(d.node_id == "n1" for d in detector.dropouts)

    def test_safe_abort(self):
        from impl_v1.training.distributed.failure_resilience import (
            NodeDropoutDetector, safe_abort_training,
        )
        detector = NodeDropoutDetector(timeout_sec=1.0, check_interval=0.3)
        detector.register_node("n1")
        detector.kill_node("n1")
        detector.start_monitoring()
        time.sleep(0.8)

        report = safe_abort_training(
            authority=None, detector=detector,
            reason="Test abort",
        )
        assert report.training_aborted is True
        assert report.nccl_cleaned is True

    def test_failure_simulator(self):
        from impl_v1.training.distributed.failure_resilience import (
            FailureSimulator,
        )
        sim = FailureSimulator(authority=None)
        report = sim.simulate_node_kill("test_node", delay_sec=0.2, epoch=5)

        assert report.failure_detected is True
        assert report.training_aborted is True
        assert any(d.node_id == "test_node" for d in report.dropout_nodes)

    def test_failure_log_persisted(self, tmp_path):
        from impl_v1.training.distributed import failure_resilience
        from impl_v1.training.distributed.failure_resilience import FailureSimulator
        original = failure_resilience.FAILURE_LOG_PATH
        failure_resilience.FAILURE_LOG_PATH = str(tmp_path / "fail.json")

        try:
            sim = FailureSimulator(authority=None)
            sim.simulate_node_kill("n_fail", delay_sec=0.1)
            assert os.path.exists(failure_resilience.FAILURE_LOG_PATH)
        finally:
            failure_resilience.FAILURE_LOG_PATH = original


# ===========================================================================
# INTEGRATION — FULL PIPELINE
# ===========================================================================

class TestIntegration:

    def test_authority_epoch_then_consensus(self, tmp_path):
        """Authority completes epoch, then strict consensus must pass."""
        from impl_v1.training.distributed.cluster_authority import ClusterAuthority
        from impl_v1.training.distributed.checkpoint_consensus import (
            run_epoch_consensus,
        )

        auth = ClusterAuthority(state_path=str(tmp_path / "s.json"))
        auth.complete_epoch(
            epoch=0, merged_weight_hash="wh_abc",
            cluster_sps=8000, per_node_sps={"n1": 4000, "n2": 4000},
            baseline_sum=9000,
        )

        ckpt = run_epoch_consensus(
            epoch=0, dataset_hash="ds", merged_weight_hash="wh_abc",
            world_size=2, shard_proportions={"n1": 0.5, "n2": 0.5},
            node_weight_hashes={"n1": "wh_abc", "n2": "wh_abc"},
        )
        assert ckpt.majority_reached is True

    def test_authority_failure_and_resume(self, tmp_path):
        """Authority crashes, restarts, validates quorum."""
        from impl_v1.training.distributed.cluster_authority import (
            ClusterAuthority, NodeInfo,
        )

        path = str(tmp_path / "state.json")
        auth1 = ClusterAuthority(state_path=path)
        auth1.register_node(NodeInfo("n1", "RTX3050", "cuda", 4096, 0))
        auth1.register_node(NodeInfo("n2", "RTX2050", "cuda", 4096, 1))
        auth1.lock_world_size(2)
        auth1.lock_dataset("ds_hash")
        auth1.complete_epoch(
            epoch=2, merged_weight_hash="wh",
            cluster_sps=8000, per_node_sps={"n1": 4000, "n2": 4000},
            baseline_sum=9000, checkpoint_id="ckpt_002",
        )

        # Simulate crash + restart
        del auth1
        auth2 = ClusterAuthority(state_path=path)
        ok, msg = auth2.restart_from_state()
        assert ok is True

        quorum = auth2.validate_quorum(["n1", "n2"])
        assert quorum['valid'] is True
        assert quorum['resume_epoch'] == 3
