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
from datetime import datetime, timezone
import json
from typing import Tuple, Optional
import hashlib
import platform
import sys

try:
    import torch
except Exception:  # pragma: no cover - import failure is environment dependent
    torch = None


@dataclass(frozen=True)
class EnvironmentFingerprint:
    """Immutable environment fingerprint."""
    fingerprint_id: Optional[str]
    os_type: Optional[str]
    arch: Optional[str]
    python_version: Optional[str]
    gpu_available: Optional[bool]
    computed_at: Optional[str]
    hash_sha256: Optional[str]


class FingerprintCollector:
    """Collect real environment fingerprint data without fabrication."""

    def collect(self) -> EnvironmentFingerprint:
        os_type = _collect_value(platform.system)
        arch = _collect_value(platform.machine)
        python_version = _collect_value(lambda: sys.version)
        gpu_available = _collect_value(_read_gpu_available)
        computed_at = _collect_value(lambda: datetime.now(timezone.utc).isoformat())

        hash_sha256 = _compute_hash(
            os_type=os_type,
            arch=arch,
            python_version=python_version,
            gpu_available=gpu_available,
        )
        fingerprint_id = hash_sha256[:16] if hash_sha256 is not None else None

        return EnvironmentFingerprint(
            fingerprint_id=fingerprint_id,
            os_type=os_type,
            arch=arch,
            python_version=python_version,
            gpu_available=gpu_available,
            computed_at=computed_at,
            hash_sha256=hash_sha256,
        )


class FingerprintStore:
    """In-memory fingerprint history capped to the latest 10 entries."""

    def __init__(self) -> None:
        self._fingerprints = []

    def add(self, fingerprint: EnvironmentFingerprint) -> None:
        self._fingerprints.append(fingerprint)
        if len(self._fingerprints) > 10:
            self._fingerprints = self._fingerprints[-10:]

    @property
    def fingerprints(self) -> Tuple[EnvironmentFingerprint, ...]:
        return tuple(self._fingerprints)

    def latest(self) -> Optional[EnvironmentFingerprint]:
        if not self._fingerprints:
            return None
        return self._fingerprints[-1]


# =============================================================================
# FINGERPRINT CAPTURE
# =============================================================================

def _collect_value(getter):
    """Safely collect a real environment value without fabricating fallbacks."""
    try:
        return getter()
    except Exception:
        return None


def _read_gpu_available() -> bool:
    """Return the real CUDA availability from torch."""
    if torch is None or not hasattr(torch, "cuda") or not hasattr(torch.cuda, "is_available"):
        raise RuntimeError("torch.cuda.is_available unavailable")
    return bool(torch.cuda.is_available())


def _serialize_hash_payload(
    os_type: Optional[str],
    arch: Optional[str],
    python_version: Optional[str],
    gpu_available: Optional[bool],
) -> str:
    """Serialize stable environment values deterministically for hashing."""
    return json.dumps(
        {
            "arch": arch,
            "gpu_available": gpu_available,
            "os_type": os_type,
            "python_version": python_version,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _compute_hash(
    os_type: Optional[str],
    arch: Optional[str],
    python_version: Optional[str],
    gpu_available: Optional[bool],
) -> Optional[str]:
    """Generate SHA-256 hash for the stable fingerprint values."""
    serialized = _collect_value(
        lambda: _serialize_hash_payload(
            os_type=os_type,
            arch=arch,
            python_version=python_version,
            gpu_available=gpu_available,
        )
    )
    if serialized is None:
        return None
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def capture_environment_fingerprint() -> EnvironmentFingerprint:
    """Capture current environment fingerprint."""
    return FingerprintCollector().collect()


def compare_fingerprints(
    baseline: EnvironmentFingerprint,
    current: EnvironmentFingerprint,
) -> Tuple[bool, Tuple[str, ...]]:
    """
    Compare two fingerprints.
    
    Returns (matches, mismatches).
    """
    mismatches = []
    
    if baseline.os_type != current.os_type:
        mismatches.append(f"os_type: {baseline.os_type} → {current.os_type}")
    if baseline.arch != current.arch:
        mismatches.append(f"arch: {baseline.arch} → {current.arch}")
    if baseline.python_version != current.python_version:
        mismatches.append(f"python_version: {baseline.python_version} → {current.python_version}")
    if baseline.gpu_available != current.gpu_available:
        mismatches.append(
            f"gpu_available: {baseline.gpu_available} → {current.gpu_available}"
        )
    
    return len(mismatches) == 0, tuple(mismatches)


def detect_drift(
    current: EnvironmentFingerprint,
    previous: Optional[EnvironmentFingerprint],
) -> bool:
    """Return True when trusted environment identity fields have changed."""
    if previous is None:
        return False

    return any(
        getattr(current, field_name) != getattr(previous, field_name)
        for field_name in ("os_type", "arch", "python_version")
    )


def should_enter_safe_mode(drift_detected: bool) -> bool:
    """Check if safe mode should be activated."""
    return drift_detected


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
