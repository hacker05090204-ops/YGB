"""
test_security_fixes.py — Tests for the comprehensive security fix pass.

Covers:
  P1: WS auth close, OAuth secure cookies, _is_private_ip
  P2: Dashboard/execution/approval ownership, video IDOR
  P3: Approval secret fail-closed, field approval identity binding
  P4: Rollout metrics null semantics
  P5: CORS includes FRONTEND_URL, start_full_stack.ps1 calls Import-DotEnv
"""

import os
import sys
import json
import subprocess
import importlib
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

# ── Project root setup ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "api"))


# ════════════════════════════════════════════════════════════════════════
# Test P1: _is_private_ip — RFC 1918 compliance
# ════════════════════════════════════════════════════════════════════════

class TestIsPrivateIp(unittest.TestCase):
    """Verify _is_private_ip correctly identifies private vs public IPs."""

    @classmethod
    def setUpClass(cls):
        # Import the function from server module
        spec = importlib.util.spec_from_file_location(
            "server", str(PROJECT_ROOT / "api" / "server.py"),
            submodule_search_locations=[],
        )
        # We can't fully load server.py (too many deps), so extract the function
        # by reading the file and exec'ing just the function
        server_src = (PROJECT_ROOT / "api" / "server.py").read_text(encoding="utf-8")

        # Extract _is_private_ip function
        start = server_src.find("def _is_private_ip(")
        if start == -1:
            raise RuntimeError("_is_private_ip not found in server.py")

        # Find the end of the function (next def at same indent or end of file)
        end = server_src.find("\ndef ", start + 10)
        if end == -1:
            end = len(server_src)

        func_src = server_src[start:end]
        ns = {}
        exec(func_src, ns)
        cls._is_private_ip = staticmethod(ns["_is_private_ip"])

    def test_localhost(self):
        self.assertTrue(self._is_private_ip("localhost"))
        self.assertTrue(self._is_private_ip("127.0.0.1"))
        self.assertTrue(self._is_private_ip("127.0.0.1:8000"))

    def test_192_168_private(self):
        self.assertTrue(self._is_private_ip("192.168.1.1"))
        self.assertTrue(self._is_private_ip("192.168.1.1:3000"))

    def test_10_private(self):
        self.assertTrue(self._is_private_ip("10.0.0.1"))
        self.assertTrue(self._is_private_ip("10.255.255.255"))

    def test_tailscale_cgnat(self):
        self.assertTrue(self._is_private_ip("100.64.0.1"))
        self.assertTrue(self._is_private_ip("100.127.255.255"))

    def test_172_16_31_private(self):
        """RFC 1918: 172.16.0.0 – 172.31.255.255 is private."""
        self.assertTrue(self._is_private_ip("172.16.0.1"))
        self.assertTrue(self._is_private_ip("172.31.255.255"))
        self.assertTrue(self._is_private_ip("172.20.0.1"))

    def test_172_public_range(self):
        """172.0-15.* and 172.32-255.* are public — must NOT match."""
        self.assertFalse(self._is_private_ip("172.0.0.1"))
        self.assertFalse(self._is_private_ip("172.15.255.255"))
        self.assertFalse(self._is_private_ip("172.32.0.1"))
        self.assertFalse(self._is_private_ip("172.217.1.1"))  # Google DNS

    def test_public_ip(self):
        """Public IPs must NOT be classified as private."""
        self.assertFalse(self._is_private_ip("8.8.8.8"))
        self.assertFalse(self._is_private_ip("142.250.185.206"))  # google.com

    def test_non_ip_hostname(self):
        """Non-IP hostnames should not match."""
        self.assertFalse(self._is_private_ip("example.com"))
        self.assertFalse(self._is_private_ip("github.com"))


# ════════════════════════════════════════════════════════════════════════
# Test P3: Approval Ledger — fail closed without secret
# ════════════════════════════════════════════════════════════════════════

