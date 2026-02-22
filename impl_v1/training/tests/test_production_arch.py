"""
test_production_arch.py — Tests for 9-Phase Production Architecture

All tests mock CUDA so they run on any machine.
"""

import hashlib
import json
import math
import os
import sys
import time

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 1 — STORAGE POLICY
# ===========================================================================

class TestStoragePolicy:

    def test_ssd_info(self):
        from impl_v1.training.distributed.storage_policy import get_drive_info
        info = get_drive_info("C:\\", "ssd_active")
        assert info.role == "ssd_active"
        assert info.total_gb > 0

    def test_nas_clean_on_empty(self, tmp_path):
        from impl_v1.training.distributed.storage_policy import check_nas_clean
        clean, violations = check_nas_clean(str(tmp_path))
        assert clean is True
        assert len(violations) == 0

    def test_nas_detects_training_data(self, tmp_path):
        from impl_v1.training.distributed.storage_policy import check_nas_clean
        # Create training marker
        (tmp_path / "cluster_state.json").write_text("{}")
        clean, violations = check_nas_clean(str(tmp_path))
        assert clean is False
        assert len(violations) > 0

    def test_get_ssd_paths(self):
        from impl_v1.training.distributed.storage_policy import get_ssd_training_paths
        paths = get_ssd_training_paths()
        assert 'weights' in paths
        assert 'features' in paths
        assert 'wal' in paths


# ===========================================================================
# PHASE 2 — DATA ENFORCEMENT
# ===========================================================================

class TestDataEnforcement:

    def test_all_checks_pass(self):
        from unittest.mock import patch, MagicMock
        from impl_v1.training.distributed.data_enforcement import enforce_data_policy
        rng = np.random.RandomState(42)
        X = rng.randn(500, 64).astype(np.float32)
        y = rng.randint(0, 2, 500).astype(np.int64)

        # Mock shuffle test to pass (random data can't differentiate)
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.original_accuracy = 0.65
        mock_result.shuffled_accuracy = 0.50

        with patch(
            'impl_v1.training.distributed.dataset_sanity.run_label_shuffle_test',
            return_value=mock_result,
        ) as _:
            report = enforce_data_policy(
                X, y,
                manifest_valid=True,
                owner_approved=True,
                min_baseline_accuracy=0.0,
            )
        assert report.passed is True
        assert len(report.checks) == 7

    def test_blocks_without_approval(self):
        from impl_v1.training.distributed.data_enforcement import enforce_data_policy
        rng = np.random.RandomState(42)
        X = rng.randn(500, 64).astype(np.float32)
        y = rng.randint(0, 2, 500).astype(np.int64)

        report = enforce_data_policy(
            X, y,
            manifest_valid=True,
            owner_approved=False,
        )
        assert report.passed is False
        assert any(c.name == "owner_approval" and not c.passed for c in report.checks)

    def test_entropy(self):
        from impl_v1.training.distributed.data_enforcement import compute_entropy
        y = np.array([0, 0, 0, 0, 1, 1, 1, 1])
        entropy = compute_entropy(y)
        assert entropy > 0.9  # Near 1.0 for balanced

    def test_duplicate_ratio(self):
        from impl_v1.training.distributed.data_enforcement import compute_duplicate_ratio
        X = np.array([[1, 2, 3], [1, 2, 3], [4, 5, 6]], dtype=np.float32)
        ratio = compute_duplicate_ratio(X)
        assert ratio > 0.3  # 1 of 3 is dupe


# ===========================================================================
# PHASE 3 — DATA COMPRESSOR
# ===========================================================================

class TestDataCompressor:

    def test_compress_dataset(self, tmp_path):
        from impl_v1.training.distributed.data_compressor import compress_dataset
        rng = np.random.RandomState(42)
        X = rng.randn(1000, 128).astype(np.float32)
        y = rng.randint(0, 3, 1000).astype(np.int64)

        result = compress_dataset(X, y, str(tmp_path))
        assert result.compressed_size_mb > 0
        assert result.compression_ratio > 1.0
        assert os.path.exists(result.output_path)

    def test_dedup(self, tmp_path):
        from impl_v1.training.distributed.data_compressor import deduplicate_dataset
        X = np.array([[1, 2], [1, 2], [3, 4]], dtype=np.float32)
        y = np.array([0, 0, 1], dtype=np.int64)
        X_u, y_u, dupes = deduplicate_dataset(X, y)
        assert dupes == 1
        assert len(X_u) == 2

    def test_load_compressed(self, tmp_path):
        from impl_v1.training.distributed.data_compressor import (
            compress_dataset, load_compressed_dataset,
        )
        rng = np.random.RandomState(42)
        X = rng.randn(100, 64).astype(np.float32)
        y = rng.randint(0, 2, 100).astype(np.int64)
        result = compress_dataset(X, y, str(tmp_path), deduplicate=False)

        X2, y2 = load_compressed_dataset(result.output_path)
        assert np.array_equal(X, X2)
        assert np.array_equal(y, y2)


