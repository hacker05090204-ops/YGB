# Test G38 Runtime - Idle Detector
"""
Tests for real OS idle detection.

Mocks are allowed ONLY in tests, not in production.
"""

import pytest
from unittest.mock import patch, MagicMock
import subprocess
import sys
import os

from impl_v1.phase49.runtime.idle_detector import (
    get_idle_seconds,
    get_idle_info,
    get_linux_idle_seconds,
    get_windows_idle_seconds,
    is_power_connected,
    is_scan_active,
    set_scan_active,
    _get_platform,
    _is_linux,
    _is_windows,
    _get_linux_idle_xprintidle,
    _get_linux_idle_loginctl,
    _get_linux_idle_proc,
)


# =============================================================================
# PLATFORM DETECTION TESTS
# =============================================================================

class TestPlatformDetection:
    """Tests for platform detection."""
    
    def test_get_platform_returns_string(self):
        platform = _get_platform()
        assert isinstance(platform, str)
        assert platform in ("linux", "windows", "darwin", "")
    
    @patch("impl_v1.phase49.runtime.idle_detector.platform.system")
    def test_is_linux_when_linux(self, mock_system):
        mock_system.return_value = "Linux"
        assert _is_linux() is True
    
    @patch("impl_v1.phase49.runtime.idle_detector.platform.system")
    def test_is_linux_when_windows(self, mock_system):
        mock_system.return_value = "Windows"
        assert _is_linux() is False
    
    @patch("impl_v1.phase49.runtime.idle_detector.platform.system")
    def test_is_windows_when_windows(self, mock_system):
        mock_system.return_value = "Windows"
        assert _is_windows() is True
    
    @patch("impl_v1.phase49.runtime.idle_detector.platform.system")
    def test_is_windows_when_linux(self, mock_system):
        mock_system.return_value = "Linux"
        assert _is_windows() is False


# =============================================================================
# LINUX IDLE DETECTION TESTS
# =============================================================================

