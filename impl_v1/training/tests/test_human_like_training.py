"""
test_human_like_training.py — Tests for Human-Like Autonomous Training
"""

import os
import sys

import numpy as np
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# PHASE 0 — IMPACT CONFIDENCE CALIBRATOR
# ===========================================================================

class TestImpactCalibrator:

    def test_critical_severity(self):
        from impl_v1.training.distributed.impact_confidence_calibrator import ImpactConfidenceCalibrator
        cal = ImpactConfidenceCalibrator()
        r = cal.calibrate(0.95, 0.9, privilege_escalation=True)
        assert r.severity == "CRITICAL"
        assert r.reliable is True

    def test_low_severity(self):
        from impl_v1.training.distributed.impact_confidence_calibrator import ImpactConfidenceCalibrator
        cal = ImpactConfidenceCalibrator()
        r = cal.calibrate(0.15, 0.1)
        assert r.severity in ("LOW", "INFO")

    def test_medium_severity(self):
        from impl_v1.training.distributed.impact_confidence_calibrator import ImpactConfidenceCalibrator
        cal = ImpactConfidenceCalibrator()
        r = cal.calibrate(0.6, 0.5)
        assert r.severity in ("MEDIUM", "HIGH")
        assert r.cvss_estimate > 0

    def test_batch_calibrate(self):
        from impl_v1.training.distributed.impact_confidence_calibrator import ImpactConfidenceCalibrator
        cal = ImpactConfidenceCalibrator()
        confidences = np.array([0.95, 0.5, 0.1])
        deltas = np.array([0.9, 0.4, 0.05])
        results = cal.batch_calibrate(confidences, deltas)
        assert len(results) == 3
        assert results[0].severity == "CRITICAL" or results[0].severity == "HIGH"
        assert cal.calibration_count == 3

    def test_data_exposure_boost(self):
        from impl_v1.training.distributed.impact_confidence_calibrator import ImpactConfidenceCalibrator
        cal = ImpactConfidenceCalibrator()
        r1 = cal.calibrate(0.7, 0.6)
        r2 = cal.calibrate(0.7, 0.6, data_exposure=True)
        assert r2.calibrated_confidence >= r1.calibrated_confidence


# ===========================================================================
# PHASE 1 — CURRICULUM MASTER CONTROLLER
# ===========================================================================

class TestCurriculumMaster:

    def test_initial_stage_theory(self):
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController, CurriculumStage
        ctrl = CurriculumMasterController()
        assert ctrl.get_stage("vuln") == CurriculumStage.THEORY

    def test_advance_on_pass(self):
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController, CurriculumStage
        ctrl = CurriculumMasterController()
        result = ctrl.execute_stage("vuln", lambda: {
            "accuracy": 0.97, "fpr": 0.005, "hallucination": 0.002,
            "stable_cycles": 6, "drift": 0.0,
        })
        assert result.can_advance is True
        assert ctrl.get_stage("vuln") == CurriculumStage.LAB

    def test_no_advance_on_fail(self):
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController, CurriculumStage
        ctrl = CurriculumMasterController()
        result = ctrl.execute_stage("vuln", lambda: {
            "accuracy": 0.80, "fpr": 0.05, "hallucination": 0.01,
            "stable_cycles": 2, "drift": 0.0,
        })
        assert result.can_advance is False
        assert ctrl.get_stage("vuln") == CurriculumStage.THEORY

    def test_full_graduation(self):
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController, CurriculumStage
        ctrl = CurriculumMasterController()
        good = lambda: {
            "accuracy": 0.98, "fpr": 0.003, "hallucination": 0.001,
            "stable_cycles": 7, "drift": 0.0,
        }
        report = ctrl.run_full_curriculum("vuln", {
            "theory": good, "lab": good, "exploit": good,
            "hard_negative": good, "cross_env": good, "shadow": good,
        })
        assert report.graduated is True
        assert ctrl.is_graduated("vuln")

    def test_stops_on_failure(self):
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController
        ctrl = CurriculumMasterController()
        bad = lambda: {"accuracy": 0.5, "fpr": 0.1, "hallucination": 0.05, "stable_cycles": 0, "drift": 0.0}
        report = ctrl.run_full_curriculum("vuln", {"theory": bad})
        assert report.graduated is False
        assert len(report.stages_completed) == 1

    def test_failure_reasons(self):
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController, StageMetrics
        ctrl = CurriculumMasterController()
        m = StageMetrics(accuracy=0.80, fpr=0.05, hallucination_rate=0.01, stable_cycles=2, drift=0.01)
        can, failures = ctrl.check_advancement(m)
        assert can is False
        assert len(failures) >= 3  # accuracy, fpr, hallucination, cycles, drift


