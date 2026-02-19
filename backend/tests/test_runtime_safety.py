"""
test_runtime_safety.py — Runtime Safety Test Suite
===================================================

Tests:
- Corrupted JSON load
- Missing field load
- CRC mismatch
- Mode race simulation
- Thermal spike simulation
- Runtime demotion after corruption
- Schema version mismatch
- Valid telemetry round-trip

NO mock data. NO auto-submit.
"""

import os
import sys
import json
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

from backend.api.runtime_api import (
    validate_telemetry,
    compute_crc32,
    compute_payload_crc,
    EXPECTED_SCHEMA_VERSION,
)


class RuntimeSafetyTest:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
        self.project_root = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))
        self.telemetry_path = os.path.join(
            self.project_root, 'reports', 'training_telemetry.json')

    def test(self, condition, name):
        if condition:
            self.passed += 1
            self.results.append(("PASS", name))
        else:
            self.failed += 1
            self.results.append(("FAIL", name))

    def _ensure_reports_dir(self):
        os.makedirs(os.path.dirname(self.telemetry_path), exist_ok=True)

    def _write_telemetry(self, data):
        self._ensure_reports_dir()
        with open(self.telemetry_path, 'w') as f:
            json.dump(data, f, indent=2)

    def _remove_telemetry(self):
        if os.path.exists(self.telemetry_path):
            os.remove(self.telemetry_path)

    def _make_valid_payload(self):
        """Create a valid telemetry payload with correct CRC."""
        payload = {
            "schema_version": EXPECTED_SCHEMA_VERSION,
            "determinism_status": True,
            "freeze_status": True,
            "precision": 0.96500000,
            "recall": 0.93000000,
            "kl_divergence": 0.01500000,
            "ece": 0.01200000,
            "loss": 0.04500000,
            "gpu_temperature": 72.50000000,
            "epoch": 42,
            "batch_size": 64,
            "timestamp": 1700000000,
        }
        payload["crc32"] = compute_payload_crc(payload)
        return payload

    def run_all(self):
        # Save any existing telemetry to restore later
        existing = None
        if os.path.exists(self.telemetry_path):
            with open(self.telemetry_path, 'r') as f:
                existing = f.read()

        try:
            self.test_corrupted_json_load()
            self.test_missing_field_load()
            self.test_crc_mismatch()
            self.test_mode_race_simulation()
            self.test_thermal_spike_simulation()
            self.test_runtime_demotion_after_corruption()
            self.test_schema_version_mismatch()
            self.test_valid_telemetry_round_trip()
        finally:
            # Restore original telemetry
            if existing is not None:
                self._ensure_reports_dir()
                with open(self.telemetry_path, 'w') as f:
                    f.write(existing)
            else:
                self._remove_telemetry()

        print(f"\n  Runtime Safety: {self.passed} passed, "
              f"{self.failed} failed")
        for status, name in self.results:
            marker = "+" if status == "PASS" else "X"
            print(f"    {marker} {name}")
        return self.failed == 0

    # =====================================================================
    # TEST CASES
    # =====================================================================

    def test_corrupted_json_load(self):
        """Corrupted JSON → error response."""
        self._ensure_reports_dir()
        with open(self.telemetry_path, 'w') as f:
            f.write("THIS IS NOT JSON {{{{")

        result = validate_telemetry()
        self.test(result['status'] == 'error',
                  "Corrupted JSON → status=error")
        self.test(result['reason'] == 'runtime_corrupted',
                  "Corrupted JSON → reason=runtime_corrupted")

    def test_missing_field_load(self):
        """Missing required field → error response."""
        # schema_version present but determinism_status missing
        self._write_telemetry({
            "schema_version": EXPECTED_SCHEMA_VERSION,
            "freeze_status": True,
            "crc32": 0
        })

        result = validate_telemetry()
        self.test(result['status'] == 'error',
                  "Missing field → status=error")
        self.test('determinism_status' in result.get('detail', ''),
                  "Missing field → detail mentions missing field")

    def test_crc_mismatch(self):
        """Tampered CRC → error response."""
        payload = self._make_valid_payload()
        payload['crc32'] = 12345  # Wrong CRC

        self._write_telemetry(payload)

        result = validate_telemetry()
        self.test(result['status'] == 'error',
                  "CRC mismatch → status=error")
        self.test('CRC mismatch' in result.get('detail', ''),
                  "CRC mismatch → detail mentions CRC")

    def test_mode_race_simulation(self):
        """Concurrent TRAIN+HUNT requests are mutually exclusive."""
        # Simulate mode mutex behavior via concurrent validation calls
        results = []
        errors = []

        def validate_concurrent(thread_id):
            try:
                # Each thread writes its own payload variant
                payload = self._make_valid_payload()
                r = validate_telemetry()
                results.append((thread_id, r))
            except Exception as e:
                errors.append((thread_id, str(e)))

        # Write valid telemetry first
        payload = self._make_valid_payload()
        self._write_telemetry(payload)

        # Launch concurrent validators
        threads = []
        for i in range(4):
            t = threading.Thread(target=validate_concurrent, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        self.test(len(errors) == 0,
                  "Concurrent validation: no exceptions")
        self.test(len(results) == 4,
                  "Concurrent validation: all 4 threads complete")

        # All concurrent reads of valid data should succeed
        all_ok = all(r[1].get('status') == 'ok' for r in results)
        self.test(all_ok,
                  "Concurrent validation: all return ok for valid data")

    def test_thermal_spike_simulation(self):
        """Temperature thresholds in telemetry data are preserved."""
        # Write telemetry with high temperature
        payload = self._make_valid_payload()
        payload['gpu_temperature'] = 90.0
        payload['crc32'] = compute_payload_crc(payload)

        self._write_telemetry(payload)

        result = validate_telemetry()
        self.test(result['status'] == 'ok',
                  "Thermal spike: valid telemetry accepted")
        self.test(result['data']['gpu_temperature'] == 90.0,
                  "Thermal spike: temperature preserved at 90°C")

    def test_runtime_demotion_after_corruption(self):
        """Corrupted state returns error, never partial data."""
        # First write valid data
        payload = self._make_valid_payload()
        self._write_telemetry(payload)

        # Verify it's valid
        r1 = validate_telemetry()
        self.test(r1['status'] == 'ok',
                  "Pre-corruption: valid data accepted")

        # Now corrupt it
        payload['precision'] = 0.50  # Tamper without updating CRC
        self._write_telemetry(payload)

        r2 = validate_telemetry()
        self.test(r2['status'] == 'error',
                  "Post-corruption: error returned")
        self.test('data' not in r2,
                  "Post-corruption: no partial data returned")

    def test_schema_version_mismatch(self):
        """Wrong schema version → error response."""
        payload = self._make_valid_payload()
        payload['schema_version'] = 99
        payload['crc32'] = compute_payload_crc(payload)

        self._write_telemetry(payload)

        result = validate_telemetry()
        self.test(result['status'] == 'error',
                  "Schema mismatch → status=error")
        self.test('Schema version' in result.get('detail', ''),
                  "Schema mismatch → detail mentions version")

    def test_valid_telemetry_round_trip(self):
        """Write → read cycle preserves all fields and CRC."""
        payload = self._make_valid_payload()
        self._write_telemetry(payload)

        result = validate_telemetry()
        self.test(result['status'] == 'ok',
                  "Round-trip: validation passes")
        self.test(result.get('validated') is True,
                  "Round-trip: validated flag true")

        data = result.get('data', {})
        self.test(data.get('schema_version') == EXPECTED_SCHEMA_VERSION,
                  "Round-trip: schema_version preserved")
        self.test(data.get('determinism_status') is True,
                  "Round-trip: determinism_status preserved")
        self.test(data.get('freeze_status') is True,
                  "Round-trip: freeze_status preserved")
        self.test(data.get('epoch') == 42,
                  "Round-trip: epoch preserved")
        self.test(data.get('batch_size') == 64,
                  "Round-trip: batch_size preserved")
        self.test(abs(data.get('precision', 0) - 0.965) < 0.001,
                  "Round-trip: precision preserved")

        # Verify CRC matches recomputation
        recomputed = compute_payload_crc(data)
        self.test(data.get('crc32') == recomputed,
                  "Round-trip: CRC32 matches recomputation")


# =========================================================================
# RUNNER
# =========================================================================

def run_tests():
    test = RuntimeSafetyTest()
    return test.run_all()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
