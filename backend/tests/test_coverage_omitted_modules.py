"""
Tests for previously-omitted modules — bringing them into coverage tracking.

Covers:
  - backend.governance.certification_gate
  - backend.governance.lab_hunt_separator
  - backend.governance.merge_guard
  - backend.governance.mode_controller
  - backend.governance.representation_guard
  - backend.governance.mode_progression
  - backend.api.browser_endpoints
  - backend.approval.report_orchestrator
"""

import json
import os
import tempfile
import unittest
from unittest.mock import patch


# =========================================================================
# CertificationGate
# =========================================================================

class TestCertificationGate(unittest.TestCase):
    def setUp(self):
        from backend.governance.certification_gate import CertificationGate
        self.tmpdir = tempfile.mkdtemp()
        self.gate = CertificationGate(
            state_path=os.path.join(self.tmpdir, "cert_log.json")
        )

    def test_class_flags_always_false(self):
        from backend.governance.certification_gate import CertificationGate
        self.assertFalse(CertificationGate.ALLOW_AUTO_SUBMIT)
        self.assertFalse(CertificationGate.ALLOW_AUTO_NEGOTIATE)
        self.assertFalse(CertificationGate.ALLOW_AUTHORITY_UNLOCK)

    def test_submit_low_confidence_rejected(self):
        result = self.gate.submit_for_review(
            "F1", "xss", confidence=0.5, duplicate_risk=0.1, severity="HIGH"
        )
        self.assertFalse(result["accepted"])
        self.assertIn("LOW_CONFIDENCE", result["reason"])

    def test_submit_high_duplicate_risk_rejected(self):
        result = self.gate.submit_for_review(
            "F2", "sqli", confidence=0.95, duplicate_risk=0.9, severity="CRITICAL"
        )
        self.assertFalse(result["accepted"])
        self.assertIn("HIGH_DUPLICATE_RISK", result["reason"])

    def test_submit_valid_accepted(self):
        result = self.gate.submit_for_review(
            "F3", "rce", confidence=0.97, duplicate_risk=0.2, severity="CRITICAL"
        )
        self.assertTrue(result["accepted"])
        self.assertEqual(result["status"], "PENDING_HUMAN_REVIEW")

    def test_human_approve(self):
        self.gate.submit_for_review(
            "F4", "idor", confidence=0.95, duplicate_risk=0.1, severity="HIGH"
        )
        result = self.gate.human_approve("F4")
        self.assertTrue(result["approved"])

    def test_human_approve_not_found(self):
        result = self.gate.human_approve("nonexistent")
        self.assertFalse(result["approved"])
        self.assertIn("FINDING_NOT_FOUND", result["reason"])

    def test_human_reject(self):
        self.gate.submit_for_review(
            "F5", "xss", confidence=0.95, duplicate_risk=0.1, severity="MEDIUM"
        )
        result = self.gate.human_reject("F5")
        self.assertTrue(result["rejected"])

    def test_human_reject_not_found(self):
        result = self.gate.human_reject("nonexistent")
        self.assertFalse(result["rejected"])

    def test_pending_count(self):
        self.gate.submit_for_review(
            "FA", "xss", confidence=0.95, duplicate_risk=0.1, severity="MED"
        )
        self.gate.submit_for_review(
            "FB", "sqli", confidence=0.96, duplicate_risk=0.2, severity="HIGH"
        )
        self.assertEqual(self.gate.pending_count, 2)
        self.gate.human_approve("FA")
        self.assertEqual(self.gate.pending_count, 1)

    def test_stats(self):
        self.gate.submit_for_review(
            "S1", "xss", confidence=0.95, duplicate_risk=0.1, severity="MED"
        )
        self.gate.submit_for_review(
            "S2", "sqli", confidence=0.5, duplicate_risk=0.1, severity="LOW"
        )
        stats = self.gate.stats
        self.assertEqual(stats["total_submitted"], 1)
        self.assertEqual(stats["total_rejected"], 1)

    def test_persistence(self):
        self.gate.submit_for_review(
            "P1", "xss", confidence=0.95, duplicate_risk=0.1, severity="HIGH"
        )
        self.assertTrue(os.path.exists(
            os.path.join(self.tmpdir, "cert_log.json")
        ))


