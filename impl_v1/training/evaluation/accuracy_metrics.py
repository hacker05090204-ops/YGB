"""Accuracy-first evaluation and feedback tracking.

This module stores only validated prediction outcomes and exposes metrics used by
training, verification, and reasoning layers.
"""

from __future__ import annotations

import json
import threading
from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Optional


def _safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def normalize_text(value: str) -> str:
    return " ".join(
        part
        for part in "".join(ch.lower() if ch.isalnum() else " " for ch in value).split()
        if part
    )


def token_set(value: str) -> set[str]:
    return set(normalize_text(value).split())


def token_overlap(left: str, right: str) -> float:
    left_tokens = token_set(left)
    right_tokens = token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union)


@dataclass(slots=True)
class EvaluationRecord:
    """Validated outcome used for metrics and future learning."""

    fingerprint: str
    category: str
    severity: str
    title: str
    description: str
    url: str
    predicted_positive: bool
    actual_positive: bool
    verification_status: str
    confidence: float
    ml_score: float = 0.0
    strategy_name: str = ""
    task_type: str = ""
    duplicate: bool = False
    false_positive: bool = False
    false_negative: bool = False
    validated: bool = True
    validation_source: str = "verification-layer"
    evidence: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=True)

    @classmethod
    def from_mapping(cls, payload: dict[str, Any]) -> "EvaluationRecord":
        filtered = dict(payload)
        filtered.setdefault("description", "")
        filtered.setdefault("url", "")
        filtered.setdefault("confidence", 0.0)
        filtered.setdefault("ml_score", 0.0)
        filtered.setdefault("strategy_name", "")
        filtered.setdefault("task_type", "")
        filtered.setdefault("duplicate", False)
        filtered.setdefault("false_positive", False)
        filtered.setdefault("false_negative", False)
        filtered.setdefault("validated", True)
        filtered.setdefault("validation_source", "verification-layer")
        filtered.setdefault("evidence", {})
        filtered.setdefault("created_at", _now_iso())
        return cls(**filtered)


@dataclass(slots=True)
class MetricsSnapshot:
    """Confusion-matrix backed metrics."""

    true_positives: int = 0
    true_negatives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    duplicates_rejected: int = 0
    validated_records: int = 0

    @property
    def accuracy(self) -> float:
        total = self.validated_records or (
            self.true_positives
            + self.true_negatives
            + self.false_positives
            + self.false_negatives
        )
        return _safe_div(self.true_positives + self.true_negatives, total)

    @property
    def precision(self) -> float:
        return _safe_div(
            self.true_positives,
            self.true_positives + self.false_positives,
        )

    @property
    def recall(self) -> float:
        return _safe_div(
            self.true_positives,
            self.true_positives + self.false_negatives,
        )

    @property
    def false_positive_rate(self) -> float:
        return _safe_div(
            self.false_positives,
            self.false_positives + self.true_negatives,
        )

    @property
    def false_negative_rate(self) -> float:
        return _safe_div(
            self.false_negatives,
            self.false_negatives + self.true_positives,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "true_positives": self.true_positives,
            "true_negatives": self.true_negatives,
            "false_positives": self.false_positives,
            "false_negatives": self.false_negatives,
            "duplicates_rejected": self.duplicates_rejected,
            "validated_records": self.validated_records,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "false_positive_rate": round(self.false_positive_rate, 4),
            "false_negative_rate": round(self.false_negative_rate, 4),
        }


def metrics_from_records(records: Iterable[EvaluationRecord]) -> MetricsSnapshot:
    snapshot = MetricsSnapshot()
    for record in records:
        if not record.validated:
            continue
        snapshot.validated_records += 1
        if record.duplicate:
            snapshot.duplicates_rejected += 1
        if record.predicted_positive and record.actual_positive:
            snapshot.true_positives += 1
        elif record.predicted_positive and not record.actual_positive:
            snapshot.false_positives += 1
        elif not record.predicted_positive and record.actual_positive:
            snapshot.false_negatives += 1
        else:
            snapshot.true_negatives += 1
    return snapshot


@dataclass(slots=True)
class StrategyPerformance:
    """Aggregated performance used by the thinking layer."""

    strategy_name: str
    task_type: str
    runs: int = 0
    verified_findings: int = 0
    rejected_findings: int = 0
    duplicate_findings: int = 0

    @property
    def precision(self) -> float:
        return _safe_div(
            self.verified_findings,
            self.verified_findings + self.rejected_findings,
        )

    @property
    def duplicate_rate(self) -> float:
        return _safe_div(
            self.duplicate_findings,
            self.verified_findings + self.rejected_findings + self.duplicate_findings,
        )

    @property
    def score(self) -> float:
        base = self.precision if self.runs else 0.75
        penalty = min(self.duplicate_rate * 0.5, 0.25)
        return max(0.1, min(0.99, base - penalty))

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "task_type": self.task_type,
            "runs": self.runs,
            "verified_findings": self.verified_findings,
            "rejected_findings": self.rejected_findings,
            "duplicate_findings": self.duplicate_findings,
            "precision": round(self.precision, 4),
            "duplicate_rate": round(self.duplicate_rate, 4),
            "score": round(self.score, 4),
        }


