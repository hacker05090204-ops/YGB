"""
Coverage Boost Tests — Security & Config Modules

Targets:
- backend/config/config_validator.py (100% coverage)
- backend/governance/incident_reconciler.py (100% coverage)
- backend/auth/auth_guard.py (additional edge cases)
- backend/startup/preflight.py (additional edge cases)
"""

import unittest
import os
import sys
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# =========================================================================
# CONFIG VALIDATOR TESTS
# =========================================================================

class TestConfigValidator(unittest.TestCase):
    """Test centralized config validation."""

    def test_import(self):
        from backend.config.config_validator import validate_config
        self.assertTrue(callable(validate_config))

    def test_placeholder_detection(self):
        from backend.config.config_validator import _is_placeholder
        self.assertTrue(_is_placeholder("CHANGE_ME_GENERATE_WITH_secrets"))
        self.assertTrue(_is_placeholder("change-me-please"))
        self.assertTrue(_is_placeholder("your-secret-here"))
        self.assertTrue(_is_placeholder("replace_me"))
        self.assertFalse(_is_placeholder("a" * 64))
        self.assertFalse(_is_placeholder("5a2d87d1c9f04e3ab6d92f0a3c1b47de"))

    def test_validate_required_secrets_missing(self):
        from backend.config.config_validator import validate_required_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "",
            "YGB_HMAC_SECRET": "",
            "YGB_VIDEO_JWT_SECRET": "",
        }, clear=False):
            violations = validate_required_secrets()
            self.assertTrue(len(violations) >= 3)
            keys = [v[0] for v in violations]
            self.assertIn("JWT_SECRET", keys)

    def test_validate_required_secrets_too_short(self):
        from backend.config.config_validator import validate_required_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "short",
            "YGB_HMAC_SECRET": "also-short",
            "YGB_VIDEO_JWT_SECRET": "nope",
        }, clear=False):
            violations = validate_required_secrets()
            self.assertTrue(len(violations) >= 3)
            self.assertTrue(any("Too short" in v[1] for v in violations))

    def test_validate_required_secrets_placeholder(self):
        from backend.config.config_validator import validate_required_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "CHANGE_ME_GENERATE_WITH_secrets_token_hex_32",
            "YGB_HMAC_SECRET": "a" * 64,
            "YGB_VIDEO_JWT_SECRET": "b" * 64,
        }, clear=False):
            violations = validate_required_secrets()
            self.assertTrue(len(violations) >= 1)
            self.assertTrue(any("placeholder" in v[1].lower() for v in violations))

    def test_validate_required_secrets_valid(self):
        from backend.config.config_validator import validate_required_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "a" * 64,
            "YGB_HMAC_SECRET": "b" * 64,
            "YGB_VIDEO_JWT_SECRET": "c" * 64,
            "YGB_PROFILE": "PRIVACY",
        }, clear=False):
            violations = validate_required_secrets()
            self.assertEqual(len(violations), 0)

    def test_validate_bind_host_unsafe(self):
        from backend.config.config_validator import validate_bind_host
        with patch.dict(os.environ, {"API_HOST": "0.0.0.0"}, clear=False):
            warnings = validate_bind_host()
            self.assertTrue(len(warnings) >= 1)
            self.assertIn("0.0.0.0", warnings[0][1])

    def test_validate_bind_host_safe(self):
        from backend.config.config_validator import validate_bind_host
        with patch.dict(os.environ, {"API_HOST": "127.0.0.1"}, clear=False):
            warnings = validate_bind_host()
            self.assertEqual(len(warnings), 0)

    def test_validate_config_strict_raises(self):
        from backend.config.config_validator import validate_config, ConfigurationError
        with patch.dict(os.environ, {
            "JWT_SECRET": "",
            "YGB_HMAC_SECRET": "",
            "YGB_VIDEO_JWT_SECRET": "",
        }, clear=False):
            with self.assertRaises(ConfigurationError) as ctx:
                validate_config(strict=True)
            self.assertTrue(len(ctx.exception.violations) >= 3)

    def test_validate_config_non_strict_no_raise(self):
        from backend.config.config_validator import validate_config
        with patch.dict(os.environ, {
            "JWT_SECRET": "",
            "YGB_HMAC_SECRET": "",
            "YGB_VIDEO_JWT_SECRET": "",
        }, clear=False):
            # Should log but not raise
            validate_config(strict=False)

    def test_connected_profile_checks_extra_secrets(self):
        from backend.config.config_validator import validate_required_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "a" * 64,
            "YGB_HMAC_SECRET": "b" * 64,
            "YGB_VIDEO_JWT_SECRET": "c" * 64,
            "YGB_PROFILE": "CONNECTED",
            "GITHUB_CLIENT_SECRET": "",
            "SMTP_PASS": "",
        }, clear=False):
            violations = validate_required_secrets()
            keys = [v[0] for v in violations]
            self.assertIn("GITHUB_CLIENT_SECRET", keys)
            self.assertIn("SMTP_PASS", keys)

    def test_configuration_error_message(self):
        from backend.config.config_validator import ConfigurationError
        err = ConfigurationError([("KEY1", "missing"), ("KEY2", "too short")])
        self.assertIn("KEY1", str(err))
        self.assertIn("KEY2", str(err))
        self.assertEqual(len(err.violations), 2)


