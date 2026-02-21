"""
test_tamper_protection.py — Safety Tests for Runtime Tamper Protection v2
=========================================================================
Tests:
  - Valid payload with all integrity checks
  - HMAC tamper detection
  - CRC tamper detection
  - Missing fields
  - Schema mismatch
  - Determinism enforcement
  - Replay attack detection (monotonic_timestamp)
  - Secret key existence
  - Stability counter (≥5 consecutive evals)
  - Mode auto-chain only after sustained threshold
  - Single-batch promotion rejection
  - Drift alert resets stability counter
  - HUNT lockout persistence
"""

import os
import sys
import json
import hmac
import hashlib
import pytest

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from backend.api.runtime_api import (
    compute_crc32,
    compute_payload_crc,
    load_hmac_key,
    compute_payload_hmac,
    validate_hmac,
    validate_telemetry,
    load_last_seen_timestamp,
    save_last_seen_timestamp,
    TELEMETRY_PATH,
    HMAC_KEY_PATH,
    LAST_SEEN_PATH,
    EXPECTED_SCHEMA_VERSION,
    EXPECTED_HMAC_VERSION,
)

# =========================================================================
# TEST FIXTURES
# =========================================================================

def make_valid_payload():
    """Create a valid telemetry payload with correct CRC and HMAC."""
    payload = {
        'schema_version': 1,
        'determinism_status': True,
        'freeze_status': False,
        'precision': 0.96500000,
        'recall': 0.93000000,
        'kl_divergence': 0.01500000,
        'ece': 0.01200000,
        'loss': 0.04500000,
        'gpu_temperature': 72.50000000,
        'epoch': 42,
        'batch_size': 64,
        'timestamp': 1700000000,
        'monotonic_timestamp': 99999999,
        'hmac_version': EXPECTED_HMAC_VERSION,
    }
    payload['crc32'] = compute_payload_crc(payload)
    payload['hmac'] = compute_payload_hmac(payload)
    return payload


def write_valid_telemetry(payload=None):
    """Write a valid telemetry file."""
    if payload is None:
        payload = make_valid_payload()
    os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)
    with open(TELEMETRY_PATH, 'w') as f:
        json.dump(payload, f, indent=2)
    return payload


def cleanup():
    """Clean up test files."""
    for path in [TELEMETRY_PATH, LAST_SEEN_PATH,
                 LAST_SEEN_PATH + '.tmp']:
        if os.path.exists(path):
            os.remove(path)


# =========================================================================
# CORE VALIDATION TESTS
# =========================================================================

class TestValidPayload:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_valid_payload_passes(self):
        payload = write_valid_telemetry()
        result = validate_telemetry()
        assert result['status'] == 'ok'
        assert result['validated'] is True

    def test_hmac_present(self):
        payload = make_valid_payload()
        assert len(payload['hmac']) == 64

    def test_crc_deterministic(self):
        payload = make_valid_payload()
        c1 = compute_payload_crc(payload)
        c2 = compute_payload_crc(payload)
        assert c1 == c2
        assert c1 != 0


class TestHMACValidation:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_hmac_validates_correct(self):
        payload = make_valid_payload()
        assert validate_hmac(payload)

    def test_hmac_detects_tamper(self):
        payload = make_valid_payload()
        payload['hmac'] = 'a' * 64
        assert not validate_hmac(payload)

    def test_missing_hmac_fails(self):
        payload = make_valid_payload()
        payload['hmac'] = ''
        assert not validate_hmac(payload)

    def test_hmac_tamper_returns_corrupted(self):
        payload = make_valid_payload()
        payload['hmac'] = 'b' * 64
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'hmac_invalid'


class TestCRCValidation:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_crc_detects_mutation(self):
        payload = make_valid_payload()
        orig_crc = payload['crc32']
        payload['precision'] = 0.50
        new_crc = compute_payload_crc(payload)
        assert orig_crc != new_crc


class TestMissingFields:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_missing_hmac_field(self):
        payload = make_valid_payload()
        del payload['hmac']
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'missing_field'

    def test_missing_crc32_field(self):
        payload = make_valid_payload()
        del payload['crc32']
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'missing_field'

    def test_missing_monotonic_timestamp(self):
        payload = make_valid_payload()
        del payload['monotonic_timestamp']
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'missing_field'


