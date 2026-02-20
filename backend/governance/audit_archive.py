"""
audit_archive.py — Audit Safe Archive (Phase 6)

After a report is closed:
- Remove exploit payloads
- Keep: hash, timestamp, target, outcome
- Encrypt archive with AES-256-CBC

Uses Python's built-in cryptography (hashlib + os.urandom for key/IV).
AES-256 implemented via a minimal CBC mode using PyCryptodome if available,
otherwise falls back to XOR-based symmetric encryption with SHA-256 key derivation.
"""

import os
import json
import hashlib
import time
import struct
from typing import Dict, Any, Optional

CONFIG_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'config')
REPORTS_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'reports')
ARCHIVE_DIR = os.path.join(REPORTS_DIR, 'archived')
ARCHIVE_KEY_PATH = os.path.join(CONFIG_DIR, 'archive_key.key')

os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)


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

    # Generate new 256-bit key
    key = os.urandom(32)
    with open(ARCHIVE_KEY_PATH, 'wb') as f:
        f.write(key)
    return key


# ===================================================================
# AES-256-CBC Encryption (using PyCryptodome if available)
# ===================================================================

def _try_aes_encrypt(data: bytes, key: bytes) -> bytes:
    """Try AES-256-CBC encryption using PyCryptodome."""
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        iv = os.urandom(16)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ct = cipher.encrypt(pad(data, AES.block_size))
        return iv + ct
    except ImportError:
        return _fallback_encrypt(data, key)


def _try_aes_decrypt(data: bytes, key: bytes) -> bytes:
    """Try AES-256-CBC decryption using PyCryptodome."""
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
        iv = data[:16]
        ct = data[16:]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), AES.block_size)
    except ImportError:
        return _fallback_decrypt(data, key)


def _fallback_encrypt(data: bytes, key: bytes) -> bytes:
    """XOR-based symmetric fallback when PyCryptodome is unavailable."""
    iv = os.urandom(16)
    # Derive stream key from key + iv using SHA-256 chain
    stream = b''
    block = iv
    while len(stream) < len(data):
        block = hashlib.sha256(key + block).digest()
        stream += block
    encrypted = bytes(a ^ b for a, b in zip(data, stream[:len(data)]))
    return iv + encrypted


def _fallback_decrypt(data: bytes, key: bytes) -> bytes:
    """XOR-based symmetric fallback decryption."""
    iv = data[:16]
    ciphertext = data[16:]
    stream = b''
    block = iv
    while len(stream) < len(ciphertext):
        block = hashlib.sha256(key + block).digest()
        stream += block
    return bytes(a ^ b for a, b in zip(ciphertext, stream[:len(ciphertext)]))


# ===================================================================
# Archive Operations
# ===================================================================

def strip_payloads(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Remove exploit payloads from a closed report.
    Keep: hash, timestamp, target, outcome.
    """
    safe_fields = {}

    # Compute hash of original report for audit trail
    report_json = json.dumps(report, sort_keys=True, default=str)
    safe_fields['report_hash'] = hashlib.sha256(report_json.encode()).hexdigest()

    # Keep safe metadata only
    safe_fields['timestamp'] = report.get('timestamp', report.get('created_at', time.time()))
    safe_fields['target'] = report.get('target_id', report.get('target', 'unknown'))
    safe_fields['outcome'] = report.get('outcome', report.get('status', 'closed'))
    safe_fields['severity'] = report.get('severity', 'unknown')
    safe_fields['archived_at'] = time.time()

    # Explicitly excluded: payloads, reproduction steps, evidence, raw data
    return safe_fields


def archive_report(report: Dict[str, Any], report_id: str) -> str:
    """
    Archive a closed report:
    1. Strip exploit payloads
    2. Encrypt with AES-256
    3. Save to archive directory
    Returns the archive file path.
    """
    # Step 1: Strip payloads
    safe_data = strip_payloads(report)

    # Step 2: Serialize
    plaintext = json.dumps(safe_data, indent=2).encode('utf-8')

    # Step 3: Encrypt
    key = get_or_create_archive_key()
    encrypted = _try_aes_encrypt(plaintext, key)

    # Step 4: Save
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

    plaintext = _try_aes_decrypt(encrypted, key)
    return json.loads(plaintext.decode('utf-8'))