# =========================================================================
# LabHuntSeparator
# =========================================================================

class TestLabHuntSeparator(unittest.TestCase):
    def setUp(self):
        from backend.governance.lab_hunt_separator import LabHuntSeparator
        self.sep = LabHuntSeparator()

    def test_class_flags(self):
        from backend.governance.lab_hunt_separator import LabHuntSeparator
        self.assertFalse(LabHuntSeparator.ALLOW_CROSS_MODE_ACCESS)

    def test_lab_action_allowed_in_lab(self):
        result = self.sep.check_lab_action("LAB", "train")
        self.assertTrue(result["allowed"])

    def test_lab_action_blocked_in_hunt(self):
        result = self.sep.check_lab_action("HUNT", "train")
        self.assertFalse(result["allowed"])
        self.assertIn("BLOCKED", result["reason"])

    def test_lab_action_unknown(self):
        result = self.sep.check_lab_action("LAB", "unknown_action")
        self.assertFalse(result["allowed"])
        self.assertIn("UNKNOWN_LAB_ACTION", result["reason"])

    def test_hunt_action_allowed_in_hunt(self):
        result = self.sep.check_hunt_action("HUNT", "scan_target")
        self.assertTrue(result["allowed"])

    def test_hunt_action_blocked_in_lab(self):
        result = self.sep.check_hunt_action("LAB", "scan_target")
        self.assertFalse(result["allowed"])

    def test_hunt_action_unknown(self):
        result = self.sep.check_hunt_action("HUNT", "unknown_action")
        self.assertFalse(result["allowed"])

    def test_forbidden_action_blocked(self):
        result = self.sep.check_forbidden("auto_submit")
        self.assertFalse(result["allowed"])
        self.assertIn("FORBIDDEN_ACTION", result["reason"])

    def test_non_forbidden_action_allowed(self):
        result = self.sep.check_forbidden("safe_action")
        self.assertTrue(result["allowed"])

    def test_violations_counter(self):
        self.sep.check_lab_action("HUNT", "train")
        self.sep.check_forbidden("auto_submit")
        self.assertEqual(self.sep.violations, 2)

    def test_all_lab_actions(self):
        lab_actions = [
            "train", "update_weights", "merge_weights", "run_regression",
            "calibrate", "tune_threshold", "run_stress_test", "export_snapshot",
        ]
        for action in lab_actions:
            result = self.sep.check_lab_action("LAB", action)
            self.assertTrue(result["allowed"], f"Lab action {action} should be allowed")

    def test_all_hunt_actions(self):
        hunt_actions = [
            "scan_target", "analyze_endpoint", "evaluate_finding",
            "generate_report", "queue_review",
        ]
        for action in hunt_actions:
            result = self.sep.check_hunt_action("HUNT", action)
            self.assertTrue(result["allowed"], f"Hunt action {action} should be allowed")

    def test_all_forbidden_actions(self):
        forbidden = [
            "auto_submit", "unlock_authority", "bypass_governance",
            "disable_review", "target_specific_company",
            "negotiate_bounty", "exploit_target",
        ]
        for action in forbidden:
            result = self.sep.check_forbidden(action)
            self.assertFalse(result["allowed"], f"Forbidden action {action} should be blocked")


# =========================================================================
# MergeGuard
# =========================================================================

