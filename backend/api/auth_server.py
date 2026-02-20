import os
import json
import secrets
import hashlib
import time
import math
import bcrypt
import smtplib
from email.message import EmailMessage
from collections import defaultdict
from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

# ===================================================================
# Directories
# ===================================================================

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'config')
REPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'reports')

USERS_FILE = os.path.join(CONFIG_DIR, 'users.json')
DEVICES_FILE = os.path.join(CONFIG_DIR, 'auth_trusted_devices.json')
SESSIONS_FILE = os.path.join(CONFIG_DIR, 'auth_sessions.json')
OTPS_FILE = os.path.join(CONFIG_DIR, 'auth_otps.json')
AUDIT_LOG = os.path.join(REPORTS_DIR, 'auth_audit.log')


def _ensure_auth_dirs():
    """Create auth directories lazily, not at import time."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)

# ===================================================================
# Rate Limit Constants
# ===================================================================

LOGIN_RATE_LIMIT = 5         # Max 5 attempts per IP per window
LOGIN_RATE_WINDOW = 600      # 10-minute window (seconds)
OTP_RATE_LIMIT = 3           # Max 3 OTP requests per window
OTP_RATE_WINDOW = 600        # 10-minute window (seconds)
BACKOFF_BASE_SECONDS = 2     # Exponential backoff base
DEVICE_TRUST_TTL = 30 * 86400  # 30 days in seconds

# In-memory rate limit stores (reset on server restart)
_login_attempts: dict = defaultdict(list)   # IP -> [timestamps]
_otp_requests: dict = defaultdict(list)     # username -> [timestamps]
_failure_counts: dict = defaultdict(int)    # IP -> consecutive failures

# ===================================================================
# Helpers
# ===================================================================

def load_json(filepath: str, default=None):
    if default is None:
        default = {}
    if not os.path.exists(filepath):
        return default
    with open(filepath, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def save_json(filepath: str, data):
    tmp_path = filepath + ".tmp"
    with open(tmp_path, 'w') as f:
        json.dump(data, f, indent=2)
    os.replace(tmp_path, filepath)


def log_audit(event: str, ip: str, username: str, success: bool, details: str = ""):
    """Audit logger — NEVER logs OTP values."""
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    status = "SUCCESS" if success else "FAILED"
    with open(AUDIT_LOG, "a") as f:
        f.write(f"[{timestamp}] [{ip}] {status} | Action={event} | User={username} | {details}\n")


# ===================================================================
# Phase 2 — Rate Limiting
# ===================================================================

def _prune_window(timestamps: list, window_seconds: int) -> list:
    """Remove timestamps older than the rate limit window."""
    cutoff = time.time() - window_seconds
    return [t for t in timestamps if t > cutoff]


def check_login_rate(ip: str):
    """Enforce login rate limit: 5 attempts per 10 minutes per IP."""
    _login_attempts[ip] = _prune_window(_login_attempts[ip], LOGIN_RATE_WINDOW)
    if len(_login_attempts[ip]) >= LOGIN_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Try again in {LOGIN_RATE_WINDOW // 60} minutes."
        )
    _login_attempts[ip].append(time.time())


def check_otp_rate(username: str):
    """Enforce OTP rate limit: 3 OTP requests per 10 minutes."""
    _otp_requests[username] = _prune_window(_otp_requests[username], OTP_RATE_WINDOW)
    if len(_otp_requests[username]) >= OTP_RATE_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Too many OTP requests. Try again in {OTP_RATE_WINDOW // 60} minutes."
        )
    _otp_requests[username].append(time.time())


def apply_backoff(ip: str):
    """Apply exponential backoff delay based on consecutive failure count."""
    failures = _failure_counts.get(ip, 0)
    if failures > 0:
        delay = min(BACKOFF_BASE_SECONDS * (2 ** (failures - 1)), 60)
        time.sleep(delay)


def record_failure(ip: str):
    _failure_counts[ip] = _failure_counts.get(ip, 0) + 1


def clear_failures(ip: str):
    _failure_counts[ip] = 0


# ===================================================================
# Device Fingerprinting
# ===================================================================

class LoginRequest(BaseModel):
    username: str
    password: str
    device_id: str


def generate_device_fingerprint(user_agent: str, ip: str, device_id: str) -> str:
    raw = f"{user_agent}|{ip}|{device_id}".encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def get_ip_subnet(ip: str) -> str:
    """Extract /24 subnet for IP change detection."""
    parts = ip.split('.')
    if len(parts) == 4:
        return '.'.join(parts[:3])
    return ip  # IPv6 or unknown — treat as unique


def is_trusted_device(username: str, fingerprint: str, current_ip: str) -> bool:
    """Check device trust with 30-day expiration and IP subnet change detection."""
    trusted = load_json(DEVICES_FILE, default={})
    user_devices = trusted.get(username, {})

    if fingerprint not in user_devices:
        return False

    device_info = user_devices[fingerprint]

    # Phase 7: Check 30-day expiration
    trusted_at = device_info.get("trusted_at", 0)
    if time.time() - trusted_at > DEVICE_TRUST_TTL:
        # Expired — remove and require re-auth
        del user_devices[fingerprint]
        save_json(DEVICES_FILE, trusted)
        return False

    # Phase 7: Check IP subnet change
    original_subnet = get_ip_subnet(device_info.get("ip", ""))
    current_subnet = get_ip_subnet(current_ip)
    if original_subnet != current_subnet:
        return False  # Significant IP change → re-require OTP

    return True


def trust_device(username: str, fingerprint: str, ip: str):
    """Register device as trusted with timestamp and IP."""
    trusted = load_json(DEVICES_FILE, default={})
    if username not in trusted:
        trusted[username] = {}
    trusted[username][fingerprint] = {
        "trusted_at": time.time(),
        "ip": ip,
    }
    save_json(DEVICES_FILE, trusted)


# ===================================================================
# OTP System (hashed storage only, never logged)
# ===================================================================

def send_otp_email(to_email: str, otp: str) -> bool:
    from_email = os.environ.get("ALERT_EMAIL_FROM") or os.environ.get("SMTP_USER")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_user or not smtp_pass or not from_email:
        return False

    msg = EmailMessage()
    msg.set_content(
        f"Your YGB Authentication OTP is: {otp}\n\n"
        "This code is valid for 5 minutes and is single-use."
    )
    msg['Subject'] = 'YGB Login OTP'
    msg['From'] = from_email
    msg['To'] = to_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
        return True
    except Exception:
        return False


def send_admin_alert_new_device(username: str, ip: str, fingerprint: str):
    """Phase 7: Alert admin on new device trust."""
    admin_email = os.environ.get("ALERT_EMAIL_TO")
    if not admin_email:
        return
    from_email = os.environ.get("ALERT_EMAIL_FROM") or os.environ.get("SMTP_USER")
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_user or not smtp_pass or not from_email:
        return

    msg = EmailMessage()
    msg.set_content(
        f"SECURITY ALERT: New device trusted for user '{username}'.\n\n"
        f"IP: {ip}\n"
        f"Fingerprint: {fingerprint}\n"
        f"Time: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n\n"
        "If this was not you, revoke the device immediately."
    )
    msg['Subject'] = 'YGB Security Alert — New Device Login'
    msg['From'] = from_email
    msg['To'] = admin_email

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.send_message(msg)
    except Exception:
        pass  # Alert is best-effort; login should not fail due to admin alert


def generate_and_store_otp(username: str, to_email: str) -> bool:
    """Generate 128-bit random OTP, store SHA256 hash only, email plaintext."""
    raw_otp_int = secrets.randbits(128)
    otp_str = f"{raw_otp_int % 10**12:012d}"

    # Store hashed only — plaintext NEVER persisted or logged
    otp_hash = hashlib.sha256(otp_str.encode()).hexdigest()

    otps = load_json(OTPS_FILE, default={})
    otps[username] = {
        "hash": otp_hash,
        "expires_at": time.time() + 300,
        "used": False,
    }
    save_json(OTPS_FILE, otps)

    return send_otp_email(to_email, otp_str)


# ===================================================================
# Session System
# ===================================================================

def create_session(username: str, fingerprint: str, ip: str) -> str:
    session_token = secrets.token_hex(32)
    sessions = load_json(SESSIONS_FILE, default={})

    sessions[session_token] = {
        "username": username,
        "fingerprint": fingerprint,
        "ip": ip,
        "created_at": time.time(),
        "expires_at": time.time() + (24 * 3600),
        "active": True,
    }
    save_json(SESSIONS_FILE, sessions)
    return session_token


# ===================================================================
# Endpoints
# ===================================================================

@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response,
          user_agent: Optional[str] = Header(None)):
    ip = request.client.host
    ua = user_agent or "Unknown"

    # Phase 2: Rate limit + exponential backoff
    check_login_rate(ip)
    apply_backoff(ip)

    # 1. Verify credentials
    users = load_json(USERS_FILE, default={})
    if req.username not in users:
        record_failure(ip)
        log_audit("login", ip, req.username, False, "User not found")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    user_data = users[req.username]
    stored_hash = user_data.get("password_hash", "").encode('utf-8')

    if not bcrypt.checkpw(req.password.encode('utf-8'), stored_hash):
        record_failure(ip)
        log_audit("login", ip, req.username, False, "Invalid password")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    clear_failures(ip)

    # 2. Check Device Trust (with 30-day expiry + IP change detection)
    fingerprint = generate_device_fingerprint(ua, ip, req.device_id)
    if is_trusted_device(req.username, fingerprint, ip):
        token = create_session(req.username, fingerprint, ip)
        log_audit("login", ip, req.username, True, "Trusted device login")

        response.set_cookie(
            key="session_token",
            value=token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=24 * 3600,
        )
        return {"status": "success", "message": "Logged in", "require_otp": False}
    else:
        # New/expired/IP-changed device → Require OTP
        check_otp_rate(req.username)

        email = user_data.get("email")
        if not email:
            log_audit("login", ip, req.username, False, "No email configured for OTP")
            raise HTTPException(status_code=500, detail="Account configuration error")

        success = generate_and_store_otp(req.username, email)
        if not success:
            log_audit("login", ip, req.username, False, "SMTP delivery failed — login aborted")
            raise HTTPException(status_code=500, detail="Login failed: unable to send OTP")

        log_audit("login_otp_sent", ip, req.username, True, "OTP dispatched to new device")
        return {
            "status": "pending",
            "message": "OTP sent to registered email",
            "require_otp": True,
            "fingerprint": fingerprint,
        }


class OTPVerifyRequest(BaseModel):
    username: str
    otp: str
    fingerprint: str


@router.post("/verify-otp")
def verify_otp(req: OTPVerifyRequest, request: Request, response: Response):
    ip = request.client.host
    otps = load_json(OTPS_FILE, default={})

    if req.username not in otps:
        raise HTTPException(status_code=401, detail="No pending OTP")

    otp_data = otps[req.username]
    if otp_data["used"] or time.time() > otp_data["expires_at"]:
        raise HTTPException(status_code=401, detail="OTP expired or already used")

    candidate_hash = hashlib.sha256(req.otp.encode()).hexdigest()
    if candidate_hash != otp_data["hash"]:
        log_audit("verify_otp", ip, req.username, False, "Invalid OTP hash")
        raise HTTPException(status_code=401, detail="Invalid OTP")

    # Mark used
    otp_data["used"] = True
    save_json(OTPS_FILE, otps)

    # Trust device and issue session
    trust_device(req.username, req.fingerprint, ip)
    token = create_session(req.username, req.fingerprint, ip)

    # Phase 7: Admin alert on new device trust
    send_admin_alert_new_device(req.username, ip, req.fingerprint)

    log_audit("verify_otp", ip, req.username, True, "OTP verified, device trusted")

    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=24 * 3600,
    )
    return {"status": "success", "message": "Logged in and device trusted"}


# ===================================================================
# Phase 8 — Admin Panel (secrets masked)
# ===================================================================

@router.get("/admin/sessions")
def admin_get_sessions():
    """
    Admin can view: User ID, device fingerprint, IP, session time, target assignments.
    Admin CANNOT view: HMAC secrets, SMTP password, device private keys.
    All secrets are masked.
    """
    sessions = load_json(SESSIONS_FILE, default={})
    active_sessions = []

    for _token, data in sessions.items():
        if data.get("active") and time.time() < data.get("expires_at", 0):
            active_sessions.append({
                "username": data["username"],
                "fingerprint": data.get("fingerprint", ""),
                "ip": data.get("ip", "***"),
                "created_at": data["created_at"],
                "expires_at": data["expires_at"],
                # Token, HMAC keys, SMTP passwords are NEVER exposed
            })

    return {"status": "success", "active_sessions": active_sessions}


@router.get("/admin/devices")
def admin_get_devices():
    """View trusted devices per user. No private keys or secrets exposed."""
    trusted = load_json(DEVICES_FILE, default={})
    result = {}
    for username, devices in trusted.items():
        result[username] = []
        for fp, info in devices.items():
            result[username].append({
                "fingerprint": fp,
                "trusted_at": info.get("trusted_at"),
                "ip": info.get("ip", "***"),
                # Private keys / HMAC secrets are NEVER included
            })
    return {"status": "success", "devices": result}
