"""
test_governance.py — Tests for 8-Phase Cluster Governance

Tests all 5 governance modules with mocked data (no CUDA required).
"""

import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np

from impl_v1.training.distributed.data_enforcement import (
    sign_manifest,
    verify_manifest,
    check_quality,
    check_leakage,
    ManifestCheck,
    QualityCheck,
    ShuffleCheck,
    SanityCheck,
    LeakageCheck,
    DataEnforcementResult,
    DUPLICATE_MAX,
    IMBALANCE_MAX,
    ENTROPY_MIN,
)

from impl_v1.training.distributed.experiment_tracker import (
    ExperimentTracker,
    ExperimentRun,
)

from impl_v1.training.distributed.training_monitor import (
    EnergyTracker,
    DriftDetector,
    DriftType,
    DriftSeverity,
)

from impl_v1.training.distributed.hpo_coordinator import (
    HPOCoordinator,
    generate_grid_search,
    generate_random_search,
)

from impl_v1.training.distributed.cluster_policies import (
    GradientCompressionPolicy,
    CompressionConfig,
    CompressionMode,
    TLSPolicy,
    NodeCertificate,
    ResourceUtilizationPolicy,
    TaskType,
)


# =============================================================================
# PHASE 1 — DATA ENFORCEMENT
# =============================================================================

class TestManifest(unittest.TestCase):
    """Test signed manifest creation and verification."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.manifest_path = os.path.join(self.tmp, 'manifest.json')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sign_and_verify(self):
        sign_manifest(
            "abc123", 1000, 256, 2,
            secret_key="test-key", path=self.manifest_path,
        )
        result = verify_manifest(
            "abc123", 1000, 256,
            secret_key="test-key", path=self.manifest_path,
        )
        self.assertTrue(result.passed)
        self.assertTrue(result.signature_valid)

    def test_reject_wrong_hash(self):
        sign_manifest(
            "abc123", 1000, 256, 2,
            secret_key="test-key", path=self.manifest_path,
        )
        result = verify_manifest(
            "wrong_hash", 1000, 256,
            secret_key="test-key", path=self.manifest_path,
        )
        self.assertFalse(result.passed)

    def test_reject_tampered_signature(self):
        sign_manifest(
            "abc123", 1000, 256, 2,
            secret_key="test-key", path=self.manifest_path,
        )
        result = verify_manifest(
            "abc123", 1000, 256,
            secret_key="wrong-key", path=self.manifest_path,
        )
        self.assertFalse(result.passed)
        self.assertFalse(result.signature_valid)

    def test_missing_manifest(self):
        result = verify_manifest(
            "abc123", 1000, 256,
            path="/nonexistent/manifest.json",
        )
        self.assertFalse(result.passed)
        self.assertFalse(result.manifest_exists)


class TestQualityCheck(unittest.TestCase):
    """Test data quality checks."""

    def test_good_data(self):
        rng = np.random.RandomState(42)
        features = rng.randn(500, 64).astype(np.float32)
        labels = np.array([0] * 250 + [1] * 250, dtype=np.int64)
        result = check_quality(features, labels)
        self.assertTrue(result.passed)

    def test_high_duplicates(self):
        base = np.ones((100, 4), dtype=np.float32)
        features = np.vstack([base] * 5)  # All identical
        labels = np.array([0] * 250 + [1] * 250, dtype=np.int64)
        result = check_quality(features, labels)
        self.assertFalse(result.passed)
        self.assertGreater(result.duplicate_ratio, DUPLICATE_MAX)

    def test_high_imbalance(self):
        rng = np.random.RandomState(42)
        features = rng.randn(109, 8).astype(np.float32)
        labels = np.array([0] * 100 + [1] * 9, dtype=np.int64)  # 11:1
        result = check_quality(features, labels)
        self.assertFalse(result.passed)
        self.assertGreater(result.imbalance_ratio, IMBALANCE_MAX)


class TestLeakageCheck(unittest.TestCase):
    """Test train/test leakage detection."""

    def test_no_leakage(self):
        X_train = np.array([[1, 2], [3, 4]], dtype=np.float32)
        X_test = np.array([[5, 6], [7, 8]], dtype=np.float32)
        result = check_leakage(X_train, X_test)
        self.assertTrue(result.passed)
        self.assertEqual(result.overlap_count, 0)

    def test_leakage_detected(self):
        X_train = np.array([[1, 2], [3, 4]], dtype=np.float32)
        X_test = np.array([[1, 2], [5, 6]], dtype=np.float32)  # row 0 leaked
        result = check_leakage(X_train, X_test)
        self.assertFalse(result.passed)
        self.assertEqual(result.overlap_count, 1)

    def test_no_test_set(self):
        X_train = np.array([[1, 2]], dtype=np.float32)
        result = check_leakage(X_train, None)
        self.assertTrue(result.passed)


# =============================================================================
# PHASE 2 — EXPERIMENT TRACKER
# =============================================================================

class TestExperimentTracker(unittest.TestCase):
    """Test experiment tracker lifecycle."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.tracker = ExperimentTracker(experiments_dir=self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_start_and_complete_run(self):
        run_id = self.tracker.start_run(
            leader_term=1, world_size=2, dataset_hash="abc",
            hyperparameters={"lr": 0.01}, per_node_batch={"n1": 1024},
        )
        self.assertIsNotNone(run_id)

        self.tracker.log_epoch(
            epoch=1, train_loss=0.5, val_loss=0.4, val_accuracy=0.8,
            cluster_sps=5000, energy_joules=100.0,
            merged_weight_hash="hash1",
        )

        self.tracker.complete_run(
            final_accuracy=0.85, scaling_efficiency=0.9,
            energy_per_epoch=100.0,
        )

        # Verify persisted
        runs = self.tracker.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]['status'], 'completed')

    def test_get_best_run(self):
        # Run 1
        self.tracker.start_run(
            leader_term=1, world_size=2, dataset_hash="abc",
            hyperparameters={"lr": 0.01}, per_node_batch={"n1": 1024},
            run_id="run1",
        )
        self.tracker.complete_run(0.80, 0.9, 100.0)

        # Run 2 (better)
        self.tracker.start_run(
            leader_term=1, world_size=2, dataset_hash="abc",
            hyperparameters={"lr": 0.05}, per_node_batch={"n1": 2048},
            run_id="run2",
        )
        self.tracker.complete_run(0.92, 0.95, 80.0)

        best = self.tracker.get_best_run()
        self.assertIsNotNone(best)
        self.assertEqual(best['run_id'], 'run2')

    def test_abort_run(self):
        self.tracker.start_run(
            leader_term=1, world_size=2, dataset_hash="abc",
            hyperparameters={"lr": 0.01}, per_node_batch={},
        )
        self.tracker.abort_run("test abort")

        runs = self.tracker.list_runs()
        self.assertEqual(runs[0]['status'], 'aborted')


