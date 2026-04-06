import numpy as np
import pytest


def test_representation_expander_is_blocked_in_backend_runtime():
    from backend.training.representation_bridge import (
        RepresentationExpander,
        SyntheticDataBlockedError,
    )

    expander = RepresentationExpander()

    with pytest.raises(SyntheticDataBlockedError, match="blocked"):
        expander.generate_http_features(1)


def test_feature_diversifier_random_augmentation_is_blocked():
    from backend.training.feature_bridge import FeatureDiversifier

    diversifier = FeatureDiversifier()
    features = np.zeros((2, 256), dtype=np.float32)

    with pytest.raises(RuntimeError, match="feature augmentation is forbidden"):
        diversifier.apply_noise_augmentation(features, epoch=1, batch=1)


def test_representation_validator_rejects_near_duplicate_tensor_on_bridge_path():
    from backend.training.representation_bridge import (
        InvalidRepresentationError,
        RepresentationValidator,
        validate_representation_for_bridge,
    )

    validator = RepresentationValidator()
    stored = np.array([[1.0, 0.0, 0.0]], dtype=np.float32)
    candidate = np.array([0.99995, 0.01, 0.0], dtype=np.float32)

    result = validator.validate(candidate, stored)

    assert result.valid is False
    assert result.cosine_similarity is not None
    assert result.cosine_similarity > 0.99

    with pytest.raises(InvalidRepresentationError, match="near-duplicate"):
        validate_representation_for_bridge(candidate, stored, validator=validator)


def test_feature_bridge_health_report_is_exposed_via_getter():
    from backend.training.feature_bridge import FeatureDiversifier

    diversifier = FeatureDiversifier()
    report = diversifier.get_health(
        {
            "features/valid.npy": np.zeros((2, 256), dtype=np.float32),
            "features/invalid.npy": np.full((2, 256), np.inf, dtype=np.float32),
        }
    )

    assert report.total == 2
    assert report.valid == 1
    assert report.invalid == 1
    assert report.invalid_paths == ["features/invalid.npy"]
    assert diversifier.get_health().invalid_paths == ["features/invalid.npy"]
