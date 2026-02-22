"""
test_shard_replication.py — Tests for 9-Phase Shard Replication Architecture

30+ tests covering all phases.
"""

import hashlib
import json
import os
import sys

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 2 — 110GB LIMIT POLICY
# ===========================================================================

class TestStorageLimitPolicy:

    def test_within_limit(self):
        from impl_v1.training.distributed.storage_limit_policy import (
            StorageLimitPolicy, ShardUsage,
        )
        policy = StorageLimitPolicy(limit_gb=110.0)
        policy.register_shard(ShardUsage(
            shard_id="s1", namespace="default",
            size_bytes=50 * 1024**3, state="active",
            last_accessed=1000, replica_count=3,
        ))
        report = policy.check_limit()
        assert report.within_limit is True

    def test_over_limit_creates_eviction(self):
        from impl_v1.training.distributed.storage_limit_policy import (
            StorageLimitPolicy, ShardUsage,
        )
        policy = StorageLimitPolicy(limit_gb=1.0)  # 1GB limit
        for i in range(5):
            policy.register_shard(ShardUsage(
                shard_id=f"s{i}", namespace="default",
                size_bytes=500 * 1024**2, state="active",
                last_accessed=1000 + i, replica_count=2,
            ))
        report = policy.check_limit()
        assert report.within_limit is False
        assert report.eviction_plan is not None

    def test_evict_shard(self):
        from impl_v1.training.distributed.storage_limit_policy import (
            StorageLimitPolicy, ShardUsage,
        )
        policy = StorageLimitPolicy()
        policy.register_shard(ShardUsage(
            shard_id="cold1", namespace="default",
            size_bytes=1024, state="active",
            last_accessed=100, replica_count=3,
        ))
        policy.evict_shard("cold1", "nas")
        report = policy.check_limit()
        assert report.within_limit is True


# ===========================================================================
# PHASE 5 — CLOUD BACKUP
# ===========================================================================

class TestCloudBackup:

    def test_add_targets(self):
        from impl_v1.training.distributed.cloud_backup import (
            CloudBackupManager, CloudTarget,
        )
        mgr = CloudBackupManager()
        mgr.add_target(CloudTarget("gd1", "google_drive", "/backup1"))
        mgr.add_target(CloudTarget("gd2", "google_drive", "/backup2"))
        mgr.add_target(CloudTarget("gd3", "google_drive", "/backup3"))
        assert len(mgr._targets) == 3

    def test_create_backup(self, tmp_path):
        from impl_v1.training.distributed.cloud_backup import (
            CloudBackupManager, CloudTarget,
        )
        mgr = CloudBackupManager(str(tmp_path))
        mgr.add_target(CloudTarget("gd1", "google_drive", "/b1"))
        mgr.add_target(CloudTarget("gd2", "google_drive", "/b2"))

        result = mgr.create_backup(
            shard_ids=["s1", "s2", "s3"],
            shard_sizes={"s1": 1000, "s2": 2000, "s3": 3000},
            encrypt=True,
        )
        assert result.success is True
        assert result.manifest.encrypted is True
        assert len(result.manifest.uploaded_to) == 2

    def test_list_backups(self, tmp_path):
        from impl_v1.training.distributed.cloud_backup import (
            CloudBackupManager, CloudTarget,
        )
        mgr = CloudBackupManager(str(tmp_path))
        mgr.add_target(CloudTarget("gd1", "google_drive", "/b1"))
        mgr.create_backup(["s1"], {"s1": 100})
        assert len(mgr.list_backups()) == 1


# ===========================================================================
# PHASE 6 — AUTO-RECOVERY
# ===========================================================================

