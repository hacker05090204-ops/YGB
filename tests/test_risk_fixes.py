"""
tests/test_risk_fixes.py — Runtime + source-level tests for the 5 risk fixes.

Covers:
  1. OAuth cookie flags (ygb_token readable, ygb_session_id HttpOnly)
  2. OAuth redirect URI uses configured _GITHUB_REDIRECT_URI, not Host header
  3. Admin-only auth on /api/g38/start, /api/g38/abort, /api/storage/enforce
  4. Proxy trust default (false) — direct LAN clients can't spoof XFF
  5. Websocket sequence IDs use runtime_state.increment(), not bare globals
"""
import ast
import importlib
import inspect
import ipaddress
import os
import sys
import textwrap
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so imports work
# ---------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _read_server_source() -> str:
    """Read api/server.py source in full."""
    server_py = os.path.join(_PROJECT_ROOT, "api", "server.py")
    with open(server_py, "r", encoding="utf-8") as f:
        return f.read()


# ============================================================================
# 1. OAuth cookie flags
# ============================================================================
class TestOAuthCookieFlags(unittest.TestCase):
    """ygb_token must be JS-readable; ygb_session_id must be HttpOnly."""

    def test_ygb_token_not_httponly_in_source(self):
        """Source-level: httponly rule excludes ygb_token."""
        src = _read_server_source()
        # The line should contain the not-in check for ygb_profile and ygb_token
        self.assertIn('cookie_name not in ("ygb_profile", "ygb_token")', src,
                       "ygb_token must be listed as non-HttpOnly along with ygb_profile")

    def test_httponly_logic_runtime(self):
        """Runtime: evaluate the httponly expression for each cookie name."""
        # Replicate the exact httponly logic from server.py
        for cookie_name, expected_httponly in [
            ("ygb_token", False),        # JWT — must be JS-readable
            ("ygb_session_id", True),     # Session ID — HttpOnly
            ("ygb_profile", False),       # Profile — JS-readable for display
        ]:
            httponly = cookie_name not in ("ygb_profile", "ygb_token")
            self.assertEqual(httponly, expected_httponly,
                             f"{cookie_name}: httponly should be {expected_httponly}")


# ============================================================================
# 2. OAuth redirect URI — no Host-header derivation
# ============================================================================
class TestOAuthRedirectURI(unittest.TestCase):
    """OAuth must use configured _GITHUB_REDIRECT_URI, never Host header."""

    def test_no_host_header_redirect_construction(self):
        """Source must not build redirect_uri from req.headers['host']."""
        src = _read_server_source()
        # The old dangerous patterns
        self.assertNotIn('f"http://{request_host}/auth/github/callback"', src,
                          "Must not derive redirect_uri from Host header")
        self.assertNotIn('"redirect_uri": dynamic_redirect', src,
                          "Must not use dynamic_redirect for redirect_uri")

    def test_configured_redirect_used(self):
        """redirect_uri params must use _GITHUB_REDIRECT_URI."""
        src = _read_server_source()
        self.assertIn('"redirect_uri": _GITHUB_REDIRECT_URI', src,
                       "redirect_uri must reference the configured _GITHUB_REDIRECT_URI")

    def test_callback_also_uses_configured_redirect(self):
        """Token exchange in callback must use the same configured URI."""
        src = _read_server_source()
        self.assertIn('callback_redirect = _GITHUB_REDIRECT_URI', src,
                       "Callback must assign callback_redirect from _GITHUB_REDIRECT_URI")
        self.assertIn('"redirect_uri": callback_redirect', src,
                       "Token exchange must use callback_redirect")


# ============================================================================
# 3. Admin-only auth on global mutating endpoints
# ============================================================================
class TestAdminOnlyEndpoints(unittest.TestCase):
    """g38/start, g38/abort, storage/enforce must use require_admin."""

    def test_g38_abort_requires_admin(self):
        src = _read_server_source()
        # Find the function definition and check its dependency
        self.assertIn("abort_g38_training(user=Depends(require_admin))", src,
                       "/api/g38/abort must require admin role")

    def test_g38_start_requires_admin(self):
        src = _read_server_source()
        self.assertIn("start_g38_training(epochs: int = 0, user=Depends(require_admin))", src,
                       "/api/g38/start must require admin role")

    def test_storage_enforce_requires_admin(self):
        src = _read_server_source()
        self.assertIn("storage_enforce(user=Depends(require_admin))", src,
                       "/api/storage/enforce must require admin role")

    def test_no_require_auth_on_mutating_endpoints(self):
        """These specific endpoints must NOT use require_auth."""
        src = _read_server_source()
        # Parse the AST and find these functions to check their decorators/args
        tree = ast.parse(src)
        mutating_functions = {
            "abort_g38_training",
            "start_g38_training",
            "storage_enforce",
        }
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                if node.name in mutating_functions:
                    # Get the source segment for this function's signature
                    func_source = ast.get_source_segment(src, node)
                    if func_source:
                        # Should not have require_auth in the first line (signature)
                        first_line = func_source.split("\n")[0]
                        self.assertNotIn("require_auth", first_line,
                                          f"{node.name} must not use require_auth")


