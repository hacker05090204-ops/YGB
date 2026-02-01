# test_g10_owner_alerts.py
"""Tests for G10: Owner Alerts"""

import pytest
from impl_v1.phase49.governors.g10_owner_alerts import (
    AlertType,
    AlertSeverity,
    AlertStatus,
    OwnerAlert,
    ALERT_SEVERITY_MAP,
    clear_alerts,
    get_all_alerts,
    get_pending_alerts,
    create_alert,
    alert_new_login,
    alert_new_ip,
    alert_geo_mismatch,
    alert_headless_request,
    alert_autonomy_abuse,
    acknowledge_alert,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_alert_type_7_members(self):
        assert len(AlertType) == 7
    
    def test_alert_severity_4_members(self):
        assert len(AlertSeverity) == 4
    
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
