"""
Tests for canonical manifest builder and backward compatibility.

Verifies:
- canonicalize_manifest() produces all 6 signed keys
- Legacy keys are preserved (backward compat)
- validate_manifest() passes on canonicalized output
- signature_hash is correctly computed
- dataset_hash derivation from tensor_hash and ingestion_manifest_hash
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from impl_v1.training.safety.manifest_builder import (
    MissingAuthorityKeyError,
    canonicalize_manifest,
    safe_canonicalize_manifest,
)
from impl_v1.training.safety.dataset_manifest import (
    DatasetManifest,
    validate_manifest,
)
from backend.startup.preflight import check_manifest_authority_key


SIGNED_KEYS = {"dataset_hash", "signed_by", "version",
               "total_samples", "created_at", "signature_hash"}


class TestCanonicalizeManifest(unittest.TestCase):
    """Test canonicalize_manifest normalizer."""

    def setUp(self):
        self._original_authority_key = os.environ.get("YGB_AUTHORITY_KEY")
        os.environ["YGB_AUTHORITY_KEY"] = "test-authority-key"

    def tearDown(self):
        if self._original_authority_key is None:
            os.environ.pop("YGB_AUTHORITY_KEY", None)
        else:
            os.environ["YGB_AUTHORITY_KEY"] = self._original_authority_key

    def _legacy_manifest(self):
        """Return a typical legacy manifest (from _write_manifest)."""
        return {
            "dataset_source": "INGESTION_PIPELINE",
            "ingestion_manifest_hash": "abc123def456",
            "tensor_hash": "d7bcdb89e8e2d7cde45d5e6a693e80149e0a43186161c347da02ff5993d1b5fc",
            "sample_count": 125996,
            "feature_dim": 256,
            "num_classes": 2,
            "accepted": 125996,
            "rejected_policy": 0,
            "rejected_quality": 4,
            "strict_real_mode": True,
            "class_histogram": {"1": 57296, "0": 68700},
            "class_entropy": 0.9941,
            "source_trust_avg": 0.9116,
            "source_trust_min": 0.7,
            "training_mode": "PRODUCTION_REAL",
            "frozen_at": "2026-03-04T23:50:27.446821",
        }

    def test_signed_keys_present(self):
        """canonicalize_manifest produces all 6 signed keys."""
        m = self._legacy_manifest()
        result = canonicalize_manifest(m)
        for key in SIGNED_KEYS:
            self.assertIn(key, result, f"Missing signed key: {key}")

    def test_legacy_keys_preserved(self):
        """All original legacy keys are preserved."""
        m = self._legacy_manifest()
        original_keys = set(m.keys())
        canonicalize_manifest(m)
        for key in original_keys:
            self.assertIn(key, m, f"Legacy key lost: {key}")

    def test_dataset_hash_from_tensor_hash(self):
        """dataset_hash derived from tensor_hash when available."""
        m = self._legacy_manifest()
        canonicalize_manifest(m)
        self.assertEqual(m["dataset_hash"], m["tensor_hash"])

    def test_dataset_hash_from_ingestion_hash(self):
        """Falls back to ingestion_manifest_hash when tensor_hash absent."""
        m = self._legacy_manifest()
        del m["tensor_hash"]
        canonicalize_manifest(m)
        self.assertEqual(m["dataset_hash"], "abc123def456")

    def test_dataset_hash_computed_when_none(self):
        """Explicit dataset hash input is now required."""
        m = {"sample_count": 100, "dataset_source": "TEST"}
        with self.assertRaises(ValueError):
            canonicalize_manifest(m)

    def test_missing_authority_key_raises(self):
        """Manifest signing must fail closed without authority key."""
        os.environ.pop("YGB_AUTHORITY_KEY", None)
        with self.assertRaises(MissingAuthorityKeyError):
            canonicalize_manifest(self._legacy_manifest())

    def test_safe_canonicalize_manifest_wraps_missing_authority_key(self):
        """Safe wrapper must return a clear runtime readiness failure."""
        os.environ.pop("YGB_AUTHORITY_KEY", None)
        with self.assertRaisesRegex(RuntimeError, "SYSTEM NOT READY: Missing authority key"):
            safe_canonicalize_manifest(self._legacy_manifest())

    def test_signed_by_is_64_char_hex(self):
        """signed_by is SHA-256 of authority key (64 hex chars)."""
        m = self._legacy_manifest()
        canonicalize_manifest(m, authority_key="test-key")
        self.assertEqual(len(m["signed_by"]), 64)
        expected = hashlib.sha256(b"test-key").hexdigest()
        self.assertEqual(m["signed_by"], expected)

    def test_signature_hash_formula(self):
        """signature_hash = sha256(dataset_hash|signed_by|version)."""
        m = self._legacy_manifest()
        canonicalize_manifest(m)
        sig_input = f"{m['dataset_hash']}|{m['signed_by']}|{m['version']}"
        expected = hashlib.sha256(sig_input.encode("utf-8")).hexdigest()
        self.assertEqual(m["signature_hash"], expected)

    def test_created_at_from_frozen_at(self):
        """created_at derived from frozen_at when present."""
        m = self._legacy_manifest()
        canonicalize_manifest(m)
        self.assertEqual(m["created_at"], "2026-03-04T23:50:27.446821")

    def test_total_samples_from_sample_count(self):
        """total_samples derived from sample_count when not explicit."""
        m = self._legacy_manifest()
        m.pop("total_samples", None)
        canonicalize_manifest(m)
        self.assertEqual(m["total_samples"], 125996)

    def test_sample_count_backfilled(self):
        """sample_count is backfilled when missing."""
        m = {
            "total_samples": 5000,
            "dataset_source": "TEST",
            "dataset_hash": "b" * 64,
        }
        canonicalize_manifest(m)
        self.assertEqual(m["sample_count"], 5000)

    def test_version_default(self):
        """Default version is 1.0."""
        m = self._legacy_manifest()
        canonicalize_manifest(m)
        self.assertEqual(m["version"], "1.0")

    def test_custom_version(self):
        """Custom version is used when provided."""
        m = self._legacy_manifest()
        canonicalize_manifest(m, version="2.5")
        self.assertEqual(m["version"], "2.5")


class TestValidateManifestCompatibility(unittest.TestCase):
    """Test that validate_manifest() passes on canonicalized manifests."""

    def setUp(self):
        self._original_authority_key = os.environ.get("YGB_AUTHORITY_KEY")
        os.environ["YGB_AUTHORITY_KEY"] = "test-authority-key"

    def tearDown(self):
        if self._original_authority_key is None:
            os.environ.pop("YGB_AUTHORITY_KEY", None)
        else:
            os.environ["YGB_AUTHORITY_KEY"] = self._original_authority_key

    def test_validate_passes_canonicalized(self):
        """Canonicalized manifest passes validate_manifest()."""
        m = {
            "dataset_source": "INGESTION_PIPELINE",
            "tensor_hash": "a" * 64,
            "sample_count": 1000,
            "frozen_at": "2026-01-01T00:00:00Z",
        }
        canonicalize_manifest(m)

        # Write to temp file and validate
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(m, f)
            tmppath = f.name

        try:
            ok, reason, manifest = validate_manifest(path=tmppath)
            self.assertTrue(ok, f"Validation failed: {reason}")
            self.assertEqual(reason, "valid")
            self.assertIsNotNone(manifest)
            self.assertEqual(manifest.dataset_hash, "a" * 64)
        finally:
            os.unlink(tmppath)

    def test_validate_fails_without_signed_keys(self):
        """Pure legacy manifest (no signed keys) fails validation."""
        m = {
            "sample_count": 1000,
            "dataset_source": "TEST",
        }
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(m, f)
            tmppath = f.name

        try:
            ok, reason, manifest = validate_manifest(path=tmppath)
            self.assertFalse(ok)
            self.assertEqual(reason, "invalid_format")
        finally:
            os.unlink(tmppath)

    def test_existing_manifest_valid(self):
        """The actual secure_data/dataset_manifest.json passes validation."""
        manifest_path = ROOT / "secure_data" / "dataset_manifest.json"
        if not manifest_path.exists():
            self.skipTest("No manifest file on disk")

        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        required_signed_by = payload.get("signed_by")
        configured_signed_by = hashlib.sha256(
            os.environ["YGB_AUTHORITY_KEY"].encode("utf-8")
        ).hexdigest()
        if required_signed_by != configured_signed_by:
            self.skipTest(
                "Production manifest signer does not match test authority key in this environment"
            )

        ok, reason, manifest = validate_manifest(path=str(manifest_path))
        self.assertTrue(ok, f"Production manifest validation failed: {reason}")


class TestBridgeWorkerManifest(unittest.TestCase):
    """Test backward-compat keys are preserved in bridge worker schema."""

    def setUp(self):
        self._original_authority_key = os.environ.get("YGB_AUTHORITY_KEY")
        os.environ["YGB_AUTHORITY_KEY"] = "test-authority-key"

    def tearDown(self):
        if self._original_authority_key is None:
            os.environ.pop("YGB_AUTHORITY_KEY", None)
        else:
            os.environ["YGB_AUTHORITY_KEY"] = self._original_authority_key

    def test_bridge_worker_schema_has_legacy_keys(self):
        """Bridge worker manifest should keep verified_samples, source_mix."""
        m = {
            "total_samples": 500,
            "verified_samples": 480,
            "per_field_counts": {"endpoint": 500},
            "source_mix": {"NVD": 300},
            "strict_real_mode": True,
            "updated_at": "2026-03-01T00:00:00Z",
            "ingestion_manifest_hash": "deadbeef",
            "worker_stats": {"total_ingested": 500},
        }
        canonicalize_manifest(m)

        # All legacy keys present
        self.assertIn("verified_samples", m)
        self.assertIn("source_mix", m)
        self.assertIn("worker_stats", m)
        self.assertIn("per_field_counts", m)

        # All signed keys present
        for key in SIGNED_KEYS:
            self.assertIn(key, m)


class TestManifestPreflight(unittest.TestCase):
    """Manifest authority readiness checks must fail closed."""

    def setUp(self):
        self._original_authority_key = os.environ.get("YGB_AUTHORITY_KEY")

    def tearDown(self):
        if self._original_authority_key is None:
            os.environ.pop("YGB_AUTHORITY_KEY", None)
        else:
            os.environ["YGB_AUTHORITY_KEY"] = self._original_authority_key

    def test_manifest_authority_key_check_fails_when_missing(self):
        os.environ.pop("YGB_AUTHORITY_KEY", None)
        result = check_manifest_authority_key()
        self.assertFalse(result.passed)
        self.assertTrue(result.critical)
        self.assertIn("YGB_AUTHORITY_KEY", result.detail)

    def test_manifest_authority_key_check_passes_when_present(self):
        os.environ["YGB_AUTHORITY_KEY"] = "test-authority-key"
        result = check_manifest_authority_key()
        self.assertTrue(result.passed)


if __name__ == "__main__":
    unittest.main()