class StrategyFeedbackStore:
    """Outcome-weighted strategy performance memory."""

    def __init__(self) -> None:
        self._entries: dict[tuple[str, str], StrategyPerformance] = {}

    def record(
        self,
        *,
        strategy_name: str,
        task_type: str,
        verified_findings: int,
        rejected_findings: int,
        duplicate_findings: int,
    ) -> StrategyPerformance:
        key = (task_type, strategy_name)
        entry = self._entries.get(key)
        if entry is None:
            entry = StrategyPerformance(
                strategy_name=strategy_name, task_type=task_type
            )
            self._entries[key] = entry
        entry.runs += 1
        entry.verified_findings += max(0, int(verified_findings))
        entry.rejected_findings += max(0, int(rejected_findings))
        entry.duplicate_findings += max(0, int(duplicate_findings))
        return entry

    def get(self, *, strategy_name: str, task_type: str) -> StrategyPerformance:
        return self._entries.get(
            (task_type, strategy_name),
            StrategyPerformance(strategy_name=strategy_name, task_type=task_type),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            f"{task_type}:{strategy_name}": entry.to_dict()
            for (task_type, strategy_name), entry in self._entries.items()
        }

    def restore(self, payload: dict[str, Any]) -> None:
        self._entries.clear()
        for raw_key, raw_entry in payload.items():
            if not isinstance(raw_entry, dict):
                continue
            task_type, _, strategy_name = str(raw_key).partition(":")
            entry = StrategyPerformance(
                strategy_name=str(raw_entry.get("strategy_name") or strategy_name),
                task_type=str(raw_entry.get("task_type") or task_type),
                runs=int(raw_entry.get("runs", 0)),
                verified_findings=int(raw_entry.get("verified_findings", 0)),
                rejected_findings=int(raw_entry.get("rejected_findings", 0)),
                duplicate_findings=int(raw_entry.get("duplicate_findings", 0)),
            )
            self._entries[(entry.task_type, entry.strategy_name)] = entry


class AccuracyFeedbackStore:
    """Persistent validated feedback used for evaluation and dataset building."""

    def __init__(self, records_path: Optional[Path] = None) -> None:
        self.records_path = records_path or (
            Path(__file__).resolve().parents[3] / "reports" / "verified_findings.jsonl"
        )
        self._records: list[EvaluationRecord] = []
        self._recent_by_category: dict[str, deque[EvaluationRecord]] = defaultdict(
            lambda: deque(maxlen=128)
        )
        self._loaded = False
        self._lock = threading.Lock()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.records_path.exists():
            return
        with self._lock:
            with self.records_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    record = EvaluationRecord.from_mapping(payload)
                    self._records.append(record)
                    self._recent_by_category[record.category.upper()].append(record)

    def add(self, record: EvaluationRecord) -> EvaluationRecord:
        self._ensure_loaded()
        self.records_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with self.records_path.open("a", encoding="utf-8") as handle:
                handle.write(record.to_json() + "\n")
            self._records.append(record)
            self._recent_by_category[record.category.upper()].append(record)
        return record

    def records(self) -> list[EvaluationRecord]:
        self._ensure_loaded()
        return list(self._records)

    def metrics(self) -> MetricsSnapshot:
        self._ensure_loaded()
        return metrics_from_records(self._records)

    def metrics_by_category(self) -> dict[str, dict[str, Any]]:
        self._ensure_loaded()
        grouped: dict[str, list[EvaluationRecord]] = defaultdict(list)
        for record in self._records:
            grouped[record.category.upper()].append(record)
        return {
            category: metrics_from_records(records).to_dict()
            for category, records in sorted(grouped.items())
        }

    def recent_false_positive_rate(self, category: str, *, window: int = 50) -> float:
        self._ensure_loaded()
        recent = list(self._recent_by_category[category.upper()])[-window:]
        if not recent:
            return 0.0
        false_positives = sum(1 for record in recent if record.false_positive)
        return _safe_div(false_positives, len(recent))

    def summary(self) -> dict[str, Any]:
        overall = self.metrics().to_dict()
        overall["by_category"] = self.metrics_by_category()
        return overall
