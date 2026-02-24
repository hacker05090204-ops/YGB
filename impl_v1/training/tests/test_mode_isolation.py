"""
Tests for Phase 1 — Safe Mode Architecture.

Proves:
  - PRODUCTION_REAL and LAB_COMPLEX modes are distinct
  - Mode tags are immutable after freeze
  - LAB artifacts are blocked from production promotion
  - Untagged artifacts are blocked (fail-closed)
  - Mode resolution defaults to PRODUCTION_REAL
"""
import os
import sys
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(ROOT))


class TestTrainingModeTypes(unittest.TestCase):
    """Test TrainingModeType enum."""

    def test_two_modes_exist(self):
        from impl_v1.training.safety.training_mode import TrainingModeType
        self.assertEqual(TrainingModeType.PRODUCTION_REAL.value, "PRODUCTION_REAL")
        self.assertEqual(TrainingModeType.LAB_COMPLEX.value, "LAB_COMPLEX")

    def test_modes_are_distinct(self):
        from impl_v1.training.safety.training_mode import TrainingModeType
        self.assertNotEqual(
            TrainingModeType.PRODUCTION_REAL,
            TrainingModeType.LAB_COMPLEX,
        )


class TestModeTag(unittest.TestCase):
    """Test ModeTag immutability and hashing."""

    def test_tag_created_with_hash(self):
        from impl_v1.training.safety.training_mode import ModeTag
        tag = ModeTag(mode="PRODUCTION_REAL", artifact_type="checkpoint")
        self.assertTrue(len(tag.tag_hash) == 64)
        self.assertFalse(tag.frozen)

    def test_freeze_sets_frozen_at(self):
        from impl_v1.training.safety.training_mode import ModeTag
        tag = ModeTag(mode="PRODUCTION_REAL", artifact_type="manifest")
        tag.freeze()
        self.assertTrue(tag.frozen)
        self.assertTrue(len(tag.frozen_at) > 0)

    def test_double_freeze_raises(self):
        from impl_v1.training.safety.training_mode import ModeTag
        tag = ModeTag(mode="LAB_COMPLEX", artifact_type="report")
        tag.freeze()
        with self.assertRaises(RuntimeError):
            tag.freeze()

    def test_hash_changes_on_freeze(self):
        from impl_v1.training.safety.training_mode import ModeTag
        tag = ModeTag(mode="PRODUCTION_REAL", artifact_type="telemetry")
        hash_before = tag.tag_hash
        tag.freeze()
        self.assertNotEqual(hash_before, tag.tag_hash)

    def test_roundtrip_dict(self):
        from impl_v1.training.safety.training_mode import ModeTag
        tag = ModeTag(mode="PRODUCTION_REAL", artifact_type="checkpoint")
        tag.freeze()
        d = tag.to_dict()
        restored = ModeTag.from_dict(d)
        self.assertEqual(restored.mode, "PRODUCTION_REAL")
        self.assertEqual(restored.tag_hash, tag.tag_hash)
        self.assertTrue(restored.frozen)


class TestTagArtifact(unittest.TestCase):
    """Test tag_artifact utility."""

    def test_tag_creates_file(self):
        from impl_v1.training.safety.training_mode import (
            tag_artifact, TrainingModeType,
        )
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            f.write(b"fake checkpoint")
            path = f.name

        try:
            tag = tag_artifact(path, TrainingModeType.PRODUCTION_REAL, "checkpoint")
            tag_path = Path(path).with_suffix(".mode_tag.json")
            self.assertTrue(tag_path.exists())
            self.assertTrue(tag.frozen)

            with open(tag_path) as f:
                data = json.load(f)
            self.assertEqual(data["mode"], "PRODUCTION_REAL")
        finally:
            os.unlink(path)
            tag_path = Path(path).with_suffix(".mode_tag.json")
            if tag_path.exists():
                os.unlink(tag_path)


class TestPromotionGuard(unittest.TestCase):
    """Test promotion guard blocks LAB artifacts."""

    def _make_tagged_artifact(self, mode, suffix=".pt"):
        from impl_v1.training.safety.training_mode import (
            tag_artifact, TrainingModeType,
        )
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(b"fake artifact")
            path = f.name
        tag_artifact(path, mode, "checkpoint")
        return path

    def test_production_artifact_passes(self):
        from impl_v1.training.safety.training_mode import (
            check_promotion, TrainingModeType,
        )
        path = self._make_tagged_artifact(TrainingModeType.PRODUCTION_REAL)
        try:
            self.assertTrue(check_promotion(path))
        finally:
            os.unlink(path)
            os.unlink(Path(path).with_suffix(".mode_tag.json"))

    def test_lab_artifact_blocked(self):
        from impl_v1.training.safety.training_mode import (
            check_promotion, TrainingModeType, PromotionGuardError,
        )
        path = self._make_tagged_artifact(TrainingModeType.LAB_COMPLEX)
        try:
            with self.assertRaises(PromotionGuardError):
                check_promotion(path)
        finally:
            os.unlink(path)
            os.unlink(Path(path).with_suffix(".mode_tag.json"))

    def test_untagged_artifact_blocked(self):
        from impl_v1.training.safety.training_mode import (
            check_promotion, PromotionGuardError,
        )
        with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
            f.write(b"no tag")
            path = f.name
        try:
            with self.assertRaises(PromotionGuardError):
                check_promotion(path)
        finally:
            os.unlink(path)


class TestModeResolution(unittest.TestCase):
    """Test mode resolution from environment."""

    def test_default_is_production(self):
        from impl_v1.training.safety.training_mode import resolve_training_mode, TrainingModeType
        # Clear env var if set
        old = os.environ.pop("YGB_TRAINING_MODE", None)
        try:
            self.assertEqual(resolve_training_mode(), TrainingModeType.PRODUCTION_REAL)
        finally:
            if old is not None:
                os.environ["YGB_TRAINING_MODE"] = old

    def test_lab_from_env(self):
        from impl_v1.training.safety.training_mode import resolve_training_mode, TrainingModeType
        old = os.environ.get("YGB_TRAINING_MODE")
        os.environ["YGB_TRAINING_MODE"] = "LAB_COMPLEX"
        try:
            self.assertEqual(resolve_training_mode(), TrainingModeType.LAB_COMPLEX)
        finally:
            if old is not None:
                os.environ["YGB_TRAINING_MODE"] = old
            else:
                os.environ.pop("YGB_TRAINING_MODE", None)

    def test_invalid_env_defaults_production(self):
        from impl_v1.training.safety.training_mode import resolve_training_mode, TrainingModeType
        old = os.environ.get("YGB_TRAINING_MODE")
        os.environ["YGB_TRAINING_MODE"] = "CHAOS_MODE"
        try:
            self.assertEqual(resolve_training_mode(), TrainingModeType.PRODUCTION_REAL)
        finally:
            if old is not None:
                os.environ["YGB_TRAINING_MODE"] = old
            else:
                os.environ.pop("YGB_TRAINING_MODE", None)


if __name__ == "__main__":
    unittest.main()