# ===========================================================================
# PHASE 4 — MODEL VERSIONING
# ===========================================================================

class TestModelVersioning:

    def test_save_and_load(self, tmp_path):
        import torch
        from impl_v1.training.distributed.model_versioning import (
            save_model_fp16, load_model_version,
        )
        model = torch.nn.Linear(64, 2)
        version = save_model_fp16(
            model, "v001", "ds_hash", 1, 5, 0.85,
            {"lr": 0.001, "batch": 512},
            base_dir=str(tmp_path),
        )
        assert version.fp16 is True
        assert os.path.exists(version.weights_path)

        loaded = load_model_version("v001", str(tmp_path))
        assert loaded is not None
        assert loaded.version_id == "v001"

    def test_list_versions(self, tmp_path):
        import torch
        from impl_v1.training.distributed.model_versioning import (
            save_model_fp16, list_model_versions,
        )
        model = torch.nn.Linear(64, 2)
        save_model_fp16(model, "v001", "dh", 1, 0, 0.5, {}, str(tmp_path))
        save_model_fp16(model, "v002", "dh", 2, 1, 0.6, {}, str(tmp_path))

        versions = list_model_versions(str(tmp_path))
        assert len(versions) == 2


# ===========================================================================
# PHASE 6 — WIPE PROTECTION
# ===========================================================================

class TestWipeProtection:

    def test_local_weights_found(self, tmp_path):
        import torch
        from impl_v1.training.distributed.wipe_protection import check_local_weights
        v_dir = tmp_path / "v001"
        v_dir.mkdir()
        torch.save({}, str(v_dir / "model_fp16.pt"))
        assert check_local_weights(str(tmp_path)) is True

    def test_no_local_weights(self, tmp_path):
        from impl_v1.training.distributed.wipe_protection import check_local_weights
        assert check_local_weights(str(tmp_path)) is False


# ===========================================================================
# PHASE 7 — HA LEADER
# ===========================================================================

class TestHALeader:

    def test_owner_wins(self):
        from impl_v1.training.distributed.ha_leader import HALeaderManager
        mgr = HALeaderManager(owner_node_id="owner", secondary_node_id="rtx3050")
        mgr.register_node("owner", "RTX2050")
        mgr.register_node("rtx3050", "RTX3050")

        state = mgr.run_election()
        assert state.leader_id == "owner"
        assert state.is_owner is True
        assert state.temporary is False

    def test_secondary_takes_over(self):
        from impl_v1.training.distributed.ha_leader import HALeaderManager
        mgr = HALeaderManager(owner_node_id="owner", secondary_node_id="rtx3050")
        mgr.register_node("owner", "RTX2050")
        mgr.register_node("rtx3050", "RTX3050")

        mgr.mark_offline("owner")
        state = mgr.run_election()
        assert state.leader_id == "rtx3050"
        assert state.temporary is True

    def test_owner_reclaims_on_rejoin(self):
        from impl_v1.training.distributed.ha_leader import HALeaderManager
        mgr = HALeaderManager(owner_node_id="owner", secondary_node_id="rtx3050")
        mgr.register_node("owner", "RTX2050")
        mgr.register_node("rtx3050", "RTX3050")

        mgr.mark_offline("owner")
        mgr.run_election()

        state = mgr.reconcile_on_rejoin("owner")
        assert state.leader_id == "owner"
        assert state.is_owner is True

    def test_non_owner_rejoin_no_change(self):
        from impl_v1.training.distributed.ha_leader import HALeaderManager
        mgr = HALeaderManager(owner_node_id="owner", secondary_node_id="rtx3050")
        mgr.register_node("owner", "RTX2050")
        mgr.register_node("rtx3050", "RTX3050")
        mgr.register_node("node3", "CPU")

        mgr.run_election()
        mgr.mark_offline("node3")

        state = mgr.reconcile_on_rejoin("node3")
        assert state.leader_id == "owner"


# ===========================================================================
# PHASE 8 — DRIFT GUARD
# ===========================================================================

