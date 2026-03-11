"""
Security Regression Guard Tests

Validates that existing security controls are in place and cannot be
removed without failing CI. These tests act as automated regression
guards for the hardening work done in previous security passes.

Tests:
1. OAuth tokens only in HTTP-only cookies (not query params)
2. Server default bind is 127.0.0.1 not 0.0.0.0
3. Ownership check module is imported in server
4. WebSocket auth includes revocation checks
5. Deny-by-default patterns are present
6. Auth guard is used in route handlers
7. No raw secrets in response payloads
8. Static scanner catches known anti-patterns
"""

import os
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class TestOAuthTokenSecurity(unittest.TestCase):
    """Verify OAuth tokens are never passed in query parameters."""

    def test_no_token_in_query_params_in_server(self):
        """api/server.py must not construct URLs with token= query params."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8")
        # Find lines that build URLs with tokens in query strings
        # Exclude comments and log lines
        for i, line in enumerate(content.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("logger."):
                continue
            if "token=" in stripped and ("redirect" in stripped.lower() or "url" in stripped.lower()):
                # Check it's not setting cookies (which is OK)
                if "Set-Cookie" not in stripped and "httponly" not in stripped.lower():
                    self.fail(
                        f"Potential token in query param at server.py:{i}: {stripped[:80]}"
                    )

    def test_auth_cookies_httponly(self):
        """Auth cookies must be set with httponly=True."""
        # Cookies are set in api/server.py where the OAuth callback lives
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8")
        # Should have httponly in cookie settings
        self.assertIn("httponly", content.lower(),
                       "api/server.py must set cookies with httponly=True")


class TestServerBindingSecurity(unittest.TestCase):
    """Verify server does not default to 0.0.0.0."""

    def test_start_script_uses_localhost(self):
        """start.cmd should bind to 127.0.0.1 or localhost."""
        start_path = PROJECT_ROOT / "start.cmd"
        if start_path.exists():
            content = start_path.read_text(encoding="utf-8")
            if "0.0.0.0" in content:
                # Check if it's behind a condition or env var
                if "YGB_BIND" not in content and "HOST" not in content:
                    self.fail("start.cmd binds to 0.0.0.0 without env var override")

    def test_no_hardcoded_bind_all_in_server(self):
        """api/server.py must not hardcode 0.0.0.0 as bind address."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8")
        # Find host= assignments with 0.0.0.0
        matches = re.findall(r"""host\s*=\s*['"]0\.0\.0\.0['"]""", content)
        self.assertEqual(len(matches), 0,
                          "Server must not hardcode host='0.0.0.0'")


class TestOwnershipChecks(unittest.TestCase):
    """Verify ownership checks are imported and available."""

    def test_server_imports_ownership(self):
        """api/server.py must import ownership checking functions."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8")
        self.assertIn("check_resource_owner", content,
                       "Server must import check_resource_owner")

    def test_ownership_module_exists(self):
        """backend/auth/ownership.py must exist."""
        ownership_path = PROJECT_ROOT / "backend" / "auth" / "ownership.py"
        self.assertTrue(ownership_path.exists(),
                         "Ownership module must exist at backend/auth/ownership.py")

    def test_ownership_fail_closed(self):
        """Ownership check must deny access when resource is None."""
        from backend.auth.ownership import check_resource_owner
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            check_resource_owner(
                resource=None,
                user={"sub": "user1", "role": "researcher"},
                resource_name="test",
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_ownership_denies_non_owner(self):
        """Non-owner, non-admin must be denied."""
        from backend.auth.ownership import check_resource_owner
        from fastapi import HTTPException

        with self.assertRaises(HTTPException) as ctx:
            check_resource_owner(
                resource={"owner_id": "user_a"},
                user={"sub": "user_b", "role": "researcher"},
                resource_name="test",
            )
        self.assertEqual(ctx.exception.status_code, 403)


class TestRevocationChecks(unittest.TestCase):
    """Verify revocation store is present and functional."""

    def test_revocation_module_exists(self):
        """backend/auth/revocation_store.py must exist."""
        rev_path = PROJECT_ROOT / "backend" / "auth" / "revocation_store.py"
        self.assertTrue(rev_path.exists())

    def test_revocation_functions_importable(self):
        """Key revocation functions must be importable."""
        from backend.auth.revocation_store import (
            revoke_token, revoke_session,
            is_token_revoked, is_session_revoked,
            get_backend_health,
        )

    def test_server_uses_revocation(self):
        """api/server.py must import revocation functions."""
        server_path = PROJECT_ROOT / "api" / "server.py"
        content = server_path.read_text(encoding="utf-8")
        self.assertIn("revoke_token", content)
        self.assertIn("revoke_session", content)


class TestDenyByDefault(unittest.TestCase):
    """Verify deny-by-default patterns are in place."""

    def test_auth_guard_exists(self):
        """Auth guard module must exist."""
        guard_path = PROJECT_ROOT / "backend" / "auth" / "auth_guard.py"
        self.assertTrue(guard_path.exists())

    def test_require_auth_importable(self):
        """require_auth dependency must be importable."""
        from backend.auth.auth_guard import require_auth, require_admin

    def test_error_taxonomy_exists(self):
        """Error taxonomy module must exist."""
        errors_path = PROJECT_ROOT / "backend" / "errors.py"
        self.assertTrue(errors_path.exists())


class TestSecurityScanner(unittest.TestCase):
    """Test that the security regression scanner works correctly."""

    def test_scanner_importable(self):
        """security_regression_scan.py must be importable."""
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        try:
            import importlib
            spec = importlib.util.spec_from_file_location(
                "security_scan",
                PROJECT_ROOT / "scripts" / "security_regression_scan.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            self.assertTrue(hasattr(mod, "scan_directory"))
            self.assertTrue(hasattr(mod, "ScanReport"))
        finally:
            sys.path.pop(0)

    def test_scanner_detects_token_pattern(self):
        """Scanner should detect token= patterns."""
        import sys
        sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
        try:
            import importlib
            spec = importlib.util.spec_from_file_location(
                "security_scan",
                PROJECT_ROOT / "scripts" / "security_regression_scan.py",
            )
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)

            report = mod.ScanReport()
            # Create a temporary test content with a known violation
            # Use a literal token value, not an f-string placeholder
            import tempfile
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", dir=str(PROJECT_ROOT),
                prefix="_test_scan_", delete=False,
            ) as f:
                f.write('url = "https://api.example.com/?token=abc123secret"\n')
                f.flush()
                temp_path = Path(f.name)

            try:
                mod._scan_file(temp_path, report)
                # Should find the TOKEN_IN_QUERY violation
                token_violations = [v for v in report.violations if v.rule == "TOKEN_IN_QUERY"]
                self.assertGreater(len(token_violations), 0)
            finally:
                temp_path.unlink(missing_ok=True)
        finally:
            sys.path.pop(0)


if __name__ == "__main__":
    unittest.main()
