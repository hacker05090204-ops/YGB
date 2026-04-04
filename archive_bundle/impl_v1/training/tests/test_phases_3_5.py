"""
Tests for Phases 3-5.

Phase 3: C++ safety precondition
Phase 4: Duplicate intelligence hardening
Phase 5: Report quality gate
"""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))


# =============================================================================
# Phase 3 — C++ Safety Precondition
# =============================================================================

class TestCppSafetyGate(unittest.TestCase):
    """Test C++ safety precondition for training."""

    def test_missing_exe_raises(self):
        from impl_v1.training.safety.cpp_safety_gate import check_cpp_safety, CppSafetyError
        with self.assertRaises(CppSafetyError):
            check_cpp_safety(exe_path="/nonexistent/path.exe")

    def test_missing_exe_skip_mode(self):
        from impl_v1.training.safety.cpp_safety_gate import check_cpp_safety
        result = check_cpp_safety(exe_path="/nonexistent/path.exe", skip_if_missing=True)
        self.assertTrue(result["passed"])
        self.assertIn("SKIPPED", result["output"])


# =============================================================================
# Phase 4 — Duplicate Intelligence
# =============================================================================

class TestCanonicalization(unittest.TestCase):
    def test_normalizes_whitespace(self):
        from impl_v1.phase41.duplicate_promotion_gate import canonicalize
        self.assertEqual(canonicalize("  hello   world  "), "hello world")

    def test_lowercases(self):
        from impl_v1.phase41.duplicate_promotion_gate import canonicalize
        self.assertEqual(canonicalize("Hello World"), "hello world")

    def test_strips_query_params(self):
        from impl_v1.phase41.duplicate_promotion_gate import canonicalize
        self.assertNotIn("?id=123", canonicalize("example.com/path?id=123"))


class TestStructuralFingerprint(unittest.TestCase):
    def test_same_input_same_fingerprint(self):
        from impl_v1.phase41.duplicate_promotion_gate import structural_fingerprint
        fp1 = structural_fingerprint("/api/users", "id=1", "IDOR")
        fp2 = structural_fingerprint("/api/users", "id=1", "IDOR")
        self.assertEqual(fp1, fp2)

    def test_different_input_different_fingerprint(self):
        from impl_v1.phase41.duplicate_promotion_gate import structural_fingerprint
        fp1 = structural_fingerprint("/api/users", "id=1", "IDOR")
        fp2 = structural_fingerprint("/api/admin", "id=1", "IDOR")
        self.assertNotEqual(fp1, fp2)


class TestSemanticSimilarity(unittest.TestCase):
    def test_identical_texts(self):
        from impl_v1.phase41.duplicate_promotion_gate import semantic_similarity
        self.assertGreater(semantic_similarity("test input", "test input"), 0.95)

    def test_different_texts(self):
        from impl_v1.phase41.duplicate_promotion_gate import semantic_similarity
        score = semantic_similarity("cat sat mat", "quantum physics theory")
        self.assertLess(score, 0.3)

    def test_similar_texts(self):
        from impl_v1.phase41.duplicate_promotion_gate import semantic_similarity
        score = semantic_similarity(
            "SQL injection in login form allows bypass",
            "SQL injection in user login allows authentication bypass",
        )
        self.assertGreater(score, 0.5)

    def test_empty_text_returns_zero(self):
        from impl_v1.phase41.duplicate_promotion_gate import semantic_similarity
        self.assertEqual(semantic_similarity("", "test"), 0.0)


class TestConfidenceCalibration(unittest.TestCase):
    def test_definite(self):
        from impl_v1.phase41.duplicate_promotion_gate import calibrate_confidence, DuplicateConfidenceLevel
        self.assertEqual(calibrate_confidence(0.99), DuplicateConfidenceLevel.DEFINITE)

    def test_high(self):
        from impl_v1.phase41.duplicate_promotion_gate import calibrate_confidence, DuplicateConfidenceLevel
        self.assertEqual(calibrate_confidence(0.96), DuplicateConfidenceLevel.HIGH)

    def test_abstain(self):
        from impl_v1.phase41.duplicate_promotion_gate import calibrate_confidence, DuplicateConfidenceLevel
        self.assertEqual(calibrate_confidence(0.3), DuplicateConfidenceLevel.ABSTAIN)


