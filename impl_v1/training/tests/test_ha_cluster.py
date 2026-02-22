"""
test_ha_cluster.py — Tests for 9-Phase HA Cluster

All tests mock CUDA/NCCL so they run on any machine.
"""

import json
import os
import sys
import time
from dataclasses import asdict

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 3 — CHECKPOINT VERSIONING
# ===========================================================================

class TestCheckpointVersioning:

    def test_create_versioned_checkpoint(self):
        from impl_v1.training.distributed.checkpoint_versioning import (
            create_versioned_checkpoint,
        )
        ckpt = create_versioned_checkpoint(
            term=3, epoch=5, dataset_hash="dh",
            merged_weight_hash="wh", world_size=2,
            shard_proportions={"n1": 0.5, "n2": 0.5},
            fencing_token=7,
        )
        assert ckpt.term == 3
        assert ckpt.epoch == 5
        assert ckpt.fencing_token == 7

    def test_reject_stale_term(self):
        from impl_v1.training.distributed.checkpoint_versioning import (
            create_versioned_checkpoint, validate_checkpoint,
        )
        ckpt = create_versioned_checkpoint(
            term=2, epoch=5, dataset_hash="dh",
            merged_weight_hash="wh", world_size=2,
            shard_proportions={},
        )
        valid, reason = validate_checkpoint(ckpt, current_term=5)
        assert valid is False
        assert "Stale" in reason

    def test_accept_current_term(self):
        from impl_v1.training.distributed.checkpoint_versioning import (
            create_versioned_checkpoint, validate_checkpoint,
        )
        ckpt = create_versioned_checkpoint(
            term=5, epoch=3, dataset_hash="dh",
            merged_weight_hash="wh", world_size=2,
            shard_proportions={},
        )
        valid, _ = validate_checkpoint(ckpt, current_term=5)
        assert valid is True

    def test_reject_stale_fence(self):
        from impl_v1.training.distributed.checkpoint_versioning import (
            create_versioned_checkpoint, validate_checkpoint,
        )
        ckpt = create_versioned_checkpoint(
            term=5, epoch=3, dataset_hash="dh",
            merged_weight_hash="wh", world_size=2,
            shard_proportions={}, fencing_token=2,
        )
        valid, reason = validate_checkpoint(ckpt, current_term=5, current_fencing_token=10)
        assert valid is False
        assert "fence" in reason.lower()

    def test_save_and_load(self, tmp_path):
        from impl_v1.training.distributed.checkpoint_versioning import (
            create_versioned_checkpoint, save_versioned_checkpoint,
            load_latest_checkpoint,
        )
        ckpt = create_versioned_checkpoint(
            term=1, epoch=0, dataset_hash="dh",
            merged_weight_hash="wh", world_size=2,
            shard_proportions={},
        )
        save_versioned_checkpoint(ckpt, str(tmp_path))
        loaded = load_latest_checkpoint(str(tmp_path))
        assert loaded is not None
        assert loaded.term == 1


# ===========================================================================
# PHASE 4 — DATA SYNC QUEUE
# ===========================================================================

class TestDataSyncQueue:

    def test_queue_and_sync(self, tmp_path):
        from impl_v1.training.distributed.data_sync_queue import (
            queue_update, sync_entry, get_pending_entries,
        )
        # Create source file
        src = str(tmp_path / "source.bin")
        with open(src, 'wb') as f:
            f.write(b"test data content")

        target = str(tmp_path / "target" / "dest.bin")
        queue_dir = str(tmp_path / "queue")

        entry = queue_update(src, target, version=1, queue_dir=queue_dir)
        assert entry.synced is False

        pending = get_pending_entries(queue_dir)
        assert len(pending) == 1

        ok, reason = sync_entry(entry, queue_dir)
        assert ok is True
        assert os.path.exists(target)

    def test_version_conflict(self, tmp_path):
        from impl_v1.training.distributed.data_sync_queue import (
            queue_update, sync_entry,
        )
        src = str(tmp_path / "source.bin")
        with open(src, 'wb') as f:
            f.write(b"data")

        target = str(tmp_path / "target" / "dest.bin")
        queue_dir = str(tmp_path / "queue")

        # First sync v2
        entry1 = queue_update(src, target, version=2, queue_dir=queue_dir)
        sync_entry(entry1, queue_dir)

        # Try to sync v1 (older) — should fail
        entry2 = queue_update(src, target, version=1, queue_dir=queue_dir)
        ok, reason = sync_entry(entry2, queue_dir)
        assert ok is False
        assert "Version conflict" in reason

    def test_clear_synced(self, tmp_path):
        from impl_v1.training.distributed.data_sync_queue import (
            queue_update, sync_entry, clear_synced_entries,
            get_pending_entries,
        )
        src = str(tmp_path / "source.bin")
        with open(src, 'wb') as f:
            f.write(b"data")

        target = str(tmp_path / "target" / "dest.bin")
        queue_dir = str(tmp_path / "queue")

        entry = queue_update(src, target, version=1, queue_dir=queue_dir)
        sync_entry(entry, queue_dir)
        removed = clear_synced_entries(queue_dir)
        assert removed == 1


