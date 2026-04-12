"""Reinforcement-learning feedback collection backed by real outcome signals."""

from __future__ import annotations

import json
import logging
import math
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from backend.ingestion.models import normalize_severity

logger = logging.getLogger("ygb.training.rl_feedback")
DEFAULT_REWARD_BUFFER_PATH = Path(
    os.environ.get("YGB_RL_REWARD_BUFFER_PATH", "data/rl_reward_buffer.json")
)
_SEVERITY_RANKS = {
    "UNKNOWN": 0,
    "INFO": 1,
    "LOW": 2,
    "MEDIUM": 3,
    "HIGH": 4,
    "CRITICAL": 5,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class OutcomeSignal:
    sample_id: str
    cve_id: str
    predicted_severity: str
    outcome: str
    reward: float
    source: str
    observed_at: str = field(default_factory=_utc_now)
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        sample_id = str(self.sample_id or "").strip()
        if not sample_id:
            raise ValueError("OutcomeSignal.sample_id must not be empty")
        cve_id = str(self.cve_id or "").strip().upper()
        predicted_severity = normalize_severity(str(self.predicted_severity or "UNKNOWN"))
        outcome = str(self.outcome or "").strip()
        source = str(self.source or "").strip()
        if not outcome:
            raise ValueError("OutcomeSignal.outcome must not be empty")
        if not source:
            raise ValueError("OutcomeSignal.source must not be empty")
        reward = float(self.reward)
        if not math.isfinite(reward):
            raise ValueError("OutcomeSignal.reward must be finite")
        _parse_timestamp(self.observed_at)
        if not isinstance(self.metadata, dict):
            raise TypeError("OutcomeSignal.metadata must be a dict")
        normalized_metadata = {
            str(key): str(value) for key, value in self.metadata.items()
        }
        object.__setattr__(self, "sample_id", sample_id)
        object.__setattr__(self, "cve_id", cve_id)
        object.__setattr__(self, "predicted_severity", predicted_severity)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "reward", reward)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "metadata", normalized_metadata)


