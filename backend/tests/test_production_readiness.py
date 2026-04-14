"""
Production Readiness Tests — Verifies all 11 fix areas from the master prompt.

Covers:
  Fix 1:  No simulated-success hunter websocket (no ws/hunter endpoint exists)
  Fix 2:  Narrow remediation scanner simulate allowlist (line-specific)
  Fix 3:  Governance Python classified as PRODUCTION
  Fix 4:  CI scanner detects f-string error leakage + str(e) leakage
  Fix 5:  Foreign-process kill is ownership-gated
  Fix 6:  CI_TOOLING misclassification of runtime governors
  Fix 7:  Incident reconciler recursive search
  Fix 8:  Session durability default = file
  Fix 9:  Insecure bind host default = 127.0.0.1
  Fix 10: Coverage expansion (this file IS the coverage expansion)
  Fix 11: Antigravity harness exists and is runnable
"""

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Fix 1: No simulated-success hunter websocket
# =============================================================================

class TestNoSimulatedHunterWebsocket(unittest.TestCase):
    """Verify hunter websocket has no simulated-success behavior."""

    def test_hunter_ws_exists_with_real_execution(self):
        """api/server.py must have /ws/hunter/ but with real execution."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8", errors="ignore")
        self.assertIn("/ws/hunter/", content,
            "Hunter WS endpoint must exist for real execution")

    def test_no_simulated_sleep_in_hunter_ws(self):
        """Hunter WS must NOT have asyncio.sleep for simulating processing."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8", errors="ignore")
        idx = content.find("async def hunter_websocket")
        self.assertNotEqual(idx, -1, "hunter_websocket function must exist")
        func_content = content[idx:idx+2500]
        self.assertNotIn("asyncio.sleep", func_content,
            "Hunter WS must not simulate processing time with asyncio.sleep")

    def test_no_unconditional_success_in_hunter_ws(self):
        """Hunter WS must NOT have hardcoded 'success': True."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8", errors="ignore")
        idx = content.find("async def hunter_websocket")
        self.assertNotEqual(idx, -1)
        func_content = content[idx:idx+2500]
        # Must NOT have unconditional success
        self.assertNotIn('"success": True', func_content,
            "Hunter WS must not hardcode success: True")
        self.assertNotIn('"checks_passed": True', func_content,
            "Hunter WS must not hardcode checks_passed: True")

    def test_no_uuid_evidence_hash(self):
        """Evidence chain hash must be content-derived, not random UUID."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8", errors="ignore")
        idx = content.find("async def hunter_websocket")
        self.assertNotEqual(idx, -1)
        func_content = content[idx:idx+2500]
        self.assertNotIn("uuid.uuid4().hex", func_content,
            "Evidence chain hash must not be random UUID")


# =============================================================================
# Fix 2: Narrowed simulate allowlist
# =============================================================================

class TestNarrowedAllowlist(unittest.TestCase):
    """Verify remediation_scan.py has line-specific api/server.py allowlist."""

    def test_no_broad_simulate_allowlist_for_server(self):
        """remediation_scan.py must NOT have broad ('simulate', 'api/server.py') allowlist."""
        scan_path = PROJECT_ROOT / "scripts" / "remediation_scan.py"
        content = scan_path.read_text(encoding="utf-8", errors="ignore")
        # Must NOT contain the broad pattern (without line number)
        broad_pattern = '("simulate", "api/server.py",'
        self.assertNotIn(broad_pattern, content,
            "Broad simulate allowlist for api/server.py must be removed")

    def test_has_line_specific_allowlist(self):
        """remediation_scan.py must have line-specific simulate allowlist."""
        scan_path = PROJECT_ROOT / "scripts" / "remediation_scan.py"
        content = scan_path.read_text(encoding="utf-8", errors="ignore")
        # Must contain line-specific entry
        self.assertIn("api/server.py:", content,
            "Must have line-specific allowlist for api/server.py")

    def test_allowlist_function_accepts_line_num(self):
        """_is_allowlisted must accept line_num parameter."""
        from scripts.remediation_scan import _is_allowlisted
        import inspect
        sig = inspect.signature(_is_allowlisted)
        params = list(sig.parameters.keys())
        self.assertIn("line_num", params,
            "_is_allowlisted must accept line_num parameter")


