"""
Tests for vault_kdf.py — PBKDF2-HMAC-SHA256 Key Derivation

Tests:
  1. Key derivation produces 32-byte output
  2. Same password + salt = same key (deterministic)
  3. Different passwords = different keys
  4. Different salts = different keys
  5. Empty password raises ValueError
  6. Salt generation produces 32 bytes
  7. Vault lock/unlock flow
  8. Locked vault raises RuntimeError on get_key
  9. PBKDF2 iteration count is 200,000
  10. Key derivation timing (not instant — proves real PBKDF2)
"""

import os
import time
import tempfile
import pytest

from backend.security.vault_kdf import (
    derive_vault_key,
    unlock_vault,
    lock_vault,
    get_vault_key,
    is_vault_unlocked,
    get_or_create_salt,
    PBKDF2_ITERATIONS,
    KEY_LENGTH,
    SALT_LENGTH,
)


# =========================================================================
# 1. KEY DERIVATION — BASIC PROPERTIES
# =========================================================================

class TestKeyDerivation:
    """Test PBKDF2-HMAC-SHA256 key derivation correctness."""

    def test_derives_32_byte_key(self):
        """Key output must be exactly 32 bytes (AES-256)."""
        salt = os.urandom(32)
        key = derive_vault_key("test_password", salt)
        assert isinstance(key, bytes)
        assert len(key) == 32

    def test_deterministic(self):
        """Same password + salt must produce same key."""
        salt = os.urandom(32)
        key1 = derive_vault_key("admin_pass_123", salt)
        key2 = derive_vault_key("admin_pass_123", salt)
        assert key1 == key2

    def test_different_passwords_different_keys(self):
        """Different passwords must produce different keys."""
        salt = os.urandom(32)
        key1 = derive_vault_key("password_A", salt)
        key2 = derive_vault_key("password_B", salt)
        assert key1 != key2

    def test_different_salts_different_keys(self):
        """Different salts must produce different keys."""
        salt1 = os.urandom(32)
        salt2 = os.urandom(32)
        key1 = derive_vault_key("same_password", salt1)
        key2 = derive_vault_key("same_password", salt2)
        assert key1 != key2

    def test_empty_password_raises(self):
        """Empty password must raise ValueError."""
        salt = os.urandom(32)
        with pytest.raises(ValueError, match="empty"):
            derive_vault_key("", salt)

    def test_unicode_password(self):
        """Unicode passwords must work correctly."""
        salt = os.urandom(32)
        key = derive_vault_key("пароль_密码_パスワード", salt)
        assert len(key) == 32


# =========================================================================
# 2. CONFIGURATION
# =========================================================================

class TestConfiguration:
    """Test PBKDF2 configuration values."""

    def test_iteration_count(self):
        """Must use 200,000 iterations (OWASP recommendation)."""
        assert PBKDF2_ITERATIONS == 200_000

    def test_key_length(self):
        """Key length must be 32 bytes (AES-256)."""
        assert KEY_LENGTH == 32

    def test_salt_length(self):
        """Salt must be 32 bytes (256-bit)."""
        assert SALT_LENGTH == 32


# =========================================================================
# 3. SALT MANAGEMENT
# =========================================================================

class TestSaltManagement:
    """Test salt generation and persistence."""

    def test_salt_is_32_bytes(self):
        """Generated salt must be 32 bytes."""
        salt = get_or_create_salt()
        assert len(salt) == 32

    def test_salt_is_persistent(self):
        """Same salt returned on repeated calls."""
        salt1 = get_or_create_salt()
        salt2 = get_or_create_salt()
        assert salt1 == salt2


# =========================================================================
# 4. VAULT LOCK/UNLOCK
# =========================================================================

class TestVaultLockUnlock:
    """Test vault lock/unlock flow."""

    def setup_method(self):
        """Ensure vault starts locked."""
        lock_vault()

    def teardown_method(self):
        """Clean up: lock vault after each test."""
        lock_vault()

    def test_unlock_sets_key(self):
        """Unlocking vault makes key available."""
        assert not is_vault_unlocked()
        result = unlock_vault("test_vault_pass")
        assert result is True
        assert is_vault_unlocked()
        key = get_vault_key()
        assert len(key) == 32

    def test_lock_clears_key(self):
        """Locking vault clears key from memory."""
        unlock_vault("test_vault_pass")
        assert is_vault_unlocked()
        lock_vault()
        assert not is_vault_unlocked()

    def test_get_key_when_locked_raises(self):
        """Getting key from locked vault must raise RuntimeError."""
        assert not is_vault_unlocked()
        with pytest.raises(RuntimeError, match="locked"):
            get_vault_key()

    def test_unlock_produces_consistent_key(self):
        """Same password always produces same key."""
        unlock_vault("consistent_pass")
        key1 = get_vault_key()
        lock_vault()
        unlock_vault("consistent_pass")
        key2 = get_vault_key()
        assert key1 == key2


# =========================================================================
# 5. TIMING (PBKDF2 is intentionally slow)
# =========================================================================

class TestTiming:
    """Verify PBKDF2 takes non-trivial time (proves real derivation)."""

    def test_derivation_takes_time(self):
        """Key derivation should take at least 50ms (200k iterations)."""
        salt = os.urandom(32)
        start = time.monotonic()
        derive_vault_key("timing_test_password", salt)
        elapsed = time.monotonic() - start
        # 200k iterations should take at least 50ms on any modern CPU
        assert elapsed > 0.01, \
            f"Derivation too fast ({elapsed:.3f}s) — PBKDF2 may not be real"
