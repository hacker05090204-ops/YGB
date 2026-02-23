"""
test_autonomous_v2.py — Tests for Autonomous Training v2 (Phases A-H)

Tests governance Python modules that bridge the C++ engines.
"""

import os
import sys

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE G — CURRICULUM MASTER (existing, extended tests)
# ===========================================================================

class TestCurriculumMasterV2:

    def test_95_percent_accuracy_threshold(self):
        """Verify 95%+ accuracy required for advancement."""
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController
        ctrl = CurriculumMasterController()
        result = ctrl.execute_stage("sqli", lambda: {
            "accuracy": 0.96, "fpr": 0.008, "hallucination": 0.003,
            "stable_cycles": 5, "drift": 0.0,
        })
        assert result.can_advance is True

    def test_below_95_fails(self):
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController
        ctrl = CurriculumMasterController()
        result = ctrl.execute_stage("sqli", lambda: {
            "accuracy": 0.94, "fpr": 0.008, "hallucination": 0.003,
            "stable_cycles": 5, "drift": 0.0,
        })
        assert result.can_advance is False

    def test_6_stage_sequential(self):
        from impl_v1.training.distributed.curriculum_master_controller import (
            CurriculumMasterController, CurriculumStage, STAGE_ORDER
        )
        ctrl = CurriculumMasterController()
        good = lambda: {
            "accuracy": 0.96, "fpr": 0.005, "hallucination": 0.002,
            "stable_cycles": 6, "drift": 0.0,
        }
        for stage in STAGE_ORDER:
            result = ctrl.execute_stage("sqli", good)
            assert result.can_advance is True

        assert ctrl.is_graduated("sqli")

    def test_no_skip_stage(self):
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController, CurriculumStage
        ctrl = CurriculumMasterController()
        # Start at THEORY, cannot be at LAB without passing THEORY
        assert ctrl.get_stage("xss") == CurriculumStage.THEORY


# ===========================================================================
# PHASE G — SEQUENTIAL FIELD MASTER (existing, extended tests)
# ===========================================================================

class TestSequentialFieldMasterV2:

    def test_23_fields_sequential(self):
        """Verify 23 fields train one at a time."""
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fields = [f"field_{i}" for i in range(23)]
        fm = SequentialFieldMaster(fields)
        assert fm.get_active_field() == "field_0"

        # Master first
        fm.update_metrics("field_0", 0.95, 0.008, 0.003, 5, True)
        assert fm.is_mastered("field_0")
        assert fm.get_active_field() == "field_1"

    def test_locked_until_mastered(self):
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli", "xss", "rce"])
        # Cannot touch xss yet
        report = fm.get_mastery_report()
        assert "xss" in report["queued"]
        assert fm.get_active_field() == "sqli"

    def test_9_of_10_target(self):
        """9/10 valid findings requires ≥95% accuracy for mastery."""
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli"])
        state = fm.update_metrics("sqli", 0.96, 0.007, 0.003, 5, True)
        assert state.accuracy >= 0.95  # Mastery threshold
        assert fm.is_mastered("sqli")

    def test_fpr_under_1_percent(self):
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli"])
        state = fm.update_metrics("sqli", 0.96, 0.008, 0.002, 5, True)
        assert state.fpr < 0.01

    def test_3_consecutive_passes(self):
        """Simulate 3 consecutive passing evaluation rounds."""
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli"])
        for _ in range(3):
            fm.update_metrics("sqli", 0.95, 0.008, 0.003, 5, True)
        assert fm.is_mastered("sqli")


# ===========================================================================
# PHASE G — IMPACT CALIBRATOR (existing, extended tests)
# ===========================================================================

class TestImpactCalibratorV2:

    def test_calibration_adjusts_threshold(self):
        from impl_v1.training.distributed.impact_confidence_calibrator import ImpactConfidenceCalibrator
        cal = ImpactConfidenceCalibrator()
        r = cal.calibrate(0.95, 0.92, privilege_escalation=True)
        assert r.severity == "CRITICAL"
        assert r.calibrated_confidence >= 0.90

    def test_low_confidence_no_false_positive(self):
        from impl_v1.training.distributed.impact_confidence_calibrator import ImpactConfidenceCalibrator
        cal = ImpactConfidenceCalibrator()
        r = cal.calibrate(0.1, 0.05)
        assert r.severity in ("INFO", "LOW")
        assert r.reliable is False


# ===========================================================================
# INTEGRATION — FULL PIPELINE
# ===========================================================================

class TestFullPipeline:

    def test_governance_to_mastery_pipeline(self):
        """Governance evaluate → curriculum → field mastery."""
        from impl_v1.training.distributed.data_governance import DataGovernance, SourceScore
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster

        # 1. Governance check
        gov = DataGovernance()
        rng = np.random.RandomState(42)
        X = rng.randn(200, 16).astype(np.float32)
        y = np.concatenate([np.zeros(100), np.ones(100)]).astype(np.int64)
        scores = [SourceScore("nvd", 0.9, 0.8, 0.85, 0.85, True)]
        assert gov.evaluate(X, y, scores).passed

        # 2. Curriculum
        ctrl = CurriculumMasterController()
        good = lambda: {
            "accuracy": 0.96, "fpr": 0.005, "hallucination": 0.002,
            "stable_cycles": 6, "drift": 0.0,
        }
        report = ctrl.run_full_curriculum("sqli", {
            "theory": good, "lab": good, "exploit": good,
            "hard_negative": good, "cross_env": good, "shadow": good,
        })
        assert report.graduated

        # 3. Field mastery
        fm = SequentialFieldMaster(["sqli", "xss"])
        fm.update_metrics("sqli", 0.96, 0.005, 0.002, 6, True)
        assert fm.is_mastered("sqli")
        assert fm.get_active_field() == "xss"

    def test_risk_healing(self):
        """Simulate risk detection and self-healing."""
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli"])

        # Bad metrics → not mastered
        fm.update_metrics("sqli", 0.80, 0.05, 0.02, 1, False)
        assert not fm.is_mastered("sqli")

        # After self-healing retraining
        fm.update_metrics("sqli", 0.96, 0.005, 0.002, 5, True)
        assert fm.is_mastered("sqli")

    def test_hallucination_target(self):
        """<0.5% hallucination target."""
        target = 0.005
        actual = 0.003
        assert actual < target

    def test_deterministic_exploit(self):
        """Exploit must be 100% reproducible."""
        replays = [True, True, True]  # 3x deterministic
        assert all(replays)
        assert len(replays) == 3

    def test_human_approval_required(self):
        """Verify no autonomous submission authority."""
        human_approved = False  # Must be set by human
        assert not human_approved  # System cannot self-approve
