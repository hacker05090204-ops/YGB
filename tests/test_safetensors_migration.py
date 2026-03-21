"""
test_safetensors_migration.py — Tests for safetensors migration and sector changes.

Covers:
- Safetensors save/load roundtrip
- Checksum verification
- Atomic write safety
- Migration script dry-run and convert
- Sector import shims
- Loop guard verification
"""

import hashlib
import json
import os
import sys
import tempfile
import shutil

import numpy as np
import pytest
import torch

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ===========================================================================
# SAFETENSORS I/O
# ===========================================================================

class TestSafetensorsIO:

    def test_save_load_roundtrip(self, tmp_path):
        """Save with safetensors, load back, verify tensor equality."""
        from training.safetensors_io import save_safetensors, load_safetensors

        tensors = {
            "weight": torch.randn(64, 32),
            "bias": torch.randn(32),
        }
        path = str(tmp_path / "test_model.safetensors")
        file_hash, tensor_hash = save_safetensors(tensors, path)

        assert os.path.exists(path)
        assert len(file_hash) == 64  # SHA-256
        assert len(tensor_hash) == 64

        loaded = load_safetensors(path)
        assert "weight" in loaded
        assert "bias" in loaded
        assert torch.allclose(tensors["weight"], loaded["weight"])
        assert torch.allclose(tensors["bias"], loaded["bias"])

    def test_fp16_conversion(self, tmp_path):
        """Save with FP16 conversion, verify types."""
        from training.safetensors_io import save_safetensors, load_safetensors

        tensors = {
            "weight": torch.randn(16, 8),
        }
        path = str(tmp_path / "fp16_model.safetensors")
        save_safetensors(tensors, path, convert_fp16=True)

        loaded = load_safetensors(path, verify_hash=True)
        assert loaded["weight"].dtype == torch.float16

    def test_checksum_verification(self, tmp_path):
        """Verify SHA-256 checksum in metadata matches."""
        from training.safetensors_io import save_safetensors, load_safetensors, _compute_tensor_hash

        tensors = {"w": torch.ones(4, 4)}
        path = str(tmp_path / "cksum.safetensors")
        _, tensor_hash = save_safetensors(tensors, path)

        # Load and verify — should not raise
        loaded = load_safetensors(path, verify_hash=True)
        assert _compute_tensor_hash(loaded) == tensor_hash

    def test_atomic_write_no_partial_file(self, tmp_path):
        """On failure, temp file should be cleaned up."""
        from training.safetensors_io import save_safetensors

        # Saving with invalid tensors should fail but not leave temp files
        path = str(tmp_path / "atomic.safetensors")
        try:
            save_safetensors({"bad": "not_a_tensor"}, path)
        except Exception:
            pass

        # No .tmp files should remain
        tmp_files = [f for f in os.listdir(str(tmp_path)) if f.endswith('.tmp')]
        assert len(tmp_files) == 0

    def test_file_not_found_raises(self):
        """Loading non-existent file should raise FileNotFoundError."""
        from training.safetensors_io import load_safetensors
        with pytest.raises(FileNotFoundError):
            load_safetensors("/nonexistent/path.safetensors")

    def test_numpy_roundtrip_without_torch(self, tmp_path, monkeypatch):
        """Numpy-only roundtrip should work when torch is unavailable."""
        import training.safetensors_io as safetensors_io

        monkeypatch.setattr(safetensors_io, "_import_torch", lambda: None)

        tensors = {"weight": np.arange(16, dtype=np.float32).reshape(4, 4)}
        path = str(tmp_path / "numpy_only.safetensors")
        safetensors_io.save_safetensors(tensors, path, convert_fp16=True)

        loaded = safetensors_io.load_safetensors(path)
        assert loaded["weight"].shape == (4, 4)
        assert loaded["weight"].dtype == np.float16
        assert np.array_equal(loaded["weight"], tensors["weight"].astype(np.float16))


# ===========================================================================
# MODEL VERSIONING (SAFETENSORS)
# ===========================================================================

