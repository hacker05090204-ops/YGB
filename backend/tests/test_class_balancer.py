import pytest

from backend.training.class_balancer import ClassBalancer


def test_class_balancer_computes_inverse_frequency_weights_and_repeats_real_samples_only():
    balancer = ClassBalancer()

    report = balancer.balance_indices(
        sample_indices=[10, 11, 12, 13],
        labels=[0, 0, 0, 1],
    )

    assert report.class_counts == {0: 3, 1: 1}
    assert report.class_weights[0] == pytest.approx(2.0 / 3.0)
    assert report.class_weights[1] == pytest.approx(2.0)
    assert report.oversampled_indices.count(13) == 3
    assert set(report.oversampled_indices) == {10, 11, 12, 13}
    assert report.added_indices == 2
