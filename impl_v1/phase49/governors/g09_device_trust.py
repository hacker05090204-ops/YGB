# G09: Device Trust
"""
Device access control and trust management.

RULES:
- Max 2-3 devices per account
- New device/IP = password required
- Random password sent to owner Gmail
- Block until verified
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict
import uuid
import hashlib
import secrets
from datetime import datetime, UTC


class DeviceTrustLevel(Enum):
    """CLOSED ENUM - 4 trust levels"""
    TRUSTED = "TRUSTED"
    PENDING = "PENDING"
    UNTRUSTED = "UNTRUSTED"
    BLOCKED = "BLOCKED"


class VerificationStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class DeviceRegistration:
    """Device registration record."""
    device_id: str
    device_name: str
    fingerprint_hash: str
    trust_level: DeviceTrustLevel
    ip_address: str
    registered_at: str
    last_seen: str
    verified: bool


@dataclass(frozen=True)
class VerificationChallenge:
    """Verification challenge for new device."""
    challenge_id: str
    device_id: str
    password_hash: str  # Hashed password for verification
    expires_at: str
    status: VerificationStatus
    attempts: int
    max_attempts: int


MAX_DEVICES = 3
MAX_VERIFICATION_ATTEMPTS = 3


# Device registry (in-memory for governance testing)
_device_registry: Dict[str, DeviceRegistration] = {}
_pending_challenges: Dict[str, VerificationChallenge] = {}


def clear_registry():
    """Clear device registry (for testing)."""
    _device_registry.clear()
    _pending_challenges.clear()


def get_registered_devices() -> List[DeviceRegistration]:
    """Get all registered devices."""
    return list(_device_registry.values())


def get_trusted_count() -> int:
    """Count trusted devices."""
    return sum(1 for d in _device_registry.values() if d.trust_level == DeviceTrustLevel.TRUSTED)


def generate_verification_password() -> str:
    """Generate secure random password."""
    return secrets.token_urlsafe(16)


def hash_password(password: str) -> str:
    """Hash password for storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def register_device(
    device_name: str,
    fingerprint: str,
    ip_address: str,
) -> tuple:
    """
    Register a new device.
    
    Returns (DeviceRegistration, Optional[VerificationChallenge], Optional[password])
    """
    device_id = f"DEV-{uuid.uuid4().hex[:16].upper()}"
    fingerprint_hash = hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
    now = datetime.now(UTC).isoformat()
    
    # Check device limit
    if get_trusted_count() >= MAX_DEVICES:
        # New device needs verification
        password = generate_verification_password()
        
        device = DeviceRegistration(
            device_id=device_id,
            device_name=device_name,
            fingerprint_hash=fingerprint_hash,
            trust_level=DeviceTrustLevel.PENDING,
            ip_address=ip_address,
            registered_at=now,
            last_seen=now,
            verified=False,
        )
        
        challenge = VerificationChallenge(
            challenge_id=f"CHL-{uuid.uuid4().hex[:16].upper()}",
            device_id=device_id,
            password_hash=hash_password(password),
            expires_at="2026-02-01T00:00:00Z",  # Mock expiry
            status=VerificationStatus.PENDING,
            attempts=0,
            max_attempts=MAX_VERIFICATION_ATTEMPTS,
        )
        
        _device_registry[device_id] = device
        _pending_challenges[challenge.challenge_id] = challenge
        
        return device, challenge, password
    
    # First device or under limit - auto-trust
    device = DeviceRegistration(
        device_id=device_id,
        device_name=device_name,
        fingerprint_hash=fingerprint_hash,
        trust_level=DeviceTrustLevel.TRUSTED,
        ip_address=ip_address,
        registered_at=now,
        last_seen=now,
        verified=True,
    )
    
    _device_registry[device_id] = device
    return device, None, None


def verify_device(
    challenge_id: str,
    password: str,
) -> tuple:
    """
    Verify a device with password.
    
    Returns (success, reason)
    """
    if challenge_id not in _pending_challenges:
        return False, "Challenge not found"
    
    challenge = _pending_challenges[challenge_id]
    
    if challenge.status != VerificationStatus.PENDING:
        return False, f"Challenge status: {challenge.status.value}"
    
    if challenge.attempts >= challenge.max_attempts:
        return False, "Max attempts exceeded"
    
    # Check password
    if hash_password(password) != challenge.password_hash:
        # Update attempts
        updated = VerificationChallenge(
            challenge_id=challenge.challenge_id,
            device_id=challenge.device_id,
            password_hash=challenge.password_hash,
            expires_at=challenge.expires_at,
            status=VerificationStatus.PENDING if challenge.attempts + 1 < challenge.max_attempts else VerificationStatus.FAILED,
            attempts=challenge.attempts + 1,
            max_attempts=challenge.max_attempts,
        )
        _pending_challenges[challenge_id] = updated
        return False, "Invalid password"
    
    # Success - update device to trusted
    device = _device_registry.get(challenge.device_id)
    if device:
        trusted = DeviceRegistration(
            device_id=device.device_id,
            device_name=device.device_name,
            fingerprint_hash=device.fingerprint_hash,
            trust_level=DeviceTrustLevel.TRUSTED,
            ip_address=device.ip_address,
            registered_at=device.registered_at,
            last_seen=datetime.now(UTC).isoformat(),
            verified=True,
        )
        _device_registry[device.device_id] = trusted
    
    # Update challenge
    verified = VerificationChallenge(
        challenge_id=challenge.challenge_id,
        device_id=challenge.device_id,
        password_hash=challenge.password_hash,
        expires_at=challenge.expires_at,
        status=VerificationStatus.VERIFIED,
        attempts=challenge.attempts + 1,
        max_attempts=challenge.max_attempts,
    )
    _pending_challenges[challenge_id] = verified
    
    return True, "Device verified"


def is_device_trusted(device_id: str) -> tuple:
    """Check if device is trusted. Returns (trusted, reason)."""
    if device_id not in _device_registry:
        return False, "Device not registered"
    
    device = _device_registry[device_id]
    
    if device.trust_level == DeviceTrustLevel.TRUSTED:
        return True, "Device trusted"
    
    if device.trust_level == DeviceTrustLevel.BLOCKED:
        return False, "Device blocked"
    
    return False, f"Device status: {device.trust_level.value}"
