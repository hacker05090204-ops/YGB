from __future__ import annotations

import hashlib
import math
import os
import queue
import threading
from collections import OrderedDict
from dataclasses import dataclass
from typing import Dict, Iterator, Tuple

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
    cache_in_ram: bool = True
    max_ram_cache_shards: int = 2
    cache_dir: str = ""
    cache_to_disk: bool = False


class ShardedStreamingDataset:
    """In-memory streaming dataset adapter preserving controller inputs."""

    _ram_cache: "OrderedDict[str, Tuple[np.ndarray, np.ndarray]]" = OrderedDict()
    _cache_lock = threading.Lock()
    _cache_stats: Dict[str, int] = {
        "ram_hits": 0,
        "disk_hits": 0,
        "cache_misses": 0,
        "disk_writes": 0,
    }

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

    def _cache_key(self, shard: np.ndarray) -> str:
        digest = hashlib.sha1()
        digest.update(np.asarray(shard, dtype=np.int64).tobytes())
        digest.update(str(self.config.rank).encode("utf-8"))
        digest.update(str(self.config.world_size).encode("utf-8"))
        digest.update(str(self.config.batch_size).encode("utf-8"))
        digest.update(str(self.config.seed).encode("utf-8"))
        digest.update(str(int(self.config.drop_last)).encode("utf-8"))
        return digest.hexdigest()

    def _cache_path(self, cache_key: str) -> str:
        return os.path.join(self.config.cache_dir, f"{cache_key}.npz")

    def _load_cached_shard(self, cache_key: str) -> Tuple[np.ndarray, np.ndarray] | None:
        if self.config.cache_in_ram:
            with self._cache_lock:
                cached = self._ram_cache.get(cache_key)
                if cached is not None:
                    self._ram_cache.move_to_end(cache_key)
                    self._cache_stats["ram_hits"] += 1
                    return cached

        if self.config.cache_to_disk and self.config.cache_dir:
            cache_path = self._cache_path(cache_key)
            if os.path.exists(cache_path):
                with np.load(cache_path) as payload:
                    self._cache_stats["disk_hits"] += 1
                    return payload["X"], payload["y"]
        return None

    def _store_cached_shard(self, cache_key: str, shard_x: np.ndarray, shard_y: np.ndarray) -> None:
        if self.config.cache_in_ram:
            with self._cache_lock:
                self._ram_cache[cache_key] = (shard_x, shard_y)
                self._ram_cache.move_to_end(cache_key)
                while len(self._ram_cache) > max(1, int(self.config.max_ram_cache_shards)):
                    self._ram_cache.popitem(last=False)

        if self.config.cache_to_disk and self.config.cache_dir:
            os.makedirs(self.config.cache_dir, exist_ok=True)
            np.savez_compressed(self._cache_path(cache_key), X=shard_x, y=shard_y)
            self._cache_stats["disk_writes"] += 1

    def _prefetched(self, iterator: Iterator[Tuple[np.ndarray, np.ndarray]]) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        if self.config.prefetch_batches <= 0:
            yield from iterator
            return

        sentinel = object()
        batch_queue: "queue.Queue[object]" = queue.Queue(maxsize=max(1, int(self.config.prefetch_batches)))

        def _worker() -> None:
            try:
                for item in iterator:
                    batch_queue.put(item)
            finally:
                batch_queue.put(sentinel)

        thread = threading.Thread(target=_worker, name="dataset-prefetch", daemon=True)
        thread.start()

        while True:
            item = batch_queue.get()
            if item is sentinel:
                break
            yield item  # type: ignore[misc]

    def __iter__(self) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        indices = self.indices.copy()
        if self.config.shuffle and len(indices) > 1:
            rng = np.random.default_rng(self.config.seed)
            rng.shuffle(indices)

        shard = indices[self.config.rank :: self.config.world_size]
        cache_key = self._cache_key(shard)
        cached = self._load_cached_shard(cache_key)
        if cached is None:
            shard_x = np.ascontiguousarray(self.X[shard])
            shard_y = np.ascontiguousarray(self.y[shard])
            self._cache_stats["cache_misses"] += 1
            self._store_cached_shard(cache_key, shard_x, shard_y)
        else:
            shard_x, shard_y = cached
        batch = self.config.batch_size
        total = len(shard_x)
        stop = total if not self.config.drop_last else total - (total % batch)

        def _batch_iterator() -> Iterator[Tuple[np.ndarray, np.ndarray]]:
            for start in range(0, max(stop, 0), batch):
                end = min(start + batch, total)
                if self.config.drop_last and end - start < batch:
                    break
                yield shard_x[start:end], shard_y[start:end]

        yield from self._prefetched(_batch_iterator())

    def __len__(self) -> int:
        shard_items = math.ceil(len(self.X) / max(1, self.config.world_size))
        if self.config.drop_last:
            return shard_items // max(1, self.config.batch_size)
        return math.ceil(shard_items / max(1, self.config.batch_size))

    @classmethod
    def cache_stats(cls) -> Dict[str, int]:
        with cls._cache_lock:
            return dict(cls._cache_stats)