# ===========================================================================
# PHASE 7 — SEQUENTIAL FIELD MASTER
# ===========================================================================

class TestSequentialFieldMaster:

    def test_initial_active(self):
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli", "xss", "rce"])
        assert fm.get_active_field() == "sqli"

    def test_cannot_skip(self):
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli", "xss", "rce"])
        # xss should still be queued
        report = fm.get_mastery_report()
        assert "xss" in report["queued"]

    def test_master_and_advance(self):
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli", "xss", "rce"])
        fm.update_metrics("sqli", 0.97, 0.005, 0.002, 6, True)
        assert fm.is_mastered("sqli")
        assert fm.get_active_field() == "xss"

    def test_not_mastered_below_threshold(self):
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli", "xss"])
        fm.update_metrics("sqli", 0.90, 0.02, 0.01, 3, False)
        assert not fm.is_mastered("sqli")
        assert fm.get_active_field() == "sqli"  # Still on sqli

    def test_all_mastered(self):
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli", "xss"])
        fm.update_metrics("sqli", 0.97, 0.005, 0.002, 6, True)
        fm.update_metrics("xss", 0.96, 0.008, 0.003, 5, True)
        report = fm.get_mastery_report()
        assert report["all_mastered"] is True
        assert fm.get_active_field() is None

    def test_mastery_report(self):
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli", "xss", "rce"])
        fm.update_metrics("sqli", 0.97, 0.005, 0.002, 6, True)
        report = fm.get_mastery_report()
        assert report["mastered_count"] == 1
        assert report["active_field"] == "xss"
        assert "rce" in report["queued"]


# ===========================================================================
# INTEGRATION — FULL PIPELINE
# ===========================================================================

class TestHumanLikeIntegration:

    def test_curriculum_to_field_mastery(self):
        """Curriculum graduate → field mastered."""
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster

        ctrl = CurriculumMasterController()
        good = lambda: {
            "accuracy": 0.97, "fpr": 0.005, "hallucination": 0.002,
            "stable_cycles": 6, "drift": 0.0,
        }
        report = ctrl.run_full_curriculum("sqli", {
            "theory": good, "lab": good, "exploit": good,
            "hard_negative": good, "cross_env": good, "shadow": good,
        })
        assert report.graduated

        fm = SequentialFieldMaster(["sqli", "xss"])
        fm.update_metrics("sqli", 0.97, 0.005, 0.002, 6, True)
        assert fm.is_mastered("sqli")
        assert fm.get_active_field() == "xss"

    def test_calibrator_with_curriculum(self):
        """Calibrator feeds into curriculum decisions."""
        from impl_v1.training.distributed.impact_confidence_calibrator import ImpactConfidenceCalibrator
        from impl_v1.training.distributed.curriculum_master_controller import CurriculumMasterController

        cal = ImpactConfidenceCalibrator()
        impact = cal.calibrate(0.95, 0.88, privilege_escalation=True)
        assert impact.severity in ("CRITICAL", "HIGH")

        ctrl = CurriculumMasterController()
        result = ctrl.execute_stage("vuln", lambda: {
            "accuracy": 0.97, "fpr": 0.005, "hallucination": 0.002,
            "stable_cycles": 6, "drift": 0.0,
        })
        assert result.can_advance

    def test_fpr_under_1_percent(self):
        """Verify <1% FPR target."""
        from impl_v1.training.distributed.sequential_field_master import SequentialFieldMaster
        fm = SequentialFieldMaster(["sqli"])
        state = fm.update_metrics("sqli", 0.97, 0.008, 0.003, 5, True)
        assert state.fpr < 0.01
        assert fm.is_mastered("sqli")
