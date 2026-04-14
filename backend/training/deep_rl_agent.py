"""Phase 4 deep RL outcome tracking with sklearn feature augmentation."""

from __future__ import annotations

import json
import logging
import math
import os
import pickle
import threading
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from backend.ingestion.models import normalize_severity
from backend.training.rl_feedback import OutcomeSignal, RewardBuffer

logger = logging.getLogger("ygb.training.deep_rl_agent")

try:  # pragma: no cover - availability depends on environment
    from sklearn.decomposition import IncrementalPCA
    from sklearn.preprocessing import StandardScaler
except ImportError as exc:  # pragma: no cover - availability depends on environment
    IncrementalPCA = None
    StandardScaler = None
    _SKLEARN_IMPORT_ERROR: Exception | None = exc
else:  # pragma: no cover - trivial availability branch
    _SKLEARN_IMPORT_ERROR = None


SKLEARN_AVAILABLE = IncrementalPCA is not None and StandardScaler is not None
DEFAULT_EPISODES_PATH = Path(
    os.environ.get("YGB_DEEP_RL_EPISODES_PATH", "data/deep_rl_episodes.json")
)
DEFAULT_SKLEARN_STATE_PATH = Path(
    os.environ.get(
        "YGB_DEEP_RL_SKLEARN_STATE_PATH",
        "checkpoints/deep_rl_sklearn_state.pkl",
    )
)
DEFAULT_SKLEARN_METADATA_PATH = Path(
    os.environ.get(
        "YGB_DEEP_RL_SKLEARN_METADATA_PATH",
        "checkpoints/deep_rl_sklearn_state.json",
    )
)
DEFAULT_REWARD_BUFFER_PATH = os.environ.get("YGB_DEEP_RL_REWARD_BUFFER_PATH")
SKLEARN_STATE_SCHEMA_VERSION = 1
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


def _coerce_json_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise TypeError("metadata must be a mapping")
    normalized: dict[str, Any] = {}
    for key, value in metadata.items():
        try:
            json.dumps(value)
            normalized[str(key)] = value
        except TypeError:
            normalized[str(key)] = str(value)
    return normalized