class TestApprovalLedgerFailClosed(unittest.TestCase):
    """Verify KeyManager raises when YGB_APPROVAL_SECRET is not set."""

    def test_missing_secret_raises(self):
        """KeyManager must not silently fall back to a hardcoded default."""
        # Ensure the env var is NOT set
        env = {k: v for k, v in os.environ.items()
               if k not in ("YGB_APPROVAL_SECRET", "YGB_KEY_DIR")}

        with patch.dict(os.environ, env, clear=True):
            # Force reimport
            mod_path = PROJECT_ROOT / "backend" / "governance" / "approval_ledger.py"
            spec = importlib.util.spec_from_file_location(
                "approval_ledger_test", str(mod_path))
            mod = importlib.util.module_from_spec(spec)

            # The module should raise ValueError at load time when KeyManager
            # can't find any secret
            with self.assertRaises((ValueError, Exception)) as ctx:
                spec.loader.exec_module(mod)
                # If module loaded without error, try creating a KeyManager
                km = mod.KeyManager()

            err_msg = str(ctx.exception).upper()
            self.assertTrue(
                "APPROVAL_SECRET" in err_msg or "MISSING" in err_msg or "REQUIRED" in err_msg,
                f"Expected error about missing approval secret, got: {ctx.exception}"
            )


# ════════════════════════════════════════════════════════════════════════
# Test P2: Dashboard/Approval identity binding
# ════════════════════════════════════════════════════════════════════════

class TestOwnershipBindingInServerSource(unittest.TestCase):
    """Verify that server.py source code binds identity server-side."""

    @classmethod
    def setUpClass(cls):
        cls.server_src = (PROJECT_ROOT / "api" / "server.py").read_text(
            encoding="utf-8")

    def test_dashboard_create_uses_auth_identity(self):
        """Dashboard create must use user['sub'], not request.user_id."""
        # Find the create_dashboard function
        idx = self.server_src.find("async def create_dashboard")
        self.assertGreater(idx, 0)
        # Get the next 500 chars
        snippet = self.server_src[idx:idx + 800]
        self.assertIn('user.get("sub"', snippet,
                      "Dashboard create must use authenticated user identity")
        self.assertNotIn("request.user_id", snippet,
                         "Dashboard create must NOT use client-supplied user_id")

    def test_approval_decision_binds_identity(self):
        """Approval decision must override client-supplied approver_id."""
        idx = self.server_src.find("async def submit_approval_decision")
        self.assertGreater(idx, 0)
        snippet = self.server_src[idx:idx + 600]
        self.assertIn("auth_approver_id", snippet,
                      "Approval must use server-derived approver id")

    def test_execution_transition_finds_user_kernel(self):
        """Execution transition must find kernel by owner, not first-in-memory."""
        idx = self.server_src.find("async def execution_transition")
        self.assertGreater(idx, 0)
        snippet = self.server_src[idx:idx + 1500]
        self.assertTrue(
            'owner_id' in snippet and 'auth_user_id' in snippet,
            "Must look up kernel by owner_id, not iterate first")

    def test_field_approve_uses_auth_identity(self):
        """Field approval route must use authenticated identity."""
        idx = self.server_src.find("async def fields_approve_endpoint")
        self.assertGreater(idx, 0)
        snippet = self.server_src[idx:idx + 600]
        self.assertIn("auth_approver_id", snippet,
                      "Field approval must use server-derived identity")
        self.assertNotIn("request.approver_id", snippet,
                         "Field approval must NOT pass client-supplied approver_id")


# ════════════════════════════════════════════════════════════════════════
# Test P1: OAuth cookie secure flag
# ════════════════════════════════════════════════════════════════════════

class TestOAuthCookieSecurity(unittest.TestCase):
    """Verify OAuth cookies auto-detect HTTPS for secure flag."""

    @classmethod
    def setUpClass(cls):
        cls.server_src = (PROJECT_ROOT / "api" / "server.py").read_text(
            encoding="utf-8")

    def test_no_hardcoded_secure_false(self):
        """OAuth cookie section must NOT have hardcoded secure=False."""
        # Check the callback handler's cookie-setting section
        idx = self.server_src.find("_set_cookies")
        self.assertGreater(idx, 0)
        # The area around cookies should use _is_https, not False
        cookie_area = self.server_src[idx:idx + 600]
        self.assertNotIn("secure=False", cookie_area,
                         "Auth cookies must not use hardcoded secure=False")

    def test_auto_detect_https(self):
        """OAuth cookie section must check request scheme for HTTPS."""
        # _is_https should be computed from req.url.scheme somewhere in the file
        self.assertTrue(
            "_is_https" in self.server_src or "_oauth_secure" in self.server_src,
            "OAuth cookies must auto-detect HTTPS scheme"
        )


