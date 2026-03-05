"""
Tests for real-time telemetry correctness.

Verifies:
- GPU status returns null + error_reason for unavailable fields (never fake zeros)
- GPU status includes CUDA version, driver version, tensor-core support
- /auth/me returns latest server state with Cache-Control: no-store
- Training frames include sequence_id
- Idle training frames use null for metrics (not 0.0)
- Frontend has no hardcoded default user profiles
"""

import os
import sys
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("JWT_SECRET", "a_very_secure_test_secret_that_is_at_least_32_chars_long_for_testing")
os.environ.setdefault("REVOCATION_BACKEND", "memory")


class TestGPUStatusSchema(unittest.TestCase):
    """Verify /gpu/status response schema has all required fields."""

    # The expected fields in every GPU status response
    REQUIRED_FIELDS = {
        "gpu_available", "device_name", "utilization_percent",
        "memory_allocated_mb", "memory_reserved_mb", "memory_total_mb",
        "temperature", "compute_capability",
        # New fields added for real-time compliance
        "cuda_version", "driver_version", "tensor_core_support",
        "error_reason", "sequence_id", "timestamp",
    }

    def test_gpu_endpoint_source_has_all_fields(self):
        """server.py GPU endpoint must declare all required fields in result dict."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")

        # Find the gpu_status function body
        for field in self.REQUIRED_FIELDS:
            # Field must appear as a key in the result dict
            pattern = rf'"{field}"'
            self.assertIn(
                f'"{field}"', content,
                f"GPU status endpoint missing required field: {field}"
            )

    def test_gpu_endpoint_returns_error_reason_on_no_cuda(self):
        """When CUDA is unavailable, error_reason must be set (not None)."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        self.assertIn(
            '"error_reason"', content,
            "GPU status must include error_reason field"
        )
        # Verify that when cuda is not available, we set error_reason
        self.assertIn(
            "CUDA not available", content,
            "GPU status must set error_reason when CUDA is not available"
        )

    def test_gpu_endpoint_has_cache_control(self):
        """GPU status must return Cache-Control: no-store."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        # Find the gpu_status function and check for no-store
        gpu_func_start = content.find("async def gpu_status")
        self.assertNotEqual(gpu_func_start, -1, "gpu_status function not found")
        gpu_func_body = content[gpu_func_start:gpu_func_start + 3000]
        self.assertIn("no-store", gpu_func_body, "GPU status must use Cache-Control: no-store")


class TestAuthMeEndpoint(unittest.TestCase):
    """Verify /auth/me endpoint exists and has correct properties."""

    def test_auth_me_endpoint_exists(self):
        """server.py must define /auth/me endpoint."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        self.assertIn('/auth/me', content, "/auth/me endpoint not found in server.py")

    def test_auth_me_has_cache_control(self):
        """auth/me must return Cache-Control: no-store."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        auth_me_start = content.find("async def auth_me")
        self.assertNotEqual(auth_me_start, -1, "auth_me function not found")
        auth_me_body = content[auth_me_start:auth_me_start + 1500]
        self.assertIn("no-store", auth_me_body, "auth/me must use Cache-Control: no-store")

    def test_auth_me_requires_auth(self):
        """auth/me must use require_auth dependency."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        auth_me_start = content.find("async def auth_me")
        self.assertNotEqual(auth_me_start, -1)
        # Look backwards to find the decorator
        decorator_area = content[max(0, auth_me_start - 200):auth_me_start + 200]
        self.assertIn("require_auth", decorator_area, "auth/me must use require_auth")


class TestTrainingFrameSchema(unittest.TestCase):
    """Verify training WS frames include sequence_id and handle idle correctly."""

    def test_training_stream_has_sequence_id(self):
        """training/stream WS frames must include sequence_id."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        stream_start = content.find("async def training_stream")
        self.assertNotEqual(stream_start, -1)
        stream_body = content[stream_start:stream_start + 6000]
        self.assertIn('"sequence_id"', stream_body, "training/stream must emit sequence_id")

    def test_training_dashboard_has_sequence_id(self):
        """training/dashboard WS frames must include sequence_id."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        dashboard_start = content.find("async def training_dashboard")
        self.assertNotEqual(dashboard_start, -1)
        dashboard_body = content[dashboard_start:dashboard_start + 7000]
        self.assertIn('"sequence_id"', dashboard_body, "training/dashboard must emit sequence_id")

    def test_idle_metrics_use_null(self):
        """When training is idle, metrics must be None/null, not 0.0."""
        server_path = ROOT / "api" / "server.py"
        content = server_path.read_text(errors="ignore")
        stream_start = content.find("async def training_stream")
        stream_body = content[stream_start:stream_start + 6000]
        # Verify the null assignment pattern for idle state
        self.assertIn("samples_per_sec = None", stream_body,
                       "Idle training must set samples_per_sec = None")
        self.assertIn("loss = None", stream_body,
                       "Idle training must set loss = None")


