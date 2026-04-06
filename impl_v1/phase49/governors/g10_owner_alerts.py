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

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
import logging
from typing import Callable, Mapping, Optional
import uuid


logger = logging.getLogger(__name__)


class AlertType(Enum):
    """CLOSED ENUM - 7 alert types"""
    NEW_LOGIN = "NEW_LOGIN"
    NEW_IP = "NEW_IP"
    GEO_MISMATCH = "GEO_MISMATCH"
    HEADLESS_REQUEST = "HEADLESS_REQUEST"
    AUTONOMY_ABUSE = "AUTONOMY_ABUSE"
    LICENSE_FAILURE = "LICENSE_FAILURE"
    DEVICE_LIMIT = "DEVICE_LIMIT"


class AlertSeverity(str, Enum):
    """Owner alert severity levels."""

    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    LOW = INFO
    MEDIUM = WARNING
    HIGH = WARNING


class AlertStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    PENDING = "PENDING"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"


@dataclass(frozen=True)
class AlertRecord:
    """Delivery record for owner alerts."""

    alert_id: str
    severity: str
    message: str
    created_at: str
    delivered: bool
    delivery_channel: str


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


class AlertLog:
    """Append-only alert log with bounded retention."""

    def __init__(self, max_entries: int = 5000) -> None:
        self.max_entries = max_entries
        self._entries: deque[str] = deque(maxlen=max_entries)

    def append(self, severity: str | AlertSeverity, message: str) -> None:
        normalized = _normalize_alert_severity(severity)
        self._entries.append(f"{_utc_now()} [{normalized.value}] {message}")

        if normalized == AlertSeverity.CRITICAL:
            logger.critical(message)
        elif normalized == AlertSeverity.WARNING:
            logger.warning(message)
        else:
            logger.info(message)

    @property
    def entries(self) -> list[str]:
        return list(self._entries)

    def get_entries(self) -> list[str]:
        return list(self._entries)

    def clear(self) -> None:
        self._entries.clear()


class OwnerAlertManager:
    """Owner alert delivery manager."""

    def __init__(
        self,
        delivery_backends: Optional[Mapping[str, Callable[[AlertRecord], bool]]] = None,
        alert_log: Optional[AlertLog] = None,
    ) -> None:
        self._delivery_backends = dict(delivery_backends or {})
        self.alert_log = alert_log or AlertLog()
        self._alerts: list[AlertRecord] = []

    def send_alert(
        self,
        severity: str | AlertSeverity,
        message: str,
        channel: str = "email",
    ) -> AlertRecord:
        normalized = _normalize_alert_severity(severity)
        alert = AlertRecord(
            alert_id=f"ALR-{uuid.uuid4().hex[:16].upper()}",
            severity=normalized.value,
            message=message,
            created_at=_utc_now(),
            delivered=False,
            delivery_channel=channel,
        )

        if normalized == AlertSeverity.CRITICAL:
            self.alert_log.append(AlertSeverity.CRITICAL, f"Critical owner alert created: {message}")

        backend = self._delivery_backends.get(channel)
        delivered = False
        if backend is None:
            self.alert_log.append(AlertSeverity.WARNING, f"Owner alert channel unavailable: {channel}")
        else:
            try:
                delivered = bool(backend(alert))
            except Exception as exc:
                self.alert_log.append(AlertSeverity.WARNING, f"Owner alert delivery failed on {channel}: {exc}")
                delivered = False
            else:
                if delivered:
                    self.alert_log.append(AlertSeverity.INFO, f"Owner alert delivered via {channel}")
                else:
                    self.alert_log.append(AlertSeverity.WARNING, f"Owner alert delivery did not complete on {channel}")

        if delivered:
            alert = replace(alert, delivered=True)

        self._alerts.append(alert)
        return alert

    def get_undelivered(self) -> list[AlertRecord]:
        return [alert for alert in self._alerts if not alert.delivered]

    def get_alerts_by_severity(self, severity: str | AlertSeverity) -> list[AlertRecord]:
        normalized = _normalize_alert_severity(severity)
        return [alert for alert in self._alerts if alert.severity == normalized.value]

    def get_all_alerts(self) -> list[AlertRecord]:
        return list(self._alerts)

    def clear(self) -> None:
        self._alerts.clear()
        self.alert_log.clear()


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_alert_severity(severity: str | AlertSeverity) -> AlertSeverity:
    if isinstance(severity, AlertSeverity):
        return severity

    normalized = str(severity).strip().upper()
    alias_map = {
        "LOW": AlertSeverity.INFO,
        "INFO": AlertSeverity.INFO,
        "MEDIUM": AlertSeverity.WARNING,
        "HIGH": AlertSeverity.WARNING,
        "WARNING": AlertSeverity.WARNING,
        "CRITICAL": AlertSeverity.CRITICAL,
    }
    if normalized not in alias_map:
        raise ValueError(f"Unsupported alert severity: {severity}")
    return alias_map[normalized]


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
_alert_store: list[OwnerAlert] = []
_default_alert_manager = OwnerAlertManager()
ALERT_LOG = _default_alert_manager.alert_log


def clear_alerts():
    """Clear alert store (for testing)."""

    _alert_store.clear()
    _default_alert_manager.clear()


def get_all_alerts() -> list[OwnerAlert]:
    """Get all alerts."""

    return list(_alert_store)


def get_pending_alerts() -> list[OwnerAlert]:
    """Get pending (unacknowledged) alerts."""

    return [a for a in _alert_store if a.status == AlertStatus.PENDING]


def send_alert(
    severity: str | AlertSeverity,
    message: str,
    channel: str = "email",
) -> AlertRecord:
    """Send an owner alert through the default manager."""

    return _default_alert_manager.send_alert(severity=severity, message=message, channel=channel)


def get_undelivered() -> list[AlertRecord]:
    """Get undelivered alerts from the default manager."""

    return _default_alert_manager.get_undelivered()


def get_alerts_by_severity(severity: str | AlertSeverity) -> list[AlertRecord]:
    """Get alerts by severity from the default manager."""

    return _default_alert_manager.get_alerts_by_severity(severity)


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
        created_at=_utc_now(),
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
                acknowledged_at=_utc_now(),
            )
            _alert_store[i] = acknowledged
            return acknowledged

    return None