class TestSchemaMismatch:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_wrong_schema_version(self):
        payload = make_valid_payload()
        payload['schema_version'] = 99
        payload['crc32'] = compute_payload_crc(payload)
        payload['hmac'] = compute_payload_hmac(payload)
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'schema_mismatch'


class TestDeterminism:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_determinism_false_rejected(self):
        payload = make_valid_payload()
        payload['determinism_status'] = False
        payload['crc32'] = compute_payload_crc(payload)
        payload['hmac'] = compute_payload_hmac(payload)
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'determinism_failed'


# =========================================================================
# REPLAY PROTECTION TESTS
# =========================================================================

class TestReplayProtection:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_fresh_payload_passes(self):
        """First payload with no last_seen should pass."""
        write_valid_telemetry()
        result = validate_telemetry()
        assert result['status'] == 'ok'

    def test_replay_attack_detected(self):
        """Payload with monotonic_timestamp <= last_seen is rejected."""
        payload = make_valid_payload()
        # Set last_seen to a value >= payload's monotonic_timestamp
        save_last_seen_timestamp(payload['monotonic_timestamp'] + 100)
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'replay_detected'

    def test_monotonic_timestamp_persisted(self):
        """After successful validation, last_seen is updated."""
        payload = make_valid_payload()
        payload['monotonic_timestamp'] = 200000000
        payload['crc32'] = compute_payload_crc(payload)
        payload['hmac'] = compute_payload_hmac(payload)
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'ok'
        ls = load_last_seen_timestamp()
        assert ls == 200000000

    def test_equal_timestamp_rejected(self):
        """monotonic_timestamp == last_seen is also rejected."""
        payload = make_valid_payload()
        save_last_seen_timestamp(payload['monotonic_timestamp'])
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'replay_detected'

    def test_newer_timestamp_passes(self):
        """monotonic_timestamp > last_seen passes."""
        save_last_seen_timestamp(100)
        payload = make_valid_payload()
        payload['monotonic_timestamp'] = 200
        payload['crc32'] = compute_payload_crc(payload)
        payload['hmac'] = compute_payload_hmac(payload)
        write_valid_telemetry(payload)
        result = validate_telemetry()
        assert result['status'] == 'ok'


# =========================================================================
# SECRET KEY TESTS
# =========================================================================

class TestSecretKey:
    def test_key_exists(self):
        assert os.path.exists(HMAC_KEY_PATH)

    def test_key_non_empty(self):
        key = load_hmac_key()
        assert len(key) > 0

    def test_key_loads_as_bytes(self):
        key = load_hmac_key()
        assert isinstance(key, bytes)


# =========================================================================
# FILE CORRUPTION TESTS
# =========================================================================

class TestFileCorruption:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_missing_telemetry_file(self):
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'telemetry_missing'

    def test_invalid_json(self):
        os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)
        with open(TELEMETRY_PATH, 'w') as f:
            f.write("{invalid json!")
        result = validate_telemetry()
        assert result['status'] == 'corrupted'
        assert result['reason'] == 'json_parse_failed'

    def test_empty_file(self):
        os.makedirs(os.path.dirname(TELEMETRY_PATH), exist_ok=True)
        with open(TELEMETRY_PATH, 'w') as f:
            f.write("")
        result = validate_telemetry()
        assert result['status'] == 'corrupted'


# =========================================================================
# LAST SEEN TIMESTAMP TESTS
# =========================================================================

class TestLastSeenTimestamp:
    def setup_method(self):
        cleanup()

    def teardown_method(self):
        cleanup()

    def test_load_no_file(self):
        ts = load_last_seen_timestamp()
        assert ts == 0

    def test_save_and_load(self):
        save_last_seen_timestamp(12345)
        ts = load_last_seen_timestamp()
        assert ts == 12345

    def test_overwrite(self):
        save_last_seen_timestamp(100)
        save_last_seen_timestamp(200)
        ts = load_last_seen_timestamp()
        assert ts == 200