# ===========================================================================
# PHASE 5 — IDLE RESOURCE SCHEDULER
# ===========================================================================

class TestIdleResourceScheduler:

    def test_not_idle_by_default(self):
        from impl_v1.training.distributed.idle_resource_scheduler import (
            IdleResourceScheduler, ResourceSnapshot,
        )
        sched = IdleResourceScheduler(idle_duration=0.1)
        snap = ResourceSnapshot(gpu_util_pct=80, cpu_util_pct=60, gpu_temp_c=50)
        assert sched.is_idle(snap) is False

    def test_idle_after_duration(self):
        from impl_v1.training.distributed.idle_resource_scheduler import (
            IdleResourceScheduler, ResourceSnapshot,
        )
        sched = IdleResourceScheduler(idle_duration=0.1)
        snap = ResourceSnapshot(gpu_util_pct=5, cpu_util_pct=10, gpu_temp_c=50)

        # First check starts timer
        assert sched.is_idle(snap) is False
        time.sleep(0.2)
        # Second check after duration
        assert sched.is_idle(snap) is True

    def test_owner_override(self):
        from impl_v1.training.distributed.idle_resource_scheduler import (
            IdleResourceScheduler, ResourceSnapshot, ScheduledTask,
        )
        sched = IdleResourceScheduler(idle_duration=0.0)
        snap = ResourceSnapshot(gpu_util_pct=5, cpu_util_pct=10, gpu_temp_c=50)

        task = ScheduledTask("t1", "bg_task", priority=1, requires_gpu=False)
        sched.add_task(task)

        sched.owner_override()
        assert sched.is_idle(snap) is False

        summary = sched.get_task_summary()
        assert summary['total'] == 1

    def test_run_tasks_when_idle(self):
        from impl_v1.training.distributed.idle_resource_scheduler import (
            IdleResourceScheduler, ResourceSnapshot, ScheduledTask,
        )
        sched = IdleResourceScheduler(idle_duration=0.0)
        snap = ResourceSnapshot(
            gpu_util_pct=5, cpu_util_pct=10,
            gpu_temp_c=50, gpu_memory_used_pct=20,
        )

        ran = []
        task = ScheduledTask(
            "t1", "test_task", priority=1, requires_gpu=False,
            func=lambda: ran.append(True),
        )
        sched.add_task(task)

        # Trigger idle
        sched.is_idle(snap)
        time.sleep(0.05)
        started = sched.run_pending(snap)
        assert len(started) == 1
        assert len(ran) == 1


# ===========================================================================
# PHASE 6 — STRICT DATASET POLICY
# ===========================================================================