# ════════════════════════════════════════════════════════════════════════
# Test P4: Rollout Metrics — null not zeros
# ════════════════════════════════════════════════════════════════════════

class TestRolloutMetricsNullSemantics(unittest.TestCase):
    """Verify rollout metrics use null/None, not fabricated zeros."""

    @classmethod
    def setUpClass(cls):
        cls.server_src = (PROJECT_ROOT / "api" / "server.py").read_text(
            encoding="utf-8")

    def test_importerror_path_uses_none(self):
        """ImportError fallback must return None for unavailable metrics."""
        # Find the ImportError handler in rollout_metrics
        idx = self.server_src.find("async def rollout_metrics")
        self.assertGreater(idx, 0)
        fn_src = self.server_src[idx:idx + 2000]

        # Find "except ImportError" block
        ie_idx = fn_src.find("except ImportError")
        self.assertGreater(ie_idx, 0)
        ie_block = fn_src[ie_idx:ie_idx + 800]

        # Must contain None for metric fields, not 0.0
        self.assertIn('"label_quality": None', ie_block)
        self.assertIn('"fpr_current": None', ie_block)
        self.assertIn('"metrics_available": False', ie_block)

    def test_no_fabricated_gate_true(self):
        """Rollout metrics must not fabricate True for gate passes."""
        idx = self.server_src.find("async def rollout_metrics")
        fn_src = self.server_src[idx:idx + 2000]
        # Check both paths
        self.assertNotIn('"drift_guard_pass": True', fn_src,
                         "Must not fabricate True for unmeasured gates")


# ════════════════════════════════════════════════════════════════════════
# Test P5: CORS includes FRONTEND_URL
# ════════════════════════════════════════════════════════════════════════

class TestCORSConfiguration(unittest.TestCase):
    """Verify CORS middleware includes FRONTEND_URL."""

    @classmethod
    def setUpClass(cls):
        cls.server_src = (PROJECT_ROOT / "api" / "server.py").read_text(
            encoding="utf-8")

    def test_cors_includes_frontend_url(self):
        """CORS origins must include FRONTEND_URL env var."""
        # Check that FRONTEND_URL is read and added to CORS origins
        self.assertTrue(
            "_CONFIGURED_FRONTEND_URL" in self.server_src or
            ("_cors_origins" in self.server_src and "FRONTEND_URL" in self.server_src),
            "CORS must include FRONTEND_URL in allowed origins"
        )

    def test_cors_not_hardcoded(self):
        """CORS must use a variable, not inline list."""
        idx = self.server_src.find("allow_origins=")
        area = self.server_src[idx:idx + 100]
        self.assertIn("_cors_origins", area,
                      "CORS must use _cors_origins variable, not inline list")


# ════════════════════════════════════════════════════════════════════════
# Test P5: start_full_stack.ps1 calls Import-DotEnv
# ════════════════════════════════════════════════════════════════════════

class TestStartFullStackEnvLoading(unittest.TestCase):
    """Verify start_full_stack.ps1 calls Import-DotEnv."""

    def test_import_dotenv_is_called(self):
        """Script must call Import-DotEnv before starting processes."""
        ps1_path = PROJECT_ROOT / "start_full_stack.ps1"
        if not ps1_path.exists():
            self.skipTest("start_full_stack.ps1 not found")

        content = ps1_path.read_text(encoding="utf-8")

        # Check that Import-DotEnv is called (not just defined)
        lines = content.split("\n")
        call_lines = [
            i for i, line in enumerate(lines)
            if "Import-DotEnv" in line
            and not line.strip().startswith("#")
            and not line.strip().startswith("function")
        ]
        # Should have at least one call (not just the function def)
        self.assertGreater(
            len(call_lines), 0,
            "Import-DotEnv must be CALLED, not just defined"
        )


# ════════════════════════════════════════════════════════════════════════
# Test: .env_secrets.txt not tracked by git
# ════════════════════════════════════════════════════════════════════════