class TestMergeGuard(unittest.TestCase):
    def setUp(self):
        from backend.governance.merge_guard import MergeGuard
        self.guard = MergeGuard()

    def test_class_flags(self):
        from backend.governance.merge_guard import MergeGuard
        self.assertFalse(MergeGuard.ALLOW_HUNT_MODE_MERGE)
        self.assertFalse(MergeGuard.ALLOW_DIRECT_OVERWRITE)

    def test_merge_blocked_in_hunt(self):
        result = self.guard.can_merge("HUNT", True, 0.96, 0.96, 0.01, 0.01)
        self.assertFalse(result["allowed"])
        self.assertIn("HUNT mode", result["reason"])

    def test_merge_blocked_uncertified(self):
        result = self.guard.can_merge("LAB", False, 0.96, 0.96, 0.01, 0.01)
        self.assertFalse(result["allowed"])
        self.assertIn("not certified", result["reason"])

    def test_merge_blocked_precision_drop(self):
        result = self.guard.can_merge("LAB", True, 0.96, 0.94, 0.01, 0.01)
        self.assertFalse(result["allowed"])
        self.assertIn("Precision degraded", result["reason"])

    def test_merge_blocked_ece_increase(self):
        result = self.guard.can_merge("LAB", True, 0.96, 0.96, 0.01, 0.02)
        self.assertFalse(result["allowed"])
        self.assertIn("ECE increased", result["reason"])

    def test_merge_allowed(self):
        result = self.guard.can_merge("LAB", True, 0.96, 0.96, 0.01, 0.01)
        self.assertTrue(result["allowed"])
        self.assertIn("MERGE_ALLOWED", result["reason"])

    def test_counters(self):
        self.guard.can_merge("LAB", True, 0.96, 0.96, 0.01, 0.01)
        self.guard.can_merge("HUNT", True, 0.96, 0.96, 0.01, 0.01)
        self.assertEqual(self.guard.merge_count, 1)
        self.assertEqual(self.guard.block_count, 1)


# =========================================================================
# ModeController
# =========================================================================

class TestModeController(unittest.TestCase):
    def setUp(self):
        from backend.governance.mode_controller import ModeController
        self.tmpdir = tempfile.mkdtemp()
        self.ctrl = ModeController(
            state_path=os.path.join(self.tmpdir, "mode.json")
        )

    def test_class_flags(self):
        from backend.governance.mode_controller import ModeController
        self.assertFalse(ModeController.ALLOW_AUTO_SUBMIT)
        self.assertFalse(ModeController.ALLOW_AUTHORITY_UNLOCK)

    def test_initial_mode_idle(self):
        from backend.governance.mode_controller import RuntimeMode
        self.assertEqual(self.ctrl.mode, RuntimeMode.IDLE)

    def test_enter_lab(self):
        result = self.ctrl.enter_lab()
        self.assertTrue(result["allowed"])
        from backend.governance.mode_controller import RuntimeMode
        self.assertEqual(self.ctrl.mode, RuntimeMode.LAB)

    def test_enter_lab_already_in_lab(self):
        self.ctrl.enter_lab()
        result = self.ctrl.enter_lab()
        self.assertFalse(result["allowed"])
        self.assertIn("ALREADY_IN_LAB", result["reason"])

    def test_enter_hunt(self):
        result = self.ctrl.enter_hunt()
        self.assertTrue(result["allowed"])

    def test_enter_hunt_already_in_hunt(self):
        self.ctrl.enter_hunt()
        result = self.ctrl.enter_hunt()
        self.assertFalse(result["allowed"])

    def test_lab_blocks_hunt(self):
        self.ctrl.enter_lab()
        result = self.ctrl.enter_hunt()
        self.assertFalse(result["allowed"])

    def test_hunt_blocks_lab(self):
        self.ctrl.enter_hunt()
        result = self.ctrl.enter_lab()
        self.assertFalse(result["allowed"])

    def test_return_to_idle(self):
        self.ctrl.enter_lab()
        result = self.ctrl.return_to_idle()
        self.assertTrue(result["allowed"])
        from backend.governance.mode_controller import RuntimeMode
        self.assertEqual(self.ctrl.mode, RuntimeMode.IDLE)

    def test_training_allowed_in_lab(self):
        self.ctrl.enter_lab()
        self.assertTrue(self.ctrl.is_training_allowed())

    def test_training_blocked_in_hunt(self):
        self.ctrl.enter_hunt()
        self.assertFalse(self.ctrl.is_training_allowed())

    def test_hunting_allowed_in_hunt(self):
        self.ctrl.enter_hunt()
        self.assertTrue(self.ctrl.is_hunting_allowed())

    def test_hunting_blocked_in_lab(self):
        self.ctrl.enter_lab()
        self.assertFalse(self.ctrl.is_hunting_allowed())

    def test_persistence(self):
        self.ctrl.enter_lab()
        path = os.path.join(self.tmpdir, "mode.json")
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            data = json.load(f)
        self.assertEqual(data["mode"], "LAB")

    def test_load_state(self):
        from backend.governance.mode_controller import ModeController, RuntimeMode
        self.ctrl.enter_lab()
        ctrl2 = ModeController(
            state_path=os.path.join(self.tmpdir, "mode.json")
        )
        self.assertEqual(ctrl2.mode, RuntimeMode.LAB)


