from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

DEFAULT_THRESHOLD = 0.5
DEFAULT_THRESHOLD_ARTIFACT = Path("checkpoints/baseline_accuracy.json")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_float(value: object, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return numeric


def _normalize_threshold(value: object, default: float = DEFAULT_THRESHOLD) -> float:
    threshold = _coerce_float(value, default)
    return max(0.0, min(1.0, threshold))


def _default_payload() -> dict[str, object]:
    return {
        "baseline_accuracy": 0.0,
        "positive_threshold": DEFAULT_THRESHOLD,
        "checkpoint_accuracy": 0.0,
        "checkpoint_precision": 0.0,
        "checkpoint_recall": 0.0,
        "checkpoint_f1": 0.0,
        "updated_at": None,
    }


def load_threshold_artifact(path: str | Path = DEFAULT_THRESHOLD_ARTIFACT) -> dict[str, object]:
    artifact_path = Path(path)
    payload = _default_payload()
    if not artifact_path.exists():
        return payload

    try:
        loaded = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return payload

    if not isinstance(loaded, dict):
        return payload

    payload.update(loaded)
    payload["baseline_accuracy"] = _coerce_float(payload.get("baseline_accuracy"), 0.0)
    payload["positive_threshold"] = _normalize_threshold(payload.get("positive_threshold"))
    payload["checkpoint_accuracy"] = _coerce_float(payload.get("checkpoint_accuracy"), 0.0)
    payload["checkpoint_precision"] = _coerce_float(payload.get("checkpoint_precision"), 0.0)
    payload["checkpoint_recall"] = _coerce_float(payload.get("checkpoint_recall"), 0.0)
    payload["checkpoint_f1"] = _coerce_float(payload.get("checkpoint_f1"), 0.0)
    return payload


def save_threshold_artifact(
    path: str | Path = DEFAULT_THRESHOLD_ARTIFACT,
    *,
    baseline_accuracy: float,
    positive_threshold: float,
    checkpoint_accuracy: float,
    checkpoint_precision: float,
    checkpoint_recall: float,
    checkpoint_f1: float,
) -> dict[str, object]:
    artifact_path = Path(path)
    payload = load_threshold_artifact(artifact_path)
    payload.update(
        {
            "baseline_accuracy": round(float(baseline_accuracy), 6),
            "positive_threshold": round(_normalize_threshold(positive_threshold), 9),
            "checkpoint_accuracy": round(float(checkpoint_accuracy), 6),
            "checkpoint_precision": round(float(checkpoint_precision), 6),
            "checkpoint_recall": round(float(checkpoint_recall), 6),
            "checkpoint_f1": round(float(checkpoint_f1), 6),
            "updated_at": _utc_now(),
        }
    )

    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = artifact_path.with_suffix(f"{artifact_path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp_path, artifact_path)
    return payload


def load_positive_threshold(path: str | Path = DEFAULT_THRESHOLD_ARTIFACT) -> float:
    env_override = os.environ.get("YGB_POSITIVE_THRESHOLD")
    if env_override:
        return _normalize_threshold(env_override)
    return _normalize_threshold(load_threshold_artifact(path).get("positive_threshold"))


def classify_positive_probability(probability: float, threshold: float | None = None) -> int:
    active_threshold = _normalize_threshold(
        DEFAULT_THRESHOLD if threshold is None else threshold
    )
    return 1 if float(probability) >= active_threshold else 0


def compute_binary_metrics(
    labels: Sequence[int],
    positive_probabilities: Sequence[float],
    threshold: float,
) -> dict[str, object]:
    if len(labels) != len(positive_probabilities):
        raise ValueError("labels and probabilities must have the same length")
    if not labels:
        raise ValueError("at least one sample is required")

    active_threshold = _normalize_threshold(threshold)
    predictions = [
        classify_positive_probability(probability, active_threshold)
        for probability in positive_probabilities
    ]

    tp = fp = tn = fn = 0
    for truth, predicted in zip(labels, predictions):
        if truth == 1 and predicted == 1:
            tp += 1
        elif truth == 0 and predicted == 1:
            fp += 1
        elif truth == 0 and predicted == 0:
            tn += 1
        else:
            fn += 1

    total = max(len(labels), 1)
    accuracy = (tp + tn) / total
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = (2.0 * precision * recall) / (precision + recall)

    return {
        "threshold": active_threshold,
        "predictions": predictions,
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def calibrate_positive_threshold(
    labels: Sequence[int],
    positive_probabilities: Sequence[float],
    *,
    fallback_threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, object]:
    if len(labels) != len(positive_probabilities):
        raise ValueError("labels and probabilities must have the same length")
    if not labels:
        raise ValueError("at least one sample is required")

    clipped_probabilities = [
        _normalize_threshold(probability)
        for probability in positive_probabilities
    ]
    positives = [
        probability
        for truth, probability in zip(labels, clipped_probabilities)
        if truth == 1
    ]
    negatives = [
        probability
        for truth, probability in zip(labels, clipped_probabilities)
        if truth == 0
    ]

    if positives and negatives:
        max_negative = max(negatives)
        min_positive = min(positives)
        if max_negative < min_positive:
            midpoint = (max_negative + min_positive) / 2.0
            result = compute_binary_metrics(labels, clipped_probabilities, midpoint)
            result["strategy"] = "class_gap_midpoint"
            return result

    unique_probabilities = sorted(set(clipped_probabilities))
    candidates = {
        _normalize_threshold(fallback_threshold),
        DEFAULT_THRESHOLD,
        0.0,
        1.0,
    }
    candidates.update(unique_probabilities)
    for left, right in zip(unique_probabilities, unique_probabilities[1:]):
        candidates.add((left + right) / 2.0)

    best_result: dict[str, object] | None = None
    for candidate in sorted(candidates):
        result = compute_binary_metrics(labels, clipped_probabilities, candidate)
        score = (
            round(float(result["f1"]), 12),
            round(float(result["precision"]), 12),
            round(float(result["accuracy"]), 12),
            round(float(result["recall"]), 12),
            -abs(float(result["threshold"]) - _normalize_threshold(fallback_threshold)),
        )
        if best_result is None:
            best_result = {**result, "_score": score}
            continue
        if score > best_result["_score"]:
            best_result = {**result, "_score": score}

    assert best_result is not None
    best_result.pop("_score", None)
    best_result["strategy"] = "search"
    return best_result
