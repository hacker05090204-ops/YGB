"""
Dependency Change Monitor - Phase 50
=====================================

Monitor runtime environment changes:
- Kernel version
- CUDA version
- Compiler version
- OpenSSL version
- glibc version

Compare to baseline and trigger validation.
"""

import platform
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, Tuple, Optional
from pathlib import Path
from datetime import datetime
import json


# =============================================================================
# CONFIGURATION
# =============================================================================

BASELINE_FILE = Path(__file__).parent.parent / "ENVIRONMENT_BASELINE.json"


# =============================================================================
# ENVIRONMENT DETECTION
# =============================================================================

@dataclass
class EnvironmentSnapshot:
    """Snapshot of runtime environment."""
    kernel_version: str
    cuda_version: Optional[str]
    compiler_version: str
    openssl_version: str
    glibc_version: Optional[str]
    python_version: str
    timestamp: str


def get_kernel_version() -> str:
    """Get kernel version."""
    return platform.release()


def get_cuda_version() -> Optional[str]:
    """Get CUDA version if available."""
    try:
        # Try nvidia-smi first
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    
    # Try CUDA_VERSION env
    return os.environ.get("CUDA_VERSION")


def get_compiler_version() -> str:
    """Get compiler version."""
    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["cl"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            # Parse MSVC version from output
            return "MSVC (detected)"
        except Exception:
            return "Unknown"
    else:
        try:
            result = subprocess.run(
                ["gcc", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.split("\n")[0]
        except Exception:
            pass
    
    return "Unknown"


def get_openssl_version() -> str:
    """Get OpenSSL version."""
    try:
        import ssl
        return ssl.OPENSSL_VERSION
    except Exception:
        return "Unknown"


def get_glibc_version() -> Optional[str]:
    """Get glibc version (Linux only)."""
    if platform.system() != "Linux":
        return None
    
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
        gnu_get_libc_version = libc.gnu_get_libc_version
        gnu_get_libc_version.restype = ctypes.c_char_p
        return gnu_get_libc_version().decode("utf-8")
    except Exception:
        return None


def take_environment_snapshot() -> EnvironmentSnapshot:
    """Take current environment snapshot."""
    return EnvironmentSnapshot(
        kernel_version=get_kernel_version(),
        cuda_version=get_cuda_version(),
        compiler_version=get_compiler_version(),
        openssl_version=get_openssl_version(),
        glibc_version=get_glibc_version(),
        python_version=platform.python_version(),
        timestamp=datetime.now().isoformat(),
    )


# =============================================================================
# BASELINE MANAGEMENT
# =============================================================================

def save_environment_baseline(snapshot: EnvironmentSnapshot) -> None:
    """Save environment baseline."""
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(BASELINE_FILE, "w") as f:
        json.dump({
            "kernel_version": snapshot.kernel_version,
            "cuda_version": snapshot.cuda_version,
            "compiler_version": snapshot.compiler_version,
            "openssl_version": snapshot.openssl_version,
            "glibc_version": snapshot.glibc_version,
            "python_version": snapshot.python_version,
            "timestamp": snapshot.timestamp,
        }, f, indent=2)


def load_environment_baseline() -> Optional[EnvironmentSnapshot]:
    """Load environment baseline."""
    if not BASELINE_FILE.exists():
        return None
    
    try:
        with open(BASELINE_FILE, "r") as f:
            data = json.load(f)
        return EnvironmentSnapshot(**data)
    except Exception:
        return None


# =============================================================================
# CHANGE DETECTION
# =============================================================================

@dataclass
class EnvironmentChange:
    """Detected environment change."""
    component: str
    baseline_value: str
    current_value: str
    severity: str  # "warn", "critical"


def compare_environments(
    baseline: EnvironmentSnapshot,
    current: EnvironmentSnapshot,
) -> Tuple[bool, list]:
    """
    Compare environments for changes.
    
    Returns:
        Tuple of (match, changes)
    """
    changes = []
    
    # Compare each component
    if baseline.kernel_version != current.kernel_version:
        changes.append(EnvironmentChange(
            component="kernel",
            baseline_value=baseline.kernel_version,
            current_value=current.kernel_version,
            severity="warn",
        ))
    
    if baseline.cuda_version != current.cuda_version:
        changes.append(EnvironmentChange(
            component="cuda",
            baseline_value=baseline.cuda_version or "N/A",
            current_value=current.cuda_version or "N/A",
            severity="critical",
        ))
    
    if baseline.openssl_version != current.openssl_version:
        changes.append(EnvironmentChange(
            component="openssl",
            baseline_value=baseline.openssl_version,
            current_value=current.openssl_version,
            severity="critical",
        ))
    
    if baseline.python_version != current.python_version:
        changes.append(EnvironmentChange(
            component="python",
            baseline_value=baseline.python_version,
            current_value=current.python_version,
            severity="warn",
        ))
    
    match = len(changes) == 0
    return match, changes


def check_environment_on_startup() -> Tuple[bool, list]:
    """
    Check environment on startup.
    
    Returns:
        Tuple of (safe_to_auto_mode, changes)
    """
    current = take_environment_snapshot()
    baseline = load_environment_baseline()
    
    if baseline is None:
        # No baseline - create one
        save_environment_baseline(current)
        return True, []
    
    match, changes = compare_environments(baseline, current)
    
    # Abort auto_mode if critical changes
    safe = not any(c.severity == "critical" for c in changes)
    
    return safe, changes
