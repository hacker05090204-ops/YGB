"""
audit_archive.py — Audit Safe Archive

After a report is closed:
- Remove exploit payloads
- Keep: hash, timestamp, target, outcome
- Encrypt archive with AES-256-CBC (PyCryptodome required)

FAIL-CLOSED: If PyCryptodome is not installed, raise RuntimeError.
No weak crypto fallback is permitted.
"""

import os
import json
import hashlib
import time
from typing import Dict, Any, Optional

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'config')
REPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'reports')
ARCHIVE_DIR = os.path.join(REPORTS_DIR, 'archived')
ARCHIVE_KEY_PATH = os.path.join(CONFIG_DIR, 'archive_key.key')

os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)


# ===================================================================
# Verify Strong Crypto Available (Phase 2: Fail-Closed)
# ===================================================================

def _require_pycryptodome():
    """Verify PyCryptodome is installed. Abort if not."""
    try:
        from Crypto.Cipher import AES  # noqa: F401
        from Crypto.Util.Padding import pad, unpad  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "Strong encryption required: install pycryptodome. "
            "Run: pip install pycryptodome. "
            "No weak crypto fallback is permitted."
        )


# Fail at import time if PyCryptodome is missing
_require_pycryptodome()


# ===================================================================
# Key Management
# ===================================================================

def get_or_create_archive_key() -> bytes:
    """Load or generate AES-256 archive encryption key."""
    if os.path.exists(ARCHIVE_KEY_PATH):
        with open(ARCHIVE_KEY_PATH, 'rb') as f:
            key = f.read()
        if len(key) >= 32:
            return key[:32]

    key = os.urandom(32)
    with open(ARCHIVE_KEY_PATH, 'wb') as f:
        f.write(key)
    return key


# ===================================================================
# AES-256-CBC Encryption (PyCryptodome only — no fallback)
# ===================================================================

def aes_encrypt(data: bytes, key: bytes) -> bytes:
    """AES-256-CBC encryption. Raises if PyCryptodome unavailable."""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(data, AES.block_size))
    return iv + ct


def aes_decrypt(data: bytes, key: bytes) -> bytes:
    """AES-256-CBC decryption. Raises if PyCryptodome unavailable."""
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    iv = data[:16]
    ct = data[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ct), AES.block_size)


# ===================================================================
# Archive Operations
# ===================================================================

def strip_payloads(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove exploit payloads from a closed report.
    Keep: hash, timestamp, target, outcome.
    """
    safe_fields = {}
    report_json = json.dumps(report, sort_keys=True, default=str)
    safe_fields['report_hash'] = hashlib.sha256(report_json.encode()).hexdigest()
    safe_fields['timestamp'] = report.get('timestamp', report.get('created_at', time.time()))
    safe_fields['target'] = report.get('target_id', report.get('target', 'unknown'))
    safe_fields['outcome'] = report.get('outcome', report.get('status', 'closed'))
    safe_fields['severity'] = report.get('severity', 'unknown')
    safe_fields['archived_at'] = time.time()
    return safe_fields


def archive_report(report: Dict[str, Any], report_id: str) -> str:
    """
    Archive a closed report:
    1. Strip exploit payloads
    2. Encrypt with AES-256-CBC
    3. Save to archive directory
    """
    safe_data = strip_payloads(report)
    plaintext = json.dumps(safe_data, indent=2).encode('utf-8')
    key = get_or_create_archive_key()
    encrypted = aes_encrypt(plaintext, key)

    archive_path = os.path.join(ARCHIVE_DIR, f"{report_id}.enc")
    with open(archive_path, 'wb') as f:
        f.write(encrypted)
    return archive_path


def read_archived_report(report_id: str) -> Optional[Dict[str, Any]]:
    """Decrypt and read an archived report."""
    archive_path = os.path.join(ARCHIVE_DIR, f"{report_id}.enc")
    if not os.path.exists(archive_path):
        return None

    key = get_or_create_archive_key()
    with open(archive_path, 'rb') as f:
        encrypted = f.read()

    plaintext = aes_decrypt(encrypted, key)
    return json.loads(plaintext.decode('utf-8'))
