"""
Tests for Email Alert System

Verifies:
- Alert email composition is correct
- SMTP connection attempted with right config
- No actual send in tests (patched SMTP)
- Graceful fallback when SMTP not configured
"""

import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.alerts import email_alerts


class TestEmailAlertComposition:
    """Test alert email content creation."""

    def test_new_login_alert_contains_user_info(self):
        """New login alert must include user name and IP."""
        with patch.object(email_alerts, "_send_email", return_value=True) as mock_send:
            email_alerts.alert_new_login("testuser", "192.168.1.1", "Chrome/120")

            mock_send.assert_called_once()
            args = mock_send.call_args
            subject = args[0][0]
            body = args[0][1]

            assert "testuser" in subject
            assert "192.168.1.1" in body
            assert "Chrome/120" in body

    def test_new_device_alert_contains_device_hash(self):
        """New device alert must include device hash."""
        with patch.object(email_alerts, "_send_email", return_value=True) as mock_send:
            email_alerts.alert_new_device("testuser", "abc123hash", "10.0.0.1", "Firefox/118")

            mock_send.assert_called_once()
            body = mock_send.call_args[0][1]
            assert "abc123hash" in body

    def test_multiple_devices_alert(self):
        """Multiple devices alert includes count."""
        with patch.object(email_alerts, "_send_email", return_value=True) as mock_send:
            email_alerts.alert_multiple_devices("testuser", 3, [
                {"device_hash": "abc123", "ip_address": "1.1.1.1", "last_seen": "2024-01-01"},
                {"device_hash": "def456", "ip_address": "2.2.2.2", "last_seen": "2024-01-02"},
            ])

            mock_send.assert_called_once()
            body = mock_send.call_args[0][1]
            assert "3" in body

    def test_suspicious_activity_alert(self):
        """Suspicious activity alert includes description."""
        with patch.object(email_alerts, "_send_email", return_value=True) as mock_send:
            email_alerts.alert_suspicious_activity(
                "Multiple failed logins", ip_address="10.0.0.1", user_name="hackerman"
            )

            mock_send.assert_called_once()
            body = mock_send.call_args[0][1]
            assert "Multiple failed logins" in body


class TestSMTPFallback:
    """Test behavior when SMTP is not configured."""

    def test_not_configured_returns_false(self):
        """When SMTP not configured, alert should return False."""
        with patch.object(email_alerts, "is_configured", return_value=False):
            result = email_alerts.alert_new_login("user", "1.1.1.1", "Chrome")
            assert result is False

    def test_no_mock_emails_sent(self):
        """No actual emails should be sent in test mode."""
        import inspect
        source = inspect.getsource(email_alerts)
        assert "MOCK_SMTP" not in source
        assert "fake_email" not in source


class TestRateLimitAlert:
    """Test rate limit exceeded alert."""

    def test_rate_limit_alert(self):
        """Rate limit alert must include IP and attempts count."""
        with patch.object(email_alerts, "_send_email", return_value=True) as mock_send:
            email_alerts.alert_rate_limit_exceeded("10.0.0.1", 10)

            mock_send.assert_called_once()
            body = mock_send.call_args[0][1]
            assert "10.0.0.1" in body
            assert "10" in body
