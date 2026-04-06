# test_g10_owner_alerts.py
"""Tests for G10: Owner Alerts"""

from pathlib import Path
import logging

import pytest

from impl_v1.phase49.governors.g10_owner_alerts import (
    ALERT_SEVERITY_MAP,
    AlertRecord,
    AlertSeverity,
    AlertStatus,
    AlertType,
    OwnerAlert,
    OwnerAlertManager,
    acknowledge_alert,
    alert_autonomy_abuse,
    alert_geo_mismatch,
    alert_headless_request,
    alert_new_ip,
    alert_new_login,
    clear_alerts,
    create_alert,
    get_alerts_by_severity,
    get_all_alerts,
    get_pending_alerts,
    get_undelivered,
    send_alert,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_alert_type_7_members(self):
        assert len(AlertType) == 7
    
    def test_alert_severity_3_members(self):
        assert len(AlertSeverity) == 3

    def test_alert_severity_expected_members(self):
        assert AlertSeverity.INFO.value == "INFO"
        assert AlertSeverity.WARNING.value == "WARNING"
        assert AlertSeverity.CRITICAL.value == "CRITICAL"
    
    def test_alert_status_4_members(self):
        assert len(AlertStatus) == 4


class TestSeverityMapping:
    """Test default severity mapping."""
    
    def test_new_login_low(self):
        assert ALERT_SEVERITY_MAP[AlertType.NEW_LOGIN] == AlertSeverity.LOW
    
    def test_geo_mismatch_high(self):
        assert ALERT_SEVERITY_MAP[AlertType.GEO_MISMATCH] == AlertSeverity.HIGH
    
    def test_autonomy_abuse_critical(self):
        assert ALERT_SEVERITY_MAP[AlertType.AUTONOMY_ABUSE] == AlertSeverity.CRITICAL


class TestCreateAlert:
    """Test alert creation."""
    
    def setup_method(self):
        clear_alerts()
    
    def test_alert_has_id(self):
        alert = create_alert(AlertType.NEW_LOGIN, "Test", "Message")
        assert alert.alert_id.startswith("ALT-")
    
    def test_alert_default_severity(self):
        alert = create_alert(AlertType.NEW_LOGIN, "Test", "Message")
        assert alert.severity == AlertSeverity.LOW
    
    def test_alert_severity_override(self):
        alert = create_alert(
            AlertType.NEW_LOGIN, "Test", "Message",
            severity_override=AlertSeverity.CRITICAL
        )
        assert alert.severity == AlertSeverity.CRITICAL
    
    def test_alert_stored(self):
        create_alert(AlertType.NEW_LOGIN, "Test", "Message")
        assert len(get_all_alerts()) == 1
    
    def test_alert_starts_pending(self):
        alert = create_alert(AlertType.NEW_LOGIN, "Test", "Message")
        assert alert.status == AlertStatus.PENDING


class TestAlertHelpers:
    """Test alert helper functions."""
    
    def setup_method(self):
        clear_alerts()
    
    def test_alert_new_login(self):
        alert = alert_new_login("dev-1", "192.168.1.1")
        assert alert.alert_type == AlertType.NEW_LOGIN
        assert alert.device_id == "dev-1"
        assert alert.ip_address == "192.168.1.1"
    
    def test_alert_new_ip(self):
        alert = alert_new_ip("dev-1", "1.1.1.1", "2.2.2.2")
        assert alert.alert_type == AlertType.NEW_IP
        assert "1.1.1.1" in alert.message
        assert "2.2.2.2" in alert.message
    
    def test_alert_geo_mismatch(self):
        alert = alert_geo_mismatch("dev-1", "USA", "Russia")
        assert alert.alert_type == AlertType.GEO_MISMATCH
        assert alert.severity == AlertSeverity.HIGH
    
    def test_alert_headless_request(self):
        alert = alert_headless_request("dev-1", "Headed failed")
        assert alert.alert_type == AlertType.HEADLESS_REQUEST
    
    def test_alert_autonomy_abuse(self):
        alert = alert_autonomy_abuse("dev-1", "Exceeded time limit")
        assert alert.alert_type == AlertType.AUTONOMY_ABUSE
        assert alert.severity == AlertSeverity.CRITICAL


class TestGetAlerts:
    """Test alert retrieval."""
    
    def setup_method(self):
        clear_alerts()
    
    def test_get_all_empty(self):
        assert len(get_all_alerts()) == 0
    
    def test_get_all_multiple(self):
        create_alert(AlertType.NEW_LOGIN, "T1", "M1")
        create_alert(AlertType.NEW_IP, "T2", "M2")
        assert len(get_all_alerts()) == 2
    
    def test_get_pending_only(self):
        alert1 = create_alert(AlertType.NEW_LOGIN, "T1", "M1")
        alert2 = create_alert(AlertType.NEW_IP, "T2", "M2")
        acknowledge_alert(alert1.alert_id)
        pending = get_pending_alerts()
        assert len(pending) == 1
        assert pending[0].alert_id == alert2.alert_id


class TestAcknowledgeAlert:
    """Test alert acknowledgment."""
    
    def setup_method(self):
        clear_alerts()
    
    def test_acknowledge_changes_status(self):
        alert = create_alert(AlertType.NEW_LOGIN, "T", "M")
        acknowledged = acknowledge_alert(alert.alert_id)
        assert acknowledged.status == AlertStatus.ACKNOWLEDGED
    
    def test_acknowledge_sets_timestamp(self):
        alert = create_alert(AlertType.NEW_LOGIN, "T", "M")
        acknowledged = acknowledge_alert(alert.alert_id)
        assert acknowledged.acknowledged_at is not None
    
    def test_acknowledge_unknown_returns_none(self):
        result = acknowledge_alert("UNKNOWN-ALERT")
        assert result is None
    
    def test_acknowledge_preserves_data(self):
        alert = create_alert(AlertType.NEW_LOGIN, "Title", "Message", device_id="dev-1")
        acknowledged = acknowledge_alert(alert.alert_id)
        assert acknowledged.title == "Title"
        assert acknowledged.message == "Message"
        assert acknowledged.device_id == "dev-1"


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def setup_method(self):
        clear_alerts()
    
    def test_alert_frozen(self):
        alert = create_alert(AlertType.NEW_LOGIN, "T", "M")
        with pytest.raises(AttributeError):
            alert.status = AlertStatus.DISMISSED


class TestOwnerAlertManager:
    """Tests for owner alert manager delivery tracking."""

    def setup_method(self):
        clear_alerts()

    def test_send_alert_returns_alert_record(self):
        alert = send_alert(AlertSeverity.WARNING, "Owner follow-up required")

        assert isinstance(alert, AlertRecord)
        assert alert.severity == "WARNING"
        assert alert.delivery_channel == "email"
        assert alert.delivered is False

    def test_critical_alert_logs_immediately(self, caplog):
        manager = OwnerAlertManager()

        with caplog.at_level(logging.CRITICAL):
            manager.send_alert(AlertSeverity.CRITICAL, "Immediate owner action required")

        assert any(
            record.levelno == logging.CRITICAL and "Immediate owner action required" in record.message
            for record in caplog.records
        )

    def test_get_undelivered_returns_pending_alerts(self):
        sent = send_alert(AlertSeverity.INFO, "Info path")

        undelivered = get_undelivered()

        assert undelivered == [sent]

    def test_get_alerts_by_severity_filters_records(self):
        send_alert(AlertSeverity.INFO, "Info path")
        critical = send_alert(AlertSeverity.CRITICAL, "Critical path")

        critical_alerts = get_alerts_by_severity(AlertSeverity.CRITICAL)

        assert critical_alerts == [critical]

    def test_production_file_has_no_mock_send_wording(self):
        source = (
            Path(__file__).resolve().parents[1]
            / "governors"
            / "g10_owner_alerts.py"
        ).read_text(encoding="utf-8").lower()

        assert "mock" not in source
