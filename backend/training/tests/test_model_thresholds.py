from __future__ import annotations

import json

import pytest

from backend.training.model_thresholds import (
    calibrate_positive_threshold,
    classify_positive_probability,
    load_positive_threshold,
    save_threshold_artifact,
)


def test_calibrate_positive_threshold_uses_class_gap_midpoint():
    result = calibrate_positive_threshold(
        [0, 0, 1, 1],
        [0.11, 0.21, 0.81, 0.91],
    )

    assert result["strategy"] == "class_gap_midpoint"
    assert result["threshold"] == pytest.approx(0.51)
    assert result["accuracy"] == pytest.approx(1.0)
    assert result["precision"] == pytest.approx(1.0)
    assert result["recall"] == pytest.approx(1.0)
    assert result["f1"] == pytest.approx(1.0)


def test_threshold_artifact_round_trip(tmp_path):
    artifact_path = tmp_path / "baseline_accuracy.json"
    save_threshold_artifact(
        artifact_path,
        baseline_accuracy=0.91,
        positive_threshold=0.77,
        checkpoint_accuracy=0.89,
        checkpoint_precision=0.95,
        checkpoint_recall=0.83,
        checkpoint_f1=0.88,
    )

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["positive_threshold"] == pytest.approx(0.77)
    assert load_positive_threshold(artifact_path) == pytest.approx(0.77)
    assert classify_positive_probability(0.76, 0.77) == 0
    assert classify_positive_probability(0.77, 0.77) == 1
