"""
test_bounty_ready_v2.py — Comprehensive Test Suite for Bounty-Ready System

Tests all 9 phases:
  Phase 5: Chaos variance injector stability
  Phase 6: Semantic entropy guard enforcement
  Phase 7: CVSS v3.1 + triager bias + program heuristic
  Phase 8: Report compiler + anti-hallucination gate
  Integration: End-to-end pipeline
"""

import sys
import os
import unittest

import numpy as np

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

from impl_v1.training.distributed.semantic_entropy_guard import (
    SemanticEntropyGuard,
)
from impl_v1.training.distributed.impact_confidence_calibrator import (
    ImpactConfidenceCalibrator,
)
from impl_v1.training.distributed.report_structural_compiler import (
    ReportStructuralCompiler,
    ExploitEvidence,
    EvidenceArtifact,
    AntiHallucinationGate,
)
from impl_v1.training.distributed.sequential_field_master import (
    SequentialFieldMaster,
)


class TestChaosVarianceInjector(unittest.TestCase):
    """Phase 5: Chaos variance testing."""

    def test_cpp_file_exists(self):
        """Verify chaos_variance_injector.cpp exists."""
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..',
            'native', 'distributed', 'chaos_variance_injector.cpp'
        )
        self.assertTrue(os.path.isfile(path), "chaos_variance_injector.cpp missing")

    def test_has_stability_threshold(self):
        """Verify STABILITY_THRESHOLD is defined."""
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..',
            'native', 'distributed', 'chaos_variance_injector.cpp'
        )
        with open(path) as f:
            content = f.read()
        self.assertIn("STABILITY_THRESHOLD", content)
        self.assertIn("0.95", content)

    def test_has_all_chaos_types(self):
        """Verify all chaos injection types are defined."""
        path = os.path.join(
            os.path.dirname(__file__), '..', '..', '..',
            'native', 'distributed', 'chaos_variance_injector.cpp'
        )
        with open(path) as f:
            content = f.read()
        for chaos_type in [
            "CHAOS_LATENCY_JITTER",
            "CHAOS_MIDDLEWARE_REWRITE",
            "CHAOS_TLS_NOISE",
            "CHAOS_HEADER_MUTATION",
        ]:
            self.assertIn(chaos_type, content)


class TestSemanticEntropyGuard(unittest.TestCase):
    """Phase 6: Semantic entropy guard."""

    def setUp(self):
        self.guard = SemanticEntropyGuard(n_classes=2)
        np.random.seed(42)
        features = np.random.randn(200, 32)
        labels = np.array([0] * 100 + [1] * 100)
        self.guard.set_baseline(features, labels)

    def test_normal_batch_passes(self):
        """Normal batch with real data should pass."""
        features = np.random.randn(50, 32)
        labels = np.array([0] * 25 + [1] * 25)
        ok, reason = self.guard.check_batch(features, labels)
        self.assertTrue(ok, f"Normal batch should pass: {reason}")

    def test_rl_cap_enforced(self):
        """Batch with >20% RL data should be rejected."""
        features = np.random.randn(50, 32)
        labels = np.array([0] * 25 + [1] * 25)
        ok, reason = self.guard.check_batch(
            features, labels, rl_count=15, total_count=50
        )
        self.assertFalse(ok)
        self.assertIn("RL ratio", reason)
        self.assertTrue(self.guard.is_frozen)

    def test_synthetic_only_rejected(self):
        """Synthetic-only batch should be rejected."""
        guard = SemanticEntropyGuard(n_classes=2)
        features = np.random.randn(50, 32)
        labels = np.array([0] * 25 + [1] * 25)
        ok, reason = guard.check_batch(
            features, labels, synthetic_count=50, total_count=50
        )
        self.assertFalse(ok)
        self.assertIn("Synthetic-only", reason)

    def test_frozen_blocks_all(self):
        """Once frozen, all batches are blocked."""
        features = np.random.randn(50, 32)
        labels = np.array([0] * 25 + [1] * 25)
        # Trigger freeze
        self.guard.check_batch(features, labels, rl_count=30, total_count=50)
        self.assertTrue(self.guard.is_frozen)
        # Subsequent normal batch blocked
        ok, reason = self.guard.check_batch(features, labels)
        self.assertFalse(ok)
        self.assertIn("FROZEN", reason)

    def test_unfreeze(self):
        """Manual unfreeze should allow batches again."""
        features = np.random.randn(50, 32)
        labels = np.array([0] * 25 + [1] * 25)
        self.guard.check_batch(features, labels, rl_count=30, total_count=50)
        self.guard.unfreeze()
        ok, _ = self.guard.check_batch(features, labels)
        self.assertTrue(ok)

    def test_report(self):
        """Guard report returns valid structure."""
        report = self.guard.get_report()
        self.assertIsInstance(report.total_batches, int)
        self.assertIsInstance(report.frozen, bool)
        self.assertIsInstance(report.violations, list)


