"""
test_cluster_authority.py — Tests for Updated ClusterAuthority

Tests the production cluster authority with persistence,
heartbeat monitoring, and quorum validation.
"""

import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from dataclasses import asdict

from impl_v1.training.distributed.cluster_authority import (
    ClusterAuthority,
    ClusterState,
    NodeInfo,
)


def make_node(
    node_id: str = "test-node-1",
    device_name: str = "NVIDIA GeForce RTX 3050",
    device_type: str = "cuda",
    vram_mb: float = 4096.0,
    rank: int = 0,
    baseline_sps: float = 16000.0,
    optimal_batch: int = 32768,
) -> NodeInfo:
    return NodeInfo(
        node_id=node_id,
        device_name=device_name,
        device_type=device_type,
        vram_mb=vram_mb,
        rank=rank,
        baseline_sps=baseline_sps,
        optimal_batch=optimal_batch,
    )


class TestNodeRegistration(unittest.TestCase):
    """Test node registration."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_register_node(self):
        auth = ClusterAuthority(state_path=self.state_path)
        node = make_node()
        ok = auth.register_node(node)
        self.assertTrue(ok)
        self.assertIn("test-node-1", auth.state.active_nodes)

    def test_register_multiple_nodes(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1", rank=0))
        auth.register_node(make_node("n2", rank=1))
        self.assertEqual(len(auth.state.active_nodes), 2)

    def test_reject_when_world_locked_and_full(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1", rank=0))
        auth.lock_world_size(1)
        ok = auth.register_node(make_node("n2", rank=1))
        self.assertFalse(ok)

    def test_deregister_node(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1"))
        auth.deregister_node("n1")
        self.assertNotIn("n1", auth.state.active_nodes)


class TestLocks(unittest.TestCase):
    """Test dataset and world size locks."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_lock_dataset(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.lock_dataset("abc123hash")
        self.assertTrue(auth.state.dataset_locked)
        self.assertEqual(auth.state.dataset_hash, "abc123hash")

    def test_lock_world_size(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1"))
        auth.register_node(make_node("n2", rank=1))
        auth.lock_world_size(2)
        self.assertTrue(auth.state.world_size_locked)
        self.assertEqual(auth.state.world_size, 2)


class TestEpochLifecycle(unittest.TestCase):
    """Test epoch completion and training lifecycle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_start_and_stop_training(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.start_training()
        self.assertTrue(auth.state.training_active)
        auth.stop_training()
        self.assertFalse(auth.state.training_active)

    def test_complete_epoch_healthy(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1", baseline_sps=10000))
        auth.register_node(make_node("n2", rank=1, baseline_sps=8000))
        auth.lock_world_size(2)
        auth.start_training()

        auth.complete_epoch(
            epoch=1,
            merged_weight_hash="whash1",
            cluster_sps=17000.0,
            per_node_sps={"n1": 10000, "n2": 7000},
            baseline_sum=18000.0,
        )
        self.assertEqual(auth.state.epoch_number, 1)
        self.assertGreater(auth.state.scaling_efficiency, 0)

    def test_complete_epoch_degraded(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1"))
        auth.lock_world_size(1)
        auth.start_training()

        auth.complete_epoch(
            epoch=1,
            merged_weight_hash="wh",
            cluster_sps=5000.0,
            per_node_sps={"n1": 5000},
            baseline_sum=10000.0,  # efficiency = 0.5 < 0.7
        )
        self.assertLess(auth.state.scaling_efficiency, 0.7)


class TestPersistence(unittest.TestCase):
    """Test atomic persistence and crash recovery."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_persist_and_reload(self):
        auth1 = ClusterAuthority(state_path=self.state_path)
        auth1.register_node(make_node("n1"))
        auth1.lock_dataset("hash123")
        auth1.lock_world_size(1)
        auth1.start_training()
        auth1.complete_epoch(1, "wh", 10000, {"n1": 10000}, 10000)

        # Load from disk
        auth2 = ClusterAuthority(state_path=self.state_path)
        self.assertEqual(auth2.state.epoch_number, 1)
        self.assertTrue(auth2.state.dataset_locked)
        self.assertEqual(auth2.state.dataset_hash, "hash123")

    def test_state_file_created(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node())
        self.assertTrue(os.path.exists(self.state_path))


class TestQuorum(unittest.TestCase):
    """Test quorum validation after restart."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_quorum_valid(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1"))
        auth.register_node(make_node("n2", rank=1))
        result = auth.validate_quorum(["n1", "n2"])
        self.assertTrue(result['valid'])
        self.assertEqual(len(result['missing']), 0)

    def test_quorum_missing_node(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1"))
        auth.register_node(make_node("n2", rank=1))
        result = auth.validate_quorum(["n1"])  # n2 missing
        self.assertFalse(result['valid'])
        self.assertEqual(len(result['missing']), 1)

    def test_quorum_unexpected_node(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1"))
        result = auth.validate_quorum(["n1", "n3"])  # n3 unexpected
        self.assertTrue(result['valid'])  # All expected present
        self.assertEqual(len(result['unexpected']), 1)


class TestRestart(unittest.TestCase):
    """Test restart from saved state."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_restart_with_checkpoint(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node())
        auth.lock_world_size(1)
        auth.start_training()
        auth.complete_epoch(1, "wh", 10000, {"n1": 10000}, 10000, "ckpt-1")

        ok, msg = auth.restart_from_state()
        self.assertTrue(ok)
        self.assertIn("epoch 2", msg)

    def test_restart_no_checkpoint(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node())
        auth.lock_world_size(1)
        auth.start_training()
        auth.complete_epoch(1, "wh", 10000, {"n1": 10000}, 10000)  # no ckpt

        ok, msg = auth.restart_from_state()
        self.assertFalse(ok)

    def test_restart_fresh_state(self):
        auth = ClusterAuthority(state_path=self.state_path)
        ok, msg = auth.restart_from_state()
        self.assertFalse(ok)


class TestHeartbeat(unittest.TestCase):
    """Test heartbeat monitoring."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_update_heartbeat(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1"))
        auth.update_heartbeat("n1")
        self.assertTrue(auth.state.active_nodes["n1"]['alive'])

    def test_start_stop_heartbeat(self):
        auth = ClusterAuthority(
            state_path=self.state_path,
            heartbeat_interval=0.1,
            heartbeat_timeout=0.5,
        )
        auth.register_node(make_node("n1"))
        auth.start_heartbeat()
        auth.stop_heartbeat()
        self.assertFalse(auth.abort_requested)


class TestReport(unittest.TestCase):
    """Test final report generation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_final_report(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1", device_type="cuda"))
        auth.register_node(make_node("n2", device_type="mps", rank=1))
        auth.lock_dataset("dhash")
        auth.lock_world_size(2)
        auth.start_training()

        report = auth.get_final_report()
        self.assertEqual(report['world_size'], 2)
        self.assertEqual(report['cuda_nodes'], 1)
        self.assertEqual(report['mps_nodes'], 1)
        self.assertEqual(report['dataset_hash'], 'dhash')


class TestShardAllocation(unittest.TestCase):
    """Test shard allocation."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.state_path = os.path.join(self.tmp, 'state.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_allocate_shards(self):
        auth = ClusterAuthority(state_path=self.state_path)
        auth.register_node(make_node("n1"))
        auth.register_node(make_node("n2", rank=1))
        auth.allocate_shards({"n1": 0.6, "n2": 0.4})
        self.assertAlmostEqual(auth.state.shard_proportions["n1"], 0.6)
        self.assertAlmostEqual(auth.state.shard_proportions["n2"], 0.4)


if __name__ == '__main__':
    unittest.main()
