# G10: Owner Alerts
"""
Real-time owner notification system.

ALERTS FOR:
- New login
- New IP address
- Geo mismatch
- Headless browser request
- Autonomy mode abuse
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
import uuid
from datetime import datetime, UTC


class AlertType(Enum):
    """CLOSED ENUM - 7 alert types"""
    NEW_LOGIN = "NEW_LOGIN"
    NEW_IP = "NEW_IP"
    GEO_MISMATCH = "GEO_MISMATCH"
    HEADLESS_REQUEST = "HEADLESS_REQUEST"
    AUTONOMY_ABUSE = "AUTONOMY_ABUSE"
    LICENSE_FAILURE = "LICENSE_FAILURE"
    DEVICE_LIMIT = "DEVICE_LIMIT"


class AlertSeverity(Enum):
    """CLOSED ENUM - 4 severities"""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AlertStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    PENDING = "PENDING"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"


@dataclass(frozen=True)
class OwnerAlert:
    """Owner alert record."""
    alert_id: str
    alert_type: AlertType
    severity: AlertSeverity
    status: AlertStatus
    title: str
    message: str
    device_id: Optional[str]
    ip_address: Optional[str]
    created_at: str
    acknowledged_at: Optional[str]


# Alert severity mapping
ALERT_SEVERITY_MAP = {
    AlertType.NEW_LOGIN: AlertSeverity.LOW,
    AlertType.NEW_IP: AlertSeverity.MEDIUM,
    AlertType.GEO_MISMATCH: AlertSeverity.HIGH,
    AlertType.HEADLESS_REQUEST: AlertSeverity.MEDIUM,
    AlertType.AUTONOMY_ABUSE: AlertSeverity.CRITICAL,
    AlertType.LICENSE_FAILURE: AlertSeverity.HIGH,
    AlertType.DEVICE_LIMIT: AlertSeverity.MEDIUM,
}

# In-memory alert store
_alert_store: List[OwnerAlert] = []


def clear_alerts():
    """Clear alert store (for testing)."""
    _alert_store.clear()


def get_all_alerts() -> List[OwnerAlert]:
    """Get all alerts."""
    return list(_alert_store)


def get_pending_alerts() -> List[OwnerAlert]:
    """Get pending (unacknowledged) alerts."""
    return [a for a in _alert_store if a.status == AlertStatus.PENDING]


def create_alert(
    alert_type: AlertType,
    title: str,
    message: str,
    device_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    severity_override: Optional[AlertSeverity] = None,
) -> OwnerAlert:
    """Create and store an alert."""
    severity = severity_override or ALERT_SEVERITY_MAP.get(alert_type, AlertSeverity.MEDIUM)
    
    alert = OwnerAlert(
        alert_id=f"ALT-{uuid.uuid4().hex[:16].upper()}",
        alert_type=alert_type,
        severity=severity,
        status=AlertStatus.PENDING,
        title=title,
        message=message,
        device_id=device_id,
        ip_address=ip_address,
        created_at=datetime.now(UTC).isoformat(),
        acknowledged_at=None,
    )
    
    _alert_store.append(alert)
    return alert


def alert_new_login(device_id: str, ip_address: str) -> OwnerAlert:
    """Create new login alert."""
    return create_alert(
        alert_type=AlertType.NEW_LOGIN,
        title="New Login Detected",
        message=f"A new login was detected from IP {ip_address}",
        device_id=device_id,
        ip_address=ip_address,
    )


def alert_new_ip(device_id: str, old_ip: str, new_ip: str) -> OwnerAlert:
    """Create new IP alert."""
    return create_alert(
        alert_type=AlertType.NEW_IP,
        title="IP Address Changed",
        message=f"IP changed from {old_ip} to {new_ip}",
        device_id=device_id,
        ip_address=new_ip,
    )


def alert_geo_mismatch(
    device_id: str,
    expected_country: str,
    actual_country: str,
) -> OwnerAlert:
    """Create geo mismatch alert."""
    return create_alert(
        alert_type=AlertType.GEO_MISMATCH,
        title="Geographic Mismatch",
        message=f"Expected {expected_country}, detected {actual_country}",
        device_id=device_id,
        severity_override=AlertSeverity.HIGH,
    )


def alert_headless_request(device_id: str, reason: str) -> OwnerAlert:
    """Create headless browser request alert."""
    return create_alert(
        alert_type=AlertType.HEADLESS_REQUEST,
        title="Headless Browser Requested",
        message=f"Headless mode requested: {reason}",
        device_id=device_id,
    )


def alert_autonomy_abuse(device_id: str, abuse_type: str) -> OwnerAlert:
    """Create autonomy abuse alert."""
    return create_alert(
        alert_type=AlertType.AUTONOMY_ABUSE,
        title="Autonomy Mode Abuse Detected",
        message=f"Potential abuse: {abuse_type}",
        device_id=device_id,
        severity_override=AlertSeverity.CRITICAL,
    )


def acknowledge_alert(alert_id: str) -> Optional[OwnerAlert]:
    """Acknowledge an alert."""
    for i, alert in enumerate(_alert_store):
        if alert.alert_id == alert_id:
            acknowledged = OwnerAlert(
                alert_id=alert.alert_id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                status=AlertStatus.ACKNOWLEDGED,
                title=alert.title,
                message=alert.message,
                device_id=alert.device_id,
                ip_address=alert.ip_address,
                created_at=alert.created_at,
                acknowledged_at=datetime.now(UTC).isoformat(),
            )
            _alert_store[i] = acknowledged
            return acknowledged
    
    return None