# =============================================================================
# PHASE 3 — ENERGY METRICS
# =============================================================================

class TestEnergyTracker(unittest.TestCase):
    """Test energy tracking."""

    def test_record_epoch(self):
        tracker = EnergyTracker()
        m = tracker.record_epoch(
            epoch=1, avg_power_watts=75.0, epoch_duration_sec=10.0,
        )
        self.assertEqual(m.energy_joules, 750.0)
        self.assertAlmostEqual(m.energy_kwh, 750.0 / 3_600_000, places=6)

    def test_average_energy(self):
        tracker = EnergyTracker()
        tracker.record_epoch(1, 100.0, 10.0)  # 1000J
        tracker.record_epoch(2, 80.0, 10.0)   # 800J
        avg = tracker.get_average_energy()
        self.assertEqual(avg, 900.0)

    def test_summary(self):
        tracker = EnergyTracker()
        tracker.record_epoch(1, 50.0, 20.0)
        summary = tracker.get_summary()
        self.assertEqual(summary['total_epochs'], 1)
        self.assertEqual(summary['total_energy_joules'], 1000.0)


# =============================================================================
# PHASE 7 — DRIFT DETECTION
# =============================================================================

class TestDriftDetector(unittest.TestCase):
    """Test drift detection."""

    def test_healthy_training(self):
        dd = DriftDetector()
        r1 = dd.check_epoch(1, val_loss=1.0, grad_norm=1.0, accuracy=0.5)
        r2 = dd.check_epoch(2, val_loss=0.9, grad_norm=1.1, accuracy=0.55)
        self.assertFalse(r1.should_pause)
        self.assertFalse(r2.should_pause)
        self.assertEqual(len(r2.anomalies), 0)

    def test_loss_spike_warning(self):
        dd = DriftDetector()
        dd.check_epoch(1, val_loss=0.5, grad_norm=1.0, accuracy=0.8)
        r = dd.check_epoch(2, val_loss=1.2, grad_norm=1.0, accuracy=0.78)
        # 1.2/0.5 = 2.4× → warning
        has_loss_warn = any(
            a.drift_type == DriftType.LOSS_SPIKE for a in r.anomalies
        )
        self.assertTrue(has_loss_warn)
        self.assertFalse(r.should_pause)  # Warning, not critical

    def test_loss_spike_critical(self):
        dd = DriftDetector()
        dd.check_epoch(1, val_loss=0.5, grad_norm=1.0, accuracy=0.8)
        r = dd.check_epoch(2, val_loss=3.0, grad_norm=1.0, accuracy=0.3)
        # 3.0/0.5 = 6× → critical
        has_critical = any(
            a.severity == DriftSeverity.CRITICAL for a in r.anomalies
        )
        self.assertTrue(has_critical)
        self.assertTrue(r.should_pause)

    def test_grad_explosion(self):
        dd = DriftDetector()
        dd.check_epoch(1, val_loss=0.5, grad_norm=1.0, accuracy=0.8)
        r = dd.check_epoch(2, val_loss=0.5, grad_norm=15.0, accuracy=0.8)
        # 15/1 = 15× → warning
        has_grad = any(
            a.drift_type == DriftType.GRAD_EXPLOSION for a in r.anomalies
        )
        self.assertTrue(has_grad)

    def test_accuracy_drop(self):
        dd = DriftDetector()
        dd.check_epoch(1, val_loss=0.5, grad_norm=1.0, accuracy=0.90)
        r = dd.check_epoch(2, val_loss=0.5, grad_norm=1.0, accuracy=0.83)
        # Drop = 0.07 → warning (>0.05)
        has_acc = any(
            a.drift_type == DriftType.ACCURACY_DROP for a in r.anomalies
        )
        self.assertTrue(has_acc)

    def test_summary(self):
        dd = DriftDetector()
        dd.check_epoch(1, 0.5, 1.0, 0.8)
        dd.check_epoch(2, 0.4, 1.0, 0.82)
        s = dd.get_summary()
        self.assertEqual(s['epochs_monitored'], 2)


