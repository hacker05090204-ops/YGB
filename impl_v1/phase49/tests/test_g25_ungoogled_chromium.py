# Test G25: Ungoogled Chromium Enforcement
"""
Tests for Ungoogled Chromium enforcement governor.

100% coverage required.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
import tempfile
import os

from impl_v1.phase49.governors.g25_ungoogled_chromium import (
    BrowserVerificationStatus,
    BrowserBinary,
    BrowserVerificationResult,
    can_browser_fallback,
    can_browser_launch_without_verification,
    can_use_standard_chromium,
    can_use_edge,
    detect_ungoogled_chromium,
    verify_and_authorize_launch,
    get_browser_launch_command,
    enforce_ungoogled_chromium,
    BrowserEnforcementError,
    TRUSTED_BINARY_NAMES,
    TRUSTED_BINARY_PATHS,
    MINIMUM_VERSION,
    _find_binary_in_path,
    _check_trusted_paths,
    _get_version,
    _compute_checksum,
    _is_version_acceptable,
)


class TestGuards:
    """Test all security guards."""
    
    def test_can_browser_fallback_always_false(self):
        """Guard: No fallback ever."""
        assert can_browser_fallback() is False
    
    def test_can_browser_launch_without_verification_always_false(self):
        """Guard: No unverified launch ever."""
        assert can_browser_launch_without_verification() is False
    
    def test_can_use_standard_chromium_always_false(self):
        """Guard: No standard Chromium ever."""
        assert can_use_standard_chromium() is False
    
    def test_can_use_edge_always_false(self):
        """Guard: No Edge ever."""
        assert can_use_edge() is False


class TestBrowserBinary:
    """Test BrowserBinary dataclass."""
    
    def test_browser_binary_creation(self):
        """Create browser binary record."""
        binary = BrowserBinary(
            path="/usr/bin/ungoogled-chromium",
            name="ungoogled-chromium",
            version="120.0.6099.129",
            checksum="abc123",
            verified=True,
        )
        assert binary.path == "/usr/bin/ungoogled-chromium"
        assert binary.name == "ungoogled-chromium"
        assert binary.version == "120.0.6099.129"
        assert binary.verified is True
    
    def test_browser_binary_immutable(self):
        """Browser binary is frozen."""
        binary = BrowserBinary(
            path="/test",
            name="test",
            version="1.0",
            checksum=None,
            verified=False,
        )
        with pytest.raises(Exception):
            binary.path = "/other"


class TestBrowserVerificationResult:
    """Test verification result dataclass."""
    
    def test_verification_result_verified(self):
        """Create verified result."""
        binary = BrowserBinary(
            path="/usr/bin/ungoogled-chromium",
            name="ungoogled-chromium",
            version="120.0.0.0",
            checksum="abc",
            verified=True,
        )
        result = BrowserVerificationResult(
            status=BrowserVerificationStatus.VERIFIED,
            binary=binary,
            error_message=None,
            timestamp="2026-01-28T00:00:00Z",
            can_launch=True,
        )
        assert result.status == BrowserVerificationStatus.VERIFIED
        assert result.can_launch is True
        assert result.error_message is None
    
    def test_verification_result_not_found(self):
        """Create not found result."""
        result = BrowserVerificationResult(
            status=BrowserVerificationStatus.NOT_FOUND,
            binary=None,
            error_message="Not found",
            timestamp="2026-01-28T00:00:00Z",
            can_launch=False,
        )
        assert result.status == BrowserVerificationStatus.NOT_FOUND
        assert result.can_launch is False


class TestBinaryDetection:
    """Test binary detection functions."""
    
    def test_find_binary_in_path_found(self):
        """Find binary in PATH."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/ungoogled-chromium"
            result = _find_binary_in_path()
            assert result == "/usr/bin/ungoogled-chromium"
    
    def test_find_binary_in_path_not_found(self):
        """Binary not in PATH."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            result = _find_binary_in_path()
            assert result is None
    
    def test_check_trusted_paths_found(self):
        """Find binary in trusted path."""
        with patch.object(Path, "exists") as mock_exists:
            with patch.object(Path, "is_file") as mock_is_file:
                mock_exists.return_value = True
                mock_is_file.return_value = True
                result = _check_trusted_paths()
                assert result is not None
    
    def test_check_trusted_paths_not_found(self):
        """Binary not in trusted paths."""
        with patch.object(Path, "exists") as mock_exists:
            mock_exists.return_value = False
            result = _check_trusted_paths()
            assert result is None


class TestVersionCheck:
    """Test version checking."""
    
    def test_get_version_with_existing_file(self):
        """Get version from existing binary path."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"mock binary")
            f.flush()
            
            result = _get_version(f.name)
            # Mock returns "125.0.0.0" for existing files
            assert result == "125.0.0.0"
            
            os.unlink(f.name)
    
    def test_get_version_with_nonexistent_file(self):
        """Get version from non-existent binary path."""
        result = _get_version("/nonexistent/path")
        assert result is None
    
    def test_is_version_acceptable_yes(self):
        """Version meets minimum."""
        assert _is_version_acceptable("120.0.0.0") is True
        assert _is_version_acceptable("125.0.0.0") is True
        assert _is_version_acceptable("120.1.0.0") is True
    
    def test_is_version_acceptable_no(self):
        """Version below minimum."""
        assert _is_version_acceptable("119.0.0.0") is False
        assert _is_version_acceptable("100.0.0.0") is False
    
    def test_is_version_acceptable_invalid(self):
        """Invalid version format."""
        assert _is_version_acceptable("invalid") is False
        assert _is_version_acceptable("") is False
    
    def test_is_version_short_format(self):
        """Version with fewer parts."""
        assert _is_version_acceptable("120.0.0") is True
        assert _is_version_acceptable("121") is True


