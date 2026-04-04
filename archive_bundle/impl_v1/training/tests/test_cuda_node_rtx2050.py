"""
test_cuda_node_rtx2050.py — Tests for CUDA RTX 2050 DDP Node

All tests mock torch.cuda so they run on any machine without a real GPU.
"""

import hashlib
import json
import math
import os
import sys
from collections import Counter
from dataclasses import asdict
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from impl_v1.training.distributed.dataset_validator import (
    compute_dataset_hash,
    validate_dataset,
    _compute_label_distribution,
    _compute_shannon_entropy,
    _check_label_tolerance,
)
from impl_v1.training.distributed.cuda_node_rtx2050 import (
    RTX2050Node,
    CUDAVerification,
)


# ===========================================================================
# FIXTURES
# ===========================================================================

@pytest.fixture
def dataset():
    """Deterministic dataset for testing."""
    rng = np.random.RandomState(42)
    X = rng.randn(2000, 256).astype(np.float32)
    y = rng.randint(0, 2, 2000).astype(np.int64)
    return X, y


@pytest.fixture
def dataset_hash(dataset):
    X, y = dataset
    return compute_dataset_hash(X, y)


@pytest.fixture
def label_dist(dataset):
    _, y = dataset
    return _compute_label_distribution(y)


@pytest.fixture
def node_kwargs(dataset, dataset_hash, label_dist):
    """Default kwargs for RTX2050Node."""
    X, y = dataset
    return dict(
        X=X, y=y,
        expected_dataset_hash=dataset_hash,
        expected_sample_count=2000,
        expected_feature_dim=256,
        expected_label_distribution=label_dist,
        epochs=1,
        starting_batch=512,
        input_dim=256,
        expected_cuda_version=None,  # Skip version check
    )


# ===========================================================================
# DATASET VALIDATOR TESTS
# ===========================================================================

class TestDatasetValidator:

    def test_hash_deterministic(self, dataset, dataset_hash):
        X, y = dataset
        assert compute_dataset_hash(X, y) == dataset_hash

    def test_hash_changes_on_mutation(self, dataset, dataset_hash):
        X, y = dataset
        X_copy = X.copy()
        X_copy[0, 0] += 1.0
        assert compute_dataset_hash(X_copy, y) != dataset_hash

    def test_validation_passes(self, dataset, dataset_hash, label_dist):
        X, y = dataset
        result = validate_dataset(
            X, y,
            expected_hash=dataset_hash,
            expected_sample_count=2000,
            expected_feature_dim=256,
            expected_label_distribution=label_dist,
        )
        assert result.valid is True
        assert result.hash_match is True
        assert result.sample_count_match is True
        assert result.feature_dim_match is True
        assert result.label_dist_within_tolerance is True
        assert result.entropy_above_threshold is True
        assert len(result.errors) == 0

    def test_wrong_hash_fails(self, dataset, label_dist):
        X, y = dataset
        result = validate_dataset(
            X, y,
            expected_hash="0000000000000000",
            expected_sample_count=2000,
            expected_feature_dim=256,
            expected_label_distribution=label_dist,
        )
        assert result.valid is False
        assert result.hash_match is False

    def test_wrong_sample_count_fails(self, dataset, dataset_hash, label_dist):
        X, y = dataset
        result = validate_dataset(
            X, y,
            expected_hash=dataset_hash,
            expected_sample_count=9999,
            expected_feature_dim=256,
            expected_label_distribution=label_dist,
        )
        assert result.valid is False
        assert result.sample_count_match is False

    def test_wrong_feature_dim_fails(self, dataset, dataset_hash, label_dist):
        X, y = dataset
        result = validate_dataset(
            X, y,
            expected_hash=dataset_hash,
            expected_sample_count=2000,
            expected_feature_dim=128,
            expected_label_distribution=label_dist,
        )
        assert result.valid is False
        assert result.feature_dim_match is False

    def test_label_distribution_tolerance(self, dataset, dataset_hash):
        X, y = dataset
        bad_dist = {0: 0.1, 1: 0.9}
        result = validate_dataset(
            X, y,
            expected_hash=dataset_hash,
            expected_sample_count=2000,
            expected_feature_dim=256,
            expected_label_distribution=bad_dist,
            label_tolerance=0.01,
        )
        assert result.label_dist_within_tolerance is False

    def test_entropy_threshold(self):
        """All-same labels should fail entropy check."""
        X = np.zeros((100, 10), dtype=np.float32)
        y = np.zeros(100, dtype=np.int64)
        h = compute_dataset_hash(X, y)
        result = validate_dataset(
            X, y,
            expected_hash=h,
            expected_sample_count=100,
            expected_feature_dim=10,
            entropy_threshold=0.5,
        )
        assert result.entropy_above_threshold is False
        assert result.valid is False

    def test_shannon_entropy_calculation(self):
        # 50/50 binary → 1.0 bit
        dist = {0: 0.5, 1: 0.5}
        assert abs(_compute_shannon_entropy(dist) - 1.0) < 0.001

        # All one class → 0.0 bits
        dist_one = {0: 1.0}
        assert _compute_shannon_entropy(dist_one) == 0.0


