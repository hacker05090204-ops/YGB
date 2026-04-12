import pytest

from backend.training.metrics_tracker import MetricsTracker


def test_metrics_tracker_reports_per_class_metrics_and_extrema():
    tracker = MetricsTracker(label_names={0: "NEGATIVE", 1: "POSITIVE"})

    report = tracker.update(
        labels=[0, 0, 1, 1, 1],
        predictions=[0, 1, 1, 0, 1],
    )

    assert report.accuracy == pytest.approx(0.6)
    assert report.macro_precision == pytest.approx((0.5 + (2.0 / 3.0)) / 2.0)
    assert report.macro_recall == pytest.approx((0.5 + (2.0 / 3.0)) / 2.0)
    assert report.macro_f1 == pytest.approx((0.5 + (2.0 / 3.0)) / 2.0)
    assert report.weighted_f1 == pytest.approx(0.6)
    assert report.per_class[0].precision == pytest.approx(0.5)
    assert report.per_class[0].recall == pytest.approx(0.5)
    assert report.per_class[0].f1 == pytest.approx(0.5)
    assert report.per_class[0].support == 2
    assert report.per_class[1].precision == pytest.approx(2.0 / 3.0)
    assert report.per_class[1].recall == pytest.approx(2.0 / 3.0)
    assert report.per_class[1].f1 == pytest.approx(2.0 / 3.0)
    assert report.per_class[1].support == 3
    assert report.worst_class.name == "NEGATIVE"
    assert report.best_class.name == "POSITIVE"
    assert tracker.last_report == report
    assert tracker.history[-1] == report
