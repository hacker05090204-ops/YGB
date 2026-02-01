# G08: Licensing & Privacy
"""
License validation, device fingerprinting, and privacy protection.

LICENSING:
- Mandatory activation
- Device + OS fingerprint
- Invalid license = BLOCK execution

PRIVACY:
- Geo masking
- Metadata randomization
- Timing jitter
- Report format rotation
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List
import uuid
import hashlib
from datetime import datetime, UTC
import random


class LicenseStatus(Enum):
    """CLOSED ENUM - 5 statuses"""
    VALID = "VALID"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    INVALID = "INVALID"
    PENDING = "PENDING"


class LicenseType(Enum):
    """CLOSED ENUM - 3 types"""
    TRIAL = "TRIAL"
    STANDARD = "STANDARD"
    PROFESSIONAL = "PROFESSIONAL"


@dataclass(frozen=True)
class DeviceFingerprint:
    """Device identification."""
    fingerprint_id: str
    os_type: str
    os_version: str
    machine_id: str
    created_at: str


@dataclass(frozen=True)
class LicenseValidation:
    """License validation result."""
    validation_id: str
    license_key: str
    status: LicenseStatus
    license_type: Optional[LicenseType]
    device_fingerprint: Optional[DeviceFingerprint]
    expires_at: Optional[str]
    execution_allowed: bool
    reason: str
    timestamp: str


@dataclass(frozen=True)
class PrivacyConfig:
    """Privacy protection configuration."""
    geo_masking: bool
    timing_jitter: bool
    metadata_masking: bool
    report_rotation: bool
    jitter_min_ms: int
    jitter_max_ms: int


# Default privacy config
DEFAULT_PRIVACY = PrivacyConfig(
    geo_masking=True,
    timing_jitter=True,
    metadata_masking=True,
    report_rotation=True,
    jitter_min_ms=500,
    jitter_max_ms=3000,
)


def create_device_fingerprint(
    os_type: str,
    os_version: str,
    machine_id: str,
) -> DeviceFingerprint:
    """Create device fingerprint."""
    # Hash the machine ID for privacy
    hashed = hashlib.sha256(machine_id.encode()).hexdigest()[:32]
    
    return DeviceFingerprint(
        fingerprint_id=f"DEV-{uuid.uuid4().hex[:16].upper()}",
        os_type=os_type,
        os_version=os_version,
        machine_id=hashed,
        created_at=datetime.now(UTC).isoformat(),
    )


def validate_license(
    license_key: str,
    device: DeviceFingerprint,
    valid_keys: Optional[List[str]] = None,
) -> LicenseValidation:
    """
    Validate a license key.
    
    NOTE: This is a mock implementation for governance testing.
    Real implementation would call license server.
    """
    timestamp = datetime.now(UTC).isoformat()
    
    # Basic format check
    if not license_key or len(license_key) < 16:
        return LicenseValidation(
            validation_id=f"VAL-{uuid.uuid4().hex[:16].upper()}",
            license_key=license_key,
            status=LicenseStatus.INVALID,
            license_type=None,
            device_fingerprint=device,
            expires_at=None,
            execution_allowed=False,
            reason="Invalid license key format",
            timestamp=timestamp,
        )
    
    # Check against known valid keys (mock)
    if valid_keys and license_key in valid_keys:
        return LicenseValidation(
            validation_id=f"VAL-{uuid.uuid4().hex[:16].upper()}",
            license_key=license_key,
            status=LicenseStatus.VALID,
            license_type=LicenseType.STANDARD,
            device_fingerprint=device,
            expires_at="2027-01-01T00:00:00Z",
            execution_allowed=True,
            reason="License valid",
            timestamp=timestamp,
        )
    
    # Default to invalid for unknown keys
    return LicenseValidation(
        validation_id=f"VAL-{uuid.uuid4().hex[:16].upper()}",
        license_key=license_key,
        status=LicenseStatus.INVALID,
        license_type=None,
        device_fingerprint=device,
        expires_at=None,
        execution_allowed=False,
        reason="License key not recognized",
        timestamp=timestamp,
    )


def apply_timing_jitter(config: PrivacyConfig) -> int:
    """Apply timing jitter and return delay in ms."""
    if not config.timing_jitter:
        return 0
    
    return random.randint(config.jitter_min_ms, config.jitter_max_ms)


def mask_metadata(data: dict, config: PrivacyConfig) -> dict:
    """Apply metadata masking."""
    if not config.metadata_masking:
        return data
    
    masked = dict(data)
    
    # Mask sensitive fields
    sensitive_keys = ['ip', 'ip_address', 'location', 'geo', 'device_id']
    for key in sensitive_keys:
        if key in masked:
            masked[key] = "[MASKED]"
    
    return masked


def is_execution_allowed(validation: LicenseValidation) -> tuple:
    """Check if execution is allowed based on license. Returns (allowed, reason)."""
    if validation.status != LicenseStatus.VALID:
        return False, f"License status: {validation.status.value}"
    
    if not validation.execution_allowed:
        return False, validation.reason
    
    return True, "Execution allowed"
