"""
test_coverage_boost.py — Targeted coverage for auth, automation_enforcer,
                         field_progression_api, and clock_guard.

Covers uncovered lines to push Python coverage ≥95%.
"""

import hashlib
import os
import sys
import tempfile
import time
import unittest
import json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'backend'))


# =========================================================================
# AUTH MODULE TESTS
# =========================================================================

class TestPasswordHashing(unittest.TestCase):
    """Cover auth.hash_password and auth.verify_password."""

    def test_hash_and_verify(self):
        from auth.auth import hash_password, verify_password
        h = hash_password("test-password-123")
        self.assertTrue(verify_password("test-password-123", h))

    def test_wrong_password_fails(self):
        from auth.auth import hash_password, verify_password
        h = hash_password("correct")
        self.assertFalse(verify_password("wrong", h))

    def test_hash_contains_salt(self):
        from auth.auth import hash_password
        h = hash_password("pwd")
        self.assertIn(":", h)
        salt, hashed = h.split(":", 1)
        self.assertEqual(len(salt), 32)  # hex encoded 16 bytes

    def test_verify_invalid_format(self):
        from auth.auth import verify_password
        self.assertFalse(verify_password("x", "no-colon-here"))


class TestJWT(unittest.TestCase):
    """Cover auth.generate_jwt and auth.verify_jwt fallback path."""

    def test_generate_simple_token(self):
        from auth.auth import _generate_simple_token
        token = _generate_simple_token("user1")
        self.assertIn(":", token)
        parts = token.split(":")
        self.assertEqual(len(parts), 3)

    def test_verify_simple_token(self):
        from auth.auth import _generate_simple_token, _verify_simple_token
        token = _generate_simple_token("user42")
        result = _verify_simple_token(token)
        self.assertIsNotNone(result)
        self.assertEqual(result["sub"], "user42")

    def test_verify_invalid_token_format(self):
        from auth.auth import _verify_simple_token
        self.assertIsNone(_verify_simple_token("bad"))
        self.assertIsNone(_verify_simple_token("a:b"))  # only 2 parts

    def test_verify_expired_token(self):
        from auth.auth import _verify_simple_token
        import hmac as _hmac
        # Create manually expired token
        data = "user1:0"  # expired at epoch 0
        sig = _hmac.new(b"", data.encode(), hashlib.sha256).hexdigest()
        self.assertIsNone(_verify_simple_token(f"{data}:{sig}"))

    def test_verify_tampered_signature(self):
        from auth.auth import _generate_simple_token, _verify_simple_token
        token = _generate_simple_token("user1")
        parts = token.split(":")
        parts[2] = "0" * 64  # tamper signature
        self.assertIsNone(_verify_simple_token(":".join(parts)))

    def test_verify_non_numeric_expiry(self):
        from auth.auth import _verify_simple_token
        self.assertIsNone(_verify_simple_token("user1:not-a-number:abc"))


class TestRateLimiter(unittest.TestCase):
    """Cover auth.RateLimiter fully."""

    def test_not_limited_initially(self):
        from auth.auth import RateLimiter
        rl = RateLimiter(max_attempts=3, window_seconds=60)
        self.assertFalse(rl.is_rate_limited("ip1"))

    def test_limited_after_max_attempts(self):
        from auth.auth import RateLimiter
        rl = RateLimiter(max_attempts=3, window_seconds=60)
        for _ in range(3):
            rl.record_attempt("ip1")
        self.assertTrue(rl.is_rate_limited("ip1"))

    def test_remaining_count(self):
        from auth.auth import RateLimiter
        rl = RateLimiter(max_attempts=5, window_seconds=60)
        rl.record_attempt("ip2")
        rl.record_attempt("ip2")
        self.assertEqual(rl.get_remaining("ip2"), 3)

    def test_reset_clears_limit(self):
        from auth.auth import RateLimiter
        rl = RateLimiter(max_attempts=2, window_seconds=60)
        rl.record_attempt("ip3")
        rl.record_attempt("ip3")
        self.assertTrue(rl.is_rate_limited("ip3"))
        rl.reset("ip3")
        self.assertFalse(rl.is_rate_limited("ip3"))

    def test_get_rate_limiter_singleton(self):
        from auth.auth import get_rate_limiter
        rl1 = get_rate_limiter()
        rl2 = get_rate_limiter()
        self.assertIs(rl1, rl2)


