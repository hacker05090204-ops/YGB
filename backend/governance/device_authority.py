"""
device_authority.py — Zero-Trust Device Authority Policy

Governance logic for device pairing approval:
  - If device_id in trusted_whitelist.json → auto-approve
  - Otherwise → require OTP approval from admin
  - Signs device certificate with authority key
  - Writes approved cert to storage/certs/device_cert.json

C++ handles runtime enforcement.
Python handles governance logic ONLY.

NO HMAC secret shared with workers.
NO auto-approve for unknown devices.
"""

import hashlib
import json
import os
import secrets
import time
from typing import Optional, Dict, Any

# =========================================================================
# PATHS
# =========================================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

WHITELIST_PATH = os.path.join(PROJECT_ROOT, 'config', 'trusted_whitelist.json')
PAIRING_DIR = os.path.join(PROJECT_ROOT, 'storage', 'pairing_requests')
CERT_DIR = os.path.join(PROJECT_ROOT, 'storage', 'certs')
REVOCATION_PATH = os.path.join(PROJECT_ROOT, 'config', 'revoked_devices.json')

# =========================================================================
# CONFIGURATION
# =========================================================================

CERT_VALIDITY_DAYS = 90
OTP_LENGTH = 6
OTP_EXPIRY_SECONDS = 300  # 5 minutes


# =========================================================================
# WHITELIST MANAGEMENT
# =========================================================================

def load_whitelist() -> list:
    """Load trusted device whitelist."""
    if not os.path.exists(WHITELIST_PATH):
        return []
    try:
        with open(WHITELIST_PATH, 'r') as f:
            data = json.load(f)
        return data.get('trusted_devices', [])
    except (json.JSONDecodeError, OSError):
        return []


def is_whitelisted(device_id: str) -> bool:
    """Check if device is in trusted whitelist."""
    whitelist = load_whitelist()
    return any(
        d.get('device_id') == device_id
        for d in whitelist
    )


# =========================================================================
# REVOCATION LIST
# =========================================================================

def load_revocation_list() -> list:
    """Load revoked device IDs."""
    if not os.path.exists(REVOCATION_PATH):
        return []
    try:
        with open(REVOCATION_PATH, 'r') as f:
            data = json.load(f)
        return data.get('revoked_devices', [])
    except (json.JSONDecodeError, OSError):
        return []


def is_revoked(device_id: str) -> bool:
    """Check if device is revoked."""
    revoked = load_revocation_list()
    return device_id in revoked


def revoke_device(device_id: str, reason: str = "admin_revoked") -> bool:
    """Add device to revocation list."""
    revoked = load_revocation_list()
    if device_id in revoked:
        return True  # Already revoked

    revoked.append(device_id)
    os.makedirs(os.path.dirname(REVOCATION_PATH), exist_ok=True)
    with open(REVOCATION_PATH, 'w') as f:
        json.dump({
            'revoked_devices': revoked,
            'last_updated': int(time.time()),
        }, f, indent=2)

    # Remove cert if exists
    cert_path = os.path.join(CERT_DIR, f"{device_id}", "device_cert.json")
    if os.path.exists(cert_path):
        os.remove(cert_path)

    return True


# =========================================================================
# OTP GENERATION
# =========================================================================

_pending_otps: Dict[str, Dict[str, Any]] = {}


def generate_otp(device_id: str) -> str:
    """Generate a one-time password for admin approval."""
    otp = ''.join([str(secrets.randbelow(10)) for _ in range(OTP_LENGTH)])
    _pending_otps[device_id] = {
        'otp': otp,
        'created_at': time.time(),
        'expires_at': time.time() + OTP_EXPIRY_SECONDS,
    }
    return otp


def verify_otp(device_id: str, otp: str) -> bool:
    """Verify OTP for a device."""
    if device_id not in _pending_otps:
        return False

    entry = _pending_otps[device_id]
    if time.time() > entry['expires_at']:
        del _pending_otps[device_id]
        return False

    if entry['otp'] != otp:
        return False

    del _pending_otps[device_id]
    return True


# =========================================================================
# CERTIFICATE SIGNING
# =========================================================================

def sign_certificate(cert_data: dict) -> str:
    """Sign certificate data with authority key.

    In production: uses Ed25519 private key.
    Here: HMAC-SHA256 with authority secret.
    Workers NEVER receive this key.
    """
    canonical = json.dumps(cert_data, sort_keys=True, separators=(',', ':'))
    # Use authority-only secret for signing
    authority_secret = os.environ.get('YGB_AUTHORITY_SECRET', '').strip()
    if not authority_secret:
        # Fall back to HMAC secret on authority node
        authority_secret = os.environ.get('YGB_HMAC_SECRET', '').strip()
    if not authority_secret:
        raise RuntimeError("Authority signing key not configured")

    signature = hashlib.sha256(
        (canonical + authority_secret).encode('utf-8')
    ).hexdigest()
    return signature


