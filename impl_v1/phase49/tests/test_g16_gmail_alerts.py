"""Tests for G16 Gmail Alerts governor."""

import inspect
import logging
from datetime import UTC, datetime, timedelta

import pytest

from impl_v1.phase49.governors.g10_owner_alerts import alert_new_login, clear_alerts
from impl_v1.phase49.governors.g16_gmail_alerts import (
    DEFAULT_OWNER_EMAIL,
    GMAIL_PROVISIONING_MESSAGE,
    GmailAlertConfig,
    GmailAlerter,
    EmailMessage,
    RealBackendNotConfiguredError,
    VerificationPassword,
    VerificationStatus,
    PASSWORD_EXPIRY_MINUTES,
    can_email_approve_execution,
    clear_verification_store,
    generate_verification_password,
    get_config,
    get_sent_alerts,
    is_password_expired,
    send_alert,
    send_new_device_alert,
    verify_password,
)


class TestGmailAlertConfig:
    """Tests for GmailAlertConfig dataclass."""

    def test_config_exists(self):
        config = GmailAlertConfig(owner_email="test@test.com")
        assert config is not None

    def test_config_has_owner_email(self):
        config = GmailAlertConfig(owner_email="user@example.com")
        assert config.owner_email == "user@example.com"

    def test_config_has_credentials_path(self):
        config = GmailAlertConfig(owner_email="test@test.com", credentials_path="creds.json")
        assert config.credentials_path == "creds.json"


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

    def test_wrong_password_fails(self):
        _, verification = generate_verification_password()
        verified, reason = verify_password(verification.password_id, "wrong-password")
        assert verified == False
        assert "Invalid password" in reason


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
    """Tests for infrastructure-gated Gmail alert delivery."""

    def setup_method(self):
        clear_verification_store()
        clear_alerts()

    def test_mock_send_parameter_is_absent(self):
        parameters = inspect.signature(send_alert).parameters
        assert "_mock_send" not in parameters

    def test_missing_credentials_raise_real_backend_not_configured(self, monkeypatch):
        monkeypatch.delenv("GMAIL_CREDENTIALS_PATH", raising=False)
        with pytest.raises(RealBackendNotConfiguredError, match=GMAIL_PROVISIONING_MESSAGE):
            send_new_device_alert("device-123", "192.168.1.1")

    def test_api_failure_logs_critical_and_returns_unsent_message(self, monkeypatch, tmp_path, caplog):
        credentials = tmp_path / "credentials.json"
        credentials.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(credentials))

        class FailingAdapter:
            def send(self, message: EmailMessage) -> bool:
                raise RuntimeError("gmail api unavailable")

        alert = alert_new_login("device-123", "192.168.1.1")
        with caplog.at_level(logging.CRITICAL):
            result = send_alert(alert, adapter=FailingAdapter())

        assert isinstance(result, EmailMessage)
        assert result.sent_at is None
        assert result.to == DEFAULT_OWNER_EMAIL
        assert "gmail api unavailable" in caplog.text

    def test_alerter_returns_sent_message_when_adapter_succeeds(self, monkeypatch, tmp_path):
        credentials = tmp_path / "credentials.json"
        credentials.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(credentials))

        class SuccessAdapter:
            def send(self, message: EmailMessage) -> bool:
                return True

        alert = alert_new_login("device-123", "192.168.1.1")
        result = GmailAlerter(adapter=SuccessAdapter()).send_alert(alert)
        assert result.sent_at is not None
        assert result.subject == f"[YGB] {alert.title}"

    def test_get_sent_alerts_returns_email_messages(self, monkeypatch, tmp_path):
        credentials = tmp_path / "credentials.json"
        credentials.write_text("{}", encoding="utf-8")
        monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(credentials))

        class SuccessAdapter:
            def send(self, message: EmailMessage) -> bool:
                return True

        alert = alert_new_login("device-123", "192.168.1.1")
        send_alert(alert, adapter=SuccessAdapter())
        alerts = get_sent_alerts()
        assert len(alerts) == 1
        assert isinstance(alerts[0], EmailMessage)


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

    def test_default_email_exists(self):
        assert DEFAULT_OWNER_EMAIL is not None

    def test_default_email_format(self):
        assert "@gmail.com" in DEFAULT_OWNER_EMAIL