# =============================================================================
# PHASE 4 — HPO COORDINATOR
# =============================================================================

class TestHPOCoordinator(unittest.TestCase):
    """Test HPO search and selection."""

    def test_generate_random_trials(self):
        coord = HPOCoordinator(search_mode="random", max_trials=5)
        trials = coord.generate_trials(seed=42)
        self.assertEqual(len(trials), 5)

    def test_generate_grid_trials(self):
        coord = HPOCoordinator(search_mode="grid", max_trials=8)
        trials = coord.generate_trials(
            search_space={'lr': [0.01, 0.05], 'bs': [512, 1024]},
        )
        self.assertEqual(len(trials), 4)  # 2×2 grid

    def test_assign_and_report(self):
        coord = HPOCoordinator(search_mode="random", max_trials=3)
        trials = coord.generate_trials()

        assignments = coord.assign_trials(["node1", "node2", "node3"])
        self.assertEqual(len(assignments), 3)

        for tid in assignments:
            coord.report_result(
                tid, val_accuracy=0.85, convergence_speed=5.0,
            )

        result = coord.select_best()
        self.assertIsNotNone(result)
        self.assertEqual(result.completed_trials, 3)
        self.assertGreater(result.best_accuracy, 0)

    def test_select_best_by_accuracy(self):
        coord = HPOCoordinator(search_mode="random", max_trials=2)
        trials = coord.generate_trials()

        tid1, tid2 = list(coord.trials.keys())
        coord.report_result(tid1, val_accuracy=0.80, convergence_speed=3.0)
        coord.report_result(tid2, val_accuracy=0.92, convergence_speed=5.0)

        result = coord.select_best()
        self.assertEqual(result.best_trial_id, tid2)
        self.assertAlmostEqual(result.best_accuracy, 0.92)

    def test_no_completed_trials(self):
        coord = HPOCoordinator(max_trials=2)
        coord.generate_trials()
        result = coord.select_best()
        self.assertIsNone(result)

    def test_mark_failed(self):
        coord = HPOCoordinator(max_trials=1)
        trials = coord.generate_trials()
        coord.mark_failed(trials[0].trial_id, "OOM")
        self.assertEqual(coord.trials[trials[0].trial_id].status, "failed")


# =============================================================================
# PHASE 5 — GRADIENT COMPRESSION
# =============================================================================

class TestGradientCompression(unittest.TestCase):
    """Test compression validation policy."""

    def test_no_compression_pass(self):
        policy = GradientCompressionPolicy()
        v = policy.validate("hash1", "hash1", 0.85, 0.85)
        self.assertTrue(v.passed)
        self.assertTrue(v.determinism_preserved)

    def test_topk_pass(self):
        config = CompressionConfig(
            mode=CompressionMode.TOPK_SPARSE, topk_ratio=0.1,
        )
        policy = GradientCompressionPolicy(config)
        v = policy.validate("hash1", "hash2", 0.85, 0.849)
        self.assertTrue(v.passed)
        self.assertEqual(v.compression_ratio, 10.0)

    def test_accuracy_delta_fail(self):
        config = CompressionConfig(mode=CompressionMode.INT8_QUANTIZE)
        policy = GradientCompressionPolicy(config)
        v = policy.validate("hash1", "hash2", 0.85, 0.83)
        self.assertFalse(v.passed)
        self.assertGreater(v.accuracy_delta, 0.005)


