"""Optimisation helpers for incremental training."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import torch


@dataclass(frozen=True)
class TrainingOptimiserConfig:
    learning_rate: float = 3e-4
    min_learning_rate: float = 1e-6
    max_epochs: int = 5
    warmup_ratio: float = 0.1
    warmup_start_factor: float = 0.1
    patience: int = 2
    min_delta: float = 1e-4
    gradient_clip_norm: float = 1.0
    accumulation_steps: int = 4
    use_amp: bool = True
    validation_split: float = 0.1
    shuffle_seed: int = 42
    hard_negative_fraction: float = 0.1
    hard_negative_min_count: int = 1
    hard_negative_max_count: int = 32
    hard_negative_weight: float = 2.0

    def __post_init__(self) -> None:
        if self.learning_rate < 0.0:
            raise ValueError("learning_rate must be non-negative")
        if self.min_learning_rate < 0.0:
            raise ValueError("min_learning_rate must be non-negative")
        if self.max_epochs < 1:
            raise ValueError("max_epochs must be at least 1")
        if not 0.0 <= self.warmup_ratio <= 1.0:
            raise ValueError("warmup_ratio must be between 0 and 1")
        if not 0.0 <= self.warmup_start_factor <= 1.0:
            raise ValueError("warmup_start_factor must be between 0 and 1")
        if self.patience < 0:
            raise ValueError("patience must be non-negative")
        if self.min_delta < 0.0:
            raise ValueError("min_delta must be non-negative")
        if self.gradient_clip_norm <= 0.0:
            raise ValueError("gradient_clip_norm must be positive")
        if self.accumulation_steps < 1:
            raise ValueError("accumulation_steps must be at least 1")
        if not 0.0 < self.validation_split < 1.0:
            raise ValueError("validation_split must be between 0 and 1")
        if not 0.0 <= self.hard_negative_fraction <= 1.0:
            raise ValueError("hard_negative_fraction must be between 0 and 1")
        if self.hard_negative_min_count < 0:
            raise ValueError("hard_negative_min_count must be non-negative")
        if self.hard_negative_max_count < 1:
            raise ValueError("hard_negative_max_count must be at least 1")
        if self.hard_negative_weight < 1.0:
            raise ValueError("hard_negative_weight must be at least 1.0")

    def resolved_warmup_steps(self, total_steps: int) -> int:
        if total_steps <= 0:
            raise ValueError("total_steps must be positive")
        if self.warmup_ratio <= 0.0:
            return 0
        return min(total_steps, max(1, int(round(total_steps * self.warmup_ratio))))

    def resolved_hard_negative_count(self, sample_count: int) -> int:
        if sample_count <= 0:
            return 0
        if self.hard_negative_fraction <= 0.0:
            return min(sample_count, self.hard_negative_min_count)
        raw_count = int(round(float(sample_count) * self.hard_negative_fraction))
        bounded = max(self.hard_negative_min_count, raw_count)
        return min(sample_count, self.hard_negative_max_count, bounded)

    def amp_enabled(self, device: torch.device | str | object) -> bool:
        device_type = getattr(device, "type", device)
        return self.use_amp and str(device_type).lower() == "cuda"


OptimiserConfig = TrainingOptimiserConfig
TrainingOptimizerConfig = TrainingOptimiserConfig
OptimizerConfig = TrainingOptimiserConfig


class WarmupCosineScheduler:
    def __init__(
        self,
        optimizer: torch.optim.Optimizer,
        *,
        total_steps: int,
        warmup_steps: int = 0,
        min_lr: float = 0.0,
        warmup_start_factor: float = 0.1,
    ) -> None:
        if total_steps < 1:
            raise ValueError("total_steps must be at least 1")
        if warmup_steps < 0:
            raise ValueError("warmup_steps must be non-negative")
        if min_lr < 0.0:
            raise ValueError("min_lr must be non-negative")
        if not 0.0 <= warmup_start_factor <= 1.0:
            raise ValueError("warmup_start_factor must be between 0 and 1")

        self.optimizer = optimizer
        self.total_steps = int(total_steps)
        self.warmup_steps = min(int(warmup_steps), self.total_steps)
        self.min_lr = float(min_lr)
        self.warmup_start_factor = float(warmup_start_factor)
        self.base_lrs = [float(group["lr"]) for group in optimizer.param_groups]
        self.current_step = 0
        self._last_lrs: list[float] = []
        self._apply_lrs(self._compute_lrs(step_index=0))

    def _scale_for_step(self, step_index: int) -> float:
        if self.warmup_steps > 0 and step_index <= self.warmup_steps:
            warmup_progress = float(step_index) / float(self.warmup_steps)
            return self.warmup_start_factor + (
                (1.0 - self.warmup_start_factor) * warmup_progress
            )
        if self.total_steps <= self.warmup_steps:
            return 1.0
        cosine_progress = float(step_index - self.warmup_steps) / float(
            max(self.total_steps - self.warmup_steps, 1)
        )
        cosine_progress = min(max(cosine_progress, 0.0), 1.0)
        return 0.5 * (1.0 + math.cos(math.pi * cosine_progress))

    def _compute_lrs(self, *, step_index: int) -> list[float]:
        scale = self._scale_for_step(step_index)
        learning_rates: list[float] = []
        for base_lr in self.base_lrs:
            floor_lr = min(base_lr, self.min_lr)
            learning_rates.append(floor_lr + ((base_lr - floor_lr) * scale))
        return learning_rates

    def _apply_lrs(self, learning_rates: list[float]) -> None:
        self._last_lrs = list(learning_rates)
        for group, learning_rate in zip(self.optimizer.param_groups, learning_rates):
            group["lr"] = float(learning_rate)

    def step(self) -> list[float]:
        self.current_step = min(self.current_step + 1, self.total_steps)
        learning_rates = self._compute_lrs(step_index=self.current_step)
        self._apply_lrs(learning_rates)
        return list(self._last_lrs)

    def get_last_lr(self) -> list[float]:
        return list(self._last_lrs)


class HardNegativeMiner:
    def __init__(self, *, max_hard_examples: int = 32) -> None:
        if max_hard_examples < 1:
            raise ValueError("max_hard_examples must be at least 1")
        self.max_hard_examples = int(max_hard_examples)
        self._records: dict[int, tuple[float, float]] = {}
        self._seen_examples = 0

    def reset(self) -> None:
        self._records.clear()
        self._seen_examples = 0

    def update(
        self,
        *,
        losses: list[float] | np.ndarray,
        labels: list[int] | np.ndarray,
        positive_probabilities: list[float] | np.ndarray,
        dataset_indices: list[int] | np.ndarray | None = None,
    ) -> None:
        loss_array = np.asarray(losses, dtype=np.float64).reshape(-1)
        label_array = np.asarray(labels, dtype=np.int64).reshape(-1)
        probability_array = np.asarray(positive_probabilities, dtype=np.float64).reshape(-1)
        if not np.isfinite(loss_array).all() or not np.isfinite(probability_array).all():
            raise ValueError("losses and positive_probabilities must be finite")
        if loss_array.shape[0] != label_array.shape[0] or loss_array.shape[0] != probability_array.shape[0]:
            raise ValueError("losses, labels, and positive_probabilities must have the same length")
        if dataset_indices is None:
            index_array = np.arange(
                self._seen_examples,
                self._seen_examples + label_array.shape[0],
                dtype=np.int64,
            )
        else:
            index_array = np.asarray(dataset_indices, dtype=np.int64).reshape(-1)
            if index_array.shape[0] != label_array.shape[0]:
                raise ValueError("dataset_indices must match labels length")

        negative_mask = label_array == 0
        for dataset_index, probability, loss in zip(
            index_array[negative_mask],
            probability_array[negative_mask],
            loss_array[negative_mask],
        ):
            current_record = self._records.get(int(dataset_index))
            next_record = (float(loss), float(probability))
            if current_record is None or next_record > current_record:
                self._records[int(dataset_index)] = next_record
        self._seen_examples += int(label_array.shape[0])

    def get_hard_indices(self, count: int | None = None) -> list[int]:
        limit = self.max_hard_examples if count is None else max(0, int(count))
        ranked = sorted(
            self._records.items(),
            key=lambda item: (-item[1][0], -item[1][1], item[0]),
        )
        return [dataset_index for dataset_index, _ in ranked[:limit]]

    def mine(
        self,
        *,
        losses: list[float] | np.ndarray,
        labels: list[int] | np.ndarray,
        positive_probabilities: list[float] | np.ndarray,
        dataset_indices: list[int] | np.ndarray | None = None,
        count: int | None = None,
    ) -> list[int]:
        self.reset()
        self.update(
            losses=losses,
            labels=labels,
            positive_probabilities=positive_probabilities,
            dataset_indices=dataset_indices,
        )
        return self.get_hard_indices(count=count)


class EarlyStopping:
    def __init__(
        self,
        *,
        patience: int = 2,
        min_delta: float = 0.0,
        mode: str = "min",
    ) -> None:
        if patience < 0:
            raise ValueError("patience must be non-negative")
        if min_delta < 0.0:
            raise ValueError("min_delta must be non-negative")
        if mode not in {"min", "max"}:
            raise ValueError("mode must be either 'min' or 'max'")
        self.patience = int(patience)
        self.min_delta = float(min_delta)
        self.mode = mode
        self.best_value: float | None = None
        self.bad_epochs = 0
        self.stopped = False

    def is_improvement(self, value: float) -> bool:
        if not math.isfinite(value):
            raise ValueError("early stopping value must be finite")
        if self.best_value is None:
            return True
        if self.mode == "min":
            return value < (self.best_value - self.min_delta)
        return value > (self.best_value + self.min_delta)

    def step(self, value: float) -> bool:
        metric = float(value)
        if self.is_improvement(metric):
            self.best_value = metric
            self.bad_epochs = 0
            self.stopped = False
            return False
        self.bad_epochs += 1
        self.stopped = self.bad_epochs >= self.patience
        return self.stopped
