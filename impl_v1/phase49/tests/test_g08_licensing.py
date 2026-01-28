# test_g08_licensing.py
"""Tests for G08: Licensing & Privacy"""

import pytest
from impl_v1.phase49.governors.g08_licensing import (
    LicenseStatus,
    LicenseType,
    DeviceFingerprint,
    LicenseValidation,
    PrivacyConfig,
    DEFAULT_PRIVACY,
    create_device_fingerprint,
    validate_license,
    apply_timing_jitter,
    mask_metadata,
    is_execution_allowed,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_license_status_5_members(self):
        assert len(LicenseStatus) == 5
    
    def test_license_type_3_members(self):
        assert len(LicenseType) == 3


class TestDeviceFingerprint:
    """Test device fingerprinting."""
    
    def test_fingerprint_has_id(self):
        fp = create_device_fingerprint("Linux", "5.15", "machine-123")
        assert fp.fingerprint_id.startswith("DEV-")
    
    def test_fingerprint_hashes_machine_id(self):
        fp = create_device_fingerprint("Linux", "5.15", "machine-123")
        # Machine ID should be hashed, not raw
        assert fp.machine_id != "machine-123"
        assert len(fp.machine_id) == 32  # SHA256 truncated
    
    def test_fingerprint_has_timestamp(self):
        fp = create_device_fingerprint("Linux", "5.15", "machine-123")
        assert fp.created_at is not None


class TestValidateLicense:
    """Test license validation."""
    
    def test_invalid_format_short(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        result = validate_license("SHORT", fp)
        assert result.status == LicenseStatus.INVALID
        assert not result.execution_allowed
    
    def test_invalid_format_empty(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        result = validate_license("", fp)
        assert result.status == LicenseStatus.INVALID
    
    def test_valid_key_recognized(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        valid_keys = ["VALID-KEY-1234567890-ABCD"]
        result = validate_license("VALID-KEY-1234567890-ABCD", fp, valid_keys)
        assert result.status == LicenseStatus.VALID
        assert result.execution_allowed
        assert result.license_type == LicenseType.STANDARD
    
    def test_unknown_key_invalid(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        result = validate_license("UNKNOWN-KEY-12345678", fp, ["DIFFERENT-KEY"])
        assert result.status == LicenseStatus.INVALID
    
    def test_validation_has_id(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        result = validate_license("SOME-KEY-123456789", fp)
        assert result.validation_id.startswith("VAL-")


class TestPrivacyConfig:
    """Test privacy configuration."""
    
    def test_default_privacy_geo_masking(self):
        assert DEFAULT_PRIVACY.geo_masking is True
    
    def test_default_privacy_timing_jitter(self):
        assert DEFAULT_PRIVACY.timing_jitter is True
    
    def test_default_privacy_metadata_masking(self):
        assert DEFAULT_PRIVACY.metadata_masking is True


class TestTimingJitter:
    """Test timing jitter."""
    
    def test_jitter_returns_value_in_range(self):
        config = DEFAULT_PRIVACY
        jitter = apply_timing_jitter(config)
        assert config.jitter_min_ms <= jitter <= config.jitter_max_ms
    
    def test_no_jitter_when_disabled(self):
        config = PrivacyConfig(
            geo_masking=True,
            timing_jitter=False,
            metadata_masking=True,
            report_rotation=True,
            jitter_min_ms=500,
            jitter_max_ms=3000,
        )
        jitter = apply_timing_jitter(config)
        assert jitter == 0


class TestMetadataMasking:
    """Test metadata masking."""
    
    def test_masks_ip(self):
        data = {"ip": "192.168.1.1", "name": "test"}
        masked = mask_metadata(data, DEFAULT_PRIVACY)
        assert masked["ip"] == "[MASKED]"
        assert masked["name"] == "test"
    
    def test_masks_location(self):
        data = {"location": "USA", "value": 123}
        masked = mask_metadata(data, DEFAULT_PRIVACY)
        assert masked["location"] == "[MASKED]"
    
    def test_no_masking_when_disabled(self):
        config = PrivacyConfig(
            geo_masking=True,
            timing_jitter=True,
            metadata_masking=False,
            report_rotation=True,
            jitter_min_ms=500,
            jitter_max_ms=3000,
        )
        data = {"ip": "192.168.1.1"}
        masked = mask_metadata(data, config)
        assert masked["ip"] == "192.168.1.1"


class TestIsExecutionAllowed:
    """Test execution permission check."""
    
    def test_valid_license_allows(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        valid_keys = ["VALID-KEY-1234567890-ABCD"]
        validation = validate_license("VALID-KEY-1234567890-ABCD", fp, valid_keys)
        allowed, reason = is_execution_allowed(validation)
        assert allowed
    
    def test_invalid_license_blocks(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        validation = validate_license("INVALID", fp)
        allowed, reason = is_execution_allowed(validation)
        assert not allowed
        assert "INVALID" in reason


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def test_fingerprint_frozen(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        with pytest.raises(AttributeError):
            fp.os_type = "Windows"
    
    def test_validation_frozen(self):
        fp = create_device_fingerprint("Linux", "5.15", "m1")
        validation = validate_license("KEY-12345678901234", fp)
        with pytest.raises(AttributeError):
            validation.status = LicenseStatus.VALID
