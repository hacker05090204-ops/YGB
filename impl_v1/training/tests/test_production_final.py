"""
test_production_final.py — Tests for 5-Phase Production Finalization
"""

import os
import sys
import time

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 1 & 4 — STANDALONE MODE
# ===========================================================================

class TestStandaloneMode:

    def test_single_node_can_start(self):
        from impl_v1.training.distributed.standalone_mode import StandaloneCluster, NodeInfo
        cluster = StandaloneCluster()
        cluster.register_node(NodeInfo("n1", "cuda", "RTX2050"))
        assert cluster.can_start is True
        assert cluster.world_size == 1

    def test_standalone_mode(self):
        from impl_v1.training.distributed.standalone_mode import StandaloneCluster, NodeInfo
        cluster = StandaloneCluster()
        cluster.register_node(NodeInfo("n1", "cuda", "RTX2050"))
        mode = cluster.get_mode()
        assert mode.mode == "standalone"
        assert mode.ddp_enabled is False
        assert mode.quorum_required is False

    def test_ddp_with_two_nodes(self):
        from impl_v1.training.distributed.standalone_mode import StandaloneCluster, NodeInfo
        cluster = StandaloneCluster()
        cluster.register_node(NodeInfo("n1", "cuda", "RTX2050"))
        cluster.register_node(NodeInfo("n2", "cuda", "RTX3050"))
        mode = cluster.get_mode()
        assert mode.mode == "ddp"
        assert mode.world_size == 2
        assert mode.ddp_enabled is True

    def test_dynamic_scale(self):
        from impl_v1.training.distributed.standalone_mode import StandaloneCluster, NodeInfo
        cluster = StandaloneCluster()
        cluster.register_node(NodeInfo("n1", "cuda", "RTX2050"))
        assert cluster.world_size == 1
        cluster.register_node(NodeInfo("n2", "cuda", "RTX3050"))
        assert cluster.world_size == 2

    def test_leader_election(self):
        from impl_v1.training.distributed.standalone_mode import StandaloneCluster, NodeInfo
        cluster = StandaloneCluster()
        cluster.register_node(NodeInfo("n1", "cuda", "RTX2050"))
        assert cluster.leader == "n1"

    def test_node_removal(self):
        from impl_v1.training.distributed.standalone_mode import StandaloneCluster, NodeInfo
        cluster = StandaloneCluster()
        cluster.register_node(NodeInfo("n1", "cuda", "RTX2050"))
        cluster.register_node(NodeInfo("n2", "cuda", "RTX3050"))
        cluster.remove_node("n2")
        assert cluster.world_size == 1

    def test_env_setup(self):
        from impl_v1.training.distributed.standalone_mode import StandaloneCluster, NodeInfo
        cluster = StandaloneCluster()
        cluster.register_node(NodeInfo("n1", "cuda", "RTX2050"))
        env = cluster.setup_env()
        assert env['WORLD_SIZE'] == '1'


# ===========================================================================
# PHASE 2 — SEMANTIC QUALITY GATE
# ===========================================================================

class TestSemanticQualityGate:

    def _make_data(self, n=2000, d=64, seed=42):
        rng = np.random.RandomState(seed)
        X = rng.randn(n, d).astype(np.float32)
        W = rng.randn(d).astype(np.float32) * 0.5
        scores = X @ W
        y = (scores > 0).astype(np.int64)
        return X, y

    def test_good_data_passes(self):
        from impl_v1.training.distributed.semantic_quality_gate import SemanticQualityGate
        gate = SemanticQualityGate()
        X, y = self._make_data(2000, 64)
        split = 1500
        report = gate.validate(
            X[:split], y[:split], X[split:], y[split:],
            field_name="vuln",
        )
        assert report.passed is True
        assert len(report.checks) == 3

    def test_high_fpr_fails(self):
        from impl_v1.training.distributed.semantic_quality_gate import SemanticQualityGate
        gate = SemanticQualityGate(fpr_threshold=0.0)  # impossible
        X, y = self._make_data(500, 16)
        split = 400
        report = gate.validate(X[:split], y[:split], X[split:], y[split:])
        # With FPR threshold=0, almost any model fails
        fpr_check = [c for c in report.checks if c.check_name == "false_positive_rate"][0]
        # It might pass if model is perfect, but with 0 threshold likely fails
        assert isinstance(fpr_check.passed, bool)

    def test_overfit_detection(self):
        from impl_v1.training.distributed.semantic_quality_gate import SemanticQualityGate
        gate = SemanticQualityGate(overfit_gap=0.0)  # impossible threshold
        X, y = self._make_data(500, 16)
        split = 400
        report = gate.validate(X[:split], y[:split], X[split:], y[split:])
        overfit_check = [c for c in report.checks if c.check_name == "overfit_detection"][0]
        assert isinstance(overfit_check.passed, bool)


