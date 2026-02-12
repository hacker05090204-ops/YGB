"""
YGB Email Alert System — SMTP-based Notifications

Sends real email alerts for:
- New login events
- Login from new/unrecognized device
- Multiple devices active simultaneously
- Suspicious activity (failed logins, unusual patterns)

Configuration via .env:
- SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
- ALERT_EMAIL_TO, ALERT_EMAIL_FROM
- SMTP_USE_TLS

ZERO placeholder emails. ZERO mock connections.
If SMTP not configured, alerts are logged but NOT sent.
"""

import os
import sys
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

logger = logging.getLogger("ygb.alerts")

# SMTP Configuration from env
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM", SMTP_USER)


def is_configured() -> bool:
    """Check if SMTP is properly configured."""
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS and ALERT_EMAIL_TO)


def _send_email(subject: str, body_html: str, to_email: str = None) -> bool:
    """
    Send an email via SMTP. Returns True if sent successfully.
    If SMTP not configured, logs the alert instead.
    """
    recipient = to_email or ALERT_EMAIL_TO

    if not is_configured():
        logger.warning(
            f"[ALERT NOT SENT - SMTP NOT CONFIGURED] {subject}: {body_html[:200]}"
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[YGB Alert] {subject}"
        msg["From"] = ALERT_EMAIL_FROM
        msg["To"] = recipient

        html_part = MIMEText(body_html, "html")
        msg.attach(html_part)

        if SMTP_USE_TLS:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
            server.starttls()
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)

        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(ALERT_EMAIL_FROM, [recipient], msg.as_string())
        server.quit()

        logger.info(f"[ALERT SENT] {subject} -> {recipient}")
        return True

    except Exception as e:
        logger.error(f"[ALERT FAILED] {subject}: {str(e)}")
        return False


# =============================================================================
# ALERT TRIGGERS
# =============================================================================

def alert_new_login(user_name: str, ip_address: str, user_agent: str,
                    location: str = "Unknown") -> bool:
    """Send alert for a new login."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"New Login: {user_name}"
    body = f"""
    <h2>🔐 New Login Detected</h2>
    <table style="border-collapse: collapse; width: 100%;">
        <tr><td><strong>User:</strong></td><td>{user_name}</td></tr>
        <tr><td><strong>IP Address:</strong></td><td>{ip_address}</td></tr>
        <tr><td><strong>User Agent:</strong></td><td>{user_agent}</td></tr>
        <tr><td><strong>Location:</strong></td><td>{location}</td></tr>
        <tr><td><strong>Time:</strong></td><td>{now}</td></tr>
    </table>
    """
    return _send_email(subject, body)


def alert_new_device(user_name: str, device_hash: str, ip_address: str,
                     user_agent: str) -> bool:
    """Send alert for login from a new/unrecognized device."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"⚠️ New Device: {user_name}"
    body = f"""
    <h2>🆕 Login From New Device</h2>
    <p style="color: #e74c3c; font-weight: bold;">
        A login was detected from an unrecognized device.
    </p>
    <table style="border-collapse: collapse; width: 100%;">
        <tr><td><strong>User:</strong></td><td>{user_name}</td></tr>
        <tr><td><strong>Device Hash:</strong></td><td>{device_hash}</td></tr>
        <tr><td><strong>IP Address:</strong></td><td>{ip_address}</td></tr>
        <tr><td><strong>User Agent:</strong></td><td>{user_agent}</td></tr>
        <tr><td><strong>Time:</strong></td><td>{now}</td></tr>
    </table>
    <p>If this was not you, change your password immediately.</p>
    """
    return _send_email(subject, body)


def alert_multiple_devices(user_name: str, device_count: int,
                           devices: List[Dict[str, Any]] = None) -> bool:
    """Send alert when multiple devices are active simultaneously."""
    subject = f"⚠️ Multiple Devices Active: {user_name}"

    device_rows = ""
    if devices:
        for d in devices[:5]:  # Max 5 devices shown
            device_rows += f"""
            <tr>
                <td>{d.get('device_hash', 'N/A')[:8]}...</td>
                <td>{d.get('ip_address', 'N/A')}</td>
                <td>{d.get('last_seen', 'N/A')}</td>
            </tr>"""

    body = f"""
    <h2>📱 Multiple Devices Active</h2>
    <p><strong>{device_count}</strong> devices are currently active for user <strong>{user_name}</strong>.</p>
    <table style="border-collapse: collapse; width: 100%;">
        <tr><th>Device</th><th>IP</th><th>Last Seen</th></tr>
        {device_rows}
    </table>
    """
    return _send_email(subject, body)


def alert_suspicious_activity(description: str, ip_address: str = None,
                              user_name: str = None,
                              metadata: Dict[str, Any] = None) -> bool:
    """Send alert for suspicious activity."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    subject = f"🚨 Suspicious Activity{' - ' + user_name if user_name else ''}"

    meta_rows = ""
    if metadata:
        for k, v in metadata.items():
            meta_rows += f"<tr><td><strong>{k}:</strong></td><td>{v}</td></tr>"

    body = f"""
    <h2>🚨 Suspicious Activity Detected</h2>
    <p style="color: #e74c3c; font-weight: bold;">{description}</p>
    <table style="border-collapse: collapse; width: 100%;">
        <tr><td><strong>User:</strong></td><td>{user_name or 'Unknown'}</td></tr>
        <tr><td><strong>IP Address:</strong></td><td>{ip_address or 'Unknown'}</td></tr>
        <tr><td><strong>Time:</strong></td><td>{now}</td></tr>
        {meta_rows}
    </table>
    """
    return _send_email(subject, body)


def alert_rate_limit_exceeded(ip_address: str, attempts: int) -> bool:
    """Send alert when rate limit is exceeded."""
    subject = f"🛑 Rate Limit Exceeded: {ip_address}"
    body = f"""
    <h2>🛑 Rate Limit Exceeded</h2>
    <p>IP address <strong>{ip_address}</strong> has exceeded the login rate limit 
    with <strong>{attempts}</strong> attempts.</p>
    <p>This IP has been temporarily blocked from further login attempts.</p>
    """
    return _send_email(subject, body)
