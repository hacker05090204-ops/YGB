from __future__ import annotations

import json
import logging

import backend.training.runtime_status_validator as validator
from backend.training.incremental_trainer import AccuracySnapshot


class _FakeTrainer:
    def __init__(self, *args, **kwargs) -> None:
        pass

    def benchmark_current_model(self, max_samples: int = 1500) -> dict[str, object]:
        return {
            "samples": max_samples,
            "source": "bridge_state",
            "threshold": 0.81,
            "accuracy": 0.96,
            "precision": 0.98,
            "recall": 0.95,
            "f1": 0.9649,
            "recommended_threshold": 0.8,
            "recommended_strategy": "class_gap_midpoint",
        }


class _LowPrecisionTrainer(_FakeTrainer):
    def benchmark_current_model(self, max_samples: int = 1500) -> dict[str, object]:
        result = super().benchmark_current_model(max_samples=max_samples)
        result["precision"] = 0.71
        return result


def test_validate_promotion_readiness_returns_false_and_logs_thresholds(caplog):
    snapshot = AccuracySnapshot(
        epoch=7,
        accuracy=0.8,
        precision=0.69,
        recall=0.64,
        f1=0.74,
        auc_roc=0.86,
        taken_at="2026-04-07T10:00:00+00:00",
    )

    with caplog.at_level(logging.WARNING):
        ready = validator.validate_promotion_readiness(snapshot)

    assert ready is False
    assert "f1=0.7400" in caplog.text
    assert "precision=0.6900" in caplog.text
    assert "recall=0.6400" in caplog.text


def test_validate_promotion_readiness_returns_true_when_thresholds_pass():
    snapshot = AccuracySnapshot(
        epoch=8,
        accuracy=0.84,
        precision=0.8,
        recall=0.75,
        f1=0.77,
        auc_roc=0.9,
        taken_at="2026-04-07T10:05:00+00:00",
    )

    assert validator.validate_promotion_readiness(snapshot) is True


def test_precision_breach_validator_clears_stale_flag(tmp_path, monkeypatch):
    runtime_path = tmp_path / "runtime_status.json"
    runtime_path.write_text(
        json.dumps(
            {
                "precision_breach": True,
                "containment_active": True,
                "containment_reason": "precision_breach: stale",
                "merge_status": "blocked_precision_breach",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(validator, "IncrementalTrainer", _FakeTrainer)

    result = validator.validate_precision_breach_status(
        runtime_path,
        precision_threshold=0.95,
        max_samples=256,
    )

    payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert result["state"] == "cleared"
    assert payload["precision_breach"] is False
    assert payload["containment_active"] is False
    assert payload["containment_reason"] is None
    assert payload["merge_status"] is None
    assert payload["validation_samples"] == 256


def test_precision_breach_validator_keeps_block_when_precision_low(tmp_path, monkeypatch):
    runtime_path = tmp_path / "runtime_status.json"
    runtime_path.write_text(json.dumps({"precision_breach": True}), encoding="utf-8")
    monkeypatch.setattr(validator, "IncrementalTrainer", _LowPrecisionTrainer)

    result = validator.validate_precision_breach_status(
        runtime_path,
        precision_threshold=0.95,
        max_samples=128,
    )

    payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    assert result["state"] == "blocked"
    assert payload["precision_breach"] is True
    assert payload["containment_active"] is True
    assert "current_precision=0.7100" in payload["containment_reason"]
