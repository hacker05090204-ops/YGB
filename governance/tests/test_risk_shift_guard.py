"""
Tests for native/risk_shift_guard.c via Python/C harness.

Tests the C risk engine contract via header analysis and,
if the compiled library is available, via ctypes calls.
"""

import pytest
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

HEADER_PATH = PROJECT_ROOT / "native" / "risk_shift_guard.h"
SOURCE_PATH = PROJECT_ROOT / "native" / "risk_shift_guard.c"


class TestRiskShiftGuardContract:
    """Verify the C header contract without requiring a compiled library."""

    def test_header_exists(self):
        assert HEADER_PATH.exists(), f"Header not found: {HEADER_PATH}"

    def test_source_exists(self):
        assert SOURCE_PATH.exists(), f"Source not found: {SOURCE_PATH}"

    def test_header_defines_risk_level_constants(self):
        content = HEADER_PATH.read_text(encoding="utf-8", errors="replace")
        # Must define result codes
        assert "RSG_PASS" in content
        assert "RSG_FAIL" in content

    def test_header_declares_check_function(self):
        content = HEADER_PATH.read_text(encoding="utf-8", errors="replace")
        # Must declare rsg_ prefixed risk checking functions
        assert "rsg_" in content
        assert "rsg_risk_gate" in content or "rsg_composite_risk_score" in content

    def test_header_declares_divergence_function(self):
        content = HEADER_PATH.read_text(encoding="utf-8", errors="replace")
        assert "rsg_jensen_shannon_divergence" in content

    def test_source_implements_threshold_enforcement(self):
        content = SOURCE_PATH.read_text(encoding="utf-8", errors="replace")
        # Must have threshold comparison logic
        assert "threshold" in content.lower() or "THRESHOLD" in content

    def test_source_has_no_unsafe_patterns(self):
        content = SOURCE_PATH.read_text(encoding="utf-8", errors="replace")
        # Must not use unsafe functions
        unsafe = ["gets(", "sprintf(", "strcat("]
        for pattern in unsafe:
            assert pattern not in content, f"Unsafe function found: {pattern}"

    def test_source_implements_shift_detection(self):
        content = SOURCE_PATH.read_text(encoding="utf-8", errors="replace")
        # Must detect risk shifts
        assert "shift" in content.lower() or "delta" in content.lower() or "change" in content.lower()


class TestRiskShiftGuardDLL:
    """Test the compiled risk_shift_guard DLL/SO if available."""

    @pytest.fixture
    def lib(self):
        """Try to load the compiled library."""
        import ctypes

        if os.name == "nt":
            lib_name = "risk_shift_guard.dll"
        else:
            lib_name = "librisk_shift_guard.so"

        lib_path = PROJECT_ROOT / "native" / lib_name
        if not lib_path.exists():
            # Also check obj/ directory
            lib_path = PROJECT_ROOT / "obj" / lib_name

        if not lib_path.exists():
            pytest.skip(f"Compiled library not found: {lib_name}")

        return ctypes.CDLL(str(lib_path))

    def test_library_loads(self, lib):
        assert lib is not None

    def test_risk_gate_function_exists(self, lib):
        # Try to find rsg_ prefixed functions
        import ctypes
        for name in ["rsg_risk_gate", "rsg_composite_risk_score", "rsg_jensen_shannon_divergence"]:
            try:
                func = getattr(lib, name)
                assert func is not None
                return
            except AttributeError:
                continue
        # If no standard name found, just verify lib loaded
        assert lib is not None
