"""Adaptive learning support with distribution-shift monitoring and EWC regularization."""

from __future__ import annotations

import json
import logging
import math
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import torch
from torch.utils.data import DataLoader

from training.safetensors_io import load_safetensors, save_safetensors

logger = logging.getLogger("ygb.training.adaptive_learner")

DEFAULT_ADAPTIVE_STATE_PATH = Path("checkpoints/adaptive_learning_state.json")
DEFAULT_EWC_STATE_PATH = Path("checkpoints/adaptive_ewc_state.safetensors")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AdaptationEvent:
    event_id: str
    observed_at: str = field(default_factory=_utc_now)
    severity_counts: dict[str, int] = field(default_factory=dict)
    baseline_distribution: dict[str, float] = field(default_factory=dict)
    current_distribution: dict[str, float] = field(default_factory=dict)
    js_distance: float = 0.0
    threshold: float = 0.0
    history_depth: int = 0
    fisher_sample_count: int = 0

    def __post_init__(self) -> None:
        event_id = str(self.event_id or "").strip()
        if not event_id:
            raise ValueError("AdaptationEvent.event_id must not be empty")
        datetime.fromisoformat(str(self.observed_at).replace("Z", "+00:00"))
        object.__setattr__(
            self,
            "severity_counts",
            {str(key): int(value) for key, value in dict(self.severity_counts).items()},
        )
        object.__setattr__(
            self,
            "baseline_distribution",
            {
                str(key): float(value)
                for key, value in dict(self.baseline_distribution).items()
            },
        )
        object.__setattr__(
            self,
            "current_distribution",
            {
                str(key): float(value)
                for key, value in dict(self.current_distribution).items()
            },
        )
        js_distance = float(self.js_distance)
        threshold = float(self.threshold)
        if not math.isfinite(js_distance):
            raise ValueError("AdaptationEvent.js_distance must be finite")
        if not math.isfinite(threshold):
            raise ValueError("AdaptationEvent.threshold must be finite")
        history_depth = int(self.history_depth)
        fisher_sample_count = int(self.fisher_sample_count)
        if history_depth < 0:
            raise ValueError("AdaptationEvent.history_depth must be >= 0")
        if fisher_sample_count < 0:
            raise ValueError("AdaptationEvent.fisher_sample_count must be >= 0")
        object.__setattr__(self, "event_id", event_id)
        object.__setattr__(self, "js_distance", js_distance)
        object.__setattr__(self, "threshold", threshold)
        object.__setattr__(self, "history_depth", history_depth)
        object.__setattr__(self, "fisher_sample_count", fisher_sample_count)


@dataclass(frozen=True)
class DistributionShift:
    shift_detected: bool
    js_distance: float
    threshold: float
    baseline_distribution: dict[str, float]
    current_distribution: dict[str, float]
    history_depth: int


