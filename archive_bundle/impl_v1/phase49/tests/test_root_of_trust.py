"""
Root of Trust Tests - Phase 49
================================

Tests for root-of-trust verification:
1. Key pinning
2. Key revocation
3. Key rotation policy
4. Time integrity
5. Emergency lock
"""

import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase49.runtime.root_of_trust import (
    verify_key_fingerprint,
    get_pinned_key,
    is_key_revoked,
    check_revocation_on_startup,
    KeyRotationPolicy,
    TimeIntegrityChecker,
    SystemLock,
    EmergencyLockMode,
    TRUSTED_KEY_FINGERPRINT,
    TRUSTED_KEY_VERSION,
)


class TestKeyPinning(unittest.TestCase):
    """Test trusted key pinning."""
    
    def test_trusted_key_accepted(self):
        """Compiled-in key is accepted."""
        is_trusted, reason = verify_key_fingerprint(TRUSTED_KEY_FINGERPRINT)
        self.assertTrue(is_trusted)
    
    def test_untrusted_key_rejected(self):
        """Unknown key is rejected."""
        fake_key = "0000000000000000000000000000000000000000000000000000000000000000"
        is_trusted, reason = verify_key_fingerprint(fake_key)
        self.assertFalse(is_trusted)
        self.assertIn("NOT TRUSTED", reason)
    
    def test_pinned_key_has_version(self):
        """Pinned key has version number."""
        key = get_pinned_key()
        self.assertIsNotNone(key.version)
        self.assertGreaterEqual(key.version, 1)


class TestKeyRevocation(unittest.TestCase):
    """Test key revocation."""
    
    def test_non_revoked_key_passes(self):
        """Non-revoked key passes check."""
        is_revoked, reason = is_key_revoked(TRUSTED_KEY_FINGERPRINT)
        self.assertFalse(is_revoked)
    
    def test_startup_check_passes(self):
        """Startup revocation check passes for valid key."""
        safe, msg = check_revocation_on_startup()
        self.assertTrue(safe)


class TestKeyRotationPolicy(unittest.TestCase):
    """Test key rotation policy."""
    
    def test_current_key_accepted(self):
        """Current key version accepted."""
        policy = KeyRotationPolicy()
        accepted, reason = policy.accept_key(
            TRUSTED_KEY_FINGERPRINT,
            TRUSTED_KEY_VERSION,
        )
        self.assertTrue(accepted)
    
    def test_downgrade_rejected(self):
        """Downgrade to older version rejected."""
        policy = KeyRotationPolicy()
        accepted, reason = policy.accept_key(
            TRUSTED_KEY_FINGERPRINT,
            0,  # Older version
        )
        self.assertFalse(accepted)
        self.assertIn("downgrade", reason.lower())
    
    def test_untrusted_key_rejected(self):
        """Untrusted key rejected regardless of version."""
        policy = KeyRotationPolicy()
        accepted, reason = policy.accept_key(
            "untrusted_fingerprint",
            TRUSTED_KEY_VERSION + 1,
        )
        self.assertFalse(accepted)


class TestTimeIntegrity(unittest.TestCase):
    """Test time integrity verification."""
    
    def test_no_drift_detected(self):
        """No drift detected immediately after init."""
        checker = TimeIntegrityChecker()
        is_normal, drift = checker.check_drift()
        self.assertTrue(is_normal)
        self.assertLess(drift, 1.0)  # Should be < 1 second
    
    def test_auto_mode_allowed_normal(self):
        """Auto-mode allowed when time is normal."""
        checker = TimeIntegrityChecker()
        allow_auto, msg = checker.verify_or_restrict()
        self.assertTrue(allow_auto)


class TestEmergencyLock(unittest.TestCase):
    """Test emergency lock mode."""
    
    def test_default_not_locked(self):
        """System not locked by default."""
        with patch.object(SystemLock, 'LOCK_FILE', Path(tempfile.gettempdir()) / "no_lock"):
            lock = SystemLock()
            self.assertFalse(lock.is_locked)
    
    def test_normal_mode_allows_all(self):
        """Normal mode allows all actions."""
        with patch.object(SystemLock, 'LOCK_FILE', Path(tempfile.gettempdir()) / "no_lock"):
            lock = SystemLock()
            restrictions = lock.get_restrictions()
            self.assertTrue(restrictions["auto_mode"])
            self.assertTrue(restrictions["training"])
    
    def test_emergency_lock_restricts(self):
        """Emergency lock restricts actions."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lock', delete=False) as f:
            f.write('{}')
            lock_path = Path(f.name)
        
        try:
            with patch.object(SystemLock, 'LOCK_FILE', lock_path):
                lock = SystemLock()
                self.assertTrue(lock.is_locked)
                
                restrictions = lock.get_restrictions()
                self.assertFalse(restrictions["auto_mode"])
                self.assertFalse(restrictions["training"])
                self.assertTrue(restrictions["read_only"])
        finally:
            lock_path.unlink()
    
    def test_can_execute_in_normal_mode(self):
        """Actions executable in normal mode."""
        with patch.object(SystemLock, 'LOCK_FILE', Path(tempfile.gettempdir()) / "no_lock"):
            lock = SystemLock()
            can_exec, msg = lock.can_execute("auto_mode")
            self.assertTrue(can_exec)


if __name__ == "__main__":
    unittest.main()