class TestModelVersioningSafetensors:

    def test_save_creates_safetensors(self, tmp_path):
        """save_model_fp16 should create .safetensors, not .pt."""
        from impl_v1.training.distributed.model_versioning import save_model_fp16

        model = torch.nn.Linear(64, 2)
        version = save_model_fp16(
            model, "v_test", "ds_hash", 1, 5, 0.85,
            {"lr": 0.001}, base_dir=str(tmp_path),
        )
        assert version.fp16 is True
        assert version.weights_path.endswith(".safetensors")
        assert os.path.exists(version.weights_path)
        # .pt should NOT exist
        pt_path = version.weights_path.replace(".safetensors", ".pt")
        assert not os.path.exists(pt_path)

    def test_load_model_version_metadata(self, tmp_path):
        """load_model_version should return correct metadata."""
        from impl_v1.training.distributed.model_versioning import (
            save_model_fp16, load_model_version,
        )
        model = torch.nn.Linear(64, 2)
        save_model_fp16(
            model, "v001", "ds_hash", 1, 5, 0.85,
            {"lr": 0.001}, base_dir=str(tmp_path),
        )

        loaded = load_model_version("v001", str(tmp_path))
        assert loaded is not None
        assert loaded.version_id == "v001"
        assert loaded.weights_path.endswith(".safetensors")

    def test_load_model_weights_roundtrip(self, tmp_path):
        """load_model_weights should return valid tensors."""
        from impl_v1.training.distributed.model_versioning import (
            save_model_fp16, load_model_weights,
        )
        model = torch.nn.Linear(64, 2)
        save_model_fp16(
            model, "v002", "dh", 1, 0, 0.5, {}, str(tmp_path),
        )

        weights = load_model_weights("v002", str(tmp_path))
        assert weights is not None
        assert "weight" in weights
        assert "bias" in weights

    def test_metadata_has_format_safetensors(self, tmp_path):
        """metadata.json should have format=safetensors."""
        from impl_v1.training.distributed.model_versioning import save_model_fp16

        model = torch.nn.Linear(16, 2)
        save_model_fp16(
            model, "v003", "dh", 1, 0, 0.5, {}, str(tmp_path),
        )

        meta_path = os.path.join(str(tmp_path), "v003", "metadata.json")
        with open(meta_path) as f:
            meta = json.load(f)
        assert meta["format"] == "safetensors"
        assert "file_hash" in meta


# ===========================================================================
# CHECKPOINT HARDENING (SAFETENSORS)
# ===========================================================================

class TestCheckpointHardeningSafetensors:

    def test_save_as_safetensors(self, tmp_path):
        """save_checkpoint should create .safetensors file."""
        from impl_v1.training.checkpoints.checkpoint_hardening import HardenedCheckpointManager

        mgr = HardenedCheckpointManager(tmp_path)
        state_dict = {"weight": torch.randn(4, 4), "bias": torch.randn(4)}
        ok, meta = mgr.save_checkpoint(state_dict, epoch=0, step=0, metrics={"loss": 0.5})

        assert ok is True
        assert meta.checkpoint_id == "ckpt_e0000_s000000"
        ckpt_path = tmp_path / "ckpt_e0000_s000000.safetensors"
        assert ckpt_path.exists()

    def test_verify_checkpoint_integrity(self, tmp_path):
        """verify_checkpoint should pass for valid checkpoint."""
        from impl_v1.training.checkpoints.checkpoint_hardening import HardenedCheckpointManager

        mgr = HardenedCheckpointManager(tmp_path)
        state_dict = {"weight": torch.randn(4, 4)}
        mgr.save_checkpoint(state_dict, epoch=1, step=100, metrics={})

        valid, msg = mgr.verify_checkpoint("ckpt_e0001_s000100")
        assert valid is True


# ===========================================================================
# WIPE PROTECTION (SAFETENSORS)
# ===========================================================================

class TestWipeProtectionSafetensors:

    def test_check_local_weights_safetensors(self, tmp_path):
        """check_local_weights should find .safetensors files."""
        from impl_v1.training.distributed.wipe_protection import check_local_weights
        from safetensors.torch import save_file

        v_dir = tmp_path / "v001"
        v_dir.mkdir()
        save_file({"w": torch.ones(2, 2)}, str(v_dir / "model_fp16.safetensors"))

        assert check_local_weights(str(tmp_path)) is True

    def test_check_local_weights_legacy_pt(self, tmp_path):
        """check_local_weights should also find .pt files."""
        from impl_v1.training.distributed.wipe_protection import check_local_weights

        v_dir = tmp_path / "v001"
        v_dir.mkdir()
        torch.save({}, str(v_dir / "model_fp16.pt"))

        assert check_local_weights(str(tmp_path)) is True

    def test_no_local_weights(self, tmp_path):
        """check_local_weights returns False for empty dir."""
        from impl_v1.training.distributed.wipe_protection import check_local_weights
        assert check_local_weights(str(tmp_path)) is False