class DistributionMonitor:
    def __init__(
        self,
        *,
        history_size: int = 5,
        shift_threshold: float = 0.2,
        severity_history: Sequence[Mapping[str, float]] | None = None,
    ) -> None:
        normalized_history_size = int(history_size)
        normalized_threshold = float(shift_threshold)
        if normalized_history_size <= 0:
            raise ValueError("history_size must be a positive integer")
        if not math.isfinite(normalized_threshold) or normalized_threshold < 0.0:
            raise ValueError("shift_threshold must be a finite non-negative float")
        self.history_size = normalized_history_size
        self.shift_threshold = normalized_threshold
        self._severity_history: list[dict[str, float]] = []
        for distribution in severity_history or []:
            self._severity_history.append(
                self._normalize_distribution(dict(distribution))
            )
        if len(self._severity_history) > self.history_size:
            self._severity_history = self._severity_history[-self.history_size :]

    @staticmethod
    def _normalize_counts(severity_counts: Mapping[str, int | float]) -> dict[str, float]:
        normalized_counts: dict[str, float] = {}
        total = 0.0
        for raw_key, raw_value in dict(severity_counts).items():
            label = str(raw_key).strip().upper()
            count = float(raw_value)
            if not label:
                continue
            if not math.isfinite(count):
                raise ValueError(f"severity count for {label!r} is not finite")
            if count < 0.0:
                raise ValueError(f"severity count for {label!r} must be non-negative")
            normalized_counts[label] = normalized_counts.get(label, 0.0) + count
            total += count
        if total <= 0.0:
            return {}
        return {
            label: float(value / total)
            for label, value in sorted(normalized_counts.items())
        }

    @classmethod
    def _normalize_distribution(
        cls,
        distribution: Mapping[str, int | float],
    ) -> dict[str, float]:
        return cls._normalize_counts(distribution)

    @staticmethod
    def _align_distribution_pairs(
        left: Mapping[str, float],
        right: Mapping[str, float],
    ) -> tuple[np.ndarray, np.ndarray]:
        keys = sorted(set(left) | set(right))
        if not keys:
            return np.asarray([], dtype=np.float64), np.asarray([], dtype=np.float64)
        return (
            np.asarray([float(left.get(key, 0.0)) for key in keys], dtype=np.float64),
            np.asarray([float(right.get(key, 0.0)) for key in keys], dtype=np.float64),
        )

    @classmethod
    def _average_distribution(cls, history: Sequence[Mapping[str, float]]) -> dict[str, float]:
        if not history:
            return {}
        keys = sorted({key for entry in history for key in entry})
        if not keys:
            return {}
        averaged = {
            key: float(
                sum(float(entry.get(key, 0.0)) for entry in history) / len(history)
            )
            for key in keys
        }
        return cls._normalize_distribution(averaged)

    @classmethod
    def _jensen_shannon_distance(
        cls,
        left: Mapping[str, float],
        right: Mapping[str, float],
    ) -> float:
        left_array, right_array = cls._align_distribution_pairs(left, right)
        if left_array.size == 0 or right_array.size == 0:
            return 0.0
        left_total = float(left_array.sum())
        right_total = float(right_array.sum())
        if left_total <= 0.0 or right_total <= 0.0:
            return 0.0
        left_prob = left_array / left_total
        right_prob = right_array / right_total
        midpoint = 0.5 * (left_prob + right_prob)
        left_mask = left_prob > 0.0
        right_mask = right_prob > 0.0
        left_kl = float(
            np.sum(left_prob[left_mask] * np.log2(left_prob[left_mask] / midpoint[left_mask]))
        )
        right_kl = float(
            np.sum(
                right_prob[right_mask] * np.log2(right_prob[right_mask] / midpoint[right_mask])
            )
        )
        divergence = max(0.5 * left_kl + 0.5 * right_kl, 0.0)
        return float(math.sqrt(divergence))

    def observe(self, severity_counts: Mapping[str, int | float]) -> DistributionShift:
        current_distribution = self._normalize_counts(severity_counts)
        history_depth = len(self._severity_history)
        if not current_distribution:
            return DistributionShift(
                shift_detected=False,
                js_distance=0.0,
                threshold=self.shift_threshold,
                baseline_distribution={},
                current_distribution={},
                history_depth=history_depth,
            )
        baseline_distribution = self._average_distribution(self._severity_history)
        if not baseline_distribution:
            baseline_distribution = dict(current_distribution)
        js_distance = self._jensen_shannon_distance(
            baseline_distribution,
            current_distribution,
        )
        shift_detected = bool(history_depth > 0 and js_distance >= self.shift_threshold)
        self._severity_history.append(dict(current_distribution))
        if len(self._severity_history) > self.history_size:
            self._severity_history = self._severity_history[-self.history_size :]
        return DistributionShift(
            shift_detected=shift_detected,
            js_distance=js_distance,
            threshold=self.shift_threshold,
            baseline_distribution=baseline_distribution,
            current_distribution=current_distribution,
            history_depth=history_depth,
        )

    def snapshot(self) -> dict[str, object]:
        return {
            "history_size": self.history_size,
            "shift_threshold": self.shift_threshold,
            "severity_history": [dict(entry) for entry in self._severity_history],
        }


