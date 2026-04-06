import numpy as np
import pytest

from backend.training.representation_bridge import (
    DataValueError,
    RealFeatureLoader,
    RepresentationExpander,
    SyntheticDataBlockedError,
)


def test_representation_bridge_generate_http_features_raises_blocked_error():
    expander = RepresentationExpander()

    with pytest.raises(SyntheticDataBlockedError, match="blocked"):
        expander.generate_http_features(2)


def test_representation_bridge_expand_accepts_real_numpy_arrays():
    expander = RepresentationExpander()
    features = np.ones((3, 256), dtype=np.float32)

    expanded = expander.expand(features)

    assert expanded.shape == (3, 256)
    assert expanded.dtype == np.float32
    assert np.array_equal(expanded, features)


def test_real_feature_loader_loads_valid_npy_shape(tmp_path):
    features = np.arange(512, dtype=np.float32).reshape(2, 256)
    path = tmp_path / "features.npy"
    np.save(path, features)

    loaded = RealFeatureLoader.load(path)

    assert loaded.shape == (2, 256)
    assert loaded.dtype == np.float32
    assert np.array_equal(loaded, features)


def test_real_feature_loader_rejects_nan_values(tmp_path):
    features = np.zeros((2, 256), dtype=np.float32)
    features[1, 10] = np.nan
    path = tmp_path / "features_nan.npy"
    np.save(path, features)

    with pytest.raises(DataValueError, match="non-finite"):
        RealFeatureLoader.load(path)