# ===========================================================================
# MIGRATION SCRIPT
# ===========================================================================

class TestMigrationScript:

    def test_migration_dry_run(self, tmp_path, monkeypatch):
        """Dry run should not create any new files."""
        # Create a .pt file
        v_dir = tmp_path / "model_versions" / "v001"
        v_dir.mkdir(parents=True)
        torch.save({"w": torch.ones(4, 4)}, str(v_dir / "model_fp16.pt"))

        # Monkey-patch scan dirs
        from scripts import migrate_pt_to_safetensors as mig
        monkeypatch.setattr(mig, "SCAN_DIRS", [str(tmp_path / "model_versions")])
        monkeypatch.setattr(mig, "MIGRATION_LOG_PATH", str(tmp_path / "log.json"))
        monkeypatch.setattr(mig, "BACKUP_DIR", str(tmp_path / "backup"))

        result = mig.run_migration(dry_run=True)
        assert result["dry_run_count"] == 1
        assert result["converted"] == 0
        # Original .pt still exists
        assert (v_dir / "model_fp16.pt").exists()
        # No .safetensors created
        assert not (v_dir / "model_fp16.safetensors").exists()

    def test_migration_converts_pt(self, tmp_path, monkeypatch):
        """Full migration should convert .pt to .safetensors."""
        v_dir = tmp_path / "model_versions" / "v001"
        v_dir.mkdir(parents=True)
        torch.save({"w": torch.ones(4, 4), "b": torch.zeros(4)}, str(v_dir / "model_fp16.pt"))

        # Write metadata
        meta = {"version_id": "v001", "merged_weight_hash": "abc"}
        with open(str(v_dir / "metadata.json"), "w") as f:
            json.dump(meta, f)

        from scripts import migrate_pt_to_safetensors as mig
        monkeypatch.setattr(mig, "SCAN_DIRS", [str(tmp_path / "model_versions")])
        monkeypatch.setattr(mig, "MIGRATION_LOG_PATH", str(tmp_path / "log.json"))
        monkeypatch.setattr(mig, "BACKUP_DIR", str(tmp_path / "backup"))
        monkeypatch.setattr(mig, "PROJECT_ROOT", str(tmp_path))

        result = mig.run_migration(dry_run=False)
        assert result["converted"] == 1
        assert (v_dir / "model_fp16.safetensors").exists()

        # Verify metadata updated
        with open(str(v_dir / "metadata.json")) as f:
            updated_meta = json.load(f)
        assert updated_meta["format"] == "safetensors"


# ===========================================================================
# SECTOR IMPORTS
# ===========================================================================

class TestSectorImports:

    def test_training_sector_import(self):
        """training sector __init__.py should be importable."""
        import importlib
        mod = importlib.import_module("training")
        assert mod is not None

    def test_governance_sector_import(self):
        """governance sector __init__.py should be importable."""
        import importlib
        mod = importlib.import_module("governance")
        assert mod is not None

    def test_voice_mode_sector_import(self):
        """voice_mode sector __init__.py should be importable."""
        import importlib
        mod = importlib.import_module("voice_mode")
        assert mod is not None

    def test_ingest_reports_media_import(self):
        """ingest_reports_media sector should be importable."""
        import importlib
        mod = importlib.import_module("ingest_reports_media")
        assert mod is not None

    def test_ai_report_generator_import(self):
        """ai_report_generator sector should be importable."""
        import importlib
        mod = importlib.import_module("ai_report_generator")
        assert mod is not None


# ===========================================================================
# ISOLATION GUARD (SAFETENSORS ALLOWED)
# ===========================================================================

class TestIsolationGuardSafetensors:

    def test_safetensors_not_blocked(self):
        """Research mode should NOT block .safetensors extension."""
        from backend.assistant.isolation_guard import IsolationGuard
        guard = IsolationGuard()
        result = guard.check_path_read("/some/path/model.safetensors")
        assert result.allowed is True

    def test_pt_still_blocked(self):
        """Research mode should still block .pt extension."""
        from backend.assistant.isolation_guard import IsolationGuard
        guard = IsolationGuard()
        result = guard.check_path_read("/cache/weights.pt")
        assert result.allowed is False
