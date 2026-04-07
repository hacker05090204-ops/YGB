"""Focused tests for startup preflight reporting and failure logging."""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from backend.startup import preflight as preflight_module


class TestPreflightReporting(unittest.TestCase):
    """Validate preflight report structure and wrapper behavior."""

    def _passing_results(self):
        return {
            "check_report_directory": preflight_module.PreflightCheck(
                "report_directory", True, "reports/ exists", True
            ),
            "check_hdd_writable": preflight_module.PreflightCheck(
                "hdd_writable", True, "Filesystem writable", True
            ),
            "check_gpu_query": preflight_module.PreflightCheck(
                "gpu_query", True, "GPU available", False
            ),
            "check_precision_baseline": preflight_module.PreflightCheck(
                "precision_baseline", True, "Precision baseline loaded", False
            ),
            "check_drift_baseline": preflight_module.PreflightCheck(
                "drift_baseline", True, "Drift baseline loaded", False
            ),
            "check_scope_registry": preflight_module.PreflightCheck(
                "scope_registry", True, "Scope registry valid", True
            ),
            "check_secrets": preflight_module.PreflightCheck(
                "secrets", True, "Secrets valid", False
            ),
            "check_manifest_authority_key": preflight_module.PreflightCheck(
                "manifest_authority_key", True, "Authority key configured", True
            ),
            "check_boot_summary": preflight_module.PreflightCheck(
                "boot_summary", True, "Boot summary generated", False
            ),
        }

    def _run_preflight_with_results(self, results, *, bootstrap_side_effect=None):
        with ExitStack() as stack:
            for attr_name, result in results.items():
                stack.enter_context(patch.object(preflight_module, attr_name, return_value=result))
            bootstrap_mock = stack.enter_context(
                patch.object(
                    preflight_module,
                    "bootstrap_pipeline",
                    side_effect=bootstrap_side_effect,
                )
            )
            report = preflight_module.preflight()
            return report, bootstrap_mock

    def test_preflight_returns_report_with_all_checks_listed(self):
        report, _ = self._run_preflight_with_results(self._passing_results())

        self.assertIsInstance(report, preflight_module.PreflightReport)
        self.assertTrue(report.passed)
        self.assertTrue(report.all_passed)
        self.assertEqual(report.fatal_errors, [])
        self.assertEqual(
            [check.name for check in report.checks],
            [
                "report_directory",
                "hdd_writable",
                "gpu_query",
                "precision_baseline",
                "drift_baseline",
                "scope_registry",
                "secrets",
                "manifest_authority_key",
                "boot_summary",
            ],
        )
        self.assertTrue(
            all(isinstance(check, preflight_module.PreflightCheck) for check in report.checks)
        )

    def test_preflight_calls_bootstrap_after_checks_pass(self):
        report, bootstrap_mock = self._run_preflight_with_results(self._passing_results())

        self.assertTrue(report.passed)
        bootstrap_mock.assert_called_once_with()

    def test_run_preflight_returns_report_all_passed_flag(self):
        report = preflight_module.PreflightReport(
            passed=True,
            checks=[
                preflight_module.PreflightCheck("report_directory", True, "ok", True),
                preflight_module.PreflightCheck("gpu_query", False, "timed out", False),
            ],
            fatal_errors=[],
        )

        self.assertFalse(report.all_passed)
        self.assertTrue(report.passed)

        with patch.object(preflight_module, "preflight", return_value=report):
            self.assertFalse(preflight_module.run_preflight())

    def test_bootstrap_failure_logged_critical_without_raising(self):
        with self.assertLogs(preflight_module.logger.name, level="CRITICAL") as captured:
            report, bootstrap_mock = self._run_preflight_with_results(
                self._passing_results(),
                bootstrap_side_effect=RuntimeError("pipeline bootstrap exploded"),
            )

        self.assertTrue(report.passed)
        self.assertTrue(report.all_passed)
        bootstrap_mock.assert_called_once_with()
        output = "\n".join(captured.output)
        self.assertIn("automatic pipeline bootstrap failed", output.lower())
        self.assertIn("pipeline bootstrap exploded", output)

    def test_failed_checks_logged_at_critical_before_raise(self):
        results = self._passing_results()
        results["check_gpu_query"] = preflight_module.PreflightCheck(
            "gpu_query", False, "nvidia-smi timed out", False
        )
        results["check_scope_registry"] = preflight_module.PreflightCheck(
            "scope_registry", False, "registry invalid", True
        )

        with self.assertLogs(preflight_module.logger.name, level="CRITICAL") as captured:
            with self.assertRaises(preflight_module.PreflightError):
                self._run_preflight_with_results(results)

        output = "\n".join(captured.output)
        self.assertIn("gpu_query", output)
        self.assertIn("nvidia-smi timed out", output)
        self.assertIn("scope_registry", output)
        self.assertIn("registry invalid", output)


if __name__ == "__main__":
    unittest.main()