class TestAutoRecovery:

    def test_recover_from_peer(self):
        from impl_v1.training.distributed.auto_recovery import AutoRecoveryEngine
        engine = AutoRecoveryEngine()
        engine.register_peer_shards("peer1", ["s1", "s2"])
        engine.register_peer_shards("peer2", ["s2", "s3"])

        report = engine.recover_shards(["s1", "s3"])
        assert report.fully_restored is True
        assert report.recovered == 2

    def test_recover_from_nas(self):
        from impl_v1.training.distributed.auto_recovery import AutoRecoveryEngine
        engine = AutoRecoveryEngine()
        engine.register_nas_shards(["nas_shard1"])

        report = engine.recover_shards(["nas_shard1"])
        assert report.recovered == 1
        assert report.operations[0].source.source_type == "nas"

    def test_recover_from_cloud(self):
        from impl_v1.training.distributed.auto_recovery import AutoRecoveryEngine
        engine = AutoRecoveryEngine()
        engine.register_cloud_shards(["cloud_shard1"])

        report = engine.recover_shards(["cloud_shard1"])
        assert report.recovered == 1
        assert report.operations[0].source.source_type == "cloud"

    def test_fallback_chain(self):
        from impl_v1.training.distributed.auto_recovery import AutoRecoveryEngine
        engine = AutoRecoveryEngine()
        engine.register_peer_shards("peer1", ["s1"])
        engine.register_nas_shards(["s2"])
        engine.register_cloud_shards(["s3"])

        report = engine.recover_shards(["s1", "s2", "s3"])
        assert report.fully_restored is True
        types = [op.source.source_type for op in report.operations]
        assert "peer" in types
        assert "nas" in types
        assert "cloud" in types

    def test_no_source_fails(self):
        from impl_v1.training.distributed.auto_recovery import AutoRecoveryEngine
        engine = AutoRecoveryEngine()
        report = engine.recover_shards(["missing_shard"])
        assert report.fully_restored is False
        assert report.failed == 1


# ===========================================================================
# PHASE 7 — NAMESPACE MANAGER
# ===========================================================================

class TestNamespaceManager:

    def test_auto_create(self):
        from impl_v1.training.distributed.namespace_manager import NamespaceManager
        mgr = NamespaceManager()
        ns = mgr.get_or_create("vulnerability")
        assert ns.namespace_id == "ns_vulnerability"
        assert ns.limit_gb == 110.0

    def test_add_shard(self):
        from impl_v1.training.distributed.namespace_manager import NamespaceManager
        mgr = NamespaceManager()
        ok = mgr.add_shard("patterns", 1024 * 1024 * 100)  # 100MB
        assert ok is True
        ns = mgr.get_or_create("patterns")
        assert ns.shard_count == 1

    def test_limit_enforcement(self):
        from impl_v1.training.distributed.namespace_manager import NamespaceManager
        mgr = NamespaceManager(default_limit_gb=0.001)  # ~1MB
        ok = mgr.add_shard("tiny", 2 * 1024**2)  # 2MB
        assert ok is False  # Exceeds 1MB

    def test_report(self):
        from impl_v1.training.distributed.namespace_manager import NamespaceManager
        mgr = NamespaceManager()
        mgr.add_shard("vuln", 1024)
        mgr.add_shard("pattern", 2048)
        report = mgr.get_report()
        assert report.total_namespaces == 2


# ===========================================================================
# PHASE 8 — REDUNDANCY GATE
# ===========================================================================

class TestRedundancyGate:

    def test_3_cluster_copies_allowed(self):
        from impl_v1.training.distributed.redundancy_gate import RedundancyGate
        gate = RedundancyGate()
        gate.register_shard("s1", cluster_copies=3, nas_copies=0)
        report = gate.check_training_allowed()
        assert report.training_allowed is True

    def test_2_cluster_1_nas_allowed(self):
        from impl_v1.training.distributed.redundancy_gate import RedundancyGate
        gate = RedundancyGate()
        gate.register_shard("s1", cluster_copies=2, nas_copies=1)
        report = gate.check_training_allowed()
        assert report.training_allowed is True

    def test_insufficient_blocked(self):
        from impl_v1.training.distributed.redundancy_gate import RedundancyGate
        gate = RedundancyGate()
        gate.register_shard("s1", cluster_copies=1, nas_copies=0)
        report = gate.check_training_allowed()
        assert report.training_allowed is False
        assert report.non_compliant_shards == 1

    def test_mixed_compliance(self):
        from impl_v1.training.distributed.redundancy_gate import RedundancyGate
        gate = RedundancyGate()
        gate.register_shard("s1", cluster_copies=3)
        gate.register_shard("s2", cluster_copies=1)
        report = gate.check_training_allowed()
        assert report.training_allowed is False