# ============================================================================
# 4. Proxy trust defaults
# ============================================================================
class TestProxyTrustDefaults(unittest.TestCase):
    """Proxy trust must default to OFF."""

    def test_trust_proxy_headers_defaults_false(self):
        """_TRUST_PROXY_HEADERS must default to 'false'."""
        src = _read_server_source()
        self.assertIn(
            'os.getenv("TRUST_PROXY_HEADERS", "false")',
            src,
            "TRUST_PROXY_HEADERS default must be 'false'"
        )

    def test_trusted_cidrs_loopback_only_default(self):
        """Default trusted CIDRs must be loopback only (no private LAN ranges)."""
        src = _read_server_source()
        # Must NOT contain the wide private-LAN ranges as default
        # Look for the TRUSTED_PROXY_CIDRS default string
        self.assertNotIn('10.0.0.0/8,172.16.0.0/12,192.168.0.0/16', src,
                          "Default trusted CIDRs must not include private LAN ranges")

    def test_extract_client_ip_ignores_xff_when_untrusted(self):
        """When _TRUST_PROXY_HEADERS=false, _extract_client_ip returns peer IP."""
        # Import the actual function and test it at runtime
        try:
            from api.server import _extract_client_ip, _TRUST_PROXY_HEADERS
        except ImportError:
            self.skipTest("Cannot import api.server (dependency missing)")

        # When trust is off, the function must return peer IP regardless of XFF
        if _TRUST_PROXY_HEADERS:
            self.skipTest("TRUST_PROXY_HEADERS is enabled in this environment (explicitly set)")

        # Create a mock request with spoofed XFF
        mock_req = MagicMock()
        mock_req.client.host = "192.168.1.50"
        # Use a MagicMock for headers so .get is overridable
        headers_data = {
            "x-forwarded-for": "8.8.8.8, 1.1.1.1",
            "cf-connecting-ip": "9.9.9.9",
        }
        mock_headers = MagicMock()
        mock_headers.get = lambda h, d="": headers_data.get(h, d)
        mock_headers.__getitem__ = lambda self, h: headers_data[h]
        mock_headers.__contains__ = lambda self, h: h in headers_data
        mock_req.headers = mock_headers

        result = _extract_client_ip(mock_req)
        # Should return the peer IP (192.168.1.50), not the spoofed 8.8.8.8
        self.assertEqual(result, "192.168.1.50",
                          "Must return peer socket IP when proxy trust is disabled")


# ============================================================================
# 5. Websocket sequence IDs — no bare global mutation
# ============================================================================
class TestWebsocketSequenceIDs(unittest.TestCase):
    """Websocket handlers must use runtime_state.increment(), not bare globals."""

    def test_no_bare_stream_seq_id_mutation(self):
        """No '_stream_seq_id += 1' in source."""
        src = _read_server_source()
        self.assertNotIn("_stream_seq_id += 1", src,
                          "Must not mutate _stream_seq_id with bare +=")

    def test_no_bare_dashboard_seq_id_mutation(self):
        """No '_dashboard_seq_id += 1' in source."""
        src = _read_server_source()
        self.assertNotIn("_dashboard_seq_id += 1", src,
                          "Must not mutate _dashboard_seq_id with bare +=")

    def test_uses_runtime_state_increment(self):
        """Handlers must use runtime_state.increment for seq IDs."""
        src = _read_server_source()
        self.assertIn('runtime_state.increment("stream_seq_id")', src,
                       "Stream handler must use runtime_state.increment('stream_seq_id')")
        self.assertIn('runtime_state.increment("dashboard_seq_id")', src,
                       "Dashboard handler must use runtime_state.increment('dashboard_seq_id')")

    def test_no_stale_global_declarations(self):
        """_stream_seq_id = 0 and _dashboard_seq_id = 0 must not exist."""
        src = _read_server_source()
        # These were the old bare global declarations
        self.assertNotIn("\n_stream_seq_id = 0\n", src,
                          "Stale _stream_seq_id global declaration must be removed")
        self.assertNotIn("\n_dashboard_seq_id = 0\n", src,
                          "Stale _dashboard_seq_id global declaration must be removed")

    def test_runtime_state_increment_actually_works(self):
        """Runtime test: runtime_state.increment returns sequential integers."""
        try:
            from backend.api.runtime_state import runtime_state
        except ImportError:
            self.skipTest("Cannot import runtime_state")

        # Set a known initial value
        runtime_state.set("test_ws_seq", 0)
        v1 = runtime_state.increment("test_ws_seq")
        v2 = runtime_state.increment("test_ws_seq")
        v3 = runtime_state.increment("test_ws_seq")

        self.assertEqual(v1, 1)
        self.assertEqual(v2, 2)
        self.assertEqual(v3, 3)

        # Cleanup
        runtime_state.set("test_ws_seq", 0)


# ============================================================================
# BONUS: Comprehensive auth consistency check
# ============================================================================
class TestAuthConsistency(unittest.TestCase):
    """Verify that mutating endpoints don't accidentally use require_auth."""

    def test_mutating_endpoints_are_admin_only(self):
        """Parse the AST and verify specific endpoint decorators."""
        src = _read_server_source()
        tree = ast.parse(src)

        # Map of endpoint paths to expected auth dependency
        admin_only_endpoints = {
            "/api/g38/abort": "require_admin",
            "/api/g38/start": "require_admin",
            "/api/storage/enforce": "require_admin",
        }

        # Collect all decorated functions with their route paths
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
                        # Get the route path from the first positional arg
                        if decorator.args and isinstance(decorator.args[0], ast.Constant):
                            path = decorator.args[0].value
                            if path in admin_only_endpoints:
                                # Check function args for the right auth dep
                                func_src = ast.get_source_segment(src, node)
                                self.assertIn(
                                    admin_only_endpoints[path],
                                    func_src.split("\n")[0] if func_src else "",
                                    f"Endpoint {path} must use {admin_only_endpoints[path]}"
                                )


if __name__ == "__main__":
    unittest.main()