class TestDriftGuard:

    def test_no_anomaly(self):
        from impl_v1.training.distributed.drift_guard import DriftGuard
        guard = DriftGuard()
        guard.check_epoch(0, loss=0.7, accuracy=0.5)
        guard.check_epoch(1, loss=0.65, accuracy=0.55)
        guard.check_epoch(2, loss=0.60, accuracy=0.60)
        assert guard.should_abort is False

    def test_loss_spike_aborts(self):
        from impl_v1.training.distributed.drift_guard import DriftGuard
        guard = DriftGuard(loss_spike_factor=2.0)
        guard.check_epoch(0, loss=0.5, accuracy=0.5)
        guard.check_epoch(1, loss=0.5, accuracy=0.55)
        guard.check_epoch(2, loss=5.0, accuracy=0.3)  # Spike!
        assert guard.should_abort is True

    def test_gradient_explosion_aborts(self):
        from impl_v1.training.distributed.drift_guard import DriftGuard
        guard = DriftGuard(max_gradient_norm=10.0)
        events = guard.check_epoch(0, loss=0.5, accuracy=0.5, gradient_norm=500.0)
        assert guard.should_abort is True
        assert any(e.event_type == "gradient_explosion" for e in events)

    def test_nan_aborts(self):
        from impl_v1.training.distributed.drift_guard import DriftGuard
        guard = DriftGuard()
        guard.check_epoch(0, loss=float('nan'), accuracy=0.5)
        assert guard.should_abort is True

    def test_accuracy_jump_warning(self):
        from impl_v1.training.distributed.drift_guard import DriftGuard
        guard = DriftGuard(max_accuracy_jump=0.1)
        guard.check_epoch(0, loss=0.5, accuracy=0.5)
        events = guard.check_epoch(1, loss=0.4, accuracy=0.9)  # +0.4 jump
        assert any(e.event_type == "accuracy_jump" for e in events)

    def test_report(self):
        from impl_v1.training.distributed.drift_guard import DriftGuard
        guard = DriftGuard()
        guard.check_epoch(0, loss=0.5, accuracy=0.5)
        report = guard.get_report()
        assert report.epochs_monitored == 1
        assert report.status == "ok"


# ===========================================================================
# PHASE 9 — CLUSTER METRICS
# ===========================================================================

class TestClusterMetrics:

    def test_record_and_report(self):
        from impl_v1.training.distributed.cluster_metrics import ClusterMetricsTracker
        tracker = ClusterMetricsTracker()
        tracker.record_epoch(
            epoch=0, world_size=2,
            per_node_sps={"n1": 50000, "n2": 45000},
            baseline_sps_sum=100000,
            merged_weight_hash="wh", dataset_hash="dh",
            leader_term=1, loss=0.5, accuracy=0.6,
        )
        report = tracker.get_report()
        assert report.total_epochs == 1
        assert report.avg_cluster_sps == 95000.0
        assert report.dataset_hash == "dh"

    def test_save_metrics(self, tmp_path):
        from impl_v1.training.distributed.cluster_metrics import ClusterMetricsTracker
        tracker = ClusterMetricsTracker(str(tmp_path))
        tracker.record_epoch(
            0, 2, {"n1": 50000}, 50000, "wh", "dh", 1,
        )
        path = tracker.save()
        assert os.path.exists(path)

    def test_energy_estimate(self):
        from impl_v1.training.distributed.cluster_metrics import ClusterMetricsTracker
        tracker = ClusterMetricsTracker()
        energy = tracker.estimate_energy(gpu_tdp_watts=75, epoch_duration_sec=3600)
        assert energy == 75.0  # 75W * 1h = 75Wh


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestProductionIntegration:

    def test_enforce_then_compress_then_version(self, tmp_path):
        """Full pipeline: enforce → compress → version."""
        from unittest.mock import patch, MagicMock
        from impl_v1.training.distributed.data_enforcement import enforce_data_policy
        from impl_v1.training.distributed.data_compressor import compress_dataset
        import torch
        from impl_v1.training.distributed.model_versioning import save_model_fp16

        rng = np.random.RandomState(42)
        X = rng.randn(500, 64).astype(np.float32)
        y = rng.randint(0, 2, 500).astype(np.int64)

        # Mock shuffle test for random data
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.original_accuracy = 0.65
        mock_result.shuffled_accuracy = 0.50

        with patch(
            'impl_v1.training.distributed.dataset_sanity.run_label_shuffle_test',
            return_value=mock_result,
        ):
            report = enforce_data_policy(
                X, y, manifest_valid=True, owner_approved=True,
                min_baseline_accuracy=0.0,
            )
        assert report.passed is True

        # Compress
        comp = compress_dataset(X, y, str(tmp_path / "compressed"))
        assert comp.compression_ratio > 1.0

        # Version
        model = torch.nn.Linear(64, 2)
        version = save_model_fp16(
            model, "v001", comp.dataset_hash, 1, 0, 0.5,
            {"lr": 0.001}, str(tmp_path / "models"),
        )
        assert version.fp16 is True

    def test_drift_guard_with_metrics(self):
        """Drift guard + metrics integration."""
        from impl_v1.training.distributed.drift_guard import DriftGuard
        from impl_v1.training.distributed.cluster_metrics import ClusterMetricsTracker

        guard = DriftGuard()
        tracker = ClusterMetricsTracker()

        for epoch in range(3):
            loss = 0.7 - epoch * 0.05
            acc = 0.5 + epoch * 0.05
            events = guard.check_epoch(epoch, loss=loss, accuracy=acc)
            assert len(events) == 0

            tracker.record_epoch(
                epoch, 2, {"n1": 50000, "n2": 45000},
                100000, f"hash_{epoch}", "dh", 1,
                loss=loss, accuracy=acc,
            )

        assert guard.should_abort is False
        report = tracker.get_report()
        assert report.total_epochs == 3
