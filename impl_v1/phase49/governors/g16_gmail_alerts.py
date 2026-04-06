# G16: Gmail Owner Alerts
"""Infrastructure-gated Gmail alert governance contract."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Protocol, runtime_checkable
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from .g10_owner_alerts import OwnerAlert


logger = logging.getLogger(__name__)

GMAIL_PROVISIONING_MESSAGE = (
    "GmailAlerter requires Gmail OAuth credentials. "
    "Set GMAIL_CREDENTIALS_PATH to a valid credentials.json file."
)


class RealBackendNotConfiguredError(RuntimeError):
    pass


class EmailStatus(Enum):
    """Legacy enum export retained for compatibility."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"


class VerificationStatus(Enum):
    """Verification status for password workflow."""

    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class GmailAlertConfig:
    """Real Gmail alert delivery configuration."""

    owner_email: str
    credentials_path: Optional[str] = None


@dataclass(frozen=True)
class VerificationPassword:
    """Time-limited verification password."""

    password_id: str
    password_hash: str
    created_at: str
    expires_at: str
    status: VerificationStatus


@dataclass(frozen=True)
class EmailMessage:
    """Concrete Gmail delivery payload contract."""

    to: str
    subject: str
    body: str
    sent_at: Optional[str]


AlertSendResult = EmailMessage


@runtime_checkable
class GmailAdapter(Protocol):
    """Real Gmail API adapter contract for production delivery."""

    def send(self, message: EmailMessage) -> bool:
        ...


class _ProvisionedGmailAPIAdapter:
    """Fail-closed adapter placeholder for a provisioned Gmail API runtime."""

    def __init__(self, credentials_path: str):
        self._credentials_path = credentials_path

    def send(self, message: EmailMessage) -> bool:
        del message
        raise RuntimeError(
            "Gmail OAuth runtime is not connected. Provide a concrete GmailAdapter "
            "bound to a provisioned Gmail API token store."
        )


# Default owner email (configurable)
DEFAULT_OWNER_EMAIL = "hacker05090204@gmail.com"

# Password expiry (5 minutes)
PASSWORD_EXPIRY_MINUTES = 5

# In-memory verification store
_verification_store: Dict[str, VerificationPassword] = {}
_sent_alerts: List[EmailMessage] = []


def get_config() -> GmailAlertConfig:
    """Get Gmail alert configuration from environment."""

    return GmailAlertConfig(
        owner_email=os.environ.get("OWNER_EMAIL", DEFAULT_OWNER_EMAIL),
        credentials_path=os.environ.get("GMAIL_CREDENTIALS_PATH"),
    )


def clear_verification_store() -> None:
    """Clear verification and alert state for tests."""

    _verification_store.clear()
    _sent_alerts.clear()


def generate_verification_password() -> tuple[str, VerificationPassword]:
    """Generate a cryptographically strong verification password."""

    length = secrets.randbelow(9) + 16
    plaintext = secrets.token_urlsafe(length)[:length]

    import hashlib

    password_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    now = datetime.now(UTC)
    expires = now + timedelta(minutes=PASSWORD_EXPIRY_MINUTES)

    verification = VerificationPassword(
        password_id=f"PWD-{uuid.uuid4().hex[:16].upper()}",
        password_hash=password_hash,
        created_at=now.isoformat(),
        expires_at=expires.isoformat(),
        status=VerificationStatus.PENDING,
    )
    _verification_store[verification.password_id] = verification
    return plaintext, verification


def is_password_expired(password: VerificationPassword) -> bool:
    """Check whether a verification password has expired."""

    try:
        expires_dt = datetime.fromisoformat(password.expires_at.replace("Z", "+00:00"))
        return datetime.now(UTC) >= expires_dt
    except (ValueError, TypeError):
        return True


def verify_password(password_id: str, submitted_password: str) -> tuple[bool, str]:
    """Verify a submitted password against the stored hash."""

    if password_id not in _verification_store:
        return False, "Password ID not found"

    password = _verification_store[password_id]
    if is_password_expired(password):
        _verification_store[password_id] = VerificationPassword(
            password_id=password.password_id,
            password_hash=password.password_hash,
            created_at=password.created_at,
            expires_at=password.expires_at,
            status=VerificationStatus.EXPIRED,
        )
        return False, "Password has expired (5 minute limit)"

    import hashlib

    submitted_hash = hashlib.sha256(submitted_password.encode()).hexdigest()
    if submitted_hash != password.password_hash:
        return False, "Invalid password"

    _verification_store[password_id] = VerificationPassword(
        password_id=password.password_id,
        password_hash=password.password_hash,
        created_at=password.created_at,
        expires_at=password.expires_at,
        status=VerificationStatus.VERIFIED,
    )
    return True, "Password verified successfully"