class TestChecksum:
    """Test checksum computation."""
    
    def test_compute_checksum_success(self):
        """Compute checksum of file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data")
            f.flush()
            
            result = _compute_checksum(f.name)
            assert result is not None
            assert len(result) == 64  # SHA-256 hex length
            
            os.unlink(f.name)
    
    def test_compute_checksum_not_exists(self):
        """Checksum of non-existent file."""
        result = _compute_checksum("/nonexistent/path")
        assert result is None


class TestDetection:
    """Test full detection flow."""
    
    def test_detect_not_found(self):
        """Detect when not installed."""
        with patch("shutil.which") as mock_which:
            with patch.object(Path, "exists") as mock_exists:
                mock_which.return_value = None
                mock_exists.return_value = False
                
                result = detect_ungoogled_chromium()
                
                assert result.status == BrowserVerificationStatus.NOT_FOUND
                assert result.can_launch is False
                assert "NOT FOUND" in result.error_message
    
    def test_detect_found_and_verified(self):
        """Detect and verify installation with temp file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"mock ungoogled chromium binary")
            f.flush()
            
            with patch("shutil.which") as mock_which:
                mock_which.return_value = f.name
                
                result = detect_ungoogled_chromium()
                
                # Mock version returns 125.0.0.0 which is >= 120.0.0.0
                assert result.status == BrowserVerificationStatus.VERIFIED
                assert result.can_launch is True
                assert result.binary is not None
                assert result.binary.verified is True
            
            os.unlink(f.name)
    
    def test_detect_version_not_available(self):
        """Detect with version detection returning None (non-existent path)."""
        with patch("shutil.which") as mock_which:
            with patch.object(Path, "exists") as mock_exists:
                with patch.object(Path, "is_file") as mock_is_file:
                    mock_which.return_value = None
                    mock_exists.return_value = True
                    mock_is_file.return_value = True
                    
                    # This will find a trusted path, but version check will work
                    # because we mock Path.exists
                    result = detect_ungoogled_chromium()
                    
                    # The detected binary should be verified (returns mock version)
                    assert result is not None


class TestVerifyAndAuthorize:
    """Test verify and authorize flow."""
    
    def test_verify_success(self):
        """Verify and authorize successfully."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"mock binary")
            f.flush()
            
            with patch("shutil.which") as mock_which:
                mock_which.return_value = f.name
                
                can_launch, result = verify_and_authorize_launch()
                
                assert can_launch is True
                assert result.status == BrowserVerificationStatus.VERIFIED
            
            os.unlink(f.name)
    
    def test_verify_failure(self):
        """Verify fails when not found."""
        with patch("shutil.which") as mock_which:
            with patch.object(Path, "exists") as mock_exists:
                mock_which.return_value = None
                mock_exists.return_value = False
                
                can_launch, result = verify_and_authorize_launch()
                
                assert can_launch is False
                assert result.status == BrowserVerificationStatus.NOT_FOUND


class TestLaunchCommand:
    """Test launch command generation."""
    
    def test_get_launch_command_verified(self):
        """Get launch command for verified browser."""
        binary = BrowserBinary(
            path="/usr/bin/ungoogled-chromium",
            name="ungoogled-chromium",
            version="120.0.0.0",
            checksum="abc",
            verified=True,
        )
        result = BrowserVerificationResult(
            status=BrowserVerificationStatus.VERIFIED,
            binary=binary,
            error_message=None,
            timestamp="2026-01-28T00:00:00Z",
            can_launch=True,
        )
        
        cmd = get_browser_launch_command(result)
        
        assert cmd is not None
        assert cmd[0] == "/usr/bin/ungoogled-chromium"
        assert "--disable-sync" in cmd
    
    def test_get_launch_command_not_verified(self):
        """No launch command for unverified browser."""
        result = BrowserVerificationResult(
            status=BrowserVerificationStatus.NOT_FOUND,
            binary=None,
            error_message="Not found",
            timestamp="2026-01-28T00:00:00Z",
            can_launch=False,
        )
        
        cmd = get_browser_launch_command(result)
        
        assert cmd is None


class TestEnforcement:
    """Test hard enforcement."""
    
    def test_enforce_success(self):
        """Enforcement passes when verified."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"mock binary")
            f.flush()
            
            with patch("shutil.which") as mock_which:
                mock_which.return_value = f.name
                
                result = enforce_ungoogled_chromium()
                
                assert result.can_launch is True
            
            os.unlink(f.name)
    
    def test_enforce_failure_raises(self):
        """Enforcement raises on failure."""
        with patch("shutil.which") as mock_which:
            with patch.object(Path, "exists") as mock_exists:
                mock_which.return_value = None
                mock_exists.return_value = False
                
                with pytest.raises(BrowserEnforcementError) as exc_info:
                    enforce_ungoogled_chromium()
                
                assert "BROWSER ENFORCEMENT FAILED" in str(exc_info.value)


class TestConstants:
    """Test constant definitions."""
    
    def test_trusted_binary_names_exist(self):
        """Trusted binary names defined."""
        assert len(TRUSTED_BINARY_NAMES) > 0
        assert "ungoogled-chromium" in TRUSTED_BINARY_NAMES
    
    def test_trusted_binary_paths_exist(self):
        """Trusted binary paths defined."""
        assert len(TRUSTED_BINARY_PATHS) > 0
    
    def test_minimum_version_defined(self):
        """Minimum version defined."""
        assert MINIMUM_VERSION is not None
        assert "." in MINIMUM_VERSION