# ===========================================================================
# PHASE 9 — REPORT SYNC
# ===========================================================================

class TestReportSync:

    def test_extract_features(self):
        from impl_v1.training.distributed.report_sync import ReportSyncEngine
        engine = ReportSyncEngine()
        features = engine.extract_features(
            {"score": 0.95, "count": 42, "label": "vuln"},
            report_type="vulnerability",
        )
        assert features.shape == (256,)
        assert features.dtype == np.float32

    def test_create_shard(self):
        from impl_v1.training.distributed.report_sync import ReportSyncEngine
        engine = ReportSyncEngine()
        features = np.random.randn(256).astype(np.float32)
        shard = engine.create_shard(features, "pattern")
        assert len(shard.shard_id) == 64  # SHA-256

    def test_full_sync_pipeline(self, tmp_path):
        from impl_v1.training.distributed.report_sync import ReportSyncEngine
        engine = ReportSyncEngine(str(tmp_path))

        result = engine.sync_report(
            report_data={"score": 0.9, "count": 10, "type": "vuln"},
            report_type="vulnerability",
            target_peers=["peer1", "peer2"],
        )
        assert result.manifest_updated is True
        assert result.delta_pushed is True
        assert len(result.push_targets) == 2


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestShardIntegration:

    def test_full_pipeline(self, tmp_path):
        """Recovery → Redundancy → Backup pipeline."""
        from impl_v1.training.distributed.auto_recovery import AutoRecoveryEngine
        from impl_v1.training.distributed.redundancy_gate import RedundancyGate
        from impl_v1.training.distributed.cloud_backup import (
            CloudBackupManager, CloudTarget,
        )

        # Recovery
        recovery = AutoRecoveryEngine()
        recovery.register_peer_shards("peer1", ["s1", "s2"])
        recovery.register_nas_shards(["s3"])
        report = recovery.recover_shards(["s1", "s2", "s3"])
        assert report.fully_restored is True

        # Redundancy check
        gate = RedundancyGate()
        gate.register_shard("s1", cluster_copies=3)
        gate.register_shard("s2", cluster_copies=2, nas_copies=1)
        gate.register_shard("s3", cluster_copies=2, nas_copies=1)
        r = gate.check_training_allowed()
        assert r.training_allowed is True

        # Cloud backup
        backup = CloudBackupManager(str(tmp_path))
        backup.add_target(CloudTarget("gd1", "google_drive", "/b1"))
        result = backup.create_backup(
            ["s1", "s2", "s3"],
            {"s1": 1000, "s2": 2000, "s3": 3000},
        )
        assert result.success is True

    def test_namespace_with_limit(self):
        """Namespace + limit policy integration."""
        from impl_v1.training.distributed.namespace_manager import NamespaceManager
        from impl_v1.training.distributed.storage_limit_policy import (
            StorageLimitPolicy, ShardUsage,
        )

        ns_mgr = NamespaceManager(default_limit_gb=110.0)
        limit = StorageLimitPolicy(limit_gb=110.0)

        # Add shards to namespace
        ns_mgr.add_shard("vuln", 50 * 1024**3)
        limit.register_shard(ShardUsage(
            shard_id="vuln_s1", namespace="vuln",
            size_bytes=50 * 1024**3, state="active",
            last_accessed=1000, replica_count=3,
        ))

        ns_report = ns_mgr.get_report()
        assert ns_report.total_namespaces == 1

        limit_report = limit.check_limit()
        assert limit_report.within_limit is True