def _atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _atomic_write_pickle(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    with open(temp_path, "wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def _require_sklearn(context: str) -> None:
    if SKLEARN_AVAILABLE:
        return
    logger.error(
        "%s requires scikit-learn, but the dependency is unavailable.",
        context,
    )
    raise RuntimeError(
        f"{context} requires scikit-learn. Install `scikit-learn` to enable Phase 4 sklearn augmentation."
    ) from _SKLEARN_IMPORT_ERROR


def _coerce_feature_matrix(features: np.ndarray | list[list[float]]) -> np.ndarray:
    feature_array = np.asarray(features, dtype=np.float32)
    if feature_array.ndim != 2:
        raise ValueError(
            f"feature matrix must be 2D, got shape {tuple(feature_array.shape)}"
        )
    if feature_array.shape[0] < 1 or feature_array.shape[1] < 1:
        raise ValueError(
            f"feature matrix must have positive dimensions, got {tuple(feature_array.shape)}"
        )
    if not np.isfinite(feature_array).all():
        raise ValueError("feature matrix must not contain NaN or Inf values")
    return feature_array


@dataclass(frozen=True)
class DeepRLEpisode:
    sample_id: str
    cve_id: str
    predicted_severity: str
    actual_severity: str
    reward: float
    normalized_reward: float
    source: str
    observed_at: str = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        sample_id = str(self.sample_id or "").strip()
        cve_id = str(self.cve_id or "").strip().upper()
        predicted_severity = normalize_severity(str(self.predicted_severity or "UNKNOWN"))
        actual_severity = normalize_severity(str(self.actual_severity or "UNKNOWN"))
        source = str(self.source or "").strip()
        reward = float(self.reward)
        normalized_reward = float(self.normalized_reward)
        if not sample_id:
            raise ValueError("DeepRLEpisode.sample_id must not be empty")
        if not cve_id:
            raise ValueError("DeepRLEpisode.cve_id must not be empty")
        if not source:
            raise ValueError("DeepRLEpisode.source must not be empty")
        if not math.isfinite(reward):
            raise ValueError("DeepRLEpisode.reward must be finite")
        if not math.isfinite(normalized_reward):
            raise ValueError("DeepRLEpisode.normalized_reward must be finite")
        _parse_timestamp(self.observed_at)
        object.__setattr__(self, "sample_id", sample_id)
        object.__setattr__(self, "cve_id", cve_id)
        object.__setattr__(self, "predicted_severity", predicted_severity)
        object.__setattr__(self, "actual_severity", actual_severity)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "metadata", _coerce_json_metadata(self.metadata))


class DeepRLAgent:
    """Records real outcome-driven RL episodes with GRPO-style normalization."""

    def __init__(
        self,
        *,
        episodes_path: str | Path | None = None,
        reward_buffer_path: str | Path | None = DEFAULT_REWARD_BUFFER_PATH,
        normalization_window: int = 256,
        max_episodes: int = 5000,
    ) -> None:
        self.episodes_path = (
            Path(episodes_path) if episodes_path is not None else DEFAULT_EPISODES_PATH
        )
        self.normalization_window = max(int(normalization_window), 1)
        self.max_episodes = max(int(max_episodes), 1)
        self._lock = threading.RLock()
        self._episodes = self._load_episodes(self.episodes_path)
        self._reward_buffer = RewardBuffer.load(
            path=reward_buffer_path,
            max_signals=self.max_episodes,
        )
        if self._episodes:
            self._recompute_normalized_rewards_locked()
            self._persist_episodes_locked()

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return _SEVERITY_RANKS.get(normalize_severity(severity), 0)

    @classmethod
    def compute_reward(cls, predicted_severity: str, actual_severity: str) -> float:
        predicted = normalize_severity(predicted_severity)
        actual = normalize_severity(actual_severity)
        if predicted == actual:
            return 1.0
        predicted_rank = cls._severity_rank(predicted)
        actual_rank = cls._severity_rank(actual)
        distance = abs(predicted_rank - actual_rank)
        underestimate_gap = max(actual_rank - predicted_rank, 0)
        overestimate_gap = max(predicted_rank - actual_rank, 0)
        reward = 1.0 - (0.5 * distance)
        reward -= 0.2 * float(underestimate_gap)
        reward -= 0.1 * float(overestimate_gap)
        if actual == "CRITICAL" and predicted != "CRITICAL":
            reward -= 0.2
        if predicted == "CRITICAL" and actual in {"LOW", "INFO", "UNKNOWN"}:
            reward -= 0.1
        return float(max(-1.0, min(1.0, reward)))

    @staticmethod
    def _load_episodes(path: Path) -> list[DeepRLEpisode]:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("DeepRLAgent episode persistence payload must be a list")
        episodes: list[DeepRLEpisode] = []
        for index, entry in enumerate(payload):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"DeepRLAgent episode entry at index {index} must be an object"
                )
            episodes.append(DeepRLEpisode(**entry))
        return episodes[-5000:]

    def _persist_episodes_locked(self) -> None:
        payload = [asdict(episode) for episode in self._episodes]
        _atomic_write_json(self.episodes_path, payload)

    def _recompute_normalized_rewards_locked(self) -> None:
        if not self._episodes:
            return
        window = self._episodes[-self.normalization_window :]
        rewards = np.asarray([episode.reward for episode in window], dtype=np.float32)
        mean_reward = float(rewards.mean())
        std_reward = float(rewards.std())
        normalized_by_identity: dict[tuple[str, str, str], float] = {}
        if len(window) < 2 or std_reward <= 1e-6:
            for episode in window:
                normalized_by_identity[
                    (episode.sample_id, episode.cve_id, episode.observed_at)
                ] = 0.0
        else:
            for episode in window:
                normalized_by_identity[
                    (episode.sample_id, episode.cve_id, episode.observed_at)
                ] = float((episode.reward - mean_reward) / std_reward)
        recomputed: list[DeepRLEpisode] = []
        for episode in self._episodes:
            identity = (episode.sample_id, episode.cve_id, episode.observed_at)
            if identity in normalized_by_identity:
                recomputed.append(
                    replace(
                        episode,
                        normalized_reward=float(normalized_by_identity[identity]),
                    )
                )
            else:
                recomputed.append(episode)
        self._episodes = recomputed[-self.max_episodes :]

    def snapshot(self) -> list[DeepRLEpisode]:
        with self._lock:
            return list(self._episodes)

    def export_reward_records(self) -> list[dict[str, object]]:
        return [
            {
                "task_id": episode.cve_id,
                "reward": float(episode.reward),
                "outcome_type": f"actual:{episode.actual_severity}",
                "source": episode.source,
            }
            for episode in self.snapshot()
        ]

    def record_outcome(
        self,
        *,
        sample_id: str,
        cve_id: str,
        predicted_severity: str,
        actual_severity: str,
        source: str = "real_outcome",
        metadata: Mapping[str, Any] | None = None,
    ) -> DeepRLEpisode:
        reward = self.compute_reward(predicted_severity, actual_severity)
        merged_metadata = _coerce_json_metadata(metadata)
        merged_metadata.setdefault("reward_strategy", "severity_distance")
        episode = DeepRLEpisode(
            sample_id=sample_id,
            cve_id=cve_id,
            predicted_severity=predicted_severity,
            actual_severity=actual_severity,
            reward=reward,
            normalized_reward=0.0,
            source=source,
            metadata=merged_metadata,
        )
        with self._lock:
            self._episodes.append(episode)
            self._episodes = self._episodes[-self.max_episodes :]
            self._recompute_normalized_rewards_locked()
            persisted_episode = self._episodes[-1]
            self._persist_episodes_locked()
        self._reward_buffer.add(
            OutcomeSignal(
                sample_id=persisted_episode.sample_id,
                cve_id=persisted_episode.cve_id,
                predicted_severity=persisted_episode.predicted_severity,
                outcome=f"actual:{persisted_episode.actual_severity}",
                reward=float(persisted_episode.reward),
                source=persisted_episode.source,
                metadata={
                    "actual_severity": persisted_episode.actual_severity,
                    "normalized_reward": f"{persisted_episode.normalized_reward:.6f}",
                    "reward_strategy": str(
                        persisted_episode.metadata.get("reward_strategy", "severity_distance")
                    ),
                },
            )
        )
        self._reward_buffer.save()
        return persisted_episode

    def record_real_outcome(
        self,
        *,
        sample_id: str,
        cve_id: str,
        predicted_severity: str,
        actual_severity: str,
        source: str = "real_outcome",
        metadata: Mapping[str, Any] | None = None,
    ) -> DeepRLEpisode:
        return self.record_outcome(
            sample_id=sample_id,
            cve_id=cve_id,
            predicted_severity=predicted_severity,
            actual_severity=actual_severity,
            source=source,
            metadata=metadata,
        )


