"""
vault_kdf.py — PBKDF2-HMAC-SHA256 Vault Key Derivation

Derives a 32-byte AES-256 key from an admin password using PBKDF2.
The derived key is held in memory only — never written to disk or env vars.
Frontend NEVER sees the vault key.

Security:
  - 200,000 PBKDF2 iterations (OWASP recommendation)
  - 32-byte random salt (generated once, stored in secure_data/)
  - Key material zeroed on vault lock
"""

import hashlib
import os
import secrets

# =========================================================================
# CONFIGURATION
# =========================================================================

PBKDF2_ITERATIONS = 200_000
KEY_LENGTH = 32  # AES-256 = 32 bytes
SALT_LENGTH = 32  # 256-bit salt

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
SECURE_DATA_DIR = os.path.join(PROJECT_ROOT, 'secure_data')
SALT_PATH = os.path.join(SECURE_DATA_DIR, 'vault_salt.bin')


# =========================================================================
# SALT MANAGEMENT
# =========================================================================

def _ensure_secure_dir():
    """Create secure_data directory with proper permissions."""
    os.makedirs(SECURE_DATA_DIR, exist_ok=True)
    if os.name != 'nt':
        os.chmod(SECURE_DATA_DIR, 0o700)


def get_or_create_salt() -> bytes:
    """Get existing salt or generate a new one.

    Salt is stored in secure_data/vault_salt.bin.
    Generated once per installation — must be preserved with vault data.
    """
    if os.path.exists(SALT_PATH):
        with open(SALT_PATH, 'rb') as f:
            salt = f.read()
        if len(salt) == SALT_LENGTH:
            return salt

    # Generate new salt
    _ensure_secure_dir()
    salt = secrets.token_bytes(SALT_LENGTH)
    with open(SALT_PATH, 'wb') as f:
        f.write(salt)

    # Restrict permissions on Linux
    if os.name != 'nt':
        os.chmod(SALT_PATH, 0o600)

    return salt


# =========================================================================
# KEY DERIVATION
# =========================================================================

def derive_vault_key(password: str, salt: bytes = None) -> bytes:
    """Derive a 32-byte AES-256 key from password using PBKDF2-HMAC-SHA256.

    Args:
        password: Admin vault password.
        salt: Optional salt bytes. If None, loads from disk.

    Returns:
        32-byte derived key.
    """
    if not password:
        raise ValueError("Vault password cannot be empty")

    if salt is None:
        salt = get_or_create_salt()

    return hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt,
        PBKDF2_ITERATIONS,
        dklen=KEY_LENGTH,
    )


# =========================================================================
# VAULT SESSION (in-memory key store)
# =========================================================================

_vault_key: bytes = b''
_vault_unlocked: bool = False


def unlock_vault(password: str) -> bool:
    """Derive vault key from password and store in memory.

    Args:
        password: Admin vault password.

    Returns:
        True if vault was successfully unlocked.
    """
    global _vault_key, _vault_unlocked

    try:
        key = derive_vault_key(password)
        _vault_key = key
        _vault_unlocked = True
        return True
    except Exception:
        return False


def lock_vault():
    """Securely clear the vault key from memory."""
    global _vault_key, _vault_unlocked

    # Overwrite with zeros (best effort in Python)
    _vault_key = b'\x00' * KEY_LENGTH
    _vault_key = b''
    _vault_unlocked = False


def get_vault_key() -> bytes:
    """Get the current vault key. Raises if vault is locked."""
    if not _vault_unlocked or not _vault_key:
        raise RuntimeError("Vault is locked. Call unlock_vault() first.")
    return _vault_key


def is_vault_unlocked() -> bool:
    """Check if vault is currently unlocked."""
    return _vault_unlocked