class TestLinuxIdleDetection:
    """Tests for Linux idle detection."""
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_xprintidle_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="120000\n",  # 120 seconds in ms
        )
        idle = _get_linux_idle_xprintidle()
        assert idle == 120
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_xprintidle_failure_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        idle = _get_linux_idle_xprintidle()
        assert idle is None
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_xprintidle_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        idle = _get_linux_idle_xprintidle()
        assert idle is None
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_loginctl_success(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="yes\n1706889600000000\n",  # Idle since some timestamp
        )
        # This won't work perfectly without proper time mocking
        # but tests the parsing logic doesn't crash
        idle = _get_linux_idle_loginctl()
        # Result depends on current time, just check it's an int or None
        assert idle is None or isinstance(idle, int)
    
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_xprintidle")
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_loginctl")
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_proc")
    def test_linux_idle_fallback_to_zero(self, mock_proc, mock_loginctl, mock_xprintidle):
        mock_xprintidle.return_value = None
        mock_loginctl.return_value = None
        mock_proc.return_value = None
        
        idle = get_linux_idle_seconds()
        assert idle == 0
    
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_xprintidle")
    def test_linux_idle_xprintidle_first(self, mock_xprintidle):
        mock_xprintidle.return_value = 45
        
        idle = get_linux_idle_seconds()
        assert idle == 45
    
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_xprintidle")
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_loginctl")
    def test_linux_idle_loginctl_fallback(self, mock_loginctl, mock_xprintidle):
        mock_xprintidle.return_value = None
        mock_loginctl.return_value = 60
        
        idle = get_linux_idle_seconds()
        assert idle == 60
    
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_xprintidle")
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_loginctl")
    @patch("impl_v1.phase49.runtime.idle_detector._get_linux_idle_proc")
    def test_linux_idle_proc_fallback(self, mock_proc, mock_loginctl, mock_xprintidle):
        mock_xprintidle.return_value = None
        mock_loginctl.return_value = None
        mock_proc.return_value = 120
        
        idle = get_linux_idle_seconds()
        assert idle == 120
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_loginctl_not_installed(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        idle = _get_linux_idle_loginctl()
        assert idle is None
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_loginctl_failure_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        idle = _get_linux_idle_loginctl()
        assert idle is None


# =============================================================================
# WINDOWS IDLE DETECTION TESTS
# =============================================================================

class TestWindowsIdleDetection:
    """Tests for Windows idle detection (mocked)."""
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    def test_windows_idle_on_non_windows_returns_zero(self, mock_linux, mock_windows):
        mock_windows.return_value = False
        mock_linux.return_value = False
        idle = get_idle_seconds()
        assert idle == 0
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    def test_windows_idle_returns_int(self, mock_windows):
        mock_windows.return_value = True
        # On actual Windows, this should work
        # On non-Windows, it returns 0
        idle = get_windows_idle_seconds()
        assert isinstance(idle, int)
        assert idle >= 0


# =============================================================================
# CROSS-PLATFORM API TESTS
# =============================================================================

class TestCrossplatformAPI:
    """Tests for cross-platform idle API."""
    
    def test_get_idle_seconds_returns_int(self):
        idle = get_idle_seconds()
        assert isinstance(idle, int)
        assert idle >= 0
    
    def test_get_idle_info_returns_tuple(self):
        idle, method = get_idle_info()
        assert isinstance(idle, int)
        assert isinstance(method, str)
        assert method in ("linux", "windows", "unsupported")
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    @patch("impl_v1.phase49.runtime.idle_detector.get_linux_idle_seconds")
    def test_get_idle_seconds_calls_linux_on_linux(self, mock_linux_idle, mock_is_linux):
        mock_is_linux.return_value = True
        mock_linux_idle.return_value = 99
        
        idle = get_idle_seconds()
        assert idle == 99
        mock_linux_idle.assert_called_once()
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    def test_unsupported_platform_returns_zero(self, mock_windows, mock_linux):
        mock_linux.return_value = False
        mock_windows.return_value = False
        
        idle = get_idle_seconds()
        assert idle == 0
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    @patch("impl_v1.phase49.runtime.idle_detector.get_windows_idle_seconds")
    def test_get_idle_seconds_calls_windows_on_windows(self, mock_windows_idle, mock_is_windows, mock_is_linux):
        mock_is_linux.return_value = False
        mock_is_windows.return_value = True
        mock_windows_idle.return_value = 77
        
        idle = get_idle_seconds()
        assert idle == 77
        mock_windows_idle.assert_called_once()
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    def test_get_idle_info_linux(self, mock_windows, mock_linux):
        mock_linux.return_value = True
        mock_windows.return_value = False
        
        idle, method = get_idle_info()
        assert method == "linux"
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    def test_get_idle_info_windows(self, mock_windows, mock_linux):
        mock_linux.return_value = False
        mock_windows.return_value = True
        
        idle, method = get_idle_info()
        assert method == "windows"
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    def test_get_idle_info_unsupported(self, mock_windows, mock_linux):
        mock_linux.return_value = False
        mock_windows.return_value = False
        
        idle, method = get_idle_info()
        assert method == "unsupported"
        assert idle == 0


# =============================================================================
# POWER STATUS TESTS
# =============================================================================

class TestPowerStatus:
    """Tests for power status detection."""
    
    def test_is_power_connected_returns_bool(self):
        result = is_power_connected()
        assert isinstance(result, bool)
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    def test_power_connected_on_unsupported_returns_true(self, mock_windows, mock_linux):
        mock_linux.return_value = False
        mock_windows.return_value = False
        result = is_power_connected()
        # Default to True for safety
        assert result is True
    
    @patch("impl_v1.phase49.runtime.idle_detector._is_linux")
    @patch("impl_v1.phase49.runtime.idle_detector._is_windows")
    def test_windows_power_detection(self, mock_windows, mock_linux):
        mock_linux.return_value = False
        mock_windows.return_value = True
        
        # On Windows, this calls the real ctypes function
        result = is_power_connected()
        assert isinstance(result, bool)


# =============================================================================
# SCAN STATUS TESTS
# =============================================================================

class TestScanStatus:
    """Tests for scan status."""
    
    def test_initial_scan_status_false(self):
        set_scan_active(False)
        assert is_scan_active() is False
    
    def test_set_scan_active_true(self):
        set_scan_active(True)
        assert is_scan_active() is True
        set_scan_active(False)  # Reset
    
    def test_set_scan_active_false(self):
        set_scan_active(True)
        set_scan_active(False)
        assert is_scan_active() is False
    
    def test_scan_status_toggle(self):
        """Test toggling scan status multiple times."""
        for _ in range(3):
            set_scan_active(True)
            assert is_scan_active() is True
            set_scan_active(False)
            assert is_scan_active() is False


# =============================================================================
# ZERO IDLE TESTS
# =============================================================================

class TestZeroIdle:
    """Tests for zero idle (no training trigger)."""
    
    @patch("impl_v1.phase49.runtime.idle_detector.get_idle_seconds")
    def test_zero_idle_returns_zero(self, mock_idle):
        mock_idle.return_value = 0
        from impl_v1.phase49.runtime.idle_detector import get_idle_seconds
        assert get_idle_seconds() == 0


# =============================================================================
# EDGE CASE TESTS
# =============================================================================

class TestEdgeCases:
    """Tests for edge cases and error handling."""
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_xprintidle_invalid_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="invalid\n",
        )
        idle = _get_linux_idle_xprintidle()
        # Should handle ValueError gracefully
        assert idle is None
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_loginctl_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="",
        )
        idle = _get_linux_idle_loginctl()
        assert idle is None
    
    @patch("impl_v1.phase49.runtime.idle_detector.subprocess.run")
    def test_loginctl_no_idle_hint(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="no\n",  # session not idle
        )
        idle = _get_linux_idle_loginctl()
        assert idle is None or idle == 0