class TestImpactConfidenceCalibrator(unittest.TestCase):
    """Phase 7: CVSS + triager bias + program heuristic."""

    def setUp(self):
        self.cal = ImpactConfidenceCalibrator()

    def test_basic_calibration(self):
        """Basic calibration maps confidence to severity."""
        result = self.cal.calibrate(0.95, 0.8)
        self.assertIn(result.severity, ["CRITICAL", "HIGH"])
        self.assertGreater(result.calibrated_confidence, 0.5)

    def test_cvss_vector_generation(self):
        """CVSS v3.1 vector should be properly formatted."""
        vector, score = self.cal.generate_cvss_vector(
            attack_vector="NETWORK",
            attack_complexity="LOW",
            privileges_required="NONE",
            user_interaction="NONE",
            scope="UNCHANGED",
            conf_impact="HIGH",
            integ_impact="HIGH",
            avail_impact="NONE",
        )
        self.assertTrue(vector.startswith("CVSS:3.1/"))
        self.assertGreater(score, 0.0)
        self.assertLessEqual(score, 10.0)

    def test_cvss_low_impact(self):
        """Low impact should give low CVSS score."""
        _, score = self.cal.generate_cvss_vector(
            attack_vector="PHYSICAL",
            attack_complexity="HIGH",
            privileges_required="HIGH",
            user_interaction="REQUIRED",
            scope="UNCHANGED",
            conf_impact="NONE",
            integ_impact="LOW",
            avail_impact="NONE",
        )
        self.assertLess(score, 5.0)

    def test_triager_bias_tracking(self):
        """Triager bias should track accept/reject rates."""
        self.cal.record_triager_decision("HIGH", True)
        self.cal.record_triager_decision("HIGH", True)
        self.cal.record_triager_decision("HIGH", False)
        bias = self.cal.get_triager_bias()
        self.assertIn("HIGH", bias)
        self.assertAlmostEqual(bias["HIGH"], 2 / 3, places=2)

    def test_calibrate_with_bias_penalty(self):
        """Low accept rate should penalize confidence."""
        # Record low accept rate
        for _ in range(8):
            self.cal.record_triager_decision("HIGH", False)
        for _ in range(2):
            self.cal.record_triager_decision("HIGH", True)

        result_biased = self.cal.calibrate_with_bias(0.9, 0.7)
        result_normal = self.cal.calibrate(0.9, 0.7)
        # Biased should have lower or equal confidence due to penalty
        self.assertLessEqual(
            result_biased.calibrated_confidence,
            result_normal.calibrated_confidence
        )

    def test_program_specific_heuristic(self):
        """Program-specific calibration should apply multiplier."""
        self.cal.register_program(
            "prog1",
            avg_severity="HIGH",
            payout_multiplier=1.2,
            historical_accept_rate=0.8,
        )
        result = self.cal.calibrate_for_program("prog1", 0.8, 0.6)
        self.assertIsNotNone(result)

    def test_picky_program_conservative(self):
        """Picky programs (low accept) get conservative scoring."""
        self.cal.register_program(
            "picky",
            avg_severity="MEDIUM",
            payout_multiplier=1.0,
            historical_accept_rate=0.2,
        )
        result = self.cal.calibrate_for_program("picky", 0.8, 0.6)
        normal = self.cal.calibrate(0.8, 0.6)
        # Picky program should have lower confidence
        self.assertLess(
            result.calibrated_confidence,
            normal.calibrated_confidence
        )