class EWCRegularizer:
    def __init__(
        self,
        *,
        lambda_weight: float = 0.1,
        state_path: str | Path = DEFAULT_EWC_STATE_PATH,
    ) -> None:
        normalized_lambda = float(lambda_weight)
        if not math.isfinite(normalized_lambda) or normalized_lambda < 0.0:
            raise ValueError("lambda_weight must be a finite non-negative float")
        self.lambda_weight = normalized_lambda
        self.state_path = Path(state_path)
        self._fisher: dict[str, torch.Tensor] = {}
        self._reference_params: dict[str, torch.Tensor] = {}
        self._sample_count = 0
        self._load_state()

    @staticmethod
    def _unpack_batch(batch: object) -> tuple[torch.Tensor, torch.Tensor]:
        if not isinstance(batch, (list, tuple)):
            raise TypeError("EWC fisher batches must be tuples or lists")
        if len(batch) < 2:
            raise ValueError("EWC fisher batches must contain features and labels")
        features = batch[0]
        labels = batch[1]
        if not isinstance(features, torch.Tensor) or not isinstance(labels, torch.Tensor):
            raise TypeError("EWC fisher batches must contain tensor features and labels")
        return features, labels

    def has_fisher(self) -> bool:
        return bool(self._fisher and self._reference_params and self._sample_count > 0)

    def compute_fisher(
        self,
        model: torch.nn.Module,
        dataloader: DataLoader | None,
        *,
        max_batches: int | None = None,
    ) -> int:
        if dataloader is None:
            logger.debug("ewc fisher computation skipped because dataloader is unavailable")
            return 0
        if not isinstance(model, torch.nn.Module):
            raise TypeError("EWC fisher computation requires a torch.nn.Module")
        first_param = next(model.parameters(), None)
        if first_param is None:
            raise ValueError("EWC fisher computation requires a model with parameters")
        device = first_param.device
        fisher_accumulator = {
            name: torch.zeros_like(parameter, dtype=torch.float32, device=device)
            for name, parameter in model.named_parameters()
            if parameter.requires_grad
        }
        if not fisher_accumulator:
            logger.debug("ewc fisher computation skipped because model has no trainable parameters")
            return 0

        sample_count = 0
        batch_count = 0
        criterion = torch.nn.CrossEntropyLoss()
        was_training = model.training
        model.eval()
        try:
            for batch in dataloader:
                features, labels = self._unpack_batch(batch)
                if labels.numel() == 0:
                    continue
                features = features.to(device)
                labels = labels.to(device)
                model.zero_grad(set_to_none=True)
                loss = criterion(model(features), labels)
                loss.backward()
                batch_size = int(labels.shape[0])
                for name, parameter in model.named_parameters():
                    if not parameter.requires_grad or parameter.grad is None:
                        continue
                    fisher_accumulator[name] += (
                        parameter.grad.detach().to(dtype=torch.float32).pow(2) * batch_size
                    )
                sample_count += batch_size
                batch_count += 1
                if max_batches is not None and batch_count >= int(max_batches):
                    break
        finally:
            model.zero_grad(set_to_none=True)
            if was_training:
                model.train()

        if sample_count <= 0:
            logger.warning("ewc fisher computation skipped because no labeled samples were available")
            return 0

        self._fisher = {
            name: tensor.detach().cpu() / float(sample_count)
            for name, tensor in fisher_accumulator.items()
        }
        self._reference_params = {
            name: parameter.detach().cpu().clone()
            for name, parameter in model.named_parameters()
            if parameter.requires_grad
        }
        self._sample_count = sample_count
        self._save_state()
        return sample_count

    def ewc_loss(self, model: torch.nn.Module) -> torch.Tensor:
        first_param = next(model.parameters(), None)
        if first_param is None:
            return torch.tensor(0.0, dtype=torch.float32)
        if not self.has_fisher():
            return torch.zeros((), dtype=torch.float32, device=first_param.device)
        loss = torch.zeros((), dtype=torch.float32, device=first_param.device)
        for name, parameter in model.named_parameters():
            fisher = self._fisher.get(name)
            reference_parameter = self._reference_params.get(name)
            if fisher is None or reference_parameter is None or not parameter.requires_grad:
                continue
            fisher_on_device = fisher.to(device=parameter.device, dtype=parameter.dtype)
            reference_on_device = reference_parameter.to(
                device=parameter.device,
                dtype=parameter.dtype,
            )
            loss = loss + torch.sum(
                fisher_on_device * (parameter - reference_on_device).pow(2)
            )
        return loss * (self.lambda_weight / 2.0)

    def _save_state(self) -> None:
        if not self.has_fisher():
            return
        tensors: dict[str, torch.Tensor] = {
            f"fisher::{name}": tensor.detach().cpu().to(dtype=torch.float32)
            for name, tensor in self._fisher.items()
        }
        tensors.update(
            {
                f"reference::{name}": tensor.detach().cpu().to(dtype=torch.float32)
                for name, tensor in self._reference_params.items()
            }
        )
        tensors["meta__sample_count"] = torch.tensor([self._sample_count], dtype=torch.int64)
        try:
            save_safetensors(
                tensors,
                str(self.state_path),
                metadata={
                    "schema_version": "1",
                    "sample_count": str(self._sample_count),
                    "updated_at": _utc_now(),
                },
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning(
                "ewc state persistence failed path=%s reason=%s",
                self.state_path,
                type(exc).__name__,
            )

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            tensors = load_safetensors(str(self.state_path), device="cpu")
        except FileNotFoundError:
            return
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            logger.warning(
                "ewc state load failed path=%s reason=%s",
                self.state_path,
                type(exc).__name__,
            )
            self._fisher = {}
            self._reference_params = {}
            self._sample_count = 0
            return
        loaded_fisher: dict[str, torch.Tensor] = {}
        loaded_reference_params: dict[str, torch.Tensor] = {}
        sample_count = 0
        for name, tensor in tensors.items():
            if name.startswith("fisher::"):
                loaded_fisher[name.split("::", 1)[1]] = tensor.detach().cpu().to(
                    dtype=torch.float32
                )
                continue
            if name.startswith("reference::"):
                loaded_reference_params[name.split("::", 1)[1]] = tensor.detach().cpu().to(
                    dtype=torch.float32
                )
                continue
            if name == "meta__sample_count":
                sample_count = int(tensor.reshape(-1)[0].item())
        self._fisher = loaded_fisher
        self._reference_params = loaded_reference_params
        self._sample_count = max(sample_count, 0)


class AdaptiveLearner:
    def __init__(
        self,
        *,
        state_path: str | Path = DEFAULT_ADAPTIVE_STATE_PATH,
        ewc_state_path: str | Path = DEFAULT_EWC_STATE_PATH,
        history_size: int = 5,
        shift_threshold: float = 0.2,
        ewc_lambda: float = 0.1,
        fisher_max_batches: int = 32,
        max_events: int = 200,
    ) -> None:
        self.state_path = Path(state_path)
        self.ewc_state_path = Path(ewc_state_path)
        self.max_events = max(int(max_events), 1)
        self.fisher_max_batches = max(int(fisher_max_batches), 1)
        self._lock = threading.RLock()
        self._model: torch.nn.Module | None = None
        self.monitor = DistributionMonitor(
            history_size=history_size,
            shift_threshold=shift_threshold,
        )
        self.regularizer = EWCRegularizer(
            lambda_weight=ewc_lambda,
            state_path=self.ewc_state_path,
        )
        self._events: list[AdaptationEvent] = []
        self._load_state()

    def attach_model(self, model: torch.nn.Module | None) -> None:
        with self._lock:
            self._model = model

    def on_new_grab_cycle(
        self,
        severity_counts: Mapping[str, int | float],
        model: torch.nn.Module | None = None,
        prev_dataloader: DataLoader | None = None,
    ) -> AdaptationEvent | None:
        if model is not None:
            self.attach_model(model)
        with self._lock:
            shift = self.monitor.observe(severity_counts)
            fisher_sample_count = 0
            active_model = model or self._model
            if shift.shift_detected and active_model is not None and prev_dataloader is not None:
                fisher_sample_count = self.regularizer.compute_fisher(
                    active_model,
                    prev_dataloader,
                    max_batches=self.fisher_max_batches,
                )
            if not shift.shift_detected:
                self._persist_state_locked()
                return None
            event = AdaptationEvent(
                event_id=uuid.uuid4().hex,
                severity_counts={
                    str(key).strip().upper(): int(value)
                    for key, value in dict(severity_counts).items()
                },
                baseline_distribution=shift.baseline_distribution,
                current_distribution=shift.current_distribution,
                js_distance=shift.js_distance,
                threshold=shift.threshold,
                history_depth=shift.history_depth,
                fisher_sample_count=fisher_sample_count,
            )
            self._events.append(event)
            if len(self._events) > self.max_events:
                self._events = self._events[-self.max_events :]
            self._persist_state_locked()
            return event

    def get_ewc_loss(self) -> torch.Tensor:
        with self._lock:
            if self._model is None:
                return torch.tensor(0.0, dtype=torch.float32)
            return self.regularizer.ewc_loss(self._model)

    def get_events(self) -> list[AdaptationEvent]:
        with self._lock:
            return list(self._events)

    def _persist_state_locked(self) -> None:
        payload = {
            "schema_version": 1,
            "updated_at": _utc_now(),
            "monitor": self.monitor.snapshot(),
            "events": [asdict(event) for event in self._events],
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(f"{self.state_path.suffix}.tmp")
        try:
            temp_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temp_path.replace(self.state_path)
        except OSError as exc:
            logger.warning(
                "adaptive learner state persistence failed path=%s reason=%s",
                self.state_path,
                type(exc).__name__,
            )
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError as cleanup_exc:
                    logger.warning(
                        "adaptive learner temp cleanup failed path=%s reason=%s",
                        temp_path,
                        type(cleanup_exc).__name__,
                    )

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "adaptive learner state load failed path=%s reason=%s",
                self.state_path,
                type(exc).__name__,
            )
            return
        if not isinstance(payload, dict):
            logger.warning(
                "adaptive learner state ignored path=%s reason=not_a_dict",
                self.state_path,
            )
            return
        monitor_payload = payload.get("monitor", {})
        if isinstance(monitor_payload, dict):
            try:
                self.monitor = DistributionMonitor(
                    history_size=int(
                        monitor_payload.get("history_size", self.monitor.history_size)
                    ),
                    shift_threshold=float(
                        monitor_payload.get(
                            "shift_threshold",
                            self.monitor.shift_threshold,
                        )
                    ),
                    severity_history=monitor_payload.get("severity_history", []),
                )
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "adaptive learner monitor state ignored path=%s reason=%s",
                    self.state_path,
                    type(exc).__name__,
                )
        events_payload = payload.get("events", [])
        if not isinstance(events_payload, list):
            logger.warning(
                "adaptive learner event state ignored path=%s reason=events_not_list",
                self.state_path,
            )
            return
        loaded_events: list[AdaptationEvent] = []
        for entry in events_payload:
            if not isinstance(entry, dict):
                logger.warning(
                    "adaptive learner event entry ignored path=%s reason=entry_not_dict",
                    self.state_path,
                )
                continue
            try:
                loaded_events.append(AdaptationEvent(**entry))
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "adaptive learner event entry ignored path=%s reason=%s",
                    self.state_path,
                    type(exc).__name__,
                )
        self._events = loaded_events[-self.max_events :]


_adaptive_learner_singletons: dict[tuple[str, str], AdaptiveLearner] = {}
_adaptive_learner_singleton_lock = threading.RLock()


def get_adaptive_learner(
    *,
    state_path: str | Path = DEFAULT_ADAPTIVE_STATE_PATH,
    ewc_state_path: str | Path = DEFAULT_EWC_STATE_PATH,
) -> AdaptiveLearner:
    key = (str(Path(state_path)), str(Path(ewc_state_path)))
    with _adaptive_learner_singleton_lock:
        adaptive_learner = _adaptive_learner_singletons.get(key)
        if adaptive_learner is None:
            adaptive_learner = AdaptiveLearner(
                state_path=key[0],
                ewc_state_path=key[1],
            )
            _adaptive_learner_singletons[key] = adaptive_learner
        return adaptive_learner