# =========================================================================
# INCIDENT RECONCILER TESTS
# =========================================================================

class TestIncidentReconciler(unittest.TestCase):
    """Test drift/incident consistency checks."""

    def test_import(self):
        from backend.governance.incident_reconciler import reconcile
        self.assertTrue(callable(reconcile))

    def test_no_auto_mode_state(self):
        from backend.governance.incident_reconciler import reconcile
        report = reconcile(
            reports_dir=Path(tempfile.mkdtemp()),
            auto_mode_path=Path("/nonexistent/auto_mode_state.json"),
        )
        self.assertFalse(report.consistent)
        self.assertTrue(any("not found" in c["detail"] for c in report.checks))

    def test_no_incidents_no_drift(self):
        from backend.governance.incident_reconciler import reconcile
        tmpdir = Path(tempfile.mkdtemp())
        state_path = tmpdir / "auto_mode_state.json"
        state_path.write_text(json.dumps({
            "no_drift_events": True,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }))
        report = reconcile(reports_dir=tmpdir, auto_mode_path=state_path)
        self.assertTrue(report.consistent)

    def test_incidents_with_no_drift_true_inconsistent(self):
        from backend.governance.incident_reconciler import reconcile
        tmpdir = Path(tempfile.mkdtemp())
        # Create incident file
        (tmpdir / "incident_001.json").write_text(json.dumps({"type": "test"}))
        # Create auto_mode_state with no_drift=True (inconsistent)
        state_path = tmpdir / "auto_mode_state.json"
        state_path.write_text(json.dumps({
            "no_drift_events": True,
        }))
        report = reconcile(reports_dir=tmpdir, auto_mode_path=state_path)
        self.assertFalse(report.consistent)
        self.assertTrue(any("INCONSISTENCY" in c["detail"] for c in report.checks))

    def test_incidents_with_no_drift_false_consistent(self):
        from backend.governance.incident_reconciler import reconcile
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "incident_001.json").write_text(json.dumps({"type": "test"}))
        state_path = tmpdir / "auto_mode_state.json"
        state_path.write_text(json.dumps({
            "no_drift_events": False,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }))
        report = reconcile(reports_dir=tmpdir, auto_mode_path=state_path)
        self.assertTrue(report.consistent)

    def test_incidents_with_drift_window_scoped(self):
        from backend.governance.incident_reconciler import reconcile
        tmpdir = Path(tempfile.mkdtemp())
        (tmpdir / "incident_001.json").write_text(json.dumps({"type": "test"}))
        state_path = tmpdir / "auto_mode_state.json"
        state_path.write_text(json.dumps({
            "no_drift_events": True,
            "drift_check_window": "2026-03-01T00:00:00Z/2026-03-01T12:00:00Z",
        }))
        report = reconcile(reports_dir=tmpdir, auto_mode_path=state_path)
        # Scoped by window — consistent
        self.assertTrue(report.consistent)

    def test_reconciliation_report_to_dict(self):
        from backend.governance.incident_reconciler import ReconciliationReport
        report = ReconciliationReport()
        report.add_check("test", True, "ok")
        report.warnings.append("warning1")
        d = report.to_dict()
        self.assertTrue(d["consistent"])
        self.assertEqual(len(d["checks"]), 1)
        self.assertEqual(len(d["warnings"]), 1)

    def test_run_reconciliation_entry_point(self):
        from backend.governance.incident_reconciler import run_reconciliation
        # Should run without crashing even with missing files
        result = run_reconciliation()
        self.assertIn("consistent", result)
        self.assertIn("checks", result)


# =========================================================================
# PREFLIGHT INTEGRATION TESTS
# =========================================================================

class TestPreflightIntegration(unittest.TestCase):
    """Test preflight with config validator integration."""

    def test_check_secrets_with_valid_env(self):
        from backend.startup.preflight import check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "a" * 64,
            "YGB_HMAC_SECRET": "b" * 64,
            "YGB_VIDEO_JWT_SECRET": "c" * 64,
            "YGB_PROFILE": "PRIVACY",
            "API_HOST": "127.0.0.1",
        }, clear=False):
            result = check_secrets()
            self.assertTrue(result.passed)

    def test_check_secrets_with_missing_env(self):
        from backend.startup.preflight import check_secrets
        with patch.dict(os.environ, {
            "JWT_SECRET": "",
            "YGB_HMAC_SECRET": "",
            "YGB_VIDEO_JWT_SECRET": "",
        }, clear=False):
            result = check_secrets()
            self.assertFalse(result.passed)


if __name__ == "__main__":
    unittest.main()