class TestReportStructuralCompiler(unittest.TestCase):
    """Phase 8: Report compiler + anti-hallucination gate."""

    def _make_evidence(self, verified=True, deterministic=True):
        return ExploitEvidence(
            exploit_id="EXP-001",
            target_url="https://example.com/api",
            vulnerability_class="SQL Injection",
            artifacts=[
                EvidenceArtifact(
                    artifact_id="ART-001",
                    artifact_type="request",
                    content_hash="abc123def456",
                    content_summary="POST /api/users with SQLi payload",
                    verified=verified,
                    verification_method="3x_replay",
                ),
                EvidenceArtifact(
                    artifact_id="ART-002",
                    artifact_type="response",
                    content_hash="789ghi012jkl",
                    content_summary="500 Internal Server Error with stack trace",
                    verified=verified,
                    verification_method="3x_replay",
                ),
            ],
            replay_deterministic=deterministic,
            cross_env_confirmed=True,
            privilege_escalation=True,
            data_exposure=True,
            confidence=0.95,
            cvss_vector="CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
            cvss_score=9.1,
        )

    def test_compile_valid_report(self):
        """Valid evidence should produce a passing report."""
        compiler = ReportStructuralCompiler()
        evidence = self._make_evidence()
        report = compiler.compile(evidence)

        self.assertTrue(report.hallucination_check_passed)
        self.assertEqual(report.severity, "CRITICAL")
        self.assertTrue(report.auto_submit_blocked)
        self.assertGreater(len(report.report_hash), 0)
        self.assertGreater(len(report.evidence_refs), 0)

    def test_auto_submit_always_blocked(self):
        """Auto-submission must always be blocked."""
        compiler = ReportStructuralCompiler()
        report = compiler.compile(self._make_evidence())
        self.assertTrue(report.auto_submit_blocked)

    def test_unverified_evidence_fails(self):
        """Unverified evidence should fail hallucination check."""
        compiler = ReportStructuralCompiler()
        evidence = self._make_evidence(verified=False)
        report = compiler.compile(evidence)
        self.assertFalse(report.hallucination_check_passed)

    def test_speculative_language_rejected(self):
        """Speculative language in summary should fail."""
        compiler = ReportStructuralCompiler()
        evidence = self._make_evidence()
        report = compiler.compile(
            evidence,
            summary="This might potentially cause issues",
        )
        self.assertFalse(report.hallucination_check_passed)

    def test_evidence_hash_integrity(self):
        """Report hash should be deterministic."""
        compiler = ReportStructuralCompiler()
        evidence = self._make_evidence()
        r1 = compiler.compile(evidence, title="Test", summary="A SQL Injection was confirmed.", impact="Data exposure confirmed.")
        r2 = compiler.compile(evidence, title="Test", summary="A SQL Injection was confirmed.", impact="Data exposure confirmed.")
        self.assertEqual(r1.report_hash, r2.report_hash)

    def test_json_serialization(self):
        """Report should serialize to valid JSON."""
        compiler = ReportStructuralCompiler()
        report = compiler.compile(self._make_evidence())
        json_str = compiler.to_json(report)
        self.assertIn("report_id", json_str)
        self.assertIn("evidence_hashes", json_str)

    def test_anti_hallucination_gate_standalone(self):
        """Test gate directly."""
        gate = AntiHallucinationGate()
        evidence = self._make_evidence()
        compiler = ReportStructuralCompiler()
        report = compiler.compile(evidence)
        passed, violations = gate.check(report, evidence)
        self.assertTrue(passed, f"Violations: {violations}")


class TestSequentialFieldMaster(unittest.TestCase):
    """Phase 9: Sequential mastery validation."""

    def test_sequential_progression(self):
        """Fields must be mastered in order."""
        master = SequentialFieldMaster(["XSS", "SQLi", "IDOR"])
        self.assertEqual(master.get_active_field(), "XSS")

        # Master XSS
        master.update_metrics("XSS", 0.96, 0.005, 0.002, 5, True)
        self.assertEqual(master.get_active_field(), "SQLi")
        self.assertTrue(master.is_mastered("XSS"))
        self.assertFalse(master.is_mastered("SQLi"))

    def test_mastery_thresholds(self):
        """Field should not master if thresholds not met."""
        master = SequentialFieldMaster(["XSS"])
        master.update_metrics("XSS", 0.90, 0.02, 0.01, 3, False)
        self.assertFalse(master.is_mastered("XSS"))

    def test_all_fields_mastered(self):
        """All 23 fields should be trackable."""
        fields = [f"FIELD_{i}" for i in range(23)]
        master = SequentialFieldMaster(fields)
        for f in fields:
            master.update_metrics(f, 0.96, 0.005, 0.002, 5, True)
        self.assertEqual(master.mastered_count, 23)
        report = master.get_mastery_report()
        self.assertTrue(report["all_mastered"])


class TestIntegration(unittest.TestCase):
    """End-to-end pipeline test."""

    def test_pipeline_evidence_to_report(self):
        """evidence → calibrator → report → field mastery."""
        # Calibrate
        cal = ImpactConfidenceCalibrator()
        result = cal.calibrate(0.92, 0.85, True, True)
        self.assertEqual(result.severity, "CRITICAL")

        # Generate CVSS
        vector, score = cal.generate_cvss_vector()
        self.assertGreater(score, 0)

        # Compile report
        evidence = ExploitEvidence(
            exploit_id="INT-001",
            target_url="https://target.com",
            vulnerability_class="SQLi",
            artifacts=[
                EvidenceArtifact(
                    "A1", "request", "hash1",
                    "SQL injection request", True, "3x_replay"
                ),
            ],
            replay_deterministic=True,
            cross_env_confirmed=True,
            privilege_escalation=True,
            data_exposure=True,
            confidence=result.calibrated_confidence,
            cvss_vector=vector,
            cvss_score=score,
        )
        compiler = ReportStructuralCompiler()
        report = compiler.compile(evidence)
        self.assertTrue(report.hallucination_check_passed)
        self.assertTrue(report.auto_submit_blocked)

        # Field mastery check
        master = SequentialFieldMaster(["SQLi", "XSS"])
        master.update_metrics("SQLi", 0.96, 0.005, 0.002, 5, True)
        self.assertTrue(master.is_mastered("SQLi"))

    def test_semantic_guard_blocks_bad_pipeline(self):
        """Guard should block synthetic-only training in pipeline."""
        guard = SemanticEntropyGuard(n_classes=2)
        features = np.random.randn(50, 16)
        labels = np.array([0] * 25 + [1] * 25)
        ok, _ = guard.check_batch(
            features, labels, synthetic_count=50, total_count=50
        )
        self.assertFalse(ok, "Synthetic-only batch should be blocked")


if __name__ == "__main__":
    unittest.main()
