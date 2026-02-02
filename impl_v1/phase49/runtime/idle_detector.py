# G38 Runtime - Idle Detector
"""
REAL OS IDLE DETECTION FOR G38 AUTO-TRAINING.

PURPOSE:
Get REAL system idle time from the operating system.
NO mock values in production. Mocks allowed ONLY in tests.

SUPPORTED PLATFORMS:
- Linux: /proc/uptime + X11 idle or loginctl
- Windows: GetLastInputInfo via ctypes

USAGE:
    idle_seconds = get_idle_seconds()
    if idle_seconds >= 60:
        # Trigger training
"""

import platform
import subprocess
import time
from typing import Tuple, Optional
from pathlib import Path


# =============================================================================
# PLATFORM DETECTION
# =============================================================================

def _get_platform() -> str:
    """Get current platform name."""
    return platform.system().lower()


def _is_linux() -> bool:
    """Check if running on Linux."""
    return _get_platform() == "linux"


def _is_windows() -> bool:
    """Check if running on Windows."""
    return _get_platform() == "windows"


# =============================================================================
# LINUX IDLE DETECTION
# =============================================================================

def _get_linux_idle_xprintidle() -> Optional[int]:
    """
    Get idle time using xprintidle (X11).
    
    Returns idle time in seconds, or None if not available.
    """
    try:
        result = subprocess.run(
            ["xprintidle"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            # xprintidle returns milliseconds
            idle_ms = int(result.stdout.strip())
            return idle_ms // 1000
    except (subprocess.SubprocessError, ValueError, FileNotFoundError):
        pass
    return None


def _get_linux_idle_loginctl() -> Optional[int]:
    """
    Get idle time using loginctl (systemd).
    
    Returns idle time in seconds, or None if not available.
    """
    try:
        # Get current session
        result = subprocess.run(
            ["loginctl", "show-session", "--property=IdleHint,IdleSinceHint", "--value"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if len(lines) >= 2 and lines[0].lower() == "yes":
                # IdleSinceHint is in microseconds since epoch
                idle_since_us = int(lines[1])
                if idle_since_us > 0:
                    now_us = int(time.time() * 1_000_000)
                    idle_seconds = (now_us - idle_since_us) // 1_000_000
                    return max(0, idle_seconds)
    except (subprocess.SubprocessError, ValueError, FileNotFoundError, IndexError):
        pass
    return None


def _get_linux_idle_proc() -> Optional[int]:
    """
    Fallback: estimate idle from /proc/stat or keyboard/mouse device timestamps.
    
    This is a rough approximation using input device timestamps.
    """
    try:
        # Check input device modification times
        input_dir = Path("/dev/input")
        if input_dir.exists():
            latest_mtime = 0
            for device in input_dir.iterdir():
                if device.name.startswith(("event", "mouse", "kbd")):
                    try:
                        mtime = device.stat().st_mtime
                        if mtime > latest_mtime:
                            latest_mtime = mtime
                    except (OSError, PermissionError):
                        continue
            
            if latest_mtime > 0:
                idle_seconds = int(time.time() - latest_mtime)
                return max(0, idle_seconds)
    except (OSError, PermissionError):
        pass
    return None


def get_linux_idle_seconds() -> int:
    """
    Get idle time on Linux using best available method.
    
    Priority:
    1. xprintidle (X11)
    2. loginctl (systemd)
    3. /dev/input timestamps (fallback)
    4. Return 0 if all methods fail
    """
    # Try xprintidle first (most accurate for X11)
    idle = _get_linux_idle_xprintidle()
    if idle is not None:
        return idle
    
    # Try loginctl (systemd sessions)
    idle = _get_linux_idle_loginctl()
    if idle is not None:
        return idle
    
    # Fallback to /dev/input timestamps
    idle = _get_linux_idle_proc()
    if idle is not None:
        return idle
    
    # Cannot determine idle - return 0 (safe default, won't trigger training)
    return 0


# =============================================================================
# WINDOWS IDLE DETECTION
# =============================================================================

def get_windows_idle_seconds() -> int:
    """
    Get idle time on Windows using GetLastInputInfo.
    
    Uses ctypes to call Win32 API directly.
    """
    try:
        import ctypes
        from ctypes import Structure, c_uint, byref, sizeof
        
        class LASTINPUTINFO(Structure):
            _fields_ = [
                ("cbSize", c_uint),
                ("dwTime", c_uint),
            ]
        
        lii = LASTINPUTINFO()
        lii.cbSize = sizeof(LASTINPUTINFO)
        
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        if user32.GetLastInputInfo(byref(lii)):
            current_tick = kernel32.GetTickCount()
            idle_ms = current_tick - lii.dwTime
            # Handle tick count overflow (every ~49 days)
            if idle_ms < 0:
                idle_ms += 0xFFFFFFFF + 1
            return idle_ms // 1000
    except (ImportError, AttributeError, OSError):
        pass
    
    # Cannot determine idle - return 0 (safe default)
    return 0


# =============================================================================
# CROSS-PLATFORM API
# =============================================================================

def get_idle_seconds() -> int:
    """
    Get REAL system idle time in seconds.
    
    This is the main API function. Returns actual OS idle time.
    
    Returns:
        int: Seconds since last user input.
             Returns 0 if idle time cannot be determined (safe default).
    
    Platform Support:
        - Linux: xprintidle → loginctl → /dev/input
        - Windows: GetLastInputInfo (Win32 API)
    """
    if _is_linux():
        return get_linux_idle_seconds()
    elif _is_windows():
        return get_windows_idle_seconds()
    else:
        # Unsupported platform - return 0 (safe default, no training)
        return 0


def get_idle_info() -> Tuple[int, str]:
    """
    Get idle time with platform info.
    
    Returns:
        Tuple[int, str]: (idle_seconds, platform_method)
    """
    idle = get_idle_seconds()
    
    if _is_linux():
        method = "linux"
    elif _is_windows():
        method = "windows"
    else:
        method = "unsupported"
    
    return idle, method


# =============================================================================
# POWER STATUS
# =============================================================================

def is_power_connected() -> bool:
    """
    Check if system is on AC power.
    
    Training should only occur when plugged in.
    """
    if _is_linux():
        try:
            # Check /sys/class/power_supply
            power_dir = Path("/sys/class/power_supply")
            if power_dir.exists():
                for supply in power_dir.iterdir():
                    online_file = supply / "online"
                    if online_file.exists():
                        content = online_file.read_text().strip()
                        if content == "1":
                            return True
                    # Check type for AC adapter
                    type_file = supply / "type"
                    if type_file.exists():
                        supply_type = type_file.read_text().strip().lower()
                        if supply_type in ("mains", "ac"):
                            return True
            # Default to True on desktop systems (no battery)
            return True
        except (OSError, PermissionError):
            return True
    
    elif _is_windows():
        try:
            import ctypes
            from ctypes import Structure, c_byte, byref
            
            class SYSTEM_POWER_STATUS(Structure):
                _fields_ = [
                    ("ACLineStatus", c_byte),
                    ("BatteryFlag", c_byte),
                    ("BatteryLifePercent", c_byte),
                    ("SystemStatusFlag", c_byte),
                    ("BatteryLifeTime", ctypes.c_ulong),
                    ("BatteryFullLifeTime", ctypes.c_ulong),
                ]
            
            status = SYSTEM_POWER_STATUS()
            kernel32 = ctypes.windll.kernel32
            
            if kernel32.GetSystemPowerStatus(byref(status)):
                # ACLineStatus: 0=Offline, 1=Online, 255=Unknown
                return status.ACLineStatus == 1
        except (ImportError, AttributeError, OSError):
            pass
        return True
    
    # Default to True for unknown platforms
    return True


# =============================================================================
# SCAN STATUS (placeholder - to be integrated)
# =============================================================================

_scan_active = False


def is_scan_active() -> bool:
    """Check if a scan is currently active."""
    global _scan_active
    return _scan_active


def set_scan_active(active: bool) -> None:
    """Set scan active state (called by scanner)."""
    global _scan_active
    _scan_active = active