def issue_certificate(device_id: str, role: str,
                      public_key: str, mesh_ip: str) -> dict:
    """Issue a signed device certificate."""
    now = int(time.time())
    cert_data = {
        'device_id': device_id,
        'role': role,
        'public_key': public_key,
        'mesh_ip': mesh_ip,
        'issued_at': now,
        'expires_at': now + (CERT_VALIDITY_DAYS * 86400),
        'cert_version': 1,
    }

    cert_data['signature'] = sign_certificate(cert_data)
    return cert_data


def save_certificate(cert: dict, device_id: str) -> str:
    """Save signed certificate for device to pick up."""
    # Save to device-specific directory
    device_cert_dir = os.path.join(CERT_DIR, device_id)
    os.makedirs(device_cert_dir, exist_ok=True)
    cert_path = os.path.join(device_cert_dir, 'device_cert.json')
    with open(cert_path, 'w') as f:
        json.dump(cert, f, indent=2)

    # Also save to default pickup location
    os.makedirs(CERT_DIR, exist_ok=True)
    default_path = os.path.join(CERT_DIR, 'device_cert.json')
    with open(default_path, 'w') as f:
        json.dump(cert, f, indent=2)

    return cert_path


# =========================================================================
# PAIRING REQUEST PROCESSING
# =========================================================================

def load_pairing_request(device_id: str) -> Optional[dict]:
    """Load a pending pairing request."""
    path = os.path.join(PAIRING_DIR, f"{device_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_pending_requests() -> list:
    """List all pending pairing requests."""
    if not os.path.exists(PAIRING_DIR):
        return []

    requests = []
    for filename in os.listdir(PAIRING_DIR):
        if filename.endswith('.json'):
            path = os.path.join(PAIRING_DIR, filename)
            try:
                with open(path, 'r') as f:
                    req = json.load(f)
                if req.get('status') == 'pending':
                    requests.append(req)
            except (json.JSONDecodeError, OSError):
                continue
    return requests


def _assign_mesh_ip(device_id: str) -> str:
    """Assign a mesh IP from the 10.0.0.0/24 range."""
    # Hash device_id to get deterministic IP assignment
    h = hashlib.sha256(device_id.encode()).digest()
    # Use bytes 0-1 for IP, range 10.0.0.2 to 10.0.0.254
    host = (h[0] % 253) + 2  # 2-254
    return f"10.0.0.{host}"


def process_pairing_request(device_id: str,
                             admin_otp: Optional[str] = None) -> dict:
    """Process a pairing request.

    If whitelisted: auto-approve.
    If OTP provided and valid: approve.
    Otherwise: generate OTP and require admin approval.
    """
    # Check revocation first
    if is_revoked(device_id):
        return {'status': 'denied', 'reason': 'device_revoked'}

    # Load request
    request = load_pairing_request(device_id)
    if not request:
        return {'status': 'error', 'reason': 'no_pending_request'}

    role = request.get('requested_role', 'WORKER')
    public_key = request.get('public_key', '')

    # Path 1: Whitelisted → auto-approve
    if is_whitelisted(device_id):
        mesh_ip = _assign_mesh_ip(device_id)
        cert = issue_certificate(device_id, role, public_key, mesh_ip)
        cert_path = save_certificate(cert, device_id)

        # Mark request as approved
        _update_request_status(device_id, 'approved')

        return {
            'status': 'approved',
            'cert_path': cert_path,
            'mesh_ip': mesh_ip,
            'role': role,
        }

    # Path 2: OTP provided → verify and approve
    if admin_otp:
        if verify_otp(device_id, admin_otp):
            mesh_ip = _assign_mesh_ip(device_id)
            cert = issue_certificate(device_id, role, public_key, mesh_ip)
            cert_path = save_certificate(cert, device_id)
            _update_request_status(device_id, 'approved')
            return {
                'status': 'approved',
                'cert_path': cert_path,
                'mesh_ip': mesh_ip,
                'role': role,
            }
        else:
            return {'status': 'denied', 'reason': 'invalid_otp'}

    # Path 3: Unknown device → generate OTP, require admin
    otp = generate_otp(device_id)
    return {
        'status': 'pending_approval',
        'otp': otp,
        'message': f'OTP {otp} sent to admin. Expires in {OTP_EXPIRY_SECONDS}s.',
    }


def _update_request_status(device_id: str, status: str):
    """Update pairing request status."""
    path = os.path.join(PAIRING_DIR, f"{device_id}.json")
    if not os.path.exists(path):
        return
    try:
        with open(path, 'r') as f:
            data = json.load(f)
        data['status'] = status
        data['processed_at'] = int(time.time())
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    except (json.JSONDecodeError, OSError):
        pass