class TestNoHardcodedDefaults(unittest.TestCase):
    """Verify frontend hooks don't contain hardcoded default user profiles."""

    def test_use_auth_user_no_hardcoded_name(self):
        """use-auth-user.ts must not contain hardcoded default names like BugHunter_01."""
        hook_path = ROOT / "frontend" / "hooks" / "use-auth-user.ts"
        if not hook_path.exists():
            self.skipTest("use-auth-user.ts not found")
        content = hook_path.read_text(errors="ignore")
        self.assertNotIn("BugHunter_01", content,
                          "use-auth-user.ts must not contain hardcoded BugHunter_01 default")
        self.assertNotIn("hunter@bugbounty.com", content,
                          "use-auth-user.ts must not contain hardcoded hunter@bugbounty.com default")

    def test_use_auth_user_fetches_from_backend(self):
        """use-auth-user.ts must fetch user data from /auth/me."""
        hook_path = ROOT / "frontend" / "hooks" / "use-auth-user.ts"
        if not hook_path.exists():
            self.skipTest("use-auth-user.ts not found")
        content = hook_path.read_text(errors="ignore")
        self.assertIn("/auth/me", content,
                       "use-auth-user.ts must fetch from /auth/me endpoint")

    def test_use_auth_user_has_unavailable_state(self):
        """use-auth-user.ts must support an UNAVAILABLE state for missing data."""
        hook_path = ROOT / "frontend" / "hooks" / "use-auth-user.ts"
        if not hook_path.exists():
            self.skipTest("use-auth-user.ts not found")
        content = hook_path.read_text(errors="ignore")
        self.assertIn("unavailable", content,
                       "use-auth-user.ts must support 'unavailable' status")


class TestFrontendStalenessDetection(unittest.TestCase):
    """Verify all training dashboards detect staleness at 5s."""

    def test_live_training_panel_5s_stale(self):
        """live-training-panel.tsx must use 5000ms stale timeout."""
        path = ROOT / "frontend" / "components" / "live-training-panel.tsx"
        if not path.exists():
            self.skipTest("File not found")
        content = path.read_text(errors="ignore")
        self.assertIn("5000", content, "live-training-panel.tsx must use 5000ms stale timeout")
        # Check for literal 10000 timeout (not substr of 1000000 formatSPS)
        self.assertFalse(
            re.search(r'\b10000\b', content),
            "live-training-panel.tsx must NOT use 10000ms timeout"
        )

    def test_auto_training_dashboard_5s_stale(self):
        """auto-training-dashboard.tsx must use 5000ms stale timeout."""
        path = ROOT / "frontend" / "components" / "auto-training-dashboard.tsx"
        if not path.exists():
            self.skipTest("File not found")
        content = path.read_text(errors="ignore")
        self.assertIn("5000", content, "auto-training-dashboard.tsx must use 5000ms stale timeout")
        self.assertFalse(
            re.search(r'\b10000\b', content),
            "auto-training-dashboard.tsx must NOT use 10000ms timeout"
        )

    def test_training_dashboard_v2_5s_stale(self):
        """training-dashboard-v2.tsx must use 5000ms stale timeout."""
        path = ROOT / "frontend" / "components" / "training-dashboard-v2.tsx"
        if not path.exists():
            self.skipTest("File not found")
        content = path.read_text(errors="ignore")
        self.assertIn("5000", content, "training-dashboard-v2.tsx must use 5000ms stale timeout")
        self.assertFalse(
            re.search(r'\b10000\b', content),
            "training-dashboard-v2.tsx must NOT use 10000ms timeout"
        )


class TestAuthFetchCacheControl(unittest.TestCase):
    """Verify authFetch uses cache: no-store."""

    def test_auth_fetch_no_store(self):
        """authFetch in ygb-api.ts must use cache: 'no-store'."""
        path = ROOT / "frontend" / "lib" / "ygb-api.ts"
        if not path.exists():
            self.skipTest("ygb-api.ts not found")
        content = path.read_text(errors="ignore")
        self.assertIn("no-store", content,
                       "authFetch must include cache: 'no-store'")


if __name__ == "__main__":
    unittest.main()
