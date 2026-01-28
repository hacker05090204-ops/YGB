# test_g09_device_trust.py
"""Tests for G09: Device Trust"""

import pytest
from impl_v1.phase49.governors.g09_device_trust import (
    DeviceTrustLevel,
    VerificationStatus,
    DeviceRegistration,
    VerificationChallenge,
    clear_registry,
    get_registered_devices,
    get_trusted_count,
    register_device,
    verify_device,
    is_device_trusted,
    MAX_DEVICES,
    MAX_VERIFICATION_ATTEMPTS,
)


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_device_trust_level_4_members(self):
        assert len(DeviceTrustLevel) == 4
    
    def test_verification_status_4_members(self):
        assert len(VerificationStatus) == 4


class TestConstants:
    """Test constants."""
    
    def test_max_devices(self):
        assert MAX_DEVICES == 3
    
    def test_max_verification_attempts(self):
        assert MAX_VERIFICATION_ATTEMPTS == 3


class TestDeviceRegistration:
    """Test device registration."""
    
    def setup_method(self):
        clear_registry()
    
    def test_first_device_auto_trusted(self):
        device, challenge, password = register_device("Device 1", "fp1", "192.168.1.1")
        assert device.trust_level == DeviceTrustLevel.TRUSTED
        assert device.verified is True
        assert challenge is None
        assert password is None
    
    def test_device_has_id(self):
        device, _, _ = register_device("Device 1", "fp1", "192.168.1.1")
        assert device.device_id.startswith("DEV-")
    
    def test_device_fingerprint_hashed(self):
        device, _, _ = register_device("Device 1", "my-fingerprint", "192.168.1.1")
        assert device.fingerprint_hash != "my-fingerprint"
    
    def test_second_device_auto_trusted(self):
        register_device("Device 1", "fp1", "192.168.1.1")
        device2, challenge, password = register_device("Device 2", "fp2", "192.168.1.2")
        assert device2.trust_level == DeviceTrustLevel.TRUSTED
        assert challenge is None
    
    def test_third_device_auto_trusted(self):
        register_device("Device 1", "fp1", "192.168.1.1")
        register_device("Device 2", "fp2", "192.168.1.2")
        device3, challenge, password = register_device("Device 3", "fp3", "192.168.1.3")
        assert device3.trust_level == DeviceTrustLevel.TRUSTED
        assert challenge is None
    
    def test_fourth_device_requires_verification(self):
        register_device("Device 1", "fp1", "192.168.1.1")
        register_device("Device 2", "fp2", "192.168.1.2")
        register_device("Device 3", "fp3", "192.168.1.3")
        device4, challenge, password = register_device("Device 4", "fp4", "192.168.1.4")
        assert device4.trust_level == DeviceTrustLevel.PENDING
        assert challenge is not None
        assert password is not None


class TestDeviceVerification:
    """Test device verification."""
    
    def setup_method(self):
        clear_registry()
        # Fill up to max devices
        register_device("D1", "fp1", "1.1.1.1")
        register_device("D2", "fp2", "1.1.1.2")
        register_device("D3", "fp3", "1.1.1.3")
    
    def test_verify_with_correct_password(self):
        device, challenge, password = register_device("D4", "fp4", "1.1.1.4")
        success, reason = verify_device(challenge.challenge_id, password)
        assert success
        assert reason == "Device verified"
    
    def test_verify_with_wrong_password(self):
        device, challenge, password = register_device("D4", "fp4", "1.1.1.4")
        success, reason = verify_device(challenge.challenge_id, "wrong-password")
        assert not success
        assert "Invalid password" in reason
    
    def test_max_attempts_exceeded(self):
        device, challenge, password = register_device("D4", "fp4", "1.1.1.4")
        for i in range(MAX_VERIFICATION_ATTEMPTS):
            verify_device(challenge.challenge_id, "wrong")
        success, reason = verify_device(challenge.challenge_id, password)
        assert not success
        assert "Max attempts" in reason or "FAILED" in reason
    
    def test_unknown_challenge_fails(self):
        success, reason = verify_device("UNKNOWN-CHALLENGE", "password")
        assert not success
        assert "not found" in reason


class TestIsDeviceTrusted:
    """Test trust checking."""
    
    def setup_method(self):
        clear_registry()
    
    def test_trusted_device(self):
        device, _, _ = register_device("D1", "fp1", "1.1.1.1")
        trusted, reason = is_device_trusted(device.device_id)
        assert trusted
    
    def test_unknown_device(self):
        trusted, reason = is_device_trusted("UNKNOWN-DEVICE")
        assert not trusted
        assert "not registered" in reason
    
    def test_pending_device(self):
        register_device("D1", "fp1", "1.1.1.1")
        register_device("D2", "fp2", "1.1.1.2")
        register_device("D3", "fp3", "1.1.1.3")
        device, _, _ = register_device("D4", "fp4", "1.1.1.4")
        trusted, reason = is_device_trusted(device.device_id)
        assert not trusted
        assert "PENDING" in reason


class TestGetRegisteredDevices:
    """Test device listing."""
    
    def setup_method(self):
        clear_registry()
    
    def test_empty_initially(self):
        assert len(get_registered_devices()) == 0
    
    def test_counts_devices(self):
        register_device("D1", "fp1", "1.1.1.1")
        register_device("D2", "fp2", "1.1.1.2")
        assert len(get_registered_devices()) == 2


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def setup_method(self):
        clear_registry()
    
    def test_device_registration_frozen(self):
        device, _, _ = register_device("D1", "fp1", "1.1.1.1")
        with pytest.raises(AttributeError):
            device.trust_level = DeviceTrustLevel.BLOCKED
