"""
Runtime Attestation Tests - Phase 49
=====================================

Tests for runtime attestation:
1. Environment lockdown
2. Kernel capability checks
3. Hash computation
4. Container detection
"""

import unittest
import os
import platform
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from impl_v1.phase49.runtime.runtime_attestation import (
    lockdown_environment,
    compute_file_hash,
    check_kernel_capabilities,
    get_sanitized_env,
    AttestationStatus,
    ENV_BLACKLIST,
    ENV_WHITELIST,
)


class TestEnvironmentLockdown(unittest.TestCase):
    """Test environment lockdown."""
    
    def test_blacklist_cleared(self):
        """Blacklisted variables are cleared."""
        # Set a blacklisted variable
        os.environ["LD_PRELOAD"] = "/tmp/evil.so"
        
        # Run lockdown
        checks = lockdown_environment()
        
        # Should be unset
        self.assertNotIn("LD_PRELOAD", os.environ)
    
    def test_whitelist_preserved(self):
        """Whitelisted variables are preserved."""
        original_path = os.environ.get("PATH", "")
        
        lockdown_environment()
        
        # PATH should still exist
        self.assertIn("PATH", os.environ)
    
    def test_sanitized_env_only_whitelist(self):
        """Sanitized env only contains whitelist."""
        sanitized = get_sanitized_env()
        
        for key in sanitized:
            self.assertIn(key, ENV_WHITELIST)


class TestBinaryHashAttestation(unittest.TestCase):
    """Test binary hash computation."""
    
    def test_compute_hash_existing_file(self):
        """Compute hash of existing file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            temp_path = Path(f.name)
        
        try:
            hash_val = compute_file_hash(temp_path)
            self.assertIsNotNone(hash_val)
            self.assertEqual(len(hash_val), 64)  # SHA256 hex
        finally:
            temp_path.unlink()
    
    def test_compute_hash_nonexistent_file(self):
        """Nonexistent file returns None."""
        hash_val = compute_file_hash(Path("/nonexistent/file"))
        self.assertIsNone(hash_val)
    
    def test_same_content_same_hash(self):
        """Same content produces same hash."""
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(b"same content")
            path1 = Path(f1.name)
        
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b"same content")
            path2 = Path(f2.name)
        
        try:
            hash1 = compute_file_hash(path1)
            hash2 = compute_file_hash(path2)
            self.assertEqual(hash1, hash2)
        finally:
            path1.unlink()
            path2.unlink()
    
    def test_different_content_different_hash(self):
        """Different content produces different hash."""
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(b"content 1")
            path1 = Path(f1.name)
        
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(b"content 2")
            path2 = Path(f2.name)
        
        try:
            hash1 = compute_file_hash(path1)
            hash2 = compute_file_hash(path2)
            self.assertNotEqual(hash1, hash2)
        finally:
            path1.unlink()
            path2.unlink()


class TestKernelCapabilities(unittest.TestCase):
    """Test kernel capability checks."""
    
    def test_returns_checks(self):
        """Returns list of checks."""
        checks = check_kernel_capabilities()
        self.assertIsInstance(checks, list)
    
    @unittest.skipIf(platform.system() == "Windows", "Unix only")
    def test_non_root_check(self):
        """Non-root check is performed."""
        checks = check_kernel_capabilities()
        check_names = [c.name for c in checks]
        self.assertIn("Non-root execution", check_names)
    
    @unittest.skipIf(platform.system() != "Windows", "Windows only")
    def test_non_admin_check(self):
        """Non-admin check is performed on Windows."""
        checks = check_kernel_capabilities()
        check_names = [c.name for c in checks]
        # Should have some admin-related check
        self.assertTrue(any("admin" in n.lower() for n in check_names))


class TestAttestationIntegrity(unittest.TestCase):
    """Test attestation integrity."""
    
    def test_lockdown_returns_valid_checks(self):
        """Lockdown returns valid attestation checks."""
        checks = lockdown_environment()
        
        for check in checks:
            self.assertIn(check.status, [
                AttestationStatus.PASS,
                AttestationStatus.FAIL,
                AttestationStatus.SKIP,
            ])
    
    def test_blacklist_all_unset_after_lockdown(self):
        """All blacklist variables unset after lockdown."""
        # Set all blacklist variables
        for var in ENV_BLACKLIST:
            os.environ[var] = "test_value"
        
        # Run lockdown
        lockdown_environment()
        
        # All should be unset
        for var in ENV_BLACKLIST:
            self.assertNotIn(var, os.environ)


if __name__ == "__main__":
    unittest.main()
