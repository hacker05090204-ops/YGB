"""
test_risk_elimination.py — Tests for 5-Phase Risk Elimination
"""

import os
import sys

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 1 — ADVERSARIAL SAMPLING
# ===========================================================================

class TestAdversarialSampling:

    def _make_data(self, n=2000, d=64, seed=42):
        rng = np.random.RandomState(seed)
        X = rng.randn(n, d).astype(np.float32)
        W = rng.randn(d).astype(np.float32) * 0.5
        y = (X @ W > 0).astype(np.int64)
        return X, y

    def test_good_data_passes(self):
        from impl_v1.training.distributed.adversarial_sampling import AdversarialSamplingGate
        gate = AdversarialSamplingGate(max_drop=0.50)  # generous
        X, y = self._make_data()
        report = gate.validate(X, y, "vuln")
        assert len(report.results) == 3
        assert report.holdout_size > 0

    def test_three_perturbations(self):
        from impl_v1.training.distributed.adversarial_sampling import AdversarialSamplingGate
        gate = AdversarialSamplingGate()
        X, y = self._make_data()
        report = gate.validate(X, y)
        names = [r.perturbation for r in report.results]
        assert "gaussian_noise" in names
        assert "feature_permutation" in names
        assert "sign_flip" in names

    def test_worst_drop_tracked(self):
        from impl_v1.training.distributed.adversarial_sampling import AdversarialSamplingGate
        gate = AdversarialSamplingGate()
        X, y = self._make_data()
        report = gate.validate(X, y)
        assert report.worst_drop >= 0


# ===========================================================================
# PHASE 2 — SUB-PATTERN VALIDATION
# ===========================================================================

class TestSubPatternValidator:

    def test_full_ready(self):
        from impl_v1.training.distributed.sub_pattern_validator import SubPatternValidator
        val = SubPatternValidator()
        y_true = np.array([0, 0, 1, 1, 0, 0, 1, 1])
        y_pred = np.array([0, 0, 1, 1, 0, 0, 1, 1])  # perfect
        tags = np.array(["sqli", "sqli", "sqli", "sqli", "xss", "xss", "xss", "xss"])
        report = val.validate("vuln", y_true, y_pred, tags)
        assert report.status == "FULL_READY"

    def test_partial_ready(self):
        from impl_v1.training.distributed.sub_pattern_validator import SubPatternValidator
        val = SubPatternValidator(sub_min=0.90, global_min=0.50)
        y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1])
        y_pred = np.array([0, 0, 1, 1, 1, 0, 1, 0])  # xss all wrong
        tags = np.array(["sqli", "sqli", "sqli", "sqli", "xss", "xss", "xss", "xss"])
        report = val.validate("vuln", y_true, y_pred, tags)
        # sqli perfect, xss terrible → PARTIAL
        assert len(report.weak_patterns) > 0

    def test_not_ready(self):
        from impl_v1.training.distributed.sub_pattern_validator import SubPatternValidator
        val = SubPatternValidator(global_min=0.99)
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 0, 0, 1])  # 75%
        tags = np.array(["a", "a", "b", "b"])
        report = val.validate("vuln", y_true, y_pred, tags)
        assert report.status == "NOT_READY"


# ===========================================================================
# PHASE 3 — DRIVER CONSISTENCY
# ===========================================================================

class TestDriverConsistency:

    def test_single_node(self):
        from impl_v1.training.distributed.driver_consistency import DriverConsistency, DriverInfo
        dc = DriverConsistency()
        dc.register_node(DriverInfo("n1", "12.1", "535.0", "8.6", "RTX2050"))
        check = dc.check()
        assert check.consistent is True
        assert check.determinism_allowed is True

    def test_matching_cluster(self):
        from impl_v1.training.distributed.driver_consistency import DriverConsistency, DriverInfo
        dc = DriverConsistency()
        dc.register_node(DriverInfo("n1", "12.1", "535.0", "8.6", "RTX2050"))
        dc.register_node(DriverInfo("n2", "12.1", "535.0", "8.6", "RTX3050"))
        check = dc.check()
        assert check.consistent is True

    def test_cuda_mismatch(self):
        from impl_v1.training.distributed.driver_consistency import DriverConsistency, DriverInfo
        dc = DriverConsistency()
        dc.register_node(DriverInfo("n1", "12.1", "535.0", "8.6", "RTX2050"))
        dc.register_node(DriverInfo("n2", "11.8", "535.0", "8.6", "RTX3050"))
        check = dc.check()
        assert check.consistent is False
        assert check.determinism_allowed is False

    def test_driver_mismatch(self):
        from impl_v1.training.distributed.driver_consistency import DriverConsistency, DriverInfo
        dc = DriverConsistency()
        dc.register_node(DriverInfo("n1", "12.1", "535.0", "8.6", "RTX2050"))
        dc.register_node(DriverInfo("n2", "12.1", "530.0", "8.6", "RTX3050"))
        check = dc.check()
        assert check.consistent is False