class TestSecretTracking(unittest.TestCase):
    """Guard: sensitive files must not be tracked by git."""

    def test_env_secrets_not_tracked(self):
        """`.env_secrets.txt` must not be in git index."""
        result = subprocess.run(
            ["git", "ls-files", ".env_secrets.txt"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
        )
        tracked = result.stdout.strip()
        self.assertEqual(tracked, "",
                         ".env_secrets.txt must NOT be tracked by git")

    def test_gitignore_covers_secrets(self):
        """`.gitignore` must have patterns for secrets."""
        gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env", gitignore)
        self.assertIn("*.secret", gitignore)
        self.assertIn("*.credentials", gitignore)


# ════════════════════════════════════════════════════════════════════════
# Test P1: WS auth socket close
# ════════════════════════════════════════════════════════════════════════

class TestWsAuthSocketClose(unittest.TestCase):
    """Verify voice_gateway.py closes socket on auth failure."""

    @classmethod
    def setUpClass(cls):
        cls.vg_src = (PROJECT_ROOT / "api" / "voice_gateway.py").read_text(
            encoding="utf-8")

    def test_ws_auth_failure_closes_socket(self):
        """When ws_authenticate returns None, socket must be closed."""
        # Find the WS handler where ws_authenticate is actually called (not the import)
        idx = self.vg_src.find("await ws_authenticate")
        self.assertGreater(idx, 0, "ws_authenticate call not found")
        # Get surrounding code
        area = self.vg_src[idx:idx + 300]
        self.assertTrue(
            "ws.close" in area or "close(code=4401" in area,
            "Must explicitly close socket on auth failure"
        )

    def test_no_assumption_comment(self):
        """Old misleading comment must be removed."""
        self.assertNotIn(
            "ws_authenticate closes the connection",
            self.vg_src,
            "Misleading comment about ws_authenticate closing connection must be removed"
        )


# ════════════════════════════════════════════════════════════════════════
# Test P2: Video listing IDOR protection
# ════════════════════════════════════════════════════════════════════════

class TestVideoListingIDOR(unittest.TestCase):
    """Verify video listing by report_id includes ownership filter."""

    @classmethod
    def setUpClass(cls):
        cls.rg_src = (PROJECT_ROOT / "backend" / "api" / "report_generator.py").read_text(
            encoding="utf-8")

    def test_report_id_filter_has_ownership(self):
        """When filtering by report_id, non-admin must also filter by created_by."""
        idx = self.rg_src.find("if report_id:")
        self.assertGreater(idx, 0)
        area = self.rg_src[idx:idx + 500]
        self.assertIn("created_by", area,
                      "Video listing by report_id must include ownership filter")

    def test_admin_bypass_exists(self):
        """Admin should see all videos without ownership filter."""
        idx = self.rg_src.find("if report_id:")
        area = self.rg_src[idx:idx + 500]
        self.assertIn('"admin"', area,
                      "Admin bypass must exist for video listing")


# ════════════════════════════════════════════════════════════════════════
# Test P4: Frontend mock data removal
# ════════════════════════════════════════════════════════════════════════

class TestFrontendMockDataRemoval(unittest.TestCase):
    """Verify hardcoded user-001/Researcher removed from control page."""

    @classmethod
    def setUpClass(cls):
        cls.control_src = (PROJECT_ROOT / "frontend" / "app" / "control" / "page.tsx").read_text(
            encoding="utf-8")

    def test_no_hardcoded_user_001(self):
        """Control page must not contain hardcoded user-001."""
        self.assertNotIn('"user-001"', self.control_src,
                         "Hardcoded user-001 must be replaced with real auth identity")

    def test_no_hardcoded_researcher(self):
        """Control page must not contain hardcoded 'Researcher' as user name."""
        # Check it's not used as a user_name value
        self.assertNotIn('"Researcher"', self.control_src,
                         "Hardcoded 'Researcher' user name must be replaced")

    def test_has_auth_identity_helpers(self):
        """Control page must have getAuthUserId/getAuthUserName helpers."""
        self.assertIn("getAuthUserId", self.control_src)
        self.assertIn("getAuthUserName", self.control_src)


if __name__ == "__main__":
    unittest.main()