# =========================================================================
# RepresentationGuard
# =========================================================================

class TestRepresentationGuard(unittest.TestCase):
    def setUp(self):
        from backend.governance.representation_guard import RepresentationGuard
        self.guard = RepresentationGuard(mode="MODE-A")

    def test_only_mode_a_allowed(self):
        from backend.governance.representation_guard import RepresentationGuard
        with self.assertRaises(ValueError):
            RepresentationGuard(mode="MODE-B")

    def test_clean_data_passes(self):
        data = {"url": "https://example.com", "description": "Login page"}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNotNone(sanitized)
        self.assertTrue(result.allowed)

    def test_mode_b_token_blocked(self):
        data = {"mode": "mode-b", "data": "test"}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNone(sanitized)
        self.assertFalse(result.allowed)
        self.assertIn("MODE-B", result.violations[0])

    def test_decision_token_blocked(self):
        data = {"is_valid": True, "url": "https://example.com"}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNone(sanitized)
        self.assertFalse(result.allowed)

    def test_exploit_pattern_blocked(self):
        data = {"content": "<script>alert(1)</script>"}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNone(sanitized)
        self.assertFalse(result.allowed)

    def test_sql_injection_blocked(self):
        data = {"input": "UNION SELECT * FROM users"}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNone(sanitized)

    def test_forbidden_fields_stripped(self):
        data = {"url": "https://example.com", "severity": "HIGH", "impact": "bad"}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNotNone(sanitized)
        self.assertNotIn("severity", sanitized)
        self.assertNotIn("impact", sanitized)
        self.assertIn("severity", result.stripped_fields)

    def test_empty_after_strip_blocked(self):
        data = {"severity": "HIGH", "impact": "bad"}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNone(sanitized)
        self.assertFalse(result.allowed)

    def test_stats(self):
        self.guard.check_and_sanitize({"url": "https://test.com"})
        self.guard.check_and_sanitize({"is_valid": True})
        stats = self.guard.get_stats()
        self.assertEqual(stats["total_checked"], 2)
        self.assertEqual(stats["total_blocked"], 1)

    def test_guard_result_to_dict(self):
        from backend.governance.representation_guard import GuardResult
        r = GuardResult(allowed=True, mode="MODE-A")
        d = r.to_dict()
        self.assertTrue(d["allowed"])
        self.assertEqual(d["mode"], "MODE-A")

    def test_singleton(self):
        from backend.governance.representation_guard import get_representation_guard
        g1 = get_representation_guard()
        g2 = get_representation_guard()
        self.assertIs(g1, g2)

    def test_nested_forbidden_fields(self):
        data = {"outer": {"severity": "HIGH", "url": "https://test.com"}}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNotNone(sanitized)
        self.assertNotIn("severity", sanitized.get("outer", {}))

    def test_path_traversal_blocked(self):
        data = {"path": "../../etc/passwd"}
        sanitized, result = self.guard.check_and_sanitize(data)
        self.assertIsNone(sanitized)


# =========================================================================
# ModeProgressionController
# =========================================================================