# ===========================================================================
# PHASE 4 — DECAY DETECTOR
# ===========================================================================

class TestDecayDetector:

    def test_stable_no_decay(self):
        from impl_v1.training.distributed.decay_detector import DecayDetector
        det = DecayDetector(window_size=7, precision_drop=0.03)
        for i in range(7):
            report = det.record(0.95, 0.94, 0.93)
        assert report.decay_detected is False

    def test_precision_decay(self):
        from impl_v1.training.distributed.decay_detector import DecayDetector
        det = DecayDetector(window_size=4, precision_drop=0.03)
        # First half: high precision
        for _ in range(2):
            det.record(0.95, 0.93, 0.90)
        # Second half: precision drops
        for _ in range(2):
            report = det.record(0.95, 0.85, 0.90)
        assert report.decay_detected is True
        assert report.retrain_needed is True

    def test_insufficient_data(self):
        from impl_v1.training.distributed.decay_detector import DecayDetector
        det = DecayDetector(window_size=7)
        report = det.record(0.95, 0.94, 0.93)
        assert report.decay_detected is False
        assert report.reason == "Insufficient data"


# ===========================================================================
# PHASE 5 — DATA SOURCE SCORING
# ===========================================================================

class TestDataSourceScoring:

    def test_trusted_source(self):
        from impl_v1.training.distributed.data_source_scoring import DataSourceScorer
        scorer = DataSourceScorer()
        score = scorer.register_source("src1", "vuln", 0.9, 0.8, 0.7)
        assert score.trusted is True
        assert score.composite_score > 0.5

    def test_untrusted_source(self):
        from impl_v1.training.distributed.data_source_scoring import DataSourceScorer
        scorer = DataSourceScorer()
        score = scorer.register_source("src2", "vuln", 0.1, 0.1, 0.1)
        assert score.trusted is False

    def test_gate_check_trusted(self):
        from impl_v1.training.distributed.data_source_scoring import DataSourceScorer
        scorer = DataSourceScorer()
        scorer.register_source("src1", "vuln", 0.9, 0.8, 0.7)
        result = scorer.gate_check("src1")
        assert result.requires_stronger_gate is False

    def test_gate_check_untrusted(self):
        from impl_v1.training.distributed.data_source_scoring import DataSourceScorer
        scorer = DataSourceScorer()
        scorer.register_source("src2", "vuln", 0.1, 0.1, 0.1)
        result = scorer.gate_check("src2")
        assert result.requires_stronger_gate is True

    def test_unknown_source(self):
        from impl_v1.training.distributed.data_source_scoring import DataSourceScorer
        scorer = DataSourceScorer()
        result = scorer.gate_check("unknown")
        assert result.requires_stronger_gate is True


# ===========================================================================
# INTEGRATION
# ===========================================================================

class TestRiskIntegration:

    def test_adversarial_then_subpattern(self):
        """Adversarial gate → sub-pattern validation."""
        from impl_v1.training.distributed.adversarial_sampling import AdversarialSamplingGate
        from impl_v1.training.distributed.sub_pattern_validator import SubPatternValidator

        rng = np.random.RandomState(42)
        X = rng.randn(1000, 32).astype(np.float32)
        W = rng.randn(32).astype(np.float32) * 0.5
        y = (X @ W > 0).astype(np.int64)

        # Adversarial
        adv = AdversarialSamplingGate(max_drop=0.50)
        adv_report = adv.validate(X, y, "vuln")
        assert len(adv_report.results) == 3

        # Sub-pattern
        tags = np.array(["a", "b"] * 500)
        sub = SubPatternValidator(sub_min=0.0, global_min=0.0)
        sub_report = sub.validate("vuln", y, y, tags)
        assert sub_report.status == "FULL_READY"
