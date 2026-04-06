"""
Config Validator Tests — backend/config/config_validator.py

Coverage targets:
- _is_placeholder() with various inputs
- validate_required_secrets() with missing, short, placeholder, and valid secrets
- validate_bind_host() with 0.0.0.0 vs 127.0.0.1
- validate_config() strict vs non-strict mode
- ConfigurationError exception class
"""

import os
import sys
import unittest
from unittest.mock import patch

import backend.config.config_validator as config_validator_module

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.config.config_validator import (
    _is_placeholder,
    ConfigDriftDetector,
    ConfigValidationError,
    validate_required_secrets,
    validate_required_fields,
    validate_bind_host,
    validate_config,
    ConfigurationError,
    REQUIRED_FIELDS,
    REQUIRED_SECRETS,
    CONNECTED_ONLY_SECRETS,
    _PLACEHOLDER_PATTERNS,
)


class TestIsPlaceholder(unittest.TestCase):
    """Test placeholder detection logic."""

    def test_obvious_placeholders(self):
        for p in ["change-me", "CHANGE_ME", "changeme", "replace-me", "replace_me",
                   "your-secret", "YOUR_SECRET", "example", "placeholder"]:
            self.assertTrue(_is_placeholder(p), f"'{p}' should be detected as placeholder")

    def test_embedded_placeholder(self):
        self.assertTrue(_is_placeholder("jwt_change-me_secret"))
        self.assertTrue(_is_placeholder("MY_EXAMPLE_KEY"))

    def test_real_secrets_pass(self):
        for v in [
            "a1b2c3d4e5f6789012345678901234567890",
            "xK9$mN2!pQ4@rT6&",
            "0123456789abcdef0123456789abcdef",
        ]:
            self.assertFalse(_is_placeholder(v), f"'{v}' should NOT be detected as placeholder")

    def test_empty_string(self):
        self.assertFalse(_is_placeholder(""))

    def test_case_insensitive(self):
        self.assertTrue(_is_placeholder("Change-Me"))
        self.assertTrue(_is_placeholder("PLACEHOLDER"))
        self.assertTrue(_is_placeholder("Your_Secret"))


class TestValidateRequiredSecrets(unittest.TestCase):
    """Test secret validation with various env states."""

    def _make_env(self, overrides=None):
        env = {
            "JWT_SECRET": "a" * 32,
            "YGB_HMAC_SECRET": "b" * 32,
            "YGB_VIDEO_JWT_SECRET": "c" * 32,
        }
        if overrides:
            env.update(overrides)
        return env

    @patch.dict(os.environ, {}, clear=True)
    def test_all_missing(self):
        violations = validate_required_secrets()
        # All 3 required secrets should be missing
        keys = [k for k, _ in violations]
        self.assertIn("JWT_SECRET", keys)
        self.assertIn("YGB_HMAC_SECRET", keys)
        self.assertIn("YGB_VIDEO_JWT_SECRET", keys)

    @patch.dict(os.environ, {"JWT_SECRET": "ab", "YGB_HMAC_SECRET": "cd", "YGB_VIDEO_JWT_SECRET": "ef"}, clear=True)
    def test_too_short(self):
        violations = validate_required_secrets()
        self.assertEqual(len(violations), 3)
        for _, reason in violations:
            self.assertIn("Too short", reason)

    @patch.dict(os.environ, {
        "JWT_SECRET": "change-me" + "x" * 30,
        "YGB_HMAC_SECRET": "b" * 32,
        "YGB_VIDEO_JWT_SECRET": "c" * 32,
    }, clear=True)
    def test_placeholder_detected(self):
        violations = validate_required_secrets()
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][0], "JWT_SECRET")
        self.assertIn("placeholder", violations[0][1].lower())

    def test_all_valid(self):
        env = self._make_env()
        with patch.dict(os.environ, env, clear=True):
            violations = validate_required_secrets()
            self.assertEqual(violations, [])

    def test_connected_profile_checks_extra(self):
        env = self._make_env({"YGB_PROFILE": "CONNECTED"})
        with patch.dict(os.environ, env, clear=True):
            violations = validate_required_secrets()
            keys = [k for k, _ in violations]
            self.assertIn("GITHUB_CLIENT_SECRET", keys)
            self.assertIn("SMTP_PASS", keys)

    def test_connected_profile_all_valid(self):
        env = self._make_env({
            "YGB_PROFILE": "CONNECTED",
            "GITHUB_CLIENT_SECRET": "gh_secret_12345678",
            "SMTP_PASS": "smtp1234",
        })
        with patch.dict(os.environ, env, clear=True):
            violations = validate_required_secrets()
            self.assertEqual(violations, [])