class GmailAlerter:
    """Fail-closed Gmail alert sender pending a real Gmail API backend."""

    def __init__(
        self,
        config: Optional[GmailAlertConfig] = None,
        adapter: Optional[GmailAdapter] = None,
        alert_logger: Optional[logging.Logger] = None,
    ):
        self._config = config or get_config()
        self._adapter = adapter
        self._logger = alert_logger or logger

    def _resolve_credentials_path(self) -> str:
        credentials_path = (self._config.credentials_path or "").strip()
        if not credentials_path or not Path(credentials_path).is_file():
            raise RealBackendNotConfiguredError(GMAIL_PROVISIONING_MESSAGE)
        return credentials_path

    def _resolve_adapter(self, credentials_path: str) -> GmailAdapter:
        if self._adapter is not None:
            return self._adapter
        return _ProvisionedGmailAPIAdapter(credentials_path)

    def _build_message(self, alert: OwnerAlert) -> EmailMessage:
        return EmailMessage(
            to=self._config.owner_email,
            subject=f"[YGB] {alert.title}",
            body=(
                f"Alert Type: {alert.alert_type.value}\n"
                f"Title: {alert.title}\n"
                f"Message: {alert.message}\n"
                f"Device: {alert.device_id}\n"
                f"Severity: {alert.severity.value}\n"
                f"Created At: {alert.created_at}\n"
            ),
            sent_at=None,
        )

    def send_alert(self, alert: OwnerAlert) -> EmailMessage:
        """Attempt real Gmail API delivery or fail closed."""

        credentials_path = self._resolve_credentials_path()
        message = self._build_message(alert)
        adapter = self._resolve_adapter(credentials_path)

        try:
            delivered = adapter.send(message)
        except Exception:
            self._logger.critical("Gmail API alert delivery failed", exc_info=True)
            _sent_alerts.append(message)
            return message

        if not delivered:
            self._logger.critical("Gmail API alert delivery failed: adapter returned False")
            _sent_alerts.append(message)
            return message

        delivered_message = EmailMessage(
            to=message.to,
            subject=message.subject,
            body=message.body,
            sent_at=datetime.now(UTC).isoformat(),
        )
        _sent_alerts.append(delivered_message)
        return delivered_message


def send_alert(
    alert: OwnerAlert,
    config: Optional[GmailAlertConfig] = None,
    adapter: Optional[GmailAdapter] = None,
) -> EmailMessage:
    """Module-level wrapper for governed Gmail alert delivery."""

    return GmailAlerter(config=config, adapter=adapter).send_alert(alert)


def send_new_device_alert(device_id: str, ip_address: str) -> EmailMessage:
    """Send alert for new device registration."""
    from .g10_owner_alerts import alert_new_login
    alert = alert_new_login(device_id, ip_address)
    return send_alert(alert)


def send_new_ip_alert(device_id: str, old_ip: str, new_ip: str) -> EmailMessage:
    """Send alert for IP address change."""
    from .g10_owner_alerts import alert_new_ip
    alert = alert_new_ip(device_id, old_ip, new_ip)
    return send_alert(alert)


def send_geo_mismatch_alert(
    device_id: str,
    expected_country: str,
    actual_country: str,
) -> EmailMessage:
    """Send alert for geographic mismatch."""
    from .g10_owner_alerts import alert_geo_mismatch
    alert = alert_geo_mismatch(device_id, expected_country, actual_country)
    return send_alert(alert)


def send_license_violation_alert(device_id: str, violation: str) -> EmailMessage:
    """Send alert for license violation."""
    from .g10_owner_alerts import create_alert, AlertType
    alert = create_alert(
        alert_type=AlertType.LICENSE_FAILURE,
        title="License Violation Detected",
        message=violation,
        device_id=device_id,
    )
    return send_alert(alert)


def send_risk_escalation_alert(device_id: str, risk_level: str, reason: str) -> EmailMessage:
    """Send alert for risk escalation."""
    from .g10_owner_alerts import create_alert, AlertType, AlertSeverity
    alert = create_alert(
        alert_type=AlertType.AUTONOMY_ABUSE,
        title=f"Risk Escalation: {risk_level}",
        message=reason,
        device_id=device_id,
        severity_override=AlertSeverity.HIGH if risk_level == "HIGH" else AlertSeverity.CRITICAL,
    )
    return send_alert(alert)


def can_email_approve_execution() -> tuple:
    """Check if email can approve execution. Returns (can_approve, reason)."""
    # Email can NEVER approve execution
    return False, "Email alerts are NOTIFICATION ONLY - cannot approve execution"


def get_sent_alerts() -> List[EmailMessage]:
    """Get list of sent alerts (for testing/audit)."""
    return list(_sent_alerts)