class TestDuplicatePromotionGate(unittest.TestCase):
    def test_gate_passes_good_scores(self):
        from impl_v1.phase41.duplicate_promotion_gate import check_duplicate_quality_gate
        result = check_duplicate_quality_gate(
            true_positives=97, false_positives=1,
            false_negatives=2, true_negatives=100,
        )
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.precision, 0.97)
        self.assertGreaterEqual(result.recall, 0.95)

    def test_gate_fails_low_precision(self):
        from impl_v1.phase41.duplicate_promotion_gate import check_duplicate_quality_gate
        result = check_duplicate_quality_gate(
            true_positives=90, false_positives=10,
            false_negatives=5, true_negatives=100,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("precision" in f for f in result.failures))

    def test_gate_fails_high_fpr(self):
        from impl_v1.phase41.duplicate_promotion_gate import check_duplicate_quality_gate
        result = check_duplicate_quality_gate(
            true_positives=97, false_positives=5,
            false_negatives=3, true_negatives=10,
        )
        self.assertFalse(result.passed)

    def test_decision_trace(self):
        from impl_v1.phase41.duplicate_promotion_gate import DuplicateDecisionTrace
        trace = DuplicateDecisionTrace(
            report_id="r1", candidate_id="c1",
            similarity_score=0.95, confidence="HIGH",
            is_duplicate=True, match_type="semantic",
        )
        d = trace.to_dict()
        self.assertEqual(d["report_id"], "r1")
        self.assertTrue(len(d["timestamp"]) > 0)


# =============================================================================
# Phase 5 — Report Quality Gate
# =============================================================================

class TestReportQualityGate(unittest.TestCase):
    def test_complete_report_passes(self):
        from impl_v1.phase49.runtime.report_quality_gate import (
            ReportContent, score_report,
        )
        content = ReportContent(
            scope_confirmation="Tested https://example.com/api as authorized",
            reproducible_steps="1. Navigate to /api 2. Submit payload 3. Observe response",
            impact_reasoning="Allows unauthorized data access to PII records",
            evidence_chain="Hash: abc123def4567890, Timestamp: 2026-02-24T20:00:00Z",
            environment_details="Windows 11, Chrome 120, API v2.1, endpoint /api/users",
            duplicate_check="No duplicates found, confidence: HIGH (0.95), checked 200 reports",
            remediation_guidance="Implement input validation on the endpoint parameter",
        )
        result = score_report(content)
        self.assertTrue(result.passed)
        self.assertGreaterEqual(result.score, 0.70)

    def test_empty_report_blocked(self):
        from impl_v1.phase49.runtime.report_quality_gate import (
            ReportContent, score_report,
        )
        content = ReportContent()
        result = score_report(content)
        self.assertFalse(result.passed)
        self.assertEqual(result.score, 0.0)
        self.assertEqual(len(result.missing_sections), 7)

    def test_partial_report_scored(self):
        from impl_v1.phase49.runtime.report_quality_gate import (
            ReportContent, score_report,
        )
        content = ReportContent(
            scope_confirmation="Tested https://example.com/api endpoint thoroughly",
            reproducible_steps="Step 1: call API, Step 2: observe error in response body",
            impact_reasoning="Medium severity — exposes internal paths and config",
        )
        result = score_report(content)
        # 3/7 = 0.43 < 0.70 threshold
        self.assertFalse(result.passed)
        self.assertEqual(len(result.missing_sections), 4)

    def test_gate_blocks_export(self):
        from impl_v1.phase49.runtime.report_quality_gate import (
            ReportContent, gate_report_export,
        )
        content = ReportContent()
        with self.assertRaises(RuntimeError):
            gate_report_export(content)

    def test_evidence_chain_validation(self):
        from impl_v1.phase49.runtime.report_quality_gate import validate_evidence_chain
        self.assertTrue(validate_evidence_chain(
            "Hash: abc123def4567890abcd, Timestamp: 2026-02-24"
        ))
        self.assertFalse(validate_evidence_chain("no evidence here"))


if __name__ == "__main__":
    unittest.main()