class TestValidateBindHost(unittest.TestCase):
    """Test bind host validation."""

    @patch.dict(os.environ, {"API_HOST": "0.0.0.0"}, clear=True)
    def test_warns_on_all_interfaces(self):
        warnings = validate_bind_host()
        self.assertEqual(len(warnings), 1)
        self.assertIn("0.0.0.0", warnings[0][1])

    @patch.dict(os.environ, {"API_HOST": "127.0.0.1"}, clear=True)
    def test_no_warning_for_localhost(self):
        warnings = validate_bind_host()
        self.assertEqual(warnings, [])

    @patch.dict(os.environ, {}, clear=True)
    def test_default_is_localhost(self):
        warnings = validate_bind_host()
        self.assertEqual(warnings, [])


class TestValidateConfig(unittest.TestCase):
    """Test unified config validation."""

    def test_strict_raises_on_violations(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError) as ctx:
                validate_config(strict=True)
            self.assertTrue(len(ctx.exception.violations) > 0)

    def test_non_strict_does_not_raise(self):
        with patch.dict(os.environ, {}, clear=True):
            # Should not raise, just log
            validate_config(strict=False)

    def test_passes_with_valid_config(self):
        env = {
            "JWT_SECRET": "a" * 32,
            "YGB_HMAC_SECRET": "b" * 32,
            "YGB_VIDEO_JWT_SECRET": "c" * 32,
        }
        with patch.dict(os.environ, env, clear=True):
            validate_config(strict=True)  # Should not raise

    def test_accepts_valid_explicit_config_mapping(self):
        config_validator_module._drift_detector._baseline_hash = None
        config = {
            "JWT_SECRET": "a" * 32,
            "YGB_HMAC_SECRET": "b" * 32,
            "YGB_VIDEO_JWT_SECRET": "c" * 32,
        }
        with patch.dict(os.environ, {}, clear=True):
            validate_config(strict=True, config=config)

    def test_missing_required_field_raises_config_validation_error(self):
        config_validator_module._drift_detector._baseline_hash = None
        config = {
            "JWT_SECRET": "a" * 32,
            "YGB_HMAC_SECRET": "b" * 32,
        }
        with self.assertRaises(ConfigValidationError) as ctx:
            validate_config(strict=True, config=config)
        self.assertEqual(
            str(ctx.exception),
            "Missing required config field: YGB_VIDEO_JWT_SECRET",
        )


class TestConfigurationError(unittest.TestCase):
    """Test ConfigurationError exception."""

    def test_stores_violations(self):
        violations = [("JWT_SECRET", "Missing"), ("YGB_HMAC_SECRET", "Too short")]
        err = ConfigurationError(violations)
        self.assertEqual(err.violations, violations)
        self.assertIn("JWT_SECRET", str(err))
        self.assertIn("Missing", str(err))

    def test_empty_violations(self):
        err = ConfigurationError([])
        self.assertEqual(err.violations, [])


class TestConfigValidationError(unittest.TestCase):
    """Test explicit config field validation helpers."""

    def test_is_value_error(self):
        self.assertTrue(issubclass(ConfigValidationError, ValueError))

    def test_required_fields_populated(self):
        self.assertEqual(REQUIRED_FIELDS, [
            "JWT_SECRET",
            "YGB_HMAC_SECRET",
            "YGB_VIDEO_JWT_SECRET",
        ])

    def test_validate_required_fields_accepts_complete_mapping(self):
        validate_required_fields({
            "JWT_SECRET": "a" * 32,
            "YGB_HMAC_SECRET": "b" * 32,
            "YGB_VIDEO_JWT_SECRET": "c" * 32,
        })


class TestConfigDriftDetector(unittest.TestCase):
    """Test config drift detection support."""

    def setUp(self):
        self.config = {
            "JWT_SECRET": "a" * 32,
            "YGB_HMAC_SECRET": "b" * 32,
            "YGB_VIDEO_JWT_SECRET": "c" * 32,
        }

    def test_no_drift_on_same_config(self):
        detector = ConfigDriftDetector()
        self.assertFalse(detector.check_drift(self.config))
        self.assertFalse(detector.check_drift(dict(self.config)))

    def test_drift_detected_on_change(self):
        detector = ConfigDriftDetector()
        self.assertFalse(detector.check_drift(self.config))
        changed = dict(self.config)
        changed["JWT_SECRET"] = "z" * 32
        self.assertTrue(detector.check_drift(changed))

    def test_drift_logs_critical_on_change(self):
        detector = ConfigDriftDetector()
        detector.check_drift(self.config)
        changed = dict(self.config)
        changed["JWT_SECRET"] = "z" * 32

        with self.assertLogs("ygb.config_validator", level="CRITICAL") as captured:
            self.assertTrue(detector.check_drift(changed))

        self.assertTrue(
            any("Configuration drift detected" in message for message in captured.output)
        )


if __name__ == "__main__":
    unittest.main()