class RewardBuffer:
    def __init__(
        self,
        signals: Iterable[OutcomeSignal] | None = None,
        *,
        path: str | Path | None = None,
        max_signals: int = 5000,
    ) -> None:
        self.path = Path(path) if path is not None else DEFAULT_REWARD_BUFFER_PATH
        self.max_signals = max(int(max_signals), 1)
        self._lock = threading.Lock()
        self._signals: list[OutcomeSignal] = []
        if signals is not None:
            for signal in signals:
                self.add(signal)

    def add(self, signal: OutcomeSignal) -> None:
        if not isinstance(signal, OutcomeSignal):
            raise TypeError("RewardBuffer.add() requires an OutcomeSignal instance")
        with self._lock:
            self._signals.append(signal)
            if len(self._signals) > self.max_signals:
                self._signals = self._signals[-self.max_signals :]

    def snapshot(self) -> list[OutcomeSignal]:
        with self._lock:
            return list(self._signals)

    def get_weighted_signals(
        self,
        *,
        now: datetime | None = None,
        max_age_days: float = 30.0,
        half_life_days: float = 7.0,
    ) -> dict[str, float]:
        current_time = now.astimezone(timezone.utc) if now is not None else datetime.now(timezone.utc)
        max_age_seconds = max(float(max_age_days), 0.0) * 86400.0
        half_life_seconds = max(float(half_life_days), 1e-6) * 86400.0
        weighted_rewards: dict[str, float] = {}
        for signal in self.snapshot():
            observed_at = _parse_timestamp(signal.observed_at)
            age_seconds = max(
                0.0,
                (current_time - observed_at).total_seconds(),
            )
            if age_seconds > max_age_seconds:
                continue
            decay = math.pow(0.5, age_seconds / half_life_seconds)
            weighted_rewards[signal.sample_id] = weighted_rewards.get(signal.sample_id, 0.0) + (
                float(signal.reward) * decay
            )
        return weighted_rewards

    def mean_reward(self) -> float:
        signals = self.snapshot()
        if not signals:
            return 0.0
        return float(sum(signal.reward for signal in signals) / len(signals))

    def stats(self) -> dict[str, float | int]:
        signals = self.snapshot()
        return {
            "total_signals": len(signals),
            "mean_reward": self.mean_reward(),
            "positive_signals": sum(1 for signal in signals if signal.reward > 0.0),
            "negative_signals": sum(1 for signal in signals if signal.reward < 0.0),
        }

    def save(self, path: str | Path | None = None) -> Path:
        target_path = Path(path) if path is not None else self.path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_suffix(f"{target_path.suffix}.tmp")
        payload = [asdict(signal) for signal in self.snapshot()]
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temp_path, target_path)
        return target_path

    @classmethod
    def load(
        cls,
        path: str | Path | None = None,
        *,
        max_signals: int = 5000,
    ) -> "RewardBuffer":
        target_path = Path(path) if path is not None else DEFAULT_REWARD_BUFFER_PATH
        if not target_path.exists():
            return cls(path=target_path, max_signals=max_signals)
        payload = json.loads(target_path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("RewardBuffer persistence payload must be a list")
        signals: list[OutcomeSignal] = []
        for entry in payload:
            if not isinstance(entry, dict):
                raise ValueError("RewardBuffer persistence payload entries must be objects")
            signals.append(OutcomeSignal(**entry))
        return cls(signals, path=target_path, max_signals=max_signals)


@dataclass(frozen=True)
class _RecordedPrediction:
    sample_id: str
    cve_id: str
    predicted_severity: str
    recorded_at: str


class RLFeedbackCollector:
    def __init__(self, reward_buffer: RewardBuffer | None = None) -> None:
        self._reward_buffer = reward_buffer or RewardBuffer.load()
        self._lock = threading.Lock()
        self._predictions_by_cve: dict[str, dict[str, _RecordedPrediction]] = {}
        self._processed_events: set[str] = set()
        self._hydrate_processed_events()

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return _SEVERITY_RANKS.get(normalize_severity(severity), 0)

    @staticmethod
    def _normalize_signal_source(source: str) -> str:
        normalized_source = str(source or "").strip().lower()
        if normalized_source.endswith("_severity_update"):
            normalized_source = normalized_source[: -len("_severity_update")]
        return normalized_source

    @staticmethod
    def _kev_event_key(cve_id: str, sample_id: str) -> str:
        return f"kev:{str(cve_id or '').strip().upper()}:{str(sample_id or '').strip()}"

    @classmethod
    def _severity_event_key(
        cls,
        *,
        source: str,
        cve_id: str,
        previous_severity: str,
        new_severity: str,
        sample_id: str,
    ) -> str:
        return (
            f"sev:{cls._normalize_signal_source(source)}:{str(cve_id or '').strip().upper()}:"
            f"{normalize_severity(previous_severity)}:{normalize_severity(new_severity)}:{str(sample_id or '').strip()}"
        )

    def _hydrate_processed_events(self) -> None:
        for signal in self._reward_buffer.snapshot():
            if signal.source == "cisa_kev":
                self._processed_events.add(
                    self._kev_event_key(signal.cve_id, signal.sample_id)
                )
                continue
            previous_severity = signal.metadata.get("previous_severity")
            new_severity = signal.metadata.get("new_severity")
            if previous_severity is None or new_severity is None:
                continue
            signal_source = self._normalize_signal_source(
                str(signal.metadata.get("signal_source") or signal.source or "")
            )
            if not signal_source:
                continue
            self._processed_events.add(
                self._severity_event_key(
                    source=signal_source,
                    cve_id=signal.cve_id,
                    previous_severity=str(previous_severity),
                    new_severity=str(new_severity),
                    sample_id=signal.sample_id,
                )
            )

    def record_prediction(
        self,
        *,
        sample_id: str,
        cve_id: str,
        predicted_severity: str,
    ) -> None:
        normalized_sample_id = str(sample_id or "").strip()
        normalized_cve_id = str(cve_id or "").strip().upper()
        if not normalized_sample_id:
            raise ValueError("record_prediction() requires a non-empty sample_id")
        if not normalized_cve_id:
            raise ValueError("record_prediction() requires a non-empty cve_id")
        prediction = _RecordedPrediction(
            sample_id=normalized_sample_id,
            cve_id=normalized_cve_id,
            predicted_severity=normalize_severity(predicted_severity),
            recorded_at=_utc_now(),
        )
        with self._lock:
            self._predictions_by_cve.setdefault(normalized_cve_id, {})[
                normalized_sample_id
            ] = prediction

    def _predictions_for_cve(self, cve_id: str) -> list[_RecordedPrediction]:
        with self._lock:
            return list(self._predictions_by_cve.get(cve_id, {}).values())

    def get_weighted_signals(
        self,
        *,
        now: datetime | None = None,
        max_age_days: float = 30.0,
        half_life_days: float = 7.0,
    ) -> dict[str, float]:
        return self._reward_buffer.get_weighted_signals(
            now=now,
            max_age_days=max_age_days,
            half_life_days=half_life_days,
        )

    @staticmethod
    def _kev_reward(predicted_severity: str) -> float:
        severity = normalize_severity(predicted_severity)
        if severity in {"CRITICAL", "HIGH"}:
            return 1.0
        if severity == "MEDIUM":
            return 0.5
        return -0.5

    def process_new_cisa_kev_batch(self, cve_ids: Iterable[str]) -> int:
        added_signals = 0
        normalized_cve_ids = sorted(
            {
                str(cve_id or "").strip().upper()
                for cve_id in cve_ids
                if str(cve_id or "").strip()
            }
        )
        for cve_id in normalized_cve_ids:
            for prediction in self._predictions_for_cve(cve_id):
                event_key = self._kev_event_key(cve_id, prediction.sample_id)
                with self._lock:
                    if event_key in self._processed_events:
                        continue
                    self._processed_events.add(event_key)
                self._reward_buffer.add(
                    OutcomeSignal(
                        sample_id=prediction.sample_id,
                        cve_id=cve_id,
                        predicted_severity=prediction.predicted_severity,
                        outcome="kev_exploit_confirmed",
                        reward=self._kev_reward(prediction.predicted_severity),
                        source="cisa_kev",
                    )
                )
                added_signals += 1
        if added_signals:
            self._reward_buffer.save()
        return added_signals

    def _severity_update_reward(
        self,
        *,
        predicted_severity: str,
        previous_severity: str,
        new_severity: str,
    ) -> float:
        predicted_rank = self._severity_rank(predicted_severity)
        previous_rank = self._severity_rank(previous_severity)
        new_rank = self._severity_rank(new_severity)
        if predicted_rank == new_rank:
            return 0.5
        previous_distance = abs(predicted_rank - previous_rank)
        new_distance = abs(predicted_rank - new_rank)
        if new_distance < previous_distance:
            return 0.25
        if new_distance > previous_distance:
            return -0.25
        return 0.0

    def process_severity_update(
        self,
        cve_id: str,
        previous_severity: str,
        new_severity: str,
        source: str = "nvd",
    ) -> int:
        normalized_cve_id = str(cve_id or "").strip().upper()
        normalized_previous = normalize_severity(previous_severity)
        normalized_new = normalize_severity(new_severity)
        normalized_source = self._normalize_signal_source(source)
        if not normalized_cve_id:
            raise ValueError("process_severity_update() requires a non-empty cve_id")
        if not normalized_source:
            raise ValueError("process_severity_update() requires a non-empty source")
        if normalized_previous == normalized_new:
            return 0
        added_signals = 0
        for prediction in self._predictions_for_cve(normalized_cve_id):
            reward = self._severity_update_reward(
                predicted_severity=prediction.predicted_severity,
                previous_severity=normalized_previous,
                new_severity=normalized_new,
            )
            if reward == 0.0:
                continue
            event_key = self._severity_event_key(
                source=normalized_source,
                cve_id=normalized_cve_id,
                previous_severity=normalized_previous,
                new_severity=normalized_new,
                sample_id=prediction.sample_id,
            )
            with self._lock:
                if event_key in self._processed_events:
                    continue
                self._processed_events.add(event_key)
            self._reward_buffer.add(
                OutcomeSignal(
                    sample_id=prediction.sample_id,
                    cve_id=normalized_cve_id,
                    predicted_severity=prediction.predicted_severity,
                    outcome=f"severity_update:{normalized_new}",
                    reward=reward,
                    source=normalized_source,
                    metadata={
                        "previous_severity": normalized_previous,
                        "new_severity": normalized_new,
                        "signal_source": normalized_source,
                    },
                )
            )
            added_signals += 1
        if added_signals:
            self._reward_buffer.save()
        return added_signals


_reward_buffer_singleton: RewardBuffer | None = None
_rl_collector_singleton: RLFeedbackCollector | None = None
_singleton_lock = threading.RLock()


def get_reward_buffer() -> RewardBuffer:
    global _reward_buffer_singleton
    with _singleton_lock:
        if _reward_buffer_singleton is None:
            _reward_buffer_singleton = RewardBuffer.load()
        return _reward_buffer_singleton


def get_rl_collector() -> RLFeedbackCollector:
    global _rl_collector_singleton
    with _singleton_lock:
        if _rl_collector_singleton is None:
            _rl_collector_singleton = RLFeedbackCollector(reward_buffer=get_reward_buffer())
        return _rl_collector_singleton


def export_rewards_for_al() -> list[dict[str, object]]:
    exported_records: list[dict[str, object]] = []
    for signal in get_reward_buffer().snapshot():
        exported_records.append(
            {
                "task_id": signal.cve_id,
                "reward": float(signal.reward),
                "outcome_type": signal.outcome,
                "source": signal.source,
            }
        )
    return exported_records


def reset_rl_feedback_state() -> None:
    global _reward_buffer_singleton, _rl_collector_singleton
    with _singleton_lock:
        _reward_buffer_singleton = None
        _rl_collector_singleton = None
