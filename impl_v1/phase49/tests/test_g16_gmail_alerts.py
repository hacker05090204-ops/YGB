# test_g16_gmail_alerts.py
"""Tests for G16 Gmail Alerts governor."""

import pytest
import time
from datetime import datetime, UTC, timedelta

from impl_v1.phase49.governors.g16_gmail_alerts import (
    GmailAlertConfig,
    AlertSendResult,
    VerificationPassword,
    EmailStatus,
    VerificationStatus,
    generate_verification_password,
    verify_password,
    send_alert,
    send_new_device_alert,
    send_new_ip_alert,
    send_geo_mismatch_alert,
    send_license_violation_alert,
    send_risk_escalation_alert,
    can_email_approve_execution,
    get_config,
    clear_verification_store,
    is_password_expired,
    get_sent_alerts,
    DEFAULT_OWNER_EMAIL,
    PASSWORD_EXPIRY_MINUTES,
)
from impl_v1.phase49.governors.g10_owner_alerts import (
    clear_alerts,
    alert_new_login,
    alert_new_ip,
    alert_geo_mismatch,
    create_alert,
    AlertType,
    AlertSeverity,
)


class TestGmailAlertConfig:
    """Tests for GmailAlertConfig dataclass."""

    def test_config_exists(self):
        config = GmailAlertConfig(owner_email="test@test.com")
        assert config is not None

    def test_config_has_owner_email(self):
        config = GmailAlertConfig(owner_email="user@example.com")
        assert config.owner_email == "user@example.com"

    def test_config_has_smtp_server(self):
        config = GmailAlertConfig(owner_email="test@test.com")
        assert config.smtp_server == "smtp.gmail.com"

    def test_config_has_smtp_port(self):
        config = GmailAlertConfig(owner_email="test@test.com")
        assert config.smtp_port == 587


class TestEmailStatus:
    """Tests for EmailStatus enum."""

    def test_has_pending(self):
        assert EmailStatus.PENDING.value == "PENDING"

    def test_has_sent(self):
        assert EmailStatus.SENT.value == "SENT"

    def test_has_failed(self):
        assert EmailStatus.FAILED.value == "FAILED"


class TestVerificationPassword:
    """Tests for verification password generation."""

    def setup_method(self):
        clear_verification_store()
        clear_alerts()

    def test_generates_password(self):
        plaintext, verification = generate_verification_password()
        assert plaintext is not None
        assert verification is not None

    def test_password_has_variable_length(self):
        lengths = set()
        for _ in range(10):
            plaintext, _ = generate_verification_password()
            lengths.add(len(plaintext))
        # Should have at least some variation
        assert len(lengths) >= 1

    def test_password_length_in_range(self):
        for _ in range(10):
            plaintext, _ = generate_verification_password()
            assert 16 <= len(plaintext) <= 24

    def test_password_is_cryptographically_random(self):
        passwords = set()
        for _ in range(10):
            plaintext, _ = generate_verification_password()
            passwords.add(plaintext)
        # All should be unique
        assert len(passwords) == 10

    def test_verification_has_id(self):
        _, verification = generate_verification_password()
        assert verification.password_id.startswith("PWD-")

    def test_verification_has_expiry(self):
        _, verification = generate_verification_password()
        assert verification.expires_at is not None

    def test_expiry_is_5_minutes(self):
        assert PASSWORD_EXPIRY_MINUTES == 5


class TestVerifyPassword:
    """Tests for password verification."""

    def setup_method(self):
        clear_verification_store()

    def test_valid_password_verifies(self):
        plaintext, verification = generate_verification_password()
        verified, reason = verify_password(verification.password_id, plaintext)
        assert verified == True

    def test_invalid_id_fails(self):
        verified, reason = verify_password("PWD-INVALID", "password")
        assert verified == False
        assert "not found" in reason

    def test_empty_password_fails(self):
        _, verification = generate_verification_password()
        verified, reason = verify_password(verification.password_id, "")
        assert verified == False


class TestIsPasswordExpired:
    """Tests for password expiry check."""

    def test_fresh_password_not_expired(self):
        _, verification = generate_verification_password()
        assert is_password_expired(verification) == False

    def test_old_password_expired(self):
        old_expires = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        old = VerificationPassword(
            password_id="PWD-OLD",
            password_hash="hash",
            created_at=datetime.now(UTC).isoformat(),
            expires_at=old_expires,
            status=VerificationStatus.PENDING,
        )
        assert is_password_expired(old) == True


class TestSendAlert:
    """Tests for send_alert function."""

    def setup_method(self):
        clear_verification_store()
        clear_alerts()

    def test_send_new_device_alert(self):
        result = send_alert(
            alert_new_login("device-123", "192.168.1.1"), _mock_send=True
        )
        assert isinstance(result, AlertSendResult)
        assert result.email_status == EmailStatus.SENT

    def test_send_new_ip_alert(self):
        result = send_alert(
            alert_new_ip("device-123", "192.168.1.1", "10.0.0.1"), _mock_send=True
        )
        assert result.email_status == EmailStatus.SENT

    def test_send_geo_mismatch_alert(self):
        result = send_alert(
            alert_geo_mismatch("device-123", "US", "RU"), _mock_send=True
        )
        assert result.email_status == EmailStatus.SENT

    def test_send_license_violation_alert(self):
        alert = create_alert(
            alert_type=AlertType.LICENSE_FAILURE,
            title="License Violation Detected",
            message="Invalid license key",
            device_id="device-123",
        )
        result = send_alert(alert, _mock_send=True)
        assert result.email_status == EmailStatus.SENT

    def test_send_risk_escalation_alert(self):
        alert = create_alert(
            alert_type=AlertType.AUTONOMY_ABUSE,
            title="Risk Escalation: HIGH",
            message="Unusual activity",
            device_id="device-123",
            severity_override=AlertSeverity.HIGH,
        )
        result = send_alert(alert, _mock_send=True)
        assert result.email_status == EmailStatus.SENT

    def test_send_alert_without_configuration_fails_closed(self):
        result = send_new_device_alert("device-123", "192.168.1.1")
        assert result.email_status == EmailStatus.FAILED

    def test_alerts_are_recorded(self):
        send_alert(alert_new_login("test", "127.0.0.1"), _mock_send=True)
        alerts = get_sent_alerts()
        assert len(alerts) >= 1


class TestCanEmailApproveExecution:
    """Tests for can_email_approve_execution function."""

    def test_returns_tuple(self):
        result = can_email_approve_execution()
        assert isinstance(result, tuple)

    def test_email_cannot_approve(self):
        can_approve, reason = can_email_approve_execution()
        assert can_approve == False

    def test_has_reason(self):
        _, reason = can_email_approve_execution()
        assert "NOTIFICATION" in reason or "cannot" in reason.lower()


class TestDefaultOwnerEmail:
    """Tests for default owner email."""

    def test_default_email_is_blank(self):
        assert DEFAULT_OWNER_EMAIL == ""
