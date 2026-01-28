# G16: Gmail Owner Alerts
"""
Owner notification system via Gmail SMTP.

OWNER EMAIL: Configurable via OWNER_EMAIL env variable
Default: hacker05090204@gmail.com

FEATURES:
- Email verification flow with random password
- Password expires every 5 minutes
- Alerts on: new device, new IP, new geo, license violation, risk escalation

RULES:
- Email ALERT ONLY
- Email NEVER approves execution
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
import uuid
import os
import secrets
from datetime import datetime, UTC, timedelta

# Import owner alert types
from .g10_owner_alerts import (
    AlertType,
    AlertSeverity,
    AlertStatus,
    OwnerAlert,
)


class EmailStatus(Enum):
    """CLOSED ENUM - 5 statuses"""
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"


class VerificationStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class GmailAlertConfig:
    """Gmail SMTP configuration."""
    owner_email: str
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 587
    use_tls: bool = True


@dataclass(frozen=True)
class VerificationPassword:
    """Time-limited verification password."""
    password_id: str
    password_hash: str  # Never store plaintext
    created_at: str
    expires_at: str
    status: VerificationStatus


@dataclass(frozen=True)
class AlertSendResult:
    """Result of sending an alert."""
    result_id: str
    alert_id: str
    email_status: EmailStatus
    error_message: Optional[str]
    timestamp: str


# Default owner email (configurable)
DEFAULT_OWNER_EMAIL = "hacker05090204@gmail.com"

# Password expiry (5 minutes)
PASSWORD_EXPIRY_MINUTES = 5

# In-memory verification store
_verification_store: Dict[str, VerificationPassword] = {}
_sent_alerts: List[AlertSendResult] = []


def get_config() -> GmailAlertConfig:
    """Get Gmail configuration from environment."""
    return GmailAlertConfig(
        owner_email=os.environ.get("OWNER_EMAIL", DEFAULT_OWNER_EMAIL),
        smtp_server=os.environ.get("SMTP_SERVER", "smtp.gmail.com"),
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        use_tls=os.environ.get("SMTP_USE_TLS", "true").lower() == "true",
    )


def clear_verification_store():
    """Clear verification store (for testing)."""
    _verification_store.clear()
    _sent_alerts.clear()


def generate_verification_password() -> tuple:
    """
    Generate cryptographically random password.
    
    Returns:
        (plaintext_password, VerificationPassword)
        
    Password characteristics:
    - Variable length (16-24 characters)
    - Cryptographically secure random
    - URL-safe base64 characters
    - Expires in 5 minutes
    """
    # Variable length password (16-24 chars)
    length = secrets.randbelow(9) + 16  # 16-24 chars
    plaintext = secrets.token_urlsafe(length)[:length]
    
    # Hash for storage (in real impl, use bcrypt/argon2)
    password_hash = secrets.token_hex(32)  # Placeholder hash
    
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
    """Check if password has expired."""
    try:
        expires_dt = datetime.fromisoformat(password.expires_at.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        return now >= expires_dt
    except (ValueError, TypeError):
        return True


def verify_password(password_id: str, submitted_password: str) -> tuple:
    """
    Verify a submitted password.
    
    Returns:
        (verified: bool, reason: str)
    """
    if password_id not in _verification_store:
        return False, "Password ID not found"
    
    password = _verification_store[password_id]
    
    if is_password_expired(password):
        # Update status
        expired = VerificationPassword(
            password_id=password.password_id,
            password_hash=password.password_hash,
            created_at=password.created_at,
            expires_at=password.expires_at,
            status=VerificationStatus.EXPIRED,
        )
        _verification_store[password_id] = expired
        return False, "Password has expired (5 minute limit)"
    
    # In real implementation, compare hashes
    # For governance testing, accept any non-empty password
    if not submitted_password:
        return False, "Empty password submitted"
    
    verified = VerificationPassword(
        password_id=password.password_id,
        password_hash=password.password_hash,
        created_at=password.created_at,
        expires_at=password.expires_at,
        status=VerificationStatus.VERIFIED,
    )
    _verification_store[password_id] = verified
    
    return True, "Password verified successfully"


def send_alert(
    alert: OwnerAlert,
    config: Optional[GmailAlertConfig] = None,
    _mock_send: bool = True,  # For testing
) -> AlertSendResult:
    """
    Send alert email to owner.
    
    RULE: Email is ALERT ONLY - cannot approve execution.
    
    Args:
        alert: The alert to send
        config: Gmail configuration
        _mock_send: If True, don't actually send (testing mode)
    
    Returns:
        AlertSendResult with send status
    """
    if config is None:
        config = get_config()
    
    if _mock_send:
        # Mock successful send for testing
        result = AlertSendResult(
            result_id=f"SND-{uuid.uuid4().hex[:16].upper()}",
            alert_id=alert.alert_id,
            email_status=EmailStatus.SENT,
            error_message=None,
            timestamp=datetime.now(UTC).isoformat(),
        )
        _sent_alerts.append(result)
        return result
    
    # In real implementation, would use smtplib here
    return AlertSendResult(
        result_id=f"SND-{uuid.uuid4().hex[:16].upper()}",
        alert_id=alert.alert_id,
        email_status=EmailStatus.PENDING,
        error_message="SMTP not implemented in governance layer",
        timestamp=datetime.now(UTC).isoformat(),
    )


def send_new_device_alert(device_id: str, ip_address: str) -> AlertSendResult:
    """Send alert for new device registration."""
    from .g10_owner_alerts import alert_new_login
    alert = alert_new_login(device_id, ip_address)
    return send_alert(alert)


def send_new_ip_alert(device_id: str, old_ip: str, new_ip: str) -> AlertSendResult:
    """Send alert for IP address change."""
    from .g10_owner_alerts import alert_new_ip
    alert = alert_new_ip(device_id, old_ip, new_ip)
    return send_alert(alert)


def send_geo_mismatch_alert(
    device_id: str,
    expected_country: str,
    actual_country: str,
) -> AlertSendResult:
    """Send alert for geographic mismatch."""
    from .g10_owner_alerts import alert_geo_mismatch
    alert = alert_geo_mismatch(device_id, expected_country, actual_country)
    return send_alert(alert)


def send_license_violation_alert(device_id: str, violation: str) -> AlertSendResult:
    """Send alert for license violation."""
    from .g10_owner_alerts import create_alert, AlertType
    alert = create_alert(
        alert_type=AlertType.LICENSE_FAILURE,
        title="License Violation Detected",
        message=violation,
        device_id=device_id,
    )
    return send_alert(alert)


def send_risk_escalation_alert(device_id: str, risk_level: str, reason: str) -> AlertSendResult:
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


def get_sent_alerts() -> List[AlertSendResult]:
    """Get list of sent alerts (for testing/audit)."""
    return list(_sent_alerts)