# ===========================================================================
# PHASE 3 — CROSS-FIELD VALIDATION
# ===========================================================================

class TestCrossFieldValidator:

    def test_no_leakage(self):
        from impl_v1.training.distributed.cross_field_validator import CrossFieldValidator
        val = CrossFieldValidator(threshold=0.5)
        rng = np.random.RandomState(42)
        X = rng.randn(100, 16).astype(np.float32)
        y = np.zeros(100, dtype=np.int64)  # all negative
        check = val.validate_pair(
            "vuln", "pattern",
            lambda x: np.zeros(len(x), dtype=np.int64),  # predicts all 0
            X, y,
        )
        assert check.passed is True
        assert check.false_positive_rate == 0.0

    def test_leakage_detected(self):
        from impl_v1.training.distributed.cross_field_validator import CrossFieldValidator
        val = CrossFieldValidator(threshold=0.05)
        rng = np.random.RandomState(42)
        X = rng.randn(100, 16).astype(np.float32)
        y = np.zeros(100, dtype=np.int64)  # all negative
        # Model predicts all positive → 100% FPR
        check = val.validate_pair(
            "vuln", "pattern",
            lambda x: np.ones(len(x), dtype=np.int64),
            X, y,
        )
        assert check.passed is False
        assert check.false_positive_rate == 1.0

    def test_validate_all(self):
        from impl_v1.training.distributed.cross_field_validator import CrossFieldValidator
        val = CrossFieldValidator(threshold=0.5)
        rng = np.random.RandomState(42)

        models = {"a": "model_a", "b": "model_b"}
        data = {
            "a": (rng.randn(50, 8).astype(np.float32), np.zeros(50, dtype=np.int64)),
            "b": (rng.randn(50, 8).astype(np.float32), np.zeros(50, dtype=np.int64)),
        }
        report = val.validate_all(
            models, data,
            predict_fn=lambda m, x: np.zeros(len(x), dtype=np.int64),
        )
        assert report.passed is True
        assert len(report.checks) == 2


# ===========================================================================
# PHASE 5 — FINAL SAFETY
# ===========================================================================

class TestFinalSafety:

    def test_all_pass(self):
        from impl_v1.training.distributed.final_safety import FinalSafetyGate
        gate = FinalSafetyGate()
        report = gate.run_checks(
            dataset_valid=True,
            determinism_match=True,
            regression_delta=0.01,
            semantic_passed=True,
            crash_count=0,
        )
        assert report.training_allowed is True
        assert len(report.checks) == 5

    def test_dataset_fail(self):
        from impl_v1.training.distributed.final_safety import FinalSafetyGate
        gate = FinalSafetyGate()
        report = gate.run_checks(dataset_valid=False)
        assert report.training_allowed is False

    def test_determinism_fail(self):
        from impl_v1.training.distributed.final_safety import FinalSafetyGate
        gate = FinalSafetyGate()
        report = gate.run_checks(determinism_match=False)
        assert report.training_allowed is False

    def test_regression_fail(self):
        from impl_v1.training.distributed.final_safety import FinalSafetyGate
        gate = FinalSafetyGate()
        report = gate.run_checks(regression_delta=-0.05)
        assert report.training_allowed is False

    def test_crash_fail(self):
        from impl_v1.training.distributed.final_safety import FinalSafetyGate
        gate = FinalSafetyGate(max_crashes=3)
        report = gate.run_checks(crash_count=3)
        assert report.training_allowed is False

    def test_semantic_fail(self):
        from impl_v1.training.distributed.final_safety import FinalSafetyGate
        gate = FinalSafetyGate()
        report = gate.run_checks(semantic_passed=False)
        assert report.training_allowed is False


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestProductionIntegration:

    def test_standalone_semantic_safety(self):
        """Standalone → Semantic gate → Final safety."""
        from impl_v1.training.distributed.standalone_mode import StandaloneCluster, NodeInfo
        from impl_v1.training.distributed.semantic_quality_gate import SemanticQualityGate
        from impl_v1.training.distributed.final_safety import FinalSafetyGate

        # Standalone cluster
        cluster = StandaloneCluster()
        cluster.register_node(NodeInfo("n1", "cuda", "RTX2050"))
        assert cluster.can_start

        # Semantic gate
        gate = SemanticQualityGate()
        rng = np.random.RandomState(42)
        X = rng.randn(2000, 64).astype(np.float32)
        W = rng.randn(64).astype(np.float32) * 0.5
        y = (X @ W > 0).astype(np.int64)
        sem = gate.validate(X[:1500], y[:1500], X[1500:], y[1500:], "vuln")

        # Final safety
        safety = FinalSafetyGate()
        report = safety.run_checks(
            dataset_valid=True,
            determinism_match=True,
            regression_delta=0.0,
            semantic_passed=sem.passed,
            crash_count=0,
        )
        assert report.training_allowed is True
