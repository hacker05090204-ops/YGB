# G09: Device Trust
"""
Device access control and trust management.

RULES:
- Max 2-3 devices per account
- New device/IP = password required
- Random password sent to owner Gmail
- Block until verified
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional
import hashlib
import json
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta


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


@dataclass(frozen=True)
class TrustAuditEntry:
    timestamp: str
    device_id: str
    decision: str
    reason: str


MAX_DEVICES = 3
MAX_VERIFICATION_ATTEMPTS = 3
_DEVICE_TRUST_REGISTRY_ENV = "YGB_DEVICE_TRUST_REGISTRY_PATH"
_DEVICE_TRUST_CHALLENGE_ENV = "YGB_DEVICE_TRUST_CHALLENGE_PATH"

logger = logging.getLogger(__name__)


# Device registry
_device_registry: Dict[str, DeviceRegistration] = {}
_pending_challenges: Dict[str, VerificationChallenge] = {}


def _registry_path() -> Path:
    return Path(
        os.environ.get(
            _DEVICE_TRUST_REGISTRY_ENV,
            "secure_data/phase49/device_trust_registry.json",
        )
    )


def _challenge_path() -> Path:
    return Path(
        os.environ.get(
            _DEVICE_TRUST_CHALLENGE_ENV,
            "secure_data/phase49/device_trust_challenges.json",
        )
    )


def _atomic_write_json(path: Path, payload: Dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp_path, path)


def _device_to_dict(device: DeviceRegistration) -> Dict[str, object]:
    return {
        "device_id": device.device_id,
        "device_name": device.device_name,
        "fingerprint_hash": device.fingerprint_hash,
        "trust_level": device.trust_level.value,
        "ip_address": device.ip_address,
        "registered_at": device.registered_at,
        "last_seen": device.last_seen,
        "verified": device.verified,
    }


def _challenge_to_dict(challenge: VerificationChallenge) -> Dict[str, object]:
    return {
        "challenge_id": challenge.challenge_id,
        "device_id": challenge.device_id,
        "password_hash": challenge.password_hash,
        "expires_at": challenge.expires_at,
        "status": challenge.status.value,
        "attempts": challenge.attempts,
        "max_attempts": challenge.max_attempts,
    }


def _load_state() -> None:
    _device_registry.clear()
    _pending_challenges.clear()

    registry_path = _registry_path()
    if registry_path.exists():
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        for item in payload.get("devices", []):
            if not isinstance(item, dict):
                continue
            device = DeviceRegistration(
                device_id=str(item.get("device_id", "") or ""),
                device_name=str(item.get("device_name", "") or ""),
                fingerprint_hash=str(item.get("fingerprint_hash", "") or ""),
                trust_level=DeviceTrustLevel(str(item.get("trust_level", DeviceTrustLevel.PENDING.value))),
                ip_address=str(item.get("ip_address", "") or ""),
                registered_at=str(item.get("registered_at", "") or ""),
                last_seen=str(item.get("last_seen", "") or ""),
                verified=bool(item.get("verified", False)),
            )
            if device.device_id:
                _device_registry[device.device_id] = device

    challenge_path = _challenge_path()
    if challenge_path.exists():
        try:
            payload = json.loads(challenge_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        for item in payload.get("challenges", []):
            if not isinstance(item, dict):
                continue
            challenge = VerificationChallenge(
                challenge_id=str(item.get("challenge_id", "") or ""),
                device_id=str(item.get("device_id", "") or ""),
                password_hash=str(item.get("password_hash", "") or ""),
                expires_at=str(item.get("expires_at", "") or ""),
                status=VerificationStatus(str(item.get("status", VerificationStatus.PENDING.value))),
                attempts=int(item.get("attempts", 0)),
                max_attempts=int(item.get("max_attempts", MAX_VERIFICATION_ATTEMPTS)),
            )
            if challenge.challenge_id:
                _pending_challenges[challenge.challenge_id] = challenge


def _persist_state() -> None:
    _atomic_write_json(
        _registry_path(),
        {"devices": [_device_to_dict(device) for device in _device_registry.values()]},
    )
    _atomic_write_json(
        _challenge_path(),
        {"challenges": [_challenge_to_dict(challenge) for challenge in _pending_challenges.values()]},
    )


def _is_challenge_expired(challenge: VerificationChallenge) -> bool:
    try:
        expires_at = datetime.fromisoformat(challenge.expires_at.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return True
    return datetime.now(UTC) >= expires_at


_load_state()


class DeviceTrustGuard:
    """Runtime device-trust evaluator with immutable audit entries."""

    _MAX_AUDIT_LOG = 10000
    _ROTATE_TO = 5000

    def __init__(self):
        self._registrations = _device_registry
        self._audit_log: List[TrustAuditEntry] = []

    def _record_audit(self, device_id: str, decision: DeviceTrustLevel, reason: str) -> None:
        self._audit_log.append(
            TrustAuditEntry(
                timestamp=datetime.now(UTC).isoformat(),
                device_id=device_id,
                decision=decision.value,
                reason=reason,
            )
        )
        if len(self._audit_log) > self._MAX_AUDIT_LOG:
            self._audit_log = self._audit_log[-self._ROTATE_TO :]

    def evaluate(self, device_id: str, fingerprint_hash: str) -> DeviceTrustLevel:
        registration = self._registrations.get(device_id)
        if registration is None:
            self._record_audit(device_id, DeviceTrustLevel.UNTRUSTED, "device not registered")
            return DeviceTrustLevel.UNTRUSTED

        if registration.trust_level == DeviceTrustLevel.BLOCKED:
            self._record_audit(device_id, DeviceTrustLevel.BLOCKED, "device blocked")
            return DeviceTrustLevel.BLOCKED

        if registration.fingerprint_hash != fingerprint_hash:
            self.revoke(device_id, reason="fingerprint mismatch")
            return DeviceTrustLevel.BLOCKED

        self._record_audit(device_id, registration.trust_level, "fingerprint match")
        return registration.trust_level

    def revoke(self, device_id: str, reason: str = "manual") -> bool:
        registration = self._registrations.get(device_id)
        if registration is None:
            return False

        blocked = DeviceRegistration(
            device_id=registration.device_id,
            device_name=registration.device_name,
            fingerprint_hash=registration.fingerprint_hash,
            trust_level=DeviceTrustLevel.BLOCKED,
            ip_address=registration.ip_address,
            registered_at=registration.registered_at,
            last_seen=datetime.now(UTC).isoformat(),
            verified=False,
        )
        self._registrations[device_id] = blocked
        self._record_audit(device_id, DeviceTrustLevel.BLOCKED, reason)
        return True

    def get_audit_log(self, device_id: Optional[str] = None) -> List[TrustAuditEntry]:
        if device_id is None:
            return list(self._audit_log)
        return [entry for entry in self._audit_log if entry.device_id == device_id]


_trust_guard = DeviceTrustGuard()


def clear_registry():
    """Clear device registry (for testing)."""
    _device_registry.clear()
    _pending_challenges.clear()
    for path in (_registry_path(), _challenge_path()):
        try:
            path.unlink()
        except FileNotFoundError:
            continue
    if "_trust_guard" in globals():
        _trust_guard._audit_log.clear()


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
    if not str(device_name or "").strip():
        raise ValueError("device_name required")
    if not str(fingerprint or "").strip():
        raise ValueError("fingerprint required")
    if not str(ip_address or "").strip():
        raise ValueError("ip_address required")

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
            expires_at=(datetime.now(UTC) + timedelta(hours=24)).isoformat(),
            status=VerificationStatus.PENDING,
            attempts=0,
            max_attempts=MAX_VERIFICATION_ATTEMPTS,
        )
        
        _device_registry[device_id] = device
        _pending_challenges[challenge.challenge_id] = challenge
        try:
            from impl_v1.phase49.governors.g10_owner_alerts import AlertType, create_alert

            create_alert(
                alert_type=AlertType.DEVICE_LIMIT,
                title="Device verification required",
                message=(
                    f"Device '{device_name}' from IP {ip_address} requires owner verification "
                    f"before trust can be granted."
                ),
                device_id=device_id,
                ip_address=ip_address,
            )
        except Exception:
            _device_registry.pop(device_id, None)
            _pending_challenges.pop(challenge.challenge_id, None)
            logger.exception(
                "Failed to create owner alert for pending device verification %s",
                device_id,
            )
            raise
        _persist_state()
        
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
    _persist_state()
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

    if _is_challenge_expired(challenge):
        expired = VerificationChallenge(
            challenge_id=challenge.challenge_id,
            device_id=challenge.device_id,
            password_hash=challenge.password_hash,
            expires_at=challenge.expires_at,
            status=VerificationStatus.FAILED,
            attempts=challenge.attempts,
            max_attempts=challenge.max_attempts,
        )
        _pending_challenges[challenge_id] = expired
        _persist_state()
        return False, "Challenge expired"
    
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
        _persist_state()
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
    _trust_guard._record_audit(challenge.device_id, DeviceTrustLevel.TRUSTED, "device verified")
    _persist_state()
    
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
