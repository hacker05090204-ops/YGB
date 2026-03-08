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

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, List, Optional
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import random
import uuid
from datetime import datetime, UTC


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


DEFAULT_PRIVACY = PrivacyConfig(
    geo_masking=True,
    timing_jitter=True,
    metadata_masking=True,
    report_rotation=True,
    jitter_min_ms=500,
    jitter_max_ms=3000,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_LICENSE_PATHS = (
    _PROJECT_ROOT / "config" / "licenses.json",
    _PROJECT_ROOT / "config" / "license_registry.json",
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _validation_result(
    license_key: str,
    status: LicenseStatus,
    device: Optional[DeviceFingerprint],
    reason: str,
    *,
    license_type: Optional[LicenseType] = None,
    expires_at: Optional[str] = None,
    execution_allowed: bool = False,
) -> LicenseValidation:
    return LicenseValidation(
        validation_id=f"VAL-{uuid.uuid4().hex[:16].upper()}",
        license_key=license_key,
        status=status,
        license_type=license_type,
        device_fingerprint=device,
        expires_at=expires_at,
        execution_allowed=execution_allowed,
        reason=reason,
        timestamp=_now_iso(),
    )


def _normalize_license_type(raw: object) -> Optional[LicenseType]:
    if raw is None:
        return None
    try:
        return LicenseType[str(raw).strip().upper()]
    except KeyError:
        return None


def _normalize_license_status(raw: object) -> LicenseStatus:
    if raw is None:
        return LicenseStatus.VALID
    try:
        return LicenseStatus[str(raw).strip().upper()]
    except KeyError:
        return LicenseStatus.INVALID


def _parse_timestamp(value: object) -> Optional[datetime]:
    if value in (None, ""):
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        return None


def _get_license_secret() -> Optional[str]:
    for env_name in ("YGB_LICENSE_SECRET", "YGB_HMAC_SECRET"):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value
    return None


def _canonicalize_record(record: dict) -> bytes:
    payload = {
        key: value
        for key, value in record.items()
        if key not in {"signature", "hmac"}
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _record_signature_valid(record: dict) -> bool:
    signature = str(record.get("signature") or record.get("hmac") or "").strip()
    if not signature:
        return True

    secret = _get_license_secret()
    if not secret:
        return False

    expected = hmac.new(
        secret.encode("utf-8"),
        _canonicalize_record(record),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature.lower(), expected.lower())


def _iter_registry_records(valid_keys: Optional[List[str]]) -> Iterable[dict]:
    for key in valid_keys or []:
        yield {
            "license_key": key,
            "status": LicenseStatus.VALID.value,
            "license_type": LicenseType.STANDARD.value,
            "reason": "License present in authoritative in-memory registry",
        }

    inline_json = os.environ.get("YGB_LICENSE_REGISTRY_JSON", "").strip()
    if inline_json:
        try:
            payload = json.loads(inline_json)
        except json.JSONDecodeError:
            payload = []
        for record in _normalize_registry_payload(payload):
            yield record

    explicit_path = os.environ.get("YGB_LICENSE_REGISTRY_PATH", "").strip()
    candidate_paths = []
    if explicit_path:
        candidate_paths.append(Path(explicit_path))
    candidate_paths.extend(_DEFAULT_LICENSE_PATHS)

    seen = set()
    for path in candidate_paths:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for record in _normalize_registry_payload(payload):
            yield record


def _normalize_registry_payload(payload: object) -> List[dict]:
    if isinstance(payload, dict):
        licenses = payload.get("licenses", [])
    else:
        licenses = payload
    if not isinstance(licenses, list):
        return []
    return [entry for entry in licenses if isinstance(entry, dict)]


def _device_binding_valid(record: dict, device: DeviceFingerprint) -> bool:
    bound_values = []

    fingerprint_value = record.get("device_fingerprint")
    if fingerprint_value:
        bound_values.append(str(fingerprint_value))

    machine_value = record.get("machine_id")
    if machine_value:
        machine_text = str(machine_value)
        if len(machine_text) == 32:
            bound_values.append(machine_text)
        else:
            bound_values.append(hashlib.sha256(machine_text.encode("utf-8")).hexdigest()[:32])

    for entry in record.get("device_fingerprints", []) or []:
        if isinstance(entry, str):
            bound_values.append(entry)

    for entry in record.get("machine_ids", []) or []:
        if isinstance(entry, str):
            if len(entry) == 32:
                bound_values.append(entry)
            else:
                bound_values.append(hashlib.sha256(entry.encode("utf-8")).hexdigest()[:32])

    if not bound_values:
        return True

    return device.machine_id in bound_values or device.fingerprint_id in bound_values


def _validate_registry_record(
    license_key: str,
    device: DeviceFingerprint,
    record: dict,
) -> LicenseValidation:
    if not _record_signature_valid(record):
        return _validation_result(
            license_key,
            LicenseStatus.INVALID,
            device,
            "License record signature verification failed",
        )

    status = _normalize_license_status(record.get("status"))
    license_type = _normalize_license_type(record.get("license_type"))
    expires_at = record.get("expires_at")
    expires_dt = _parse_timestamp(expires_at)
    reason = str(record.get("reason") or "License evaluated from configured registry")

    if status == LicenseStatus.REVOKED:
        return _validation_result(
            license_key,
            LicenseStatus.REVOKED,
            device,
            "License revoked by registry",
            license_type=license_type,
            expires_at=str(expires_at) if expires_at else None,
        )

    if status == LicenseStatus.PENDING:
        return _validation_result(
            license_key,
            LicenseStatus.PENDING,
            device,
            "License pending activation",
            license_type=license_type,
            expires_at=str(expires_at) if expires_at else None,
        )

    if expires_dt is not None and expires_dt <= datetime.now(UTC):
        return _validation_result(
            license_key,
            LicenseStatus.EXPIRED,
            device,
            "License expired",
            license_type=license_type,
            expires_at=str(expires_at),
        )

    if not _device_binding_valid(record, device):
        return _validation_result(
            license_key,
            LicenseStatus.INVALID,
            device,
            "License is not bound to this device fingerprint",
            license_type=license_type,
            expires_at=str(expires_at) if expires_at else None,
        )

    if status != LicenseStatus.VALID:
        return _validation_result(
            license_key,
            LicenseStatus.INVALID,
            device,
            f"Unsupported license status: {status.value}",
            license_type=license_type,
            expires_at=str(expires_at) if expires_at else None,
        )

    execution_allowed = bool(record.get("execution_allowed", True))
    final_reason = reason if execution_allowed else "License explicitly disables execution"
    return _validation_result(
        license_key,
        LicenseStatus.VALID if execution_allowed else LicenseStatus.INVALID,
        device,
        final_reason,
        license_type=license_type or LicenseType.STANDARD,
        expires_at=str(expires_at) if expires_at else None,
        execution_allowed=execution_allowed,
    )


def _urlsafe_b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _validate_signed_license(
    license_key: str,
    device: DeviceFingerprint,
) -> Optional[LicenseValidation]:
    if not license_key.startswith("YGB1."):
        return None

    parts = license_key.split(".", 2)
    if len(parts) != 3:
        return _validation_result(
            license_key,
            LicenseStatus.INVALID,
            device,
            "Signed license format is invalid",
        )

    _, payload_b64, signature = parts
    secret = _get_license_secret()
    if not secret:
        return _validation_result(
            license_key,
            LicenseStatus.INVALID,
            device,
            "Signed license provided but no validation secret is configured",
        )

    expected = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature.lower(), expected.lower()):
        return _validation_result(
            license_key,
            LicenseStatus.INVALID,
            device,
            "Signed license HMAC verification failed",
        )

    try:
        payload = json.loads(_urlsafe_b64decode(payload_b64).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return _validation_result(
            license_key,
            LicenseStatus.INVALID,
            device,
            "Signed license payload is unreadable",
        )

    if not isinstance(payload, dict):
        return _validation_result(
            license_key,
            LicenseStatus.INVALID,
            device,
            "Signed license payload is invalid",
        )

    record = dict(payload)
    record.setdefault("license_key", license_key)
    record.setdefault("reason", "License validated from signed token")
    return _validate_registry_record(license_key, device, record)


def create_device_fingerprint(
    os_type: str,
    os_version: str,
    machine_id: str,
) -> DeviceFingerprint:
    """Create device fingerprint."""

    raw = f"{os_type}|{os_version}|{machine_id}"
    hashed = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return DeviceFingerprint(
        fingerprint_id=f"DEV-{uuid.uuid4().hex[:16].upper()}",
        os_type=os_type,
        os_version=os_version,
        machine_id=hashed,
        created_at=_now_iso(),
    )


def validate_license(
    license_key: str,
    device: DeviceFingerprint,
    valid_keys: Optional[List[str]] = None,
) -> LicenseValidation:
    """
    Validate a license key against configured real activation data.

    Supported real sources:
    - Signed offline license tokens (YGB1.<payload>.<hmac>)
    - JSON license registry from env or config file
    - Caller-supplied authoritative registry entries via valid_keys
    """

    normalized_key = (license_key or "").strip()
    if len(normalized_key) < 16:
        return _validation_result(
            normalized_key,
            LicenseStatus.INVALID,
            device,
            "Invalid license key format",
        )

    signed_result = _validate_signed_license(normalized_key, device)
    if signed_result is not None:
        return signed_result

    for record in _iter_registry_records(valid_keys):
        if str(record.get("license_key", "")).strip() != normalized_key:
            continue
        return _validate_registry_record(normalized_key, device, record)

    return _validation_result(
        normalized_key,
        LicenseStatus.INVALID,
        device,
        "License key not recognized by configured registry",
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
    sensitive_keys = ["ip", "ip_address", "location", "geo", "device_id"]
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
