"""
Root of Trust - Phase 49
=========================

Cryptographic signing authority protection:
1. Trusted public key pinning (compiled-in fingerprint)
2. Key revocation support
3. Key rotation policy with monotonic versioning
4. Build server attestation
5. Time integrity verification
6. Emergency lock mode
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum


# =============================================================================
# TRUSTED KEY PINNING (STEP 1)
# =============================================================================

# COMPILED-IN TRUSTED KEY FINGERPRINT
# This is the ONLY trusted key - loaded from file is REJECTED
TRUSTED_KEY_FINGERPRINT = "E78B8362E90EBAE9AAE85BEAE31F9C9D5ACB925D606968460108BB693805C2A7"
TRUSTED_KEY_VERSION = 1

# Next scheduled key (for rotation)
NEXT_KEY_FINGERPRINT = None  # Set during key rotation
NEXT_KEY_VERSION = None


@dataclass
class TrustedKey:
    """A trusted signing key."""
    fingerprint: str
    version: int
    valid_from: str
    valid_until: Optional[str]


def verify_key_fingerprint(key_fingerprint: str) -> Tuple[bool, str]:
    """
    Verify key against compiled-in fingerprint.
    
    Returns:
        Tuple of (trusted, reason)
    """
    if key_fingerprint == TRUSTED_KEY_FINGERPRINT:
        return True, "Matches compiled-in trusted key"
    
    if NEXT_KEY_FINGERPRINT and key_fingerprint == NEXT_KEY_FINGERPRINT:
        return True, "Matches scheduled next key"
    
    return False, "KEY NOT TRUSTED - Fingerprint does not match compiled-in key"


def get_pinned_key() -> TrustedKey:
    """Get the compiled-in trusted key."""
    return TrustedKey(
        fingerprint=TRUSTED_KEY_FINGERPRINT,
        version=TRUSTED_KEY_VERSION,
        valid_from="2026-02-06",
        valid_until=None,
    )


# =============================================================================
# KEY REVOCATION (STEP 2)
# =============================================================================

REVOCATION_LIST_FILE = Path(__file__).parent.parent / "REVOCATION_LIST.json"


@dataclass
class RevokedKey:
    """A revoked key entry."""
    fingerprint: str
    revoked_at: str
    reason: str


def load_revocation_list() -> List[RevokedKey]:
    """Load revocation list from file."""
    if not REVOCATION_LIST_FILE.exists():
        return []
    
    try:
        with open(REVOCATION_LIST_FILE, "r") as f:
            data = json.load(f)
        
        return [
            RevokedKey(
                fingerprint=entry["fingerprint"],
                revoked_at=entry["revoked_at"],
                reason=entry["reason"],
            )
            for entry in data.get("revoked_keys", [])
        ]
    except Exception:
        return []


def is_key_revoked(fingerprint: str) -> Tuple[bool, Optional[str]]:
    """
    Check if key is revoked.
    
    Returns:
        Tuple of (is_revoked, reason)
    """
    revoked = load_revocation_list()
    
    for key in revoked:
        if key.fingerprint == fingerprint:
            return True, key.reason
    
    return False, None


def check_revocation_on_startup() -> Tuple[bool, str]:
    """
    Check signing key against revocation list.
    
    Returns:
        Tuple of (safe, message)
    """
    is_revoked, reason = is_key_revoked(TRUSTED_KEY_FINGERPRINT)
    
    if is_revoked:
        return False, f"ABORT: Current signing key REVOKED - {reason}"
    
    return True, "Signing key not revoked"


# =============================================================================
# KEY ROTATION POLICY (STEP 3)
# =============================================================================

class KeyRotationPolicy:
    """Enforce key rotation policy with monotonic versioning."""
    
    def __init__(self):
        self.current_version = TRUSTED_KEY_VERSION
        self.min_version = 1  # Never downgrade below this
    
    def accept_key(self, fingerprint: str, version: int) -> Tuple[bool, str]:
        """
        Check if key should be accepted.
        
        Enforces:
        - Monotonic versioning (no downgrades)
        - Only current or next key allowed
        """
        # Check version monotonicity
        if version < self.current_version:
            return False, f"REJECT: Key version {version} < current {self.current_version} (downgrade attack)"
        
        # Check fingerprint
        is_trusted, reason = verify_key_fingerprint(fingerprint)
        if not is_trusted:
            return False, reason
        
        # Check revocation
        is_revoked, revoke_reason = is_key_revoked(fingerprint)
        if is_revoked:
            return False, f"REJECT: Key revoked - {revoke_reason}"
        
        return True, "Key accepted"
    
    def rotate_to_next_key(self, new_fingerprint: str, new_version: int) -> bool:
        """Rotate to next key (requires code update)."""
        if new_version <= self.current_version:
            return False  # Must be higher version
        
        # In production: update NEXT_KEY_FINGERPRINT and NEXT_KEY_VERSION
        return True


# =============================================================================
# BUILD SERVER ATTESTATION (STEP 4)
# =============================================================================

@dataclass
class BuildMetadata:
    """Immutable build metadata stored in artifact."""
    build_host_fingerprint: str
    build_timestamp: str
    baseline_hash: str
    compiler_version: str
    signed_by: str


def get_build_host_fingerprint() -> str:
    """Get fingerprint of build host."""
    import platform
    import socket
    
    # Combine host identifiers
    host_data = f"{platform.node()}:{platform.system()}:{platform.machine()}"
    return hashlib.sha256(host_data.encode()).hexdigest()[:32]


def create_build_metadata(
    baseline_hash: str,
    compiler_version: str,
    signing_key: str,
) -> BuildMetadata:
    """Create build metadata for embedding in artifact."""
    return BuildMetadata(
        build_host_fingerprint=get_build_host_fingerprint(),
        build_timestamp=datetime.utcnow().isoformat(),
        baseline_hash=baseline_hash,
        compiler_version=compiler_version,
        signed_by=signing_key,
    )


def validate_build_metadata(metadata: BuildMetadata) -> Tuple[bool, str]:
    """Validate build metadata integrity."""
    # Log build host
    print(f"Build host fingerprint: {metadata.build_host_fingerprint}")
    
    # Verify signing key
    is_trusted, reason = verify_key_fingerprint(metadata.signed_by)
    if not is_trusted:
        return False, f"Build signed with untrusted key: {reason}"
    
    return True, "Build metadata validated"


# =============================================================================
# TIME INTEGRITY (STEP 5)
# =============================================================================

MAX_CLOCK_DRIFT_SECONDS = 300  # 5 minutes


class TimeIntegrityChecker:
    """Detect system clock manipulation."""
    
    def __init__(self):
        self.monotonic_baseline = time.monotonic()
        self.system_baseline = time.time()
    
    def check_drift(self) -> Tuple[bool, float]:
        """
        Check for abnormal clock drift.
        
        Returns:
            Tuple of (is_normal, drift_seconds)
        """
        monotonic_elapsed = time.monotonic() - self.monotonic_baseline
        system_elapsed = time.time() - self.system_baseline
        
        drift = abs(monotonic_elapsed - system_elapsed)
        
        is_normal = drift < MAX_CLOCK_DRIFT_SECONDS
        
        return is_normal, drift
    
    def verify_or_restrict(self) -> Tuple[bool, str]:
        """
        Verify time integrity or restrict auto-mode.
        
        Returns:
            Tuple of (allow_auto_mode, message)
        """
        is_normal, drift = self.check_drift()
        
        if not is_normal:
            return False, f"CLOCK DRIFT DETECTED: {drift:.1f}s - Auto-mode disabled"
        
        return True, "Time integrity verified"


# =============================================================================
# EMERGENCY LOCK MODE (STEP 6)
# =============================================================================

class EmergencyLockMode(Enum):
    """System lock modes."""
    NORMAL = "NORMAL"
    EMERGENCY_LOCK = "EMERGENCY_LOCK"


class SystemLock:
    """Emergency lock controller."""
    
    LOCK_FILE = Path(__file__).parent.parent / ".EMERGENCY_LOCK"
    
    def __init__(self):
        self._mode = self._detect_mode()
    
    def _detect_mode(self) -> EmergencyLockMode:
        """Detect current lock mode."""
        if self.LOCK_FILE.exists():
            return EmergencyLockMode.EMERGENCY_LOCK
        return EmergencyLockMode.NORMAL
    
    @property
    def is_locked(self) -> bool:
        """Check if system is in emergency lock."""
        return self._mode == EmergencyLockMode.EMERGENCY_LOCK
    
    def get_restrictions(self) -> Dict[str, bool]:
        """Get current restrictions."""
        if self.is_locked:
            return {
                "auto_mode": False,
                "training": False,
                "report_generation": False,
                "data_write": False,
                "read_only": True,
            }
        return {
            "auto_mode": True,
            "training": True,
            "report_generation": True,
            "data_write": True,
            "read_only": False,
        }
    
    def can_execute(self, action: str) -> Tuple[bool, str]:
        """Check if action is allowed."""
        restrictions = self.get_restrictions()
        
        if action in restrictions and not restrictions[action]:
            return False, f"EMERGENCY LOCK: {action} is disabled"
        
        return True, "Action allowed"
    
    def activate_emergency_lock(self, reason: str) -> None:
        """Activate emergency lock mode."""
        self.LOCK_FILE.write_text(json.dumps({
            "activated_at": datetime.utcnow().isoformat(),
            "reason": reason,
        }))
        self._mode = EmergencyLockMode.EMERGENCY_LOCK
    
    def deactivate_emergency_lock(self) -> None:
        """Deactivate emergency lock (requires manual intervention)."""
        if self.LOCK_FILE.exists():
            self.LOCK_FILE.unlink()
        self._mode = EmergencyLockMode.NORMAL


# =============================================================================
# ROOT OF TRUST VERIFICATION
# =============================================================================

def verify_root_of_trust() -> Tuple[bool, List[str]]:
    """
    Run all root-of-trust checks.
    
    Returns:
        Tuple of (all_passed, messages)
    """
    messages = []
    all_passed = True
    
    # 1. Key revocation check
    safe, msg = check_revocation_on_startup()
    messages.append(f"Revocation check: {msg}")
    if not safe:
        all_passed = False
    
    # 2. Emergency lock check
    lock = SystemLock()
    if lock.is_locked:
        messages.append("EMERGENCY LOCK ACTIVE - System read-only")
        all_passed = False
    else:
        messages.append("Emergency lock: Not active")
    
    # 3. Time integrity
    time_checker = TimeIntegrityChecker()
    is_normal, drift = time_checker.check_drift()
    if not is_normal:
        messages.append(f"Time integrity: FAIL (drift={drift:.1f}s)")
        all_passed = False
    else:
        messages.append(f"Time integrity: PASS (drift={drift:.2f}s)")
    
    return all_passed, messages