# =============================================================================
# PHASE 6 — TLS POLICY
# =============================================================================

class TestTLSPolicy(unittest.TestCase):
    """Test TLS certificate validation."""

    def test_issue_and_validate(self):
        tls = TLSPolicy(authority_ca_id="test-ca-id")
        cert = tls.issue_certificate("node-1")
        v = tls.validate_node("node-1", cert)
        self.assertTrue(v.passed)
        self.assertTrue(v.cert_valid)
        self.assertTrue(v.issuer_match)
        self.assertTrue(v.not_expired)

    def test_reject_wrong_issuer(self):
        tls = TLSPolicy(authority_ca_id="test-ca-id")
        cert = NodeCertificate(
            node_id="node-1", cert_hash="fake",
            issuer="wrong-ca", issued_at=datetime.now().isoformat(),
            expires_at=(datetime.now() + timedelta(hours=24)).isoformat(),
        )
        v = tls.validate_node("node-1", cert)
        self.assertFalse(v.passed)
        self.assertFalse(v.issuer_match)

    def test_reject_expired(self):
        tls = TLSPolicy(authority_ca_id="test-ca-id")
        cert = tls.issue_certificate("node-1", validity_hours=24)
        # Tamper expiry
        cert.expires_at = (datetime.now() - timedelta(hours=1)).isoformat()
        v = tls.validate_node("node-1", cert)
        self.assertFalse(v.passed)
        self.assertFalse(v.not_expired)

    def test_reject_node_id_mismatch(self):
        tls = TLSPolicy(authority_ca_id="test-ca-id")
        cert = tls.issue_certificate("node-1")
        v = tls.validate_node("node-2", cert)  # Wrong node
        self.assertFalse(v.passed)
        self.assertFalse(v.node_id_match)

    def test_revoke_certificate(self):
        tls = TLSPolicy()
        cert = tls.issue_certificate("node-1")
        tls.revoke_certificate("node-1")
        v = tls.validate_node("node-1", cert)
        self.assertFalse(v.passed)


# =============================================================================
# PHASE 8 — RESOURCE UTILIZATION
# =============================================================================

class TestResourceUtilization(unittest.TestCase):
    """Test resource utilization policy."""

    def test_ddp_active_no_assignment(self):
        policy = ResourceUtilizationPolicy()
        d = policy.evaluate_node(
            "n1", gpu_util_pct=20, cpu_util_pct=30, ddp_active=True,
        )
        self.assertEqual(d.task, TaskType.NONE)

    def test_gpu_idle_hpo_assigned(self):
        policy = ResourceUtilizationPolicy()
        d = policy.evaluate_node(
            "n1", gpu_util_pct=10, cpu_util_pct=80,
            ddp_active=False, hpo_trials_pending=3,
        )
        self.assertEqual(d.task, TaskType.HPO_TRIAL)

    def test_gpu_idle_preprocessing(self):
        policy = ResourceUtilizationPolicy()
        d = policy.evaluate_node(
            "n1", gpu_util_pct=10, cpu_util_pct=80,
            ddp_active=False, hpo_trials_pending=0,
        )
        self.assertEqual(d.task, TaskType.PREPROCESSING)

    def test_cpu_idle_data_validation(self):
        policy = ResourceUtilizationPolicy()
        d = policy.evaluate_node(
            "n1", gpu_util_pct=80, cpu_util_pct=20,
            ddp_active=False,
        )
        self.assertEqual(d.task, TaskType.DATA_VALIDATION)

    def test_fully_utilized(self):
        policy = ResourceUtilizationPolicy()
        d = policy.evaluate_node(
            "n1", gpu_util_pct=80, cpu_util_pct=80,
            ddp_active=False,
        )
        self.assertEqual(d.task, TaskType.NONE)

    def test_get_idle_nodes(self):
        policy = ResourceUtilizationPolicy()
        policy.evaluate_node("n1", 10, 80, False, hpo_trials_pending=1)
        policy.evaluate_node("n2", 90, 90, True)
        idle = policy.get_idle_nodes()
        self.assertIn("n1", idle)
        self.assertNotIn("n2", idle)


if __name__ == '__main__':
    unittest.main()