class SklearnFeatureAugmenter:
    """scikit-learn-backed feature augmenter for Phase 4 RL flows."""

    def __init__(
        self,
        *,
        state_path: str | Path | None = None,
        metadata_path: str | Path | None = None,
        n_components: int = 32,
        batch_size: int = 128,
        auto_load: bool = True,
    ) -> None:
        _require_sklearn("SklearnFeatureAugmenter")
        self.state_path = (
            Path(state_path) if state_path is not None else DEFAULT_SKLEARN_STATE_PATH
        )
        self.metadata_path = (
            Path(metadata_path)
            if metadata_path is not None
            else DEFAULT_SKLEARN_METADATA_PATH
        )
        self.requested_n_components = max(int(n_components), 1)
        self.batch_size = max(int(batch_size), 1)
        self._input_dim: int | None = None
        self._resolved_n_components: int | None = None
        self._scaler = None
        self._pca = None
        self._is_fitted = False
        if auto_load and self.state_path.exists():
            self.load()

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def augmented_dim(self) -> int | None:
        if not self._is_fitted or self._input_dim is None or self._resolved_n_components is None:
            return None
        return int((self._input_dim * 2) + self._resolved_n_components + 5)

    def fit(self, features: np.ndarray | list[list[float]]) -> "SklearnFeatureAugmenter":
        _require_sklearn("SklearnFeatureAugmenter.fit")
        feature_array = _coerce_feature_matrix(features)
        resolved_components = max(
            1,
            min(
                self.requested_n_components,
                int(feature_array.shape[0]),
                int(feature_array.shape[1]),
            ),
        )
        scaler = StandardScaler(copy=True)
        scaled = scaler.fit_transform(feature_array).astype(np.float32, copy=False)
        pca = IncrementalPCA(
            n_components=resolved_components,
            batch_size=min(self.batch_size, max(int(feature_array.shape[0]), 1)),
        )
        pca.fit(scaled)
        self._scaler = scaler
        self._pca = pca
        self._input_dim = int(feature_array.shape[1])
        self._resolved_n_components = int(resolved_components)
        self._is_fitted = True
        self.save()
        return self

    def _summary_features(self, scaled: np.ndarray) -> np.ndarray:
        l2_norm = np.linalg.norm(scaled, axis=1, keepdims=True)
        return np.concatenate(
            [
                scaled.mean(axis=1, keepdims=True),
                scaled.std(axis=1, keepdims=True),
                scaled.min(axis=1, keepdims=True),
                scaled.max(axis=1, keepdims=True),
                l2_norm,
            ],
            axis=1,
        ).astype(np.float32, copy=False)

    def transform(self, features: np.ndarray | list[list[float]]) -> np.ndarray:
        if not self._is_fitted or self._scaler is None or self._pca is None:
            raise RuntimeError(
                "SklearnFeatureAugmenter.transform() requires a fitted augmenter state"
            )
        feature_array = _coerce_feature_matrix(features)
        if self._input_dim is None or feature_array.shape[1] != self._input_dim:
            raise ValueError(
                "feature width mismatch: "
                f"expected {self._input_dim}, got {feature_array.shape[1]}"
            )
        scaled = self._scaler.transform(feature_array).astype(np.float32, copy=False)
        projected = self._pca.transform(scaled).astype(np.float32, copy=False)
        summary = self._summary_features(scaled)
        return np.concatenate(
            [feature_array.astype(np.float32, copy=False), scaled, projected, summary],
            axis=1,
        ).astype(np.float32, copy=False)

    def fit_transform(self, features: np.ndarray | list[list[float]]) -> np.ndarray:
        return self.fit(features).transform(features)

    def save(
        self,
        path: str | Path | None = None,
        metadata_path: str | Path | None = None,
    ) -> Path:
        if not self._is_fitted or self._scaler is None or self._pca is None:
            raise RuntimeError("SklearnFeatureAugmenter.save() requires a fitted augmenter")
        target_path = Path(path) if path is not None else self.state_path
        target_metadata_path = (
            Path(metadata_path) if metadata_path is not None else self.metadata_path
        )
        payload = {
            "schema_version": SKLEARN_STATE_SCHEMA_VERSION,
            "requested_n_components": self.requested_n_components,
            "resolved_n_components": self._resolved_n_components,
            "batch_size": self.batch_size,
            "input_dim": self._input_dim,
            "scaler": self._scaler,
            "pca": self._pca,
        }
        _atomic_write_pickle(target_path, payload)
        _atomic_write_json(
            target_metadata_path,
            {
                "schema_version": SKLEARN_STATE_SCHEMA_VERSION,
                "saved_at": _utc_now(),
                "input_dim": self._input_dim,
                "resolved_n_components": self._resolved_n_components,
                "augmented_dim": self.augmented_dim,
                "sklearn_available": bool(SKLEARN_AVAILABLE),
            },
        )
        return target_path

    def load(
        self,
        path: str | Path | None = None,
        metadata_path: str | Path | None = None,
    ) -> "SklearnFeatureAugmenter":
        _require_sklearn("SklearnFeatureAugmenter.load")
        target_path = Path(path) if path is not None else self.state_path
        if not target_path.exists():
            raise FileNotFoundError(f"SklearnFeatureAugmenter state not found: {target_path}")
        with open(target_path, "rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("SklearnFeatureAugmenter state payload must be a dict")
        if int(payload.get("schema_version", 0)) != SKLEARN_STATE_SCHEMA_VERSION:
            raise ValueError(
                "SklearnFeatureAugmenter state schema version mismatch: "
                f"{payload.get('schema_version')}"
            )
        self.requested_n_components = max(int(payload["requested_n_components"]), 1)
        self.batch_size = max(int(payload["batch_size"]), 1)
        self._resolved_n_components = int(payload["resolved_n_components"])
        self._input_dim = int(payload["input_dim"])
        self._scaler = payload["scaler"]
        self._pca = payload["pca"]
        self._is_fitted = True
        if metadata_path is not None:
            self.metadata_path = Path(metadata_path)
        return self


__all__ = [
    "DEFAULT_EPISODES_PATH",
    "DEFAULT_SKLEARN_METADATA_PATH",
    "DEFAULT_SKLEARN_STATE_PATH",
    "DeepRLAgent",
    "DeepRLEpisode",
    "SKLEARN_AVAILABLE",
    "SklearnFeatureAugmenter",
]