# ===========================================================================
# CUDA VERIFICATION TESTS
# ===========================================================================

class TestCUDAVerification:

    def _make_mock_props(self, major=8, minor=6, name="NVIDIA GeForce RTX 2050",
                         total_memory=4 * 1024 ** 3):
        props = MagicMock()
        props.major = major
        props.minor = minor
        props.name = name
        props.total_memory = total_memory
        return props

    @patch("impl_v1.training.distributed.cuda_node_rtx2050.torch", create=True)
    def test_cuda_verification_passes(self, mock_torch, node_kwargs):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_properties.return_value = self._make_mock_props()
        mock_torch.version.cuda = "12.1"

        node = RTX2050Node(**node_kwargs)
        # Patch the import inside verify_cuda
        with patch.dict('sys.modules', {'torch': mock_torch}):
            result = node.verify_cuda()

        assert result.passed is True
        assert result.cuda_available is True
        assert result.fp16_supported is True
        assert result.cc_version >= 7.5

    @patch("impl_v1.training.distributed.cuda_node_rtx2050.torch", create=True)
    def test_cuda_not_available(self, mock_torch, node_kwargs):
        mock_torch.cuda.is_available.return_value = False

        node = RTX2050Node(**node_kwargs)
        with patch.dict('sys.modules', {'torch': mock_torch}):
            result = node.verify_cuda()

        assert result.passed is False
        assert result.cuda_available is False

    @patch("impl_v1.training.distributed.cuda_node_rtx2050.torch", create=True)
    def test_low_compute_capability(self, mock_torch, node_kwargs):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_properties.return_value = self._make_mock_props(
            major=6, minor=1
        )
        mock_torch.version.cuda = "12.1"

        node = RTX2050Node(**node_kwargs)
        with patch.dict('sys.modules', {'torch': mock_torch}):
            result = node.verify_cuda()

        assert result.passed is False
        assert any("Compute capability" in e for e in result.errors)

    @patch("impl_v1.training.distributed.cuda_node_rtx2050.torch", create=True)
    def test_cuda_version_mismatch(self, mock_torch, node_kwargs):
        mock_torch.cuda.is_available.return_value = True
        mock_torch.cuda.get_device_properties.return_value = self._make_mock_props()
        mock_torch.version.cuda = "11.8"

        node_kwargs['expected_cuda_version'] = "12.1"
        node = RTX2050Node(**node_kwargs)
        with patch.dict('sys.modules', {'torch': mock_torch}):
            result = node.verify_cuda()

        assert result.passed is False
        assert result.cuda_version_match is False


# ===========================================================================
# DDP GROUP TESTS
# ===========================================================================