class TestModeProgression(unittest.TestCase):
    def setUp(self):
        from backend.governance.mode_progression import (
            ModeProgressionController, OperatingMode, GateMetrics,
        )
        self.ctrl = ModeProgressionController()
        self.OperatingMode = OperatingMode
        self.GateMetrics = GateMetrics

    def test_class_flags(self):
        self.assertFalse(self.ctrl.CAN_UNLOCK_AUTHORITY)
        self.assertFalse(self.ctrl.CAN_SKIP_GATES)
        self.assertFalse(self.ctrl.CAN_ENTER_PRODUCTION)

    def test_initial_mode_a(self):
        self.assertEqual(self.ctrl.current_mode, self.OperatingMode.MODE_A)
        self.assertEqual(self.ctrl.mode_name, "MODE_A")

    def test_regression_always_allowed(self):
        # Even without metrics, regression should pass
        decision = self.ctrl.evaluate_gate(
            self.GateMetrics(), self.OperatingMode.MODE_A
        )
        self.assertTrue(decision.approved)

    def test_same_mode_noop(self):
        decision = self.ctrl.evaluate_gate(
            self.GateMetrics(), self.OperatingMode.MODE_A
        )
        self.assertTrue(decision.approved)
        self.assertIn("Already in target mode", decision.reasons)

    def test_a_to_b_all_pass(self):
        metrics = self.GateMetrics(
            accuracy=0.96, ece=0.015, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=96, precision_above_threshold=0.96,
            scope_engine_accuracy=0.96,
        )
        decision = self.ctrl.request_transition(metrics, self.OperatingMode.MODE_B)
        self.assertTrue(decision.approved)
        self.assertEqual(self.ctrl.current_mode, self.OperatingMode.MODE_B)

    def test_a_to_b_insufficient_accuracy(self):
        metrics = self.GateMetrics(accuracy=0.90)
        decision = self.ctrl.evaluate_gate(metrics, self.OperatingMode.MODE_B)
        self.assertFalse(decision.approved)

    def test_skip_b_to_c_blocked(self):
        metrics = self.GateMetrics(
            accuracy=0.99, ece=0.01, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=99, precision_above_threshold=0.99,
            scope_engine_accuracy=0.99,
        )
        decision = self.ctrl.evaluate_gate(metrics, self.OperatingMode.MODE_C)
        self.assertFalse(decision.approved)
        self.assertIn("Cannot skip MODE-B", decision.reasons[0])

    def test_b_to_c_transition(self):
        # First go to B
        metrics_b = self.GateMetrics(
            accuracy=0.96, ece=0.015, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=96, precision_above_threshold=0.96,
            scope_engine_accuracy=0.96,
        )
        self.ctrl.request_transition(metrics_b, self.OperatingMode.MODE_B)
        # Then go to C
        metrics_c = self.GateMetrics(
            accuracy=0.98, ece=0.01, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=99, precision_above_threshold=0.98,
            scope_engine_accuracy=0.99,
        )
        decision = self.ctrl.request_transition(metrics_c, self.OperatingMode.MODE_C)
        self.assertTrue(decision.approved)

    def test_regress_to_a(self):
        metrics = self.GateMetrics(
            accuracy=0.96, ece=0.015, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=96, precision_above_threshold=0.96,
            scope_engine_accuracy=0.96,
        )
        self.ctrl.request_transition(metrics, self.OperatingMode.MODE_B)
        decision = self.ctrl.regress_to(self.OperatingMode.MODE_A)
        self.assertTrue(decision.approved)
        self.assertEqual(self.ctrl.current_mode, self.OperatingMode.MODE_A)

    def test_capabilities(self):
        self.assertTrue(self.ctrl.can_expand_representation())
        self.assertFalse(self.ctrl.can_shadow_validate())
        self.assertFalse(self.ctrl.can_lab_autonomy())
        self.assertFalse(self.ctrl.can_production_autonomy())
        self.assertFalse(self.ctrl.can_unlock_authority())

    def test_transition_log(self):
        metrics = self.GateMetrics(accuracy=0.5)
        self.ctrl.request_transition(metrics, self.OperatingMode.MODE_B)
        log = self.ctrl.transition_log
        self.assertEqual(len(log), 1)
        self.assertFalse(log[0]["approved"])

    def test_gate_decision_to_dict(self):
        decision = self.ctrl.evaluate_gate(
            self.GateMetrics(), self.OperatingMode.MODE_A
        )
        d = decision.to_dict()
        self.assertIn("current_mode", d)
        self.assertIn("target_mode", d)

    def test_save_load_state(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "mode_state.json")
        metrics = self.GateMetrics(
            accuracy=0.96, ece=0.015, drift_stable=True,
            no_containment_24h=True, determinism_proven=True,
            long_run_stable=True, calibration_passed=True,
            integrity_score=96, precision_above_threshold=0.96,
            scope_engine_accuracy=0.96,
        )
        self.ctrl.request_transition(metrics, self.OperatingMode.MODE_B)
        self.ctrl.save_state(path)
        from backend.governance.mode_progression import ModeProgressionController
        ctrl2 = ModeProgressionController()
        ctrl2.load_state(path)
        self.assertEqual(ctrl2.current_mode, self.OperatingMode.MODE_B)

    def test_load_state_invalid_json(self):
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "bad_mode.json")
        with open(path, "w") as f:
            f.write("NOT JSON")
        from backend.governance.mode_progression import ModeProgressionController
        ctrl = ModeProgressionController()
        ctrl.load_state(path)
        self.assertEqual(ctrl.current_mode, self.OperatingMode.MODE_A)


