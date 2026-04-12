"""Agent Lightning bridge backed by real CVE severity data and rewards."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from backend.ingestion.models import normalize_severity
from backend.training.rl_feedback import export_rewards_for_al
from backend.training.safetensors_store import SafetensorsFeatureStore

logger = logging.getLogger("ygb.training.agent_lightning_bridge")

try:  # pragma: no cover - optional dependency path depends on environment
    import agentlightning as _agent_lightning_module
except ImportError:  # pragma: no cover - optional dependency path depends on environment
    try:
        import agent_lightning as _agent_lightning_module
    except ImportError:  # pragma: no cover - optional dependency path depends on environment
        _agent_lightning_module = None

AL_AVAILABLE = _agent_lightning_module is not None
SEVERITY_RANKS = {
    "UNKNOWN": 0,
    "LOW": 1,
    "MEDIUM": 2,
    "HIGH": 3,
    "CRITICAL": 4,
}
DEFAULT_FEATURE_STORE_ROOT = Path("training/features_safetensors")
DEFAULT_RAW_DATA_ROOT = Path("data/raw")
_SEVERITY_PATTERN = re.compile(r"\b(UNKNOWN|LOW|MEDIUM|HIGH|CRITICAL)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CVETrainingTask:
    task_id: str
    sample_id: str
    cve_id: str
    source: str
    raw_text: str
    expected_severity: str
    prompt: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        task_id = str(self.task_id or "").strip().upper()
        sample_id = str(self.sample_id or "").strip()
        cve_id = str(self.cve_id or "").strip().upper()
        source = str(self.source or "").strip()
        raw_text = str(self.raw_text or "").strip()
        prompt = str(self.prompt or "").strip()
        expected_severity = normalize_severity(self.expected_severity)
        if not task_id:
            raise ValueError("CVETrainingTask.task_id must not be empty")
        if not sample_id:
            raise ValueError("CVETrainingTask.sample_id must not be empty")
        if not cve_id:
            raise ValueError("CVETrainingTask.cve_id must not be empty")
        if not raw_text:
            raise ValueError("CVETrainingTask.raw_text must not be empty")
        if not prompt:
            raise ValueError("CVETrainingTask.prompt must not be empty")
        if not isinstance(self.metadata, dict):
            raise TypeError("CVETrainingTask.metadata must be a dict")
        object.__setattr__(self, "task_id", task_id)
        object.__setattr__(self, "sample_id", sample_id)
        object.__setattr__(self, "cve_id", cve_id)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "raw_text", raw_text)
        object.__setattr__(self, "prompt", prompt)
        object.__setattr__(self, "expected_severity", expected_severity)


class YBGDatasetProvider:
    """Loads real CVE severity tasks from feature shards or raw ingested samples."""

    def __init__(
        self,
        feature_store_root: str | Path = DEFAULT_FEATURE_STORE_ROOT,
        raw_data_root: str | Path = DEFAULT_RAW_DATA_ROOT,
    ) -> None:
        self.feature_store_root = Path(feature_store_root)
        self.raw_data_root = Path(raw_data_root)
        self.feature_store = SafetensorsFeatureStore(self.feature_store_root)

    @staticmethod
    def _build_prompt(*, cve_id: str, source: str, raw_text: str) -> str:
        source_line = f"Source: {source}\n" if source else ""
        return (
            "Classify the real CVE severity for the record below.\n\n"
            f"CVE: {cve_id}\n"
            f"{source_line}"
            f"Description:\n{raw_text}\n\n"
            "Respond with exactly one label: UNKNOWN, LOW, MEDIUM, HIGH, or CRITICAL."
        )

    @staticmethod
    def _coerce_row_ids(shard_name: str, metadata: Mapping[str, Any], row_count: int) -> list[str]:
        raw_row_ids = metadata.get("row_ids")
        if isinstance(raw_row_ids, (list, tuple)):
            row_ids = [str(value) for value in raw_row_ids]
            if len(row_ids) == row_count:
                return row_ids
        sample_sha256 = str(metadata.get("sample_sha256") or metadata.get("sample_id") or "").strip()
        if row_count == 1:
            return [sample_sha256 or shard_name]
        return [f"{shard_name}:{index}" for index in range(row_count)]

    def _task_from_feature_row(
        self,
        *,
        shard_name: str,
        shard_metadata: dict[str, Any],
        row_id: str,
        description_record: Mapping[str, Any],
    ) -> CVETrainingTask | None:
        raw_text = str(
            description_record.get("raw_text") or description_record.get("description") or ""
        ).strip()
        cve_id = str(
            description_record.get("cve_id") or shard_metadata.get("sample_cve_id") or ""
        ).strip().upper()
        if not raw_text or not cve_id:
            return None
        source = str(
            description_record.get("source") or shard_metadata.get("sample_source") or ""
        ).strip()
        expected_severity = normalize_severity(
            str(
                description_record.get("severity")
                or shard_metadata.get("sample_severity")
                or "UNKNOWN"
            )
        )
        sample_id = str(
            description_record.get("sample_sha256")
            or description_record.get("row_id")
            or row_id
        ).strip()
        metadata = {
            "shard_name": shard_name,
            "source": source,
            "url": str(description_record.get("url") or shard_metadata.get("sample_url") or ""),
            "lang": str(description_record.get("lang") or ""),
            "token_count": description_record.get("token_count"),
        }
        return CVETrainingTask(
            task_id=cve_id,
            sample_id=sample_id or row_id,
            cve_id=cve_id,
            source=source,
            raw_text=raw_text,
            expected_severity=expected_severity,
            prompt=self._build_prompt(cve_id=cve_id, source=source, raw_text=raw_text),
            metadata=metadata,
        )

    def _iter_feature_store_tasks(self) -> Iterable[CVETrainingTask]:
        for shard_name in self.feature_store.list_shards():
            descriptions = self.feature_store.read_descriptions(shard_name)
            if not descriptions:
                continue
            shard = self.feature_store.read(shard_name)
            row_count = int(shard.labels.shape[0])
            row_ids = self._coerce_row_ids(shard_name, shard.metadata, row_count)
            if len(descriptions) != row_count:
                logger.warning(
                    "agent_lightning_descriptions_length_mismatch shard=%s rows=%d descriptions=%d",
                    shard_name,
                    row_count,
                    len(descriptions),
                )
            for row_index, description_record in enumerate(descriptions[:row_count]):
                if not isinstance(description_record, Mapping):
                    continue
                task = self._task_from_feature_row(
                    shard_name=shard_name,
                    shard_metadata=shard.metadata,
                    row_id=row_ids[row_index],
                    description_record=description_record,
                )
                if task is not None:
                    yield task

    def _iter_raw_data_tasks(self) -> Iterable[CVETrainingTask]:
        if not self.raw_data_root.exists():
            return
        for sample_path in sorted(self.raw_data_root.rglob("*.json")):
            try:
                payload = json.loads(sample_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "agent_lightning_raw_sample_skipped path=%s reason=%s",
                    sample_path.as_posix(),
                    type(exc).__name__,
                )
                continue
            if not isinstance(payload, dict):
                continue
            raw_text = str(payload.get("raw_text") or payload.get("description") or "").strip()
            cve_id = str(payload.get("cve_id") or "").strip().upper()
            if not raw_text or not cve_id:
                continue
            source = str(payload.get("source") or "").strip()
            sample_id = str(payload.get("sha256_hash") or sample_path.as_posix()).strip()
            expected_severity = normalize_severity(str(payload.get("severity") or "UNKNOWN"))
            yield CVETrainingTask(
                task_id=cve_id,
                sample_id=sample_id,
                cve_id=cve_id,
                source=source,
                raw_text=raw_text,
                expected_severity=expected_severity,
                prompt=self._build_prompt(cve_id=cve_id, source=source, raw_text=raw_text),
                metadata={
                    "path": sample_path.as_posix(),
                    "url": str(payload.get("url") or ""),
                    "lang": str(payload.get("lang") or ""),
                    "token_count": payload.get("token_count"),
                },
            )

    def load_tasks(self, *, limit: int | None = None) -> list[CVETrainingTask]:
        normalized_limit = None if limit is None or int(limit) <= 0 else int(limit)
        tasks: list[CVETrainingTask] = []
        seen_task_ids: set[str] = set()
        for iterator in (self._iter_feature_store_tasks(), self._iter_raw_data_tasks()):
            for task in iterator:
                if task.task_id in seen_task_ids:
                    continue
                tasks.append(task)
                seen_task_ids.add(task.task_id)
                if normalized_limit is not None and len(tasks) >= normalized_limit:
                    return tasks
        return tasks


class CVESeverityAgent:
    """Reward-aware severity agent for Agent Lightning style trainers."""

    def __init__(
        self,
        *,
        predict_fn: Callable[..., str] | None = None,
        reward_records: Iterable[Mapping[str, Any]] | None = None,
    ) -> None:
        self._predict_fn = predict_fn
        self._static_reward_records = None if reward_records is None else list(reward_records)
        self._reward_index = self._index_rewards(
            self._static_reward_records or export_rewards_for_al()
        )

    @staticmethod
    def _index_rewards(records: Iterable[Mapping[str, Any]]) -> dict[str, list[float]]:
        indexed: dict[str, list[float]] = {}
        for record in records:
            task_id = str(record.get("task_id") or "").strip().upper()
            if not task_id:
                continue
            try:
                reward_value = float(record.get("reward"))
            except (TypeError, ValueError):
                continue
            indexed.setdefault(task_id, []).append(reward_value)
        return indexed

    def _refresh_rewards(self) -> None:
        if self._static_reward_records is None:
            self._reward_index = self._index_rewards(export_rewards_for_al())

    @staticmethod
    def _coerce_task(task: CVETrainingTask | Mapping[str, Any]) -> CVETrainingTask:
        if isinstance(task, CVETrainingTask):
            return task
        if not isinstance(task, Mapping):
            raise TypeError("CVESeverityAgent.run() requires a CVETrainingTask or mapping")
        raw_text = str(task.get("raw_text") or task.get("description") or "").strip()
        cve_id = str(task.get("cve_id") or task.get("task_id") or "").strip().upper()
        source = str(task.get("source") or "").strip()
        expected_severity = normalize_severity(
            str(task.get("expected_severity") or task.get("severity") or "UNKNOWN")
        )
        prompt = str(task.get("prompt") or "").strip()
        if not prompt and raw_text and cve_id:
            prompt = YBGDatasetProvider._build_prompt(
                cve_id=cve_id,
                source=source,
                raw_text=raw_text,
            )
        return CVETrainingTask(
            task_id=str(task.get("task_id") or cve_id),
            sample_id=str(task.get("sample_id") or task.get("row_id") or cve_id),
            cve_id=cve_id,
            source=source,
            raw_text=raw_text,
            expected_severity=expected_severity,
            prompt=prompt,
            metadata=dict(task.get("metadata") or {}),
        )

    @staticmethod
    def _extract_predicted_severity(prediction: str) -> str:
        normalized = normalize_severity(str(prediction or "UNKNOWN"))
        if normalized != "UNKNOWN" or str(prediction or "").strip().upper() == "UNKNOWN":
            return normalized
        match = _SEVERITY_PATTERN.search(str(prediction or ""))
        if match is None:
            return "UNKNOWN"
        return normalize_severity(match.group(1))

    @staticmethod
    def _ground_truth_reward(predicted_severity: str, actual_severity: str) -> float:
        predicted_rank = SEVERITY_RANKS.get(normalize_severity(predicted_severity), 0)
        actual_rank = SEVERITY_RANKS.get(normalize_severity(actual_severity), 0)
        distance = abs(predicted_rank - actual_rank)
        return float(max(-1.0, 1.0 - (0.5 * distance)))

    def _resolve_reward(self, task: CVETrainingTask, predicted_severity: str) -> tuple[float, str]:
        self._refresh_rewards()
        rl_rewards = self._reward_index.get(task.task_id, [])
        if rl_rewards:
            return float(sum(rl_rewards) / len(rl_rewards)), "rl_feedback"
        return self._ground_truth_reward(predicted_severity, task.expected_severity), "ground_truth"

    def _predict(self, task: CVETrainingTask) -> str:
        if self._predict_fn is None:
            raise RuntimeError(
                "CVESeverityAgent requires a predict_fn when predicted_severity is not provided"
            )
        try:
            return str(self._predict_fn(task.prompt, task))
        except TypeError:
            return str(self._predict_fn(task))

    def run(
        self,
        task: CVETrainingTask | Mapping[str, Any],
        predicted_severity: str | None = None,
    ) -> dict[str, Any]:
        resolved_task = self._coerce_task(task)
        raw_prediction = (
            str(predicted_severity)
            if predicted_severity is not None
            else self._predict(resolved_task)
        )
        normalized_prediction = self._extract_predicted_severity(raw_prediction)
        reward, reward_source = self._resolve_reward(resolved_task, normalized_prediction)
        return {
            "task_id": resolved_task.task_id,
            "sample_id": resolved_task.sample_id,
            "cve_id": resolved_task.cve_id,
            "prediction": normalized_prediction,
            "raw_prediction": raw_prediction,
            "expected_severity": resolved_task.expected_severity,
            "reward": reward,
            "reward_source": reward_source,
        }


def _detect_trainer_factory() -> Callable[..., Any] | None:
    if _agent_lightning_module is None:
        return None
    for attribute_chain in (
        ("Trainer",),
        ("LightningTrainer",),
        ("trainer", "Trainer"),
        ("trainer", "LightningTrainer"),
    ):
        candidate: Any = _agent_lightning_module
        for attribute_name in attribute_chain:
            candidate = getattr(candidate, attribute_name, None)
            if candidate is None:
                break
        if callable(candidate):
            return candidate
    return None


def build_ybg_trainer(
    *,
    dataset_provider: YBGDatasetProvider | None = None,
    agent: CVESeverityAgent | None = None,
    trainer_factory: Callable[..., Any] | None = None,
    trainer_kwargs: Mapping[str, Any] | None = None,
) -> Any:
    if not AL_AVAILABLE and trainer_factory is None:
        raise RuntimeError(
            "Agent Lightning is not installed in this environment. Install `agentlightning` or provide an explicit trainer_factory."
        )
    resolved_dataset_provider = dataset_provider or YBGDatasetProvider()
    resolved_agent = agent or CVESeverityAgent()
    resolved_factory = trainer_factory or _detect_trainer_factory()
    if resolved_factory is None:
        raise RuntimeError(
            "Agent Lightning is available but no compatible trainer factory could be located."
        )
    factory_kwargs = dict(trainer_kwargs or {})
    dataset_limit = factory_kwargs.pop("dataset_limit", None)
    tasks = resolved_dataset_provider.load_tasks(limit=dataset_limit)
    last_type_error: TypeError | None = None
    for candidate_kwargs in (
        {"agent": resolved_agent, "dataset_provider": resolved_dataset_provider, **factory_kwargs},
        {"agent": resolved_agent, "dataset": tasks, **factory_kwargs},
        {"policy": resolved_agent, "dataset": tasks, **factory_kwargs},
    ):
        try:
            return resolved_factory(**candidate_kwargs)
        except TypeError as exc:
            last_type_error = exc
    raise RuntimeError(
        "Unable to construct an Agent Lightning trainer with the detected factory signature."
    ) from last_type_error