# =============================================================================
# Fix 3: Governance Python classified as PRODUCTION
# =============================================================================

class TestGovernanceClassification(unittest.TestCase):
    """Verify runtime governance Python modules are PRODUCTION."""

    def test_incident_reconciler_is_production(self):
        """backend/governance/incident_reconciler.py must be PRODUCTION."""
        from scripts.remediation_scan import classify_path
        path = str(PROJECT_ROOT / "backend" / "governance" / "incident_reconciler.py")
        self.assertEqual(classify_path(path), "PRODUCTION")

    def test_governance_markdown_is_config_docs(self):
        """governance/*.md files should still be CONFIG/DOCS."""
        from scripts.remediation_scan import classify_path
        path = str(PROJECT_ROOT / "governance" / "README.md")
        self.assertEqual(classify_path(path), "CONFIG/DOCS")

    def test_governance_json_is_config_docs(self):
        """governance/*.json files should still be CONFIG/DOCS."""
        from scripts.remediation_scan import classify_path
        path = str(PROJECT_ROOT / "governance" / "config.json")
        self.assertEqual(classify_path(path), "CONFIG/DOCS")


# =============================================================================
# Fix 4: CI scanner detects f-string error leakage
# =============================================================================

class TestCIErrorLeakageDetection(unittest.TestCase):
    """Verify CI scanner catches f-string exception leakage patterns."""

    def test_scanner_has_fstring_patterns(self):
        """ci_security_scan.py must detect f-string error leakage."""
        scan_path = PROJECT_ROOT / "scripts" / "ci_security_scan.py"
        content = scan_path.read_text(encoding="utf-8", errors="ignore")
        # Scanner must mention f-string detection in comments
        self.assertIn("f-string", content.lower(),
            "Scanner must mention f-string patterns")
        # Must have patterns covering exception variables e, exc, err
        self.assertIn("(e|exc|err)", content,
            "Scanner must detect e, exc, and err exception variables")

    def test_no_exception_leak_in_health_reason(self):
        """api/server.py health endpoint must not leak exception text."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8", errors="ignore")
        # Find the health_check function
        idx = content.find("async def health_check")
        self.assertNotEqual(idx, -1, "health_check function must exist")
        func_content = content[idx:idx+500]
        self.assertNotIn('f"Storage probe error: {e}"', func_content)
        self.assertNotIn("str(e)", func_content)

    def test_no_exception_leak_in_training_progress(self):
        """backend/api/training_progress.py must not leak exception text."""
        path = PROJECT_ROOT / "backend" / "api" / "training_progress.py"
        content = path.read_text(encoding="utf-8", errors="ignore")
        # Check that no f-string with exception var in message field
        self.assertNotIn('f"Cannot read telemetry: {e}"', content)


# =============================================================================
# Fix 5: Foreign-process kill safety
# =============================================================================

class TestForeignProcessKillSafety(unittest.TestCase):
    """Verify start_full_stack.ps1 has ownership checks."""

    def test_ps1_has_ownership_guard(self):
        """start_full_stack.ps1 must check process ownership before killing."""
        ps1_path = PROJECT_ROOT / "start_full_stack.ps1"
        content = ps1_path.read_text(encoding="utf-8", errors="ignore")
        self.assertIn("$isYgbOwned", content,
            "Must have YGB ownership check")
        self.assertIn("$ForceKillForeign", content,
            "Foreign kill must require explicit opt-in")

    def test_ps1_foreign_kill_off_by_default(self):
        """AllowForeignPortKill must default to off."""
        ps1_path = PROJECT_ROOT / "start_full_stack.ps1"
        content = ps1_path.read_text(encoding="utf-8", errors="ignore")
        # The switch parameter defaults to $false if not provided
        self.assertIn("[switch]$AllowForeignPortKill", content)

    def test_ci_scanner_includes_ps1(self):
        """CI security scanner must scan .ps1 files."""
        scan_path = PROJECT_ROOT / "scripts" / "ci_security_scan.py"
        content = scan_path.read_text(encoding="utf-8", errors="ignore")
        self.assertIn(".ps1", content,
            "CI scanner must include .ps1 extension")

    def test_ci_scanner_detects_kill_patterns(self):
        """CI scanner must detect Stop-Process patterns."""
        scan_path = PROJECT_ROOT / "scripts" / "ci_security_scan.py"
        content = scan_path.read_text(encoding="utf-8", errors="ignore")
        self.assertIn("Stop-Process", content,
            "CI scanner must detect Stop-Process patterns")


# =============================================================================
# Fix 6: CI_TOOLING misclassification of governors
# =============================================================================

class TestGovernorClassification(unittest.TestCase):
    """Verify production-imported governors are not CI_TOOLING."""

    def test_runtime_governor_is_production(self):
        """g38_auto_training.py must be PRODUCTION."""
        from scripts.remediation_scan import classify_path
        path = str(PROJECT_ROOT / "impl_v1" / "phase49" / "governors" / "g38_auto_training.py")
        result = classify_path(path)
        self.assertEqual(result, "PRODUCTION",
            f"g38_auto_training.py classified as {result}, expected PRODUCTION")

    def test_g35_governor_is_production(self):
        """g35_ai_accelerator.py must be PRODUCTION."""
        from scripts.remediation_scan import classify_path
        path = str(PROJECT_ROOT / "impl_v1" / "phase49" / "governors" / "g35_ai_accelerator.py")
        self.assertEqual(classify_path(path), "PRODUCTION")

    def test_non_runtime_governor_is_ci_tooling(self):
        """Non-runtime governors should still be CI_TOOLING."""
        from scripts.remediation_scan import classify_path
        path = str(PROJECT_ROOT / "impl_v1" / "phase20" / "governors" / "g01_test_governor.py")
        self.assertEqual(classify_path(path), "CI_TOOLING")

    def test_impl_v1_validation_is_ci_tooling(self):
        """impl_v1 validation directories should be CI_TOOLING."""
        from scripts.remediation_scan import classify_path
        path = str(PROJECT_ROOT / "impl_v1" / "phase30" / "validation" / "check.py")
        self.assertEqual(classify_path(path), "CI_TOOLING")


# =============================================================================
# Fix 7: Incident reconciler recursive search
# =============================================================================

class TestIncidentReconcilerRecursive(unittest.TestCase):
    """Verify _find_incident_files searches recursively."""

    def test_finds_nested_incidents(self):
        """Must find incidents under reports/incidents/ subdirectory."""
        from backend.governance.incident_reconciler import _find_incident_files
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested incidents directory
            nested = Path(tmpdir) / "incidents"
            nested.mkdir()
            (nested / "incident_001.json").write_text("{}")
            (nested / "incident_log_002.json").write_text("{}")
            # Create top-level incident
            (Path(tmpdir) / "incident_top.json").write_text("{}")

            files = _find_incident_files(Path(tmpdir))
            filenames = {f.name for f in files}
            self.assertIn("incident_001.json", filenames)
            self.assertIn("incident_log_002.json", filenames)
            self.assertIn("incident_top.json", filenames)

    def test_uses_rglob(self):
        """incident_reconciler.py must use rglob for recursive search."""
        path = PROJECT_ROOT / "backend" / "governance" / "incident_reconciler.py"
        content = path.read_text(encoding="utf-8", errors="ignore")
        self.assertIn(".rglob(", content)
        self.assertNotIn(".glob(", content.replace(".rglob(", ""))


# =============================================================================
# Fix 8: Session durability default
# =============================================================================

class TestSessionDurabilityDefault(unittest.TestCase):
    """Verify revocation store defaults to file, not memory."""

    def test_default_is_file_backend(self):
        """revocation_store.py must default to 'file' backend."""
        store_path = PROJECT_ROOT / "backend" / "auth" / "revocation_store.py"
        content = store_path.read_text(encoding="utf-8", errors="ignore")
        self.assertIn('REVOCATION_BACKEND", "file"', content,
            "Default backend must be 'file', not 'memory'")

    def test_revocation_survives_reset(self):
        """Revocation must survive store reset under default (file) config."""
        # Use explicit file backend for this test
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            tmp_path = f.name
            f.write(b'{"tokens": [], "sessions": []}')

        try:
            os.environ["REVOCATION_BACKEND"] = "file"
            os.environ["REVOCATION_FILE_PATH"] = tmp_path

            from backend.auth.revocation_store import (
                reset_store, revoke_token, is_token_revoked, _get_store
            )

            reset_store()
            revoke_token("durable-test-token-xyz")
            self.assertTrue(is_token_revoked("durable-test-token-xyz"))

            # Simulate process restart
            reset_store()

            # Token must still be revoked after restart
            self.assertTrue(is_token_revoked("durable-test-token-xyz"),
                "Revocation must survive store reset with file backend")
        finally:
            os.environ.pop("REVOCATION_BACKEND", None)
            os.environ.pop("REVOCATION_FILE_PATH", None)
            from backend.auth.revocation_store import reset_store
            reset_store()
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def test_memory_mode_is_explicit_only(self):
        """Memory mode should only activate with explicit env var."""
        store_path = PROJECT_ROOT / "backend" / "auth" / "revocation_store.py"
        content = store_path.read_text(encoding="utf-8", errors="ignore")
        # The _get_store default must be 'file', not 'memory'
        idx = content.find('def _get_store')
        self.assertNotEqual(idx, -1, "_get_store function must exist")
        func_content = content[idx:idx+200]
        self.assertIn('"file"', func_content,
            "_get_store must default to file backend")
        # Check the os.getenv line specifically does NOT default to memory
        for line in func_content.split('\n'):
            if 'REVOCATION_BACKEND' in line and 'os.getenv' in line:
                self.assertNotIn('"memory"', line,
                    "Default backend in os.getenv must not be memory")


# =============================================================================
# Fix 9: Insecure bind host default
# =============================================================================

class TestBindHostDefault(unittest.TestCase):
    """Verify API_HOST defaults to 127.0.0.1."""

    def test_default_is_loopback(self):
        """api/server.py must default API_HOST to 127.0.0.1."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8", errors="ignore")
        self.assertIn('os.getenv("API_HOST", "127.0.0.1")', content)

    def test_not_wildcard(self):
        """api/server.py must NOT default to 0.0.0.0."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8", errors="ignore")
        self.assertNotIn('os.getenv("API_HOST", "0.0.0.0")', content)


# =============================================================================
# Fix 11: Antigravity harness
# =============================================================================

class TestAntigravityHarness(unittest.TestCase):
    """Verify antigravity harness exists and is runnable."""

    def test_harness_exists(self):
        """scripts/antigravity_harness.py must exist."""
        harness = PROJECT_ROOT / "scripts" / "antigravity_harness.py"
        self.assertTrue(harness.exists(),
            "Antigravity harness must exist at scripts/antigravity_harness.py")

    def test_harness_importable(self):
        """Harness must be importable."""
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "antigravity_harness",
            str(PROJECT_ROOT / "scripts" / "antigravity_harness.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertTrue(hasattr(mod, "main"))


if __name__ == "__main__":
    unittest.main()