# =========================================================================
# BrowserEndpoints
# =========================================================================

class TestBrowserEndpoints(unittest.TestCase):
    def test_daily_summary_no_data(self):
        from backend.api.browser_endpoints import get_daily_summary
        with patch("backend.api.browser_endpoints.SUMMARY_PATH", "/nonexistent/path.json"):
            result = get_daily_summary()
            self.assertEqual(result["status"], "no_data")

    def test_daily_summary_with_data(self):
        from backend.api.browser_endpoints import get_daily_summary
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "summary.json")
        data = {
            "date": "2026-03-13",
            "cves_processed": [{"cve_id": "CVE-2026-0001"}],
            "domains_visited": ["example.com"],
            "total_dedup_skipped": 5,
            "total_blocked": 2,
            "total_expanded": 10,
            "total_fetched": 15,
            "errors": [],
            "timestamp": "2026-03-13T00:00:00Z",
        }
        with open(path, "w") as f:
            json.dump(data, f)
        with patch("backend.api.browser_endpoints.SUMMARY_PATH", path):
            result = get_daily_summary()
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["new_cves_count"], 1)

    def test_new_cves_no_data(self):
        from backend.api.browser_endpoints import get_new_cves
        with patch("backend.api.browser_endpoints.SUMMARY_PATH", "/nonexistent"):
            result = get_new_cves()
            self.assertEqual(result["status"], "no_data")
            self.assertEqual(result["count"], 0)

    def test_new_cves_with_data(self):
        from backend.api.browser_endpoints import get_new_cves
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "summary.json")
        data = {
            "date": "2026-03-13",
            "cves_processed": [
                {"cve_id": "CVE-2026-0001", "title": "Test", "summary": "A" * 300,
                 "cvss_score": 9.8, "cwe_id": "CWE-79", "source_url": "https://nvd.nist.gov"},
            ],
            "timestamp": "2026-03-13T00:00:00Z",
        }
        with open(path, "w") as f:
            json.dump(data, f)
        with patch("backend.api.browser_endpoints.SUMMARY_PATH", path):
            result = get_new_cves()
            self.assertEqual(result["count"], 1)
            self.assertLessEqual(len(result["cves"][0]["summary"]), 200)

    def test_representation_impact_no_data(self):
        from backend.api.browser_endpoints import get_representation_impact
        with patch("backend.api.browser_endpoints.SUMMARY_PATH", "/nonexistent"):
            result = get_representation_impact()
            self.assertEqual(result["status"], "no_data")

    def test_representation_impact_with_data(self):
        from backend.api.browser_endpoints import get_representation_impact
        tmpdir = tempfile.mkdtemp()
        summary_path = os.path.join(tmpdir, "summary.json")
        hash_path = os.path.join(tmpdir, "hash_index.json")
        with open(summary_path, "w") as f:
            json.dump({
                "representation_diversity_delta": 0.15,
                "total_expanded": 42,
                "date": "2026-03-13",
                "timestamp": "2026-03-13T00:00:00Z",
            }, f)
        with open(hash_path, "w") as f:
            json.dump({"url_hashes": {"a": 1, "b": 2}}, f)
        with patch("backend.api.browser_endpoints.SUMMARY_PATH", summary_path), \
             patch("backend.api.browser_endpoints.HASH_INDEX_PATH", hash_path):
            result = get_representation_impact()
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["total_indexed"], 2)

    def test_load_summary_invalid_json(self):
        from backend.api.browser_endpoints import _load_summary
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "bad.json")
        with open(path, "w") as f:
            f.write("NOT JSON")
        with patch("backend.api.browser_endpoints.SUMMARY_PATH", path):
            self.assertIsNone(_load_summary())

    def test_load_hash_index_invalid(self):
        from backend.api.browser_endpoints import _load_hash_index
        tmpdir = tempfile.mkdtemp()
        path = os.path.join(tmpdir, "bad_hash.json")
        with open(path, "w") as f:
            f.write("{bad}")
        with patch("backend.api.browser_endpoints.HASH_INDEX_PATH", path):
            self.assertIsNone(_load_hash_index())