class TestStrictDatasetPolicy:

    def test_valid_manifest(self):
        from impl_v1.training.distributed.strict_dataset_policy import (
            DatasetManifest, compute_data_hash, sign_manifest,
            verify_manifest_signature,
        )
        rng = np.random.RandomState(42)
        X = rng.randn(100, 64).astype(np.float32)
        y = rng.randint(0, 2, 100).astype(np.int64)

        data_hash = compute_data_hash(X, y)
        manifest = DatasetManifest(
            dataset_id="ds1", version=1,
            num_samples=100, num_features=64, num_classes=2,
            sha256=data_hash, signature="",
            created_at="2026-01-01",
        )
        manifest.signature = sign_manifest(manifest, "secret")
        assert verify_manifest_signature(manifest, "secret") is True
        assert verify_manifest_signature(manifest, "wrong_key") is False

    def test_policy_passes_good_data(self):
        from impl_v1.training.distributed.strict_dataset_policy import (
            DatasetManifest, compute_data_hash, sign_manifest,
            validate_dataset_policy,
        )
        rng = np.random.RandomState(42)
        X = rng.randn(500, 64).astype(np.float32)
        y = rng.randint(0, 2, 500).astype(np.int64)

        data_hash = compute_data_hash(X, y)
        manifest = DatasetManifest(
            dataset_id="ds1", version=1,
            num_samples=500, num_features=64, num_classes=2,
            sha256=data_hash, signature="",
            created_at="2026-01-01",
        )
        manifest.signature = sign_manifest(manifest, "secret")

        report = validate_dataset_policy(
            X, y, manifest, "secret",
            num_classes=2, input_dim=64,
            baseline_accuracy=0.0,  # Low bar for random data
        )
        assert report.passed is True

    def test_invalid_signature_blocks(self):
        from impl_v1.training.distributed.strict_dataset_policy import (
            DatasetManifest, compute_data_hash,
            validate_dataset_policy,
        )
        rng = np.random.RandomState(42)
        X = rng.randn(500, 64).astype(np.float32)
        y = rng.randint(0, 2, 500).astype(np.int64)

        manifest = DatasetManifest(
            dataset_id="ds1", version=1,
            num_samples=500, num_features=64, num_classes=2,
            sha256=compute_data_hash(X, y),
            signature="BAD_SIGNATURE",
            created_at="2026-01-01",
        )

        report = validate_dataset_policy(
            X, y, manifest, "secret",
            num_classes=2, input_dim=64,
        )
        assert report.passed is False
        assert any(c.check_name == "manifest_signature" and not c.passed
                    for c in report.checks)


# ===========================================================================
# PHASE 7 — SAFE MULTI-GPU EXECUTION
# ===========================================================================

class TestSafeMultiGPUExecution:

    def test_join_approved(self):
        from impl_v1.training.distributed.safe_multigpu_execution import (
            SafeMultiGPUExecutor, GPUNodeRequest,
        )
        ex = SafeMultiGPUExecutor()
        node = GPUNodeRequest("n1", "RTX3050", 0, True, "12.1", "550")
        ok, _ = ex.request_join(node, leader_term=1)
        assert ok is True

    def test_join_rejected_no_determinism(self):
        from impl_v1.training.distributed.safe_multigpu_execution import (
            SafeMultiGPUExecutor, GPUNodeRequest,
        )
        ex = SafeMultiGPUExecutor()
        node = GPUNodeRequest("n1", "RTX3050", 0, False, "12.1", "550")
        ok, reason = ex.request_join(node, leader_term=1)
        assert ok is False
        assert "determinism" in reason.lower()

    def test_efficiency_removes_weakest(self):
        from impl_v1.training.distributed.safe_multigpu_execution import (
            SafeMultiGPUExecutor, GPUNodeRequest,
        )
        ex = SafeMultiGPUExecutor()
        ex.request_join(GPUNodeRequest("n1", "RTX3050", 0, True, "12.1", "550"), 1)
        ex.request_join(GPUNodeRequest("n2", "RTX2050", 1, True, "12.1", "550"), 1)

        ex.report_node_sps("n1", 5000)
        ex.report_node_sps("n2", 500)  # Very weak

        report = ex.enforce_efficiency(
            cluster_sps=3000,
            baselines={"n1": 5000, "n2": 5000},
        )
        assert report.efficiency < 0.7
        assert report.weakest_removed is True
        assert report.weakest_node == "n2"

    def test_leader_approve_group(self):
        from impl_v1.training.distributed.safe_multigpu_execution import (
            SafeMultiGPUExecutor, GPUNodeRequest,
        )
        ex = SafeMultiGPUExecutor()
        ex.request_join(GPUNodeRequest("n1", "RTX3050", 0, True, "12.1", "550"), 1)
        assert ex.leader_approve_group() is True


# ===========================================================================
# PHASE 8 — AUTO-BOOTSTRAP
# ===========================================================================

