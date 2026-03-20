from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator, Tuple

import numpy as np


@dataclass
class StreamingDatasetConfig:
    batch_size: int
    rank: int = 0
    world_size: int = 1
    shuffle: bool = True
    seed: int = 42
    drop_last: bool = False
    prefetch_batches: int = 2


class ShardedStreamingDataset:
    """In-memory streaming dataset adapter preserving controller inputs."""

    def __init__(self, X: np.ndarray, y: np.ndarray, config: StreamingDatasetConfig):
        self.X = X
        self.y = y
        self.config = config
        self.indices = np.arange(len(X), dtype=np.int64)

    def reshard(self, world_size: int, rank: int) -> None:
        self.config.world_size = max(1, int(world_size))
        self.config.rank = max(0, int(rank))

    def set_batch_size(self, batch_size: int) -> None:
        self.config.batch_size = max(1, int(batch_size))

    def __iter__(self) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        indices = self.indices.copy()
        if self.config.shuffle and len(indices) > 1:
            rng = np.random.default_rng(self.config.seed)
            rng.shuffle(indices)

        shard = indices[self.config.rank :: self.config.world_size]
        batch = self.config.batch_size
        total = len(shard)
        stop = total if not self.config.drop_last else total - (total % batch)
        for start in range(0, max(stop, 0), batch):
            end = min(start + batch, total)
            if self.config.drop_last and end - start < batch:
                break
            batch_idx = shard[start:end]
            yield self.X[batch_idx], self.y[batch_idx]

    def __len__(self) -> int:
        shard_items = math.ceil(len(self.X) / max(1, self.config.world_size))
        if self.config.drop_last:
            return shard_items // max(1, self.config.batch_size)
        return math.ceil(shard_items / max(1, self.config.batch_size))