class TestCSRFAndDevice(unittest.TestCase):
    """Cover CSRF and device hash."""

    def test_csrf_token_generation(self):
        from auth.auth import generate_csrf_token
        t = generate_csrf_token()
        self.assertEqual(len(t), 64)  # 32 bytes hex

    def test_csrf_verification(self):
        from auth.auth import generate_csrf_token, verify_csrf_token
        t = generate_csrf_token()
        self.assertTrue(verify_csrf_token(t, t))
        self.assertFalse(verify_csrf_token(t, "other"))

    def test_device_hash(self):
        from auth.auth import compute_device_hash
        h = compute_device_hash("Mozilla/5.0")
        self.assertEqual(len(h), 16)

    def test_device_hash_deterministic(self):
        from auth.auth import compute_device_hash
        h1 = compute_device_hash("Chrome/120")
        h2 = compute_device_hash("Chrome/120")
        self.assertEqual(h1, h2)


# =========================================================================
# AUTOMATION ENFORCER TESTS
# =========================================================================

class TestAutomationEnforcer(unittest.TestCase):
    """Cover all AutomationEnforcer methods."""

    def setUp(self):
        from governance.automation_enforcer import AutomationEnforcer
        self.enforcer = AutomationEnforcer()

    def test_block_submission(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.block_submission("hackerone", "R-001")
        self.assertEqual(result, ActionResult.BLOCKED)
        self.assertEqual(self.enforcer.blocked_count, 1)

    def test_block_authority_unlock(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.block_authority_unlock("admin")
        self.assertEqual(result, ActionResult.BLOCKED)

    def test_validate_target_approved(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.validate_target_selection("example.com", True)
        self.assertEqual(result, ActionResult.ALLOWED)

    def test_validate_target_not_approved(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.validate_target_selection("evil.com", False)
        self.assertEqual(result, ActionResult.BLOCKED)

    def test_validate_report_export_approved(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.validate_report_export("RPT-1", True)
        self.assertEqual(result, ActionResult.ALLOWED)

    def test_validate_report_export_denied(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.validate_report_export("RPT-2", False)
        self.assertEqual(result, ActionResult.BLOCKED)

    def test_validate_hunt_start_no_scope(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.validate_hunt_start("t1", False, True)
        self.assertEqual(result, ActionResult.BLOCKED)

    def test_validate_hunt_start_not_approved(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.validate_hunt_start("t2", True, False)
        self.assertEqual(result, ActionResult.BLOCKED)

    def test_validate_hunt_start_ok(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.validate_hunt_start("t3", True, True)
        self.assertEqual(result, ActionResult.ALLOWED)

    def test_log_hunt_step(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.log_hunt_step("scanning port 80")
        self.assertEqual(result, ActionResult.LOGGED_ONLY)

    def test_log_evidence(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.log_evidence("screenshot", "abc123def456")
        self.assertEqual(result, ActionResult.ALLOWED)

    def test_log_voice_command(self):
        from governance.automation_enforcer import ActionResult
        result = self.enforcer.log_voice_command("start scan")
        self.assertEqual(result, ActionResult.LOGGED_ONLY)

    def test_audit_log_tracking(self):
        self.enforcer.block_submission("plat", "r1")
        self.enforcer.validate_target_selection("d.com", True)
        self.assertEqual(self.enforcer.total_actions, 2)
        self.assertEqual(len(self.enforcer.audit_log), 2)
        self.assertEqual(self.enforcer.blocked_count, 1)
        self.assertEqual(self.enforcer.allowed_count, 1)

    def test_constants_immutable(self):
        from governance.automation_enforcer import AutomationEnforcer
        self.assertFalse(AutomationEnforcer.CAN_AUTO_SUBMIT)
        self.assertFalse(AutomationEnforcer.CAN_UNLOCK_AUTHORITY)
        self.assertFalse(AutomationEnforcer.CAN_MODIFY_SEVERITY)
        self.assertFalse(AutomationEnforcer.CAN_BYPASS_APPROVAL)
        self.assertFalse(AutomationEnforcer.CAN_SCRAPE_BEYOND_SCOPE)

    def test_audit_entry_has_hash(self):
        self.enforcer.block_submission("p", "r")
        log = self.enforcer.audit_log
        self.assertIn("hash", log[0])
        self.assertEqual(len(log[0]["hash"]), 16)


# =========================================================================
# FIELD PROGRESSION API TESTS
# =========================================================================

class TestFieldProgressionAPI(unittest.TestCase):
    """Cover field_progression_api endpoints."""

    @classmethod
    def setUpClass(cls):
        import importlib.util
        api_path = os.path.join(PROJECT_ROOT, 'backend', 'api',
                                'field_progression_api.py')
        spec = importlib.util.spec_from_file_location(
            "field_progression_api", api_path)
        cls.api = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.api)

    def test_default_state_structure(self):
        state = self.api._default_state()
        self.assertIn("fields", state)
        self.assertEqual(len(state["fields"]), self.api.TOTAL_FIELDS)

    def test_get_active_progress(self):
        result = self.api.get_active_progress()
        self.assertEqual(result["status"], "ok")
        self.assertIn("active_field", result)

    def test_get_active_progress_all_complete(self):
        """Simulated all-complete scenario."""
        import importlib.util
        api_path = os.path.join(PROJECT_ROOT, 'backend', 'api',
                                'field_progression_api.py')
        spec = importlib.util.spec_from_file_location(
            "field_progression_api_2", api_path)
        api2 = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(api2)
        # Monkey-patch to simulate all complete
        original = api2._load_field_state
        def mock_state():
            s = original()
            s["active_field_id"] = api2.TOTAL_FIELDS + 1
            s["certified_count"] = api2.TOTAL_FIELDS
            return s
        api2._load_field_state = mock_state
        result = api2.get_active_progress()
        self.assertEqual(result["status"], "all_complete")

    def test_approve_field_missing_approver(self):
        result = self.api.approve_field(0, "", "")
        self.assertEqual(result["status"], "error")
        self.assertIn("APPROVAL_REJECTED", result["message"])

    def test_approve_field_invalid_id(self):
        result = self.api.approve_field(-1, "admin", "test")
        self.assertEqual(result["status"], "error")
        self.assertIn("INVALID_FIELD_ID", result["message"])

    def test_approve_field_too_high_id(self):
        result = self.api.approve_field(999, "admin", "test")
        self.assertEqual(result["status"], "error")
        self.assertIn("INVALID_FIELD_ID", result["message"])

    def test_approve_field_valid(self):
        result = self.api.approve_field(0, "admin-user", "field 0 approved")
        self.assertEqual(result["status"], "ok")
        self.assertIn("APPROVED", result["message"])

    def test_start_training(self):
        result = self.api.start_training()
        self.assertEqual(result["status"], "ok")
        self.assertIn("TRAINING_STARTED", result["message"])

    def test_start_hunt_blocked_no_certification(self):
        result = self.api.start_hunt()
        # Should be blocked — field not certified
        self.assertIn(result["status"], ("blocked", "error"))

    def test_get_fields_state_has_runtime(self):
        result = self.api.get_fields_state()
        self.assertEqual(result["status"], "ok")
        self.assertIn("runtime", result)
        self.assertIn("ladder", result)
        self.assertIn("authority_lock", result)
        self.assertIn("approval_ledger", result)

    def test_calculate_progress_returns_dict(self):
        field = self.api._default_state()["fields"][0]
        progress = self.api._calculate_progress(field)
        self.assertIsInstance(progress, dict)

    def test_build_runtime_status_keys(self):
        state = self.api._default_state()
        runtime = self.api._build_runtime_status(state)
        required = [
            "containment_active", "precision_breach", "drift_alert",
            "determinism_pass", "merge_status",
        ]
        for key in required:
            self.assertIn(key, runtime)


# =========================================================================
# CLOCK GUARD — NTP UNREACHABLE PATH
# =========================================================================

class TestClockGuardNTPFailure(unittest.TestCase):
    """Cover clock_guard NTP failure path."""

    def test_unreachable_ntp_blocks(self):
        from governance.clock_guard import ClockGuard
        guard = ClockGuard(
            ntp_servers=["192.0.2.1"],  # RFC 5737 TEST-NET, unreachable
            timeout=0.3,
        )
        result = guard.check_skew()
        self.assertFalse(result.passed)
        self.assertIn("unreachable", result.reason.lower())

    def test_query_ntp_invalid_host(self):
        from governance.clock_guard import ClockGuard
        result = ClockGuard._query_ntp("this.does.not.exist.invalid", 0.3)
        self.assertIsNone(result)


# =========================================================================
# AUTO MODE CONTROLLER
# =========================================================================

class TestAutoModeController(unittest.TestCase):
    """Boost coverage for auto_mode_controller."""

    def test_import_and_state(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        state = ctrl.state
        self.assertFalse(state.enabled)
        self.assertTrue(state.shadow_only)

    def test_no_auto_submit_constant(self):
        from governance.auto_mode_controller import AutoModeController
        self.assertFalse(AutoModeController.CAN_AUTO_SUBMIT)

    def test_no_auto_export_constant(self):
        from governance.auto_mode_controller import AutoModeController
        self.assertFalse(AutoModeController.CAN_AUTO_EXPORT)

    def test_cannot_bypass_integrity(self):
        from governance.auto_mode_controller import AutoModeController
        self.assertFalse(AutoModeController.CAN_BYPASS_INTEGRITY)

    def test_cannot_disable_shadow(self):
        from governance.auto_mode_controller import AutoModeController
        self.assertFalse(AutoModeController.CAN_DISABLE_SHADOW)

    def test_is_shadow_only_always_true(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        self.assertTrue(ctrl.is_shadow_only)

    def test_evaluate_conditions_all_pass(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        cond = ctrl.evaluate_conditions(
            integrity_score=99.0,
            has_containment_24h=False,
            drift_stable=True,
            dataset_balanced=True,
            storage_healthy=True,
        )
        self.assertTrue(cond.all_conditions_met)
        self.assertEqual(len(cond.blocked_reasons), 0)

    def test_evaluate_conditions_some_fail(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        cond = ctrl.evaluate_conditions(
            integrity_score=50.0,
            has_containment_24h=True,
            drift_stable=False,
            dataset_balanced=False,
            storage_healthy=False,
        )
        self.assertFalse(cond.all_conditions_met)
        self.assertEqual(len(cond.blocked_reasons), 5)

    def test_request_activation_blocked_no_eval(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        state = ctrl.request_activation()
        self.assertFalse(state.enabled)

    def test_request_activation_blocked_conditions(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        ctrl.evaluate_conditions(50, True, False, False, False)
        state = ctrl.request_activation()
        self.assertFalse(state.enabled)

    def test_request_activation_success(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        ctrl.evaluate_conditions(99, False, True, True, True)
        state = ctrl.request_activation()
        self.assertTrue(state.enabled)
        self.assertTrue(state.shadow_only)
        self.assertTrue(ctrl.is_active)

    def test_deactivate(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        ctrl.evaluate_conditions(99, False, True, True, True)
        ctrl.request_activation()
        state = ctrl.deactivate()
        self.assertFalse(state.enabled)

    def test_export_approval_denied(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        self.assertFalse(ctrl.request_export_approval("rpt-1", False))

    def test_export_approval_granted(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        self.assertTrue(ctrl.request_export_approval("rpt-2", True))

    def test_activation_log(self):
        from governance.auto_mode_controller import AutoModeController
        ctrl = AutoModeController()
        ctrl.request_activation()  # will log blocked
        log = ctrl.activation_log
        self.assertGreater(len(log), 0)
        self.assertIn("message", log[0])


if __name__ == "__main__":
    unittest.main()