class TestAutoBootstrap:

    def test_bootstrap_completes(self):
        from impl_v1.training.distributed.auto_bootstrap import (
            auto_bootstrap, detect_device,
        )
        result = auto_bootstrap(
            dataset_hash="test_hash",
            priority=50,
        )
        assert result.ready is True
        assert result.cluster_joined is True
        assert result.role == "follower"

    def test_high_priority_becomes_leader(self):
        from impl_v1.training.distributed.auto_bootstrap import auto_bootstrap
        result = auto_bootstrap(priority=100)
        assert result.role == "leader"

    def test_device_detection(self):
        from impl_v1.training.distributed.auto_bootstrap import detect_device
        info = detect_device()
        assert info.device_type in ("cuda", "mps", "cpu")
        assert len(info.device_name) > 0

    def test_node_id_unique(self):
        from impl_v1.training.distributed.auto_bootstrap import (
            detect_device, generate_node_id,
        )
        dev = detect_device()
        id1 = generate_node_id(dev)
        time.sleep(0.01)
        id2 = generate_node_id(dev)
        assert id1 != id2


# ===========================================================================
# PHASE 9 — SAFE SHUTDOWN
# ===========================================================================

class TestSafeShutdown:

    def test_leader_failover(self):
        from impl_v1.training.distributed.safe_shutdown import (
            SafeShutdownManager,
        )
        mgr = SafeShutdownManager(heartbeat_timeout=1.0, check_interval=0.3)
        mgr.register_node("leader_node", is_leader=True, priority=100)
        mgr.register_node("secondary", is_leader=False, priority=80)

        mgr.start_monitoring()

        # Kill leader
        mgr.mark_offline("leader_node")
        time.sleep(0.8)

        mgr.stop_monitoring()

        report = mgr.get_failover_report()
        assert report['new_leader'] == "secondary"

    def test_all_offline_halts(self):
        from impl_v1.training.distributed.safe_shutdown import (
            SafeShutdownManager,
        )
        mgr = SafeShutdownManager(heartbeat_timeout=1.0, check_interval=0.3)
        mgr.register_node("n1", is_leader=True, priority=100)

        mgr.start_monitoring()
        mgr.mark_offline("n1")
        time.sleep(0.8)

        mgr.stop_monitoring()
        assert mgr.is_halted is True

    def test_no_failover_if_alive(self):
        from impl_v1.training.distributed.safe_shutdown import (
            SafeShutdownManager,
        )
        mgr = SafeShutdownManager(heartbeat_timeout=5.0, check_interval=0.2)
        mgr.register_node("leader", is_leader=True, priority=100)
        mgr.register_node("follower", priority=50)

        mgr.start_monitoring()
        time.sleep(0.5)
        mgr.stop_monitoring()

        assert mgr.new_leader is None
        assert mgr.is_halted is False


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestHAIntegration:

    def test_bootstrap_then_checkpoint(self):
        """Bootstrap → create checkpoint → validate."""
        from impl_v1.training.distributed.auto_bootstrap import auto_bootstrap
        from impl_v1.training.distributed.checkpoint_versioning import (
            create_versioned_checkpoint, validate_checkpoint,
        )

        boot = auto_bootstrap(priority=100, dataset_hash="ds_hash")
        assert boot.ready is True

        ckpt = create_versioned_checkpoint(
            term=1, epoch=0, dataset_hash="ds_hash",
            merged_weight_hash="wh", world_size=1,
            shard_proportions={boot.node_id: 1.0},
        )
        valid, _ = validate_checkpoint(ckpt, current_term=1)
        assert valid is True

    def test_shutdown_preserves_state_for_restart(self, tmp_path):
        """Shutdown → state preserved → can reload."""
        from impl_v1.training.distributed.safe_shutdown import SafeShutdownManager
        from impl_v1.training.distributed.checkpoint_versioning import (
            create_versioned_checkpoint, save_versioned_checkpoint,
            load_latest_checkpoint,
        )

        # Save checkpoint before shutdown
        ckpt = create_versioned_checkpoint(
            term=3, epoch=10, dataset_hash="dh",
            merged_weight_hash="wh", world_size=2,
            shard_proportions={"n1": 0.5, "n2": 0.5},
        )
        save_versioned_checkpoint(ckpt, str(tmp_path))

        # Simulate shutdown
        mgr = SafeShutdownManager(heartbeat_timeout=1.0, check_interval=0.2)
        mgr.register_node("n1", is_leader=True)
        mgr.start_monitoring()
        mgr.mark_offline("n1")
        time.sleep(0.5)
        mgr.stop_monitoring()

        # Restart: load checkpoint
        loaded = load_latest_checkpoint(str(tmp_path))
        assert loaded is not None
        assert loaded.term == 3
        assert loaded.epoch == 10
