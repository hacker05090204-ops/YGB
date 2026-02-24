"""
Tests for Phase 2 — Ingestion Quality Gates.

Tests:
  - Preflight gate blocks insufficient samples
  - Preflight gate blocks num_classes=1
  - Preflight gate blocks class imbalance
  - Quarantine store preserves data with audit trail
  - Manifest hardening includes class histogram and entropy
"""
import os
import sys
import json
import math
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestPreflightGate(unittest.TestCase):
    """Test ingestion preflight checks."""

    def test_sufficient_samples_pass(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=6000,
            class_histogram={0: 3000, 1: 3000},
            min_samples=5000,
        )
        self.assertTrue(result.passed)

    def test_insufficient_samples_blocked(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=100,
            class_histogram={0: 50, 1: 50},
            min_samples=5000,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any(f.check_name == "MIN_SAMPLES" for f in result.failures))

    def test_single_class_blocked(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=6000,
            class_histogram={0: 6000},
            min_samples=5000,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any(f.check_name == "MIN_CLASSES" for f in result.failures))

    def test_class_imbalance_blocked(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=6000,
            class_histogram={0: 5900, 1: 100},
            min_samples=5000,
            max_imbalance=10.0,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any(f.check_name == "CLASS_IMBALANCE" for f in result.failures))

    def test_balanced_classes_pass(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=6000,
            class_histogram={0: 3200, 1: 2800},
            min_samples=5000,
        )
        self.assertTrue(result.passed)

    def test_hash_mismatch_blocked(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=6000,
            class_histogram={0: 3000, 1: 3000},
            manifest_hash="abc123",
            stored_hash="def456",
            min_samples=5000,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any(f.check_name == "HASH_CONSISTENCY" for f in result.failures))

    def test_low_source_trust_blocked(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=6000,
            class_histogram={0: 3000, 1: 3000},
            source_trust_scores=[0.1, 0.2, 0.3],
            min_samples=5000,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any(f.check_name == "SOURCE_TRUST" for f in result.failures))

    def test_per_class_minimum_blocked(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=6000,
            class_histogram={0: 5950, 1: 50},
            min_samples=5000,
            per_class_min=100,
        )
        self.assertFalse(result.passed)
        self.assertTrue(any(f.check_name == "PER_CLASS_MIN" for f in result.failures))

    def test_result_to_dict(self):
        from impl_v1.training.safety.ingestion_preflight import run_preflight
        result = run_preflight(
            sample_count=100,
            class_histogram={0: 100},
            min_samples=5000,
        )
        d = result.to_dict()
        self.assertFalse(d["passed"])
        self.assertTrue(len(d["failures"]) > 0)
        self.assertIn("checks_run", d)


class TestQuarantineStore(unittest.TestCase):
    """Test quarantine store with audit trail."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_quarantine_creates_record(self):
        from impl_v1.training.safety.quarantine_store import QuarantineStore
        store = QuarantineStore(quarantine_dir=self._tmpdir)
        record = store.quarantine(
            sample_id="test-001",
            sample_data={"field": "value"},
            reason_code="LOW_QUALITY",
            reason_detail="Quality score below threshold",
            source_provenance="test-source",
        )
        self.assertEqual(record.reason_code, "LOW_QUALITY")
        self.assertEqual(store.count, 1)

    def test_quarantine_preserves_data(self):
        from impl_v1.training.safety.quarantine_store import QuarantineStore
        store = QuarantineStore(quarantine_dir=self._tmpdir)
        store.quarantine(
            sample_id="test-002",
            sample_data={"important": "data"},
            reason_code="SCHEMA_VIOLATION",
            reason_detail="Missing required field",
        )
        # Check sample file exists
        samples_dir = Path(self._tmpdir) / "samples"
        sample_files = list(samples_dir.glob("test-002_*.json"))
        self.assertEqual(len(sample_files), 1)

        with open(sample_files[0]) as f:
            data = json.load(f)
        self.assertEqual(data["sample_data"]["important"], "data")

    def test_ledger_is_append_only(self):
        from impl_v1.training.safety.quarantine_store import QuarantineStore
        store = QuarantineStore(quarantine_dir=self._tmpdir)
        store.quarantine("s1", {"a": 1}, "LOW_QUALITY", "test1")
        store.quarantine("s2", {"b": 2}, "DUPLICATE", "test2")

        records = store.get_ledger()
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0].sample_id, "s1")
        self.assertEqual(records[1].sample_id, "s2")

    def test_summary_by_reason(self):
        from impl_v1.training.safety.quarantine_store import QuarantineStore
        store = QuarantineStore(quarantine_dir=self._tmpdir)
        store.quarantine("s1", {}, "LOW_QUALITY", "bad")
        store.quarantine("s2", {}, "LOW_QUALITY", "bad2")
        store.quarantine("s3", {}, "DUPLICATE", "dup")

        summary = store.get_summary()
        self.assertEqual(summary["total_quarantined"], 3)
        self.assertEqual(summary["by_reason"]["LOW_QUALITY"], 2)
        self.assertEqual(summary["by_reason"]["DUPLICATE"], 1)

    def test_no_silent_deletion(self):
        """Quarantine preserves data — original is never deleted."""
        from impl_v1.training.safety.quarantine_store import QuarantineStore
        store = QuarantineStore(quarantine_dir=self._tmpdir)
        record = store.quarantine("s1", {"vital": "evidence"}, "BAD", "test")
        # Verify original hash is preserved
        self.assertTrue(len(record.original_hash) == 64)
        # Verify data exists on disk
        samples = list((Path(self._tmpdir) / "samples").glob("*.json"))
        self.assertTrue(len(samples) > 0)


if __name__ == "__main__":
    unittest.main()
