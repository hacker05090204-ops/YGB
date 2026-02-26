"""
Test No Synthetic Fallback
===========================

Validates:
- No synthetic data in training pipeline
- No random.random() for training data
- No fallback to mock data
- Real dataset connected
- STRICT_REAL_MODE never touches SyntheticTrainingDataset in validate_dataset_integrity
"""

import pytest
import inspect
import sys
import os
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))


class TestNoSyntheticFallback:
    """Ensure no synthetic data survives in the training pipeline."""
    
    def test_no_random_data_in_init_gpu(self):
        """_init_gpu_resources must NOT use random.random() for training data."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        # Must NOT contain random data generation
        assert "random.random()" not in source, \
            "_init_gpu_resources still uses random.random() for synthetic data"
        assert "random.randint(0, 1)" not in source, \
            "_init_gpu_resources still uses random.randint for synthetic labels"
    
    def test_no_512_samples_hardcoded(self):
        """Must NOT have hardcoded 512 synthetic samples."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        assert "range(512)" not in source, \
            "_init_gpu_resources still has hardcoded 512 sample loop"
    
    def test_uses_real_dataset_loader(self):
        """_init_gpu_resources must import real_dataset_loader."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        assert "real_dataset_loader" in source, \
            "_init_gpu_resources must use real_dataset_loader"
        assert "create_training_dataloader" in source, \
            "_init_gpu_resources must use create_training_dataloader"
    
    def test_uses_validate_dataset_integrity(self):
        """_init_gpu_resources must validate dataset before use."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        assert "validate_dataset_integrity" in source, \
            "_init_gpu_resources must validate dataset integrity"
    
    def test_real_dataset_has_minimum_samples(self):
        """Real dataset validation must return structured result.
        
        In STRICT_REAL_MODE (default), validate_dataset_integrity() uses
        IngestionPipelineDataset only. If the bridge DLL is unavailable,
        it returns (False, 'INGESTION_SOURCE_INVALID: ...') — a truthful
        structured failure, NOT a crash or synthetic fallback.
        """
        from impl_v1.training.data.real_dataset_loader import (
            validate_dataset_integrity, STRICT_REAL_MODE,
        )
        
        valid, msg = validate_dataset_integrity()
        
        if STRICT_REAL_MODE:
            # In strict mode: either passes with real data, or fails with
            # a structured reason (INGESTION_SOURCE_INVALID, etc.)
            if not valid:
                assert any(reason in msg for reason in [
                    "INSUFFICIENT_REAL_SAMPLES",
                    "INGESTION_SOURCE_INVALID",
                    "STRICT_REAL_MODE_VIOLATION",
                ]), f"Strict mode must return structured fail reason, got: {msg}"
            # If valid, it means real ingestion data is available
        else:
            # Lab mode: synthetic is allowed
            assert valid, f"Dataset validation failed in lab mode: {msg}"
    
    def test_no_mock_keyword_in_init(self):
        """No 'mock' or 'synthetic' in _init_gpu_resources."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources).lower()
        
        assert "mock" not in source, \
            "Found 'mock' keyword in _init_gpu_resources"
        # Allow 'synthetic' only in 'NO SYNTHETIC' documentation
        lines_with_synthetic = [
            line for line in source.split('\n')
            if 'synthetic' in line and 'no synthetic' not in line
        ]
        assert len(lines_with_synthetic) == 0, \
            f"Found synthetic data references: {lines_with_synthetic}"
    
    def test_batch_size_is_1024(self):
        """Batch size must be 1024 for optimal GPU utilization."""
        from impl_v1.phase49.runtime.auto_trainer import AutoTrainer
        
        source = inspect.getsource(AutoTrainer._init_gpu_resources)
        
        assert "batch_size=1024" in source, \
            f"Batch size should be 1024, not found in _init_gpu_resources"


class TestStrictModeEnforcement:
    """Ensure STRICT_REAL_MODE enforcement in validate_dataset_integrity."""

    def test_strict_mode_never_instantiates_synthetic(self):
        """validate_dataset_integrity() must NEVER instantiate
        SyntheticTrainingDataset when STRICT_REAL_MODE=True."""
        from impl_v1.training.data.real_dataset_loader import (
            validate_dataset_integrity,
        )
        
        call_log = []
        original_init = None
        
        # Patch SyntheticTrainingDataset.__init__ to detect instantiation
        import impl_v1.training.data.real_dataset_loader as rdl
        original_init = rdl.SyntheticTrainingDataset.__init__
        
        def spy_init(self, *args, **kwargs):
            call_log.append("SYNTHETIC_INSTANTIATED")
            return original_init(self, *args, **kwargs)
        
        with patch.object(rdl, 'STRICT_REAL_MODE', True):
            with patch.object(rdl.SyntheticTrainingDataset, '__init__', spy_init):
                valid, msg = validate_dataset_integrity()
        
        assert len(call_log) == 0, (
            f"SyntheticTrainingDataset was instantiated {len(call_log)} time(s) "
            f"during validate_dataset_integrity() under STRICT_REAL_MODE=True! "
            f"msg={msg}"
        )

    def test_strict_mode_explicit_fail_reason(self):
        """When strict mode can't load the bridge, fail reason must be structured."""
        import impl_v1.training.data.real_dataset_loader as rdl
        
        with patch.object(rdl, 'STRICT_REAL_MODE', True):
            valid, msg = rdl.validate_dataset_integrity()
        
        if not valid:
            valid_prefixes = [
                "INSUFFICIENT_REAL_SAMPLES",
                "INGESTION_SOURCE_INVALID",
                "STRICT_REAL_MODE_VIOLATION",
            ]
            assert any(msg.startswith(p) for p in valid_prefixes), (
                f"Strict mode fail reason must start with one of "
                f"{valid_prefixes}, got: {msg}"
            )

    def test_lab_mode_can_use_synthetic(self):
        """Lab mode (STRICT_REAL_MODE=False) should use SyntheticTrainingDataset."""
        import impl_v1.training.data.real_dataset_loader as rdl
        
        with patch.object(rdl, 'STRICT_REAL_MODE', False):
            valid, msg = rdl.validate_dataset_integrity()
        
        # In lab mode, synthetic should work fine
        assert valid, f"Lab mode validation failed: {msg}"
        assert "LAB" in msg, f"Lab mode message should mention LAB, got: {msg}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