class TestNCCLGroupJoin:

    def test_world_size_equals_cuda_nodes(self, node_kwargs):
        nodes = [
            {'backend': 'cuda', 'ddp_eligible': True, 'device_name': 'RTX 2050'},
            {'backend': 'cuda', 'ddp_eligible': True, 'device_name': 'RTX 3050'},
        ]
        node_kwargs['all_nodes'] = nodes

        node = RTX2050Node(**node_kwargs)

        with patch(
            'impl_v1.training.distributed.cuda_ddp_group.init_cuda_ddp',
            return_value=True,
        ):
            ok = node.join_nccl_group()

        assert ok is True
        assert node.world_size == 2

    def test_mps_nodes_excluded(self, node_kwargs):
        nodes = [
            {'backend': 'cuda', 'ddp_eligible': True, 'device_name': 'RTX 2050'},
            {'backend': 'mps', 'ddp_eligible': False, 'device_name': 'M1'},
        ]
        node_kwargs['all_nodes'] = nodes

        node = RTX2050Node(**node_kwargs)

        with patch(
            'impl_v1.training.distributed.cuda_ddp_group.init_cuda_ddp',
            return_value=True,
        ):
            ok = node.join_nccl_group()

        assert ok is True
        assert node.world_size == 1  # Only the CUDA node


# ===========================================================================
# DETERMINISTIC MODE TESTS
# ===========================================================================

class TestDeterministicMode:

    @patch("impl_v1.training.distributed.cuda_node_rtx2050.torch", create=True)
    def test_deterministic_config_set(self, mock_torch, node_kwargs):
        mock_torch.use_deterministic_algorithms = MagicMock()
        mock_torch.backends.cudnn = MagicMock()

        node = RTX2050Node(**node_kwargs)
        with patch.dict('sys.modules', {'torch': mock_torch}):
            node.init_deterministic()

        mock_torch.manual_seed.assert_called_once_with(42)
        assert mock_torch.backends.cudnn.deterministic is True
        assert mock_torch.backends.cudnn.benchmark is False
        assert os.environ.get("CUBLAS_WORKSPACE_CONFIG") == ":4096:8"
        mock_torch.use_deterministic_algorithms.assert_called_once_with(True)


# ===========================================================================
# STRUCTURED LOG TESTS
# ===========================================================================

class TestStructuredLog:

    def test_log_output_format(self, node_kwargs):
        node = RTX2050Node(**node_kwargs)
        node.world_size = 2
        node.optimal_batch_2050 = 2048
        node.weight_hash = "abc123"
        node.dataset_hash = "def456"

        from impl_v1.training.distributed.cuda_node_rtx2050 import EpochReport
        node.epoch_reports = [
            EpochReport(
                epoch=0, weight_hash="abc123", loss=0.5,
                samples_processed=2000, samples_per_sec=5000.0,
                elapsed_sec=0.4,
            )
        ]

        log = node.emit_log()

        assert log["world_size"] == 2
        assert log["local_batch"] == 2048
        assert log["samples_per_sec"] == 5000.0
        assert log["weight_hash"] == "abc123"
        assert log["dataset_hash"] == "def456"


# ===========================================================================
# FULL PIPELINE INTEGRATION (CPU-only mock)
# ===========================================================================

class TestFullPipeline:

    def test_dataset_validation_failure_aborts(self, node_kwargs):
        """Pipeline should abort if dataset hash doesn't match."""
        node_kwargs['expected_dataset_hash'] = "wrong_hash"

        node = RTX2050Node(**node_kwargs)

        # Mock CUDA as available for step 1
        with patch.object(node, 'verify_cuda') as vc:
            vc.return_value = CUDAVerification(
                cuda_available=True, compute_capability="8.6",
                cc_version=8.6, fp16_supported=True,
                cuda_version="12.1", cuda_version_match=True,
                device_name="RTX 2050", vram_total_mb=4096,
                passed=True, errors=[],
            )
            result = node.run()

        assert result.cuda_verified is True
        assert result.dataset_valid is False
        assert result.epochs_completed == 0
        assert len(result.errors) > 0
