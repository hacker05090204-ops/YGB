"""Real-sample class balancing helpers for incremental training."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence

import torch


@dataclass(frozen=True)
class ClassBalanceReport:
    class_counts: dict[int, int]
    class_weights: dict[int, float]
    oversampled_indices: tuple[int, ...]
    added_indices: int

    def weights_tensor(self, *, num_classes: int) -> torch.Tensor:
        values = [float(self.class_weights.get(label, 0.0)) for label in range(num_classes)]
        return torch.tensor(values, dtype=torch.float32)


class ClassBalancer:
    """Inverse-frequency weighting with minority oversampling using repeated real samples only."""

    @staticmethod
    def compute_class_weights(labels: Sequence[int]) -> dict[int, float]:
        counts = Counter(int(label) for label in labels)
        if not counts:
            return {}
        total = float(sum(counts.values()))
        class_count = float(len(counts))
        return {
            int(label): total / (class_count * float(count))
            for label, count in counts.items()
            if count > 0
        }

    @staticmethod
    def oversample_minority_indices(
        sample_indices: Sequence[int],
        labels: Sequence[int],
    ) -> tuple[tuple[int, ...], int]:
        if len(sample_indices) != len(labels):
            raise ValueError("sample_indices and labels must have the same length")
        if not sample_indices:
            return tuple(), 0

        grouped_indices: dict[int, list[int]] = defaultdict(list)
        for sample_index, label in zip(sample_indices, labels, strict=True):
            grouped_indices[int(label)].append(int(sample_index))

        max_count = max(len(indices) for indices in grouped_indices.values())
        oversampled = [int(sample_index) for sample_index in sample_indices]
        for label in sorted(grouped_indices):
            label_indices = grouped_indices[label]
            deficit = max_count - len(label_indices)
            if deficit <= 0:
                continue
            oversampled.extend(label_indices[offset % len(label_indices)] for offset in range(deficit))
        return tuple(oversampled), max(0, len(oversampled) - len(sample_indices))

    def balance_indices(
        self,
        *,
        sample_indices: Sequence[int],
        labels: Sequence[int],
    ) -> ClassBalanceReport:
        class_counts = Counter(int(label) for label in labels)
        oversampled_indices, added_indices = self.oversample_minority_indices(
            sample_indices,
            labels,
        )
        return ClassBalanceReport(
            class_counts={int(label): int(count) for label, count in sorted(class_counts.items())},
            class_weights=self.compute_class_weights(labels),
            oversampled_indices=oversampled_indices,
            added_indices=int(added_indices),
        )
