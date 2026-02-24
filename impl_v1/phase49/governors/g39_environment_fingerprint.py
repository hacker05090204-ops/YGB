# G39: Environment Fingerprint Governor
"""
ENVIRONMENT FINGERPRINT GOVERNOR.

PURPOSE:
Eliminate environment drift risk by capturing and validating
immutable system fingerprints.

RULES:
- Capture baseline on first trusted run
- Any mismatch → AUTO SAFE MODE
- Disable auto-mode until human review
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional
import hashlib
import platform
import sys
import os


class SafeMode(Enum):
    """CLOSED ENUM - Safe mode states."""
    NORMAL = "NORMAL"              # Full operation
    SAFE = "SAFE"                  # Restricted operation
    LOCKDOWN = "LOCKDOWN"          # Manual only


class DriftStatus(Enum):
    """CLOSED ENUM - Environment drift status."""
    TRUSTED = "TRUSTED"            # Matches baseline
    DRIFTED = "DRIFTED"            # Changed from baseline
    UNKNOWN = "UNKNOWN"            # No baseline


@dataclass(frozen=True)
class EnvironmentFingerprint:
    """Immutable environment fingerprint."""
    fingerprint_id: str
    os_name: str
    os_version: str
    kernel_version: str
    python_version: str
    python_hash: str
    platform_machine: str
    libc_version: str
    gpu_info: str
    browser_version: str
    fingerprint_hash: str


@dataclass(frozen=True)
class DriftReport:
    """Environment drift report."""
    report_id: str
    status: DriftStatus
    baseline: Optional[EnvironmentFingerprint]
    current: EnvironmentFingerprint
    mismatches: Tuple[str, ...]
    recommended_mode: SafeMode


# =============================================================================
# FINGERPRINT CAPTURE
# =============================================================================

def _hash_content(content: str) -> str:
    """Generate hash."""
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def capture_environment_fingerprint() -> EnvironmentFingerprint:
    """Capture current environment fingerprint."""
    os_name = platform.system()
    os_version = platform.release()
    kernel = platform.version()
    py_version = platform.python_version()
    py_hash = _hash_content(sys.executable)
    machine = platform.machine()
    
    # libc version
    try:
        libc = platform.libc_ver()[1] or "unknown"
    except Exception:
        libc = "unknown"
    
    # GPU info (from C++ bridge or env override)
    gpu_info = os.environ.get("GPU_INFO", "undetected")
    
    # Browser version (from browser module or env override)
    browser = os.environ.get("BROWSER_VERSION", "undetected")
    
    # Combine for hash
    combined = f"{os_name}|{os_version}|{kernel}|{py_version}|{machine}|{libc}|{gpu_info}|{browser}"
    
    return EnvironmentFingerprint(
        fingerprint_id=_hash_content(combined)[:16].upper(),
        os_name=os_name,
        os_version=os_version,
        kernel_version=kernel,
        python_version=py_version,
        python_hash=py_hash,
        platform_machine=machine,
        libc_version=libc,
        gpu_info=gpu_info,
        browser_version=browser,
        fingerprint_hash=_hash_content(combined),
    )


def compare_fingerprints(
    baseline: EnvironmentFingerprint,
    current: EnvironmentFingerprint,
) -> Tuple[bool, Tuple[str, ...]]:
    """
    Compare two fingerprints.
    
    Returns (matches, mismatches).
    """
    mismatches = []
    
    if baseline.os_name != current.os_name:
        mismatches.append(f"os_name: {baseline.os_name} → {current.os_name}")
    if baseline.os_version != current.os_version:
        mismatches.append(f"os_version: {baseline.os_version} → {current.os_version}")
    if baseline.kernel_version != current.kernel_version:
        mismatches.append(f"kernel: {baseline.kernel_version} → {current.kernel_version}")
    if baseline.python_version != current.python_version:
        mismatches.append(f"python: {baseline.python_version} → {current.python_version}")
    if baseline.platform_machine != current.platform_machine:
        mismatches.append(f"machine: {baseline.platform_machine} → {current.platform_machine}")
    
    return len(mismatches) == 0, tuple(mismatches)


def detect_drift(
    baseline: Optional[EnvironmentFingerprint],
    current: EnvironmentFingerprint,
) -> DriftReport:
    """Detect environment drift and recommend safe mode."""
    import uuid
    
    if baseline is None:
        return DriftReport(
            report_id=uuid.uuid4().hex[:16].upper(),
            status=DriftStatus.UNKNOWN,
            baseline=None,
            current=current,
            mismatches=tuple(),
            recommended_mode=SafeMode.SAFE,
        )
    
    matches, mismatches = compare_fingerprints(baseline, current)
    
    if matches:
        return DriftReport(
            report_id=uuid.uuid4().hex[:16].upper(),
            status=DriftStatus.TRUSTED,
            baseline=baseline,
            current=current,
            mismatches=tuple(),
            recommended_mode=SafeMode.NORMAL,
        )
    
    return DriftReport(
        report_id=uuid.uuid4().hex[:16].upper(),
        status=DriftStatus.DRIFTED,
        baseline=baseline,
        current=current,
        mismatches=mismatches,
        recommended_mode=SafeMode.SAFE,
    )


def should_enter_safe_mode(drift: DriftReport) -> bool:
    """Check if safe mode should be activated."""
    return drift.status != DriftStatus.TRUSTED


# =============================================================================
# GUARDS (ALL RETURN FALSE)
# =============================================================================

def can_ignore_environment_drift() -> Tuple[bool, str]:
    """
    Check if environment drift can be ignored.
    
    ALWAYS returns (False, ...).
    """
    return False, "Environment drift cannot be ignored - triggers SAFE MODE"


def can_override_safe_mode() -> Tuple[bool, str]:
    """
    Check if safe mode can be overridden.
    
    ALWAYS returns (False, ...).
    """
    return False, "SAFE MODE cannot be overridden programmatically"


def can_train_on_untrusted_env() -> Tuple[bool, str]:
    """
    Check if training can run on untrusted environment.
    
    ALWAYS returns (False, ...).
    """
    return False, "Training requires trusted environment baseline"
