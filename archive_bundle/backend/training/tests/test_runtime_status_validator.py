from __future__ import annotations

import json

import backend.training.runtime_status_validator as validator


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