# =========================================================================
# ReportOrchestrator
# =========================================================================

class TestReportOrchestrator(unittest.TestCase):
    def setUp(self):
        from backend.approval.report_orchestrator import (
            ReportOrchestrator, Evidence, ConfidenceBand, ApprovalStatus,
        )
        self.tmpdir = tempfile.mkdtemp()
        self.orch = ReportOrchestrator(reports_dir=self.tmpdir)
        self.Evidence = Evidence
        self.ConfidenceBand = ConfidenceBand
        self.ApprovalStatus = ApprovalStatus

    def test_auto_submit_always_false(self):
        self.assertFalse(self.orch.auto_submit_enabled)

    def test_create_report(self):
        ev = self.Evidence(screenshots=["s1.png"])
        cb = self.ConfidenceBand(confidence_pct=92.0, scope_compliant=True)
        report = self.orch.create_report(
            "SQLi in Login", "SQLi", "Critical", "api.test.com",
            "SQL injection", "Auth bypass",
            ["Step 1", "Step 2", "Step 3"],
            ev, cb,
        )
        self.assertTrue(report.report_id.startswith("RPT-"))
        self.assertEqual(len(report.hash), 64)

    def test_assess_quality_excellent(self):
        from backend.approval.report_orchestrator import ReportQuality
        ev = self.Evidence(
            screenshots=["s1.png", "s2.png"], videos=["v.mp4"],
            poc_steps=["p1", "p2", "p3"],
        )
        cb = self.ConfidenceBand(
            confidence_pct=95.0, scope_compliant=True, duplicate_risk_pct=10.0,
        )
        report = self.orch.create_report(
            "RCE", "RCE", "Critical", "target.com", "desc", "impact",
            ["s1", "s2", "s3"], ev, cb,
        )
        quality = self.orch.assess_quality(report)
        self.assertIn(quality, [ReportQuality.EXCELLENT, ReportQuality.GOOD])

    def test_assess_quality_insufficient_dup(self):
        from backend.approval.report_orchestrator import ReportQuality
        ev = self.Evidence()
        cb = self.ConfidenceBand(confidence_pct=95.0, duplicate_risk_pct=85.0)
        report = self.orch.create_report(
            "Dup", "XSS", "Med", "t.com", "t", "t", ["s"], ev, cb,
        )
        quality = self.orch.assess_quality(report)
        self.assertEqual(quality, ReportQuality.INSUFFICIENT)

    def test_save_for_review(self):
        ev = self.Evidence(screenshots=["s1.png"])
        cb = self.ConfidenceBand(confidence_pct=92.0, scope_compliant=True)
        report = self.orch.create_report(
            "XSS", "XSS", "Medium", "site.com", "dom xss", "impact",
            ["s1", "s2", "s3"], ev, cb,
        )
        filepath = self.orch.save_for_review(report)
        self.assertTrue(os.path.exists(filepath))
        with open(filepath) as f:
            saved = json.load(f)
        self.assertFalse(saved["auto_submit"])
        self.assertTrue(saved["human_review_required"])

    def test_record_decision(self):
        decision = self.orch.record_decision(
            "RPT-123", self.ApprovalStatus.APPROVED, "reviewer", "looks good",
        )
        self.assertEqual(decision.status, self.ApprovalStatus.APPROVED)
        self.assertEqual(len(self.orch.approval_log), 1)

    def test_warnings_generated(self):
        ev = self.Evidence()
        cb = self.ConfidenceBand(
            confidence_pct=30.0, duplicate_risk_pct=70.0, scope_compliant=False,
        )
        report = self.orch.create_report(
            "T", "T", "Low", "t.com", "t", "t", ["s"], ev, cb,
        )
        warnings = self.orch._generate_warnings(report)
        self.assertTrue(any("LOW CONFIDENCE" in w for w in warnings))
        self.assertTrue(any("DUPLICATE RISK" in w for w in warnings))
        self.assertTrue(any("SCOPE" in w for w in warnings))
        self.assertTrue(any("POC" in w for w in warnings))
        self.assertTrue(any("EVIDENCE" in w for w in warnings))


if __name__ == "__main__":
    unittest.main()
