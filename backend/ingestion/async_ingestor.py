"""Async orchestration for multi-source ingestion."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from aiolimiter import AsyncLimiter

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.adapters import (
    BugcrowdAdapter,
    CISAKEVAdapter,
    ExploitDBAdapter,
    GitHubAdvisoryAdapter,
    HackerOneAdapter,
    NVDAdapter,
)
from backend.ingestion.dedup import DedupIndex
from backend.ingestion.models import IngestedSample, sample_to_dict
from backend.ingestion.normalizer import normalize_batch
from backend.observability.metrics import metrics_registry

logger = logging.getLogger("ygb.ingestion.async_ingestor")


@dataclass(frozen=True)
class IngestCycleResult:
    new_count: int
    dupes_found: int
    duration_ms: float
    errors: int


class AsyncIngestor:
    def __init__(
        self,
        raw_root: str = "data/raw",
        dedup_index_path: str = "data/raw/dedup.db",
        adapters: list[object] | None = None,
    ) -> None:
        self.raw_root = Path(raw_root)
        self.semaphore = asyncio.Semaphore(10)
        self.limiter = AsyncLimiter(2, 1)
        self.dedup = DedupIndex(dedup_index_path)
        self.adapters = adapters or [
            HackerOneAdapter(self.semaphore, self.limiter),
            NVDAdapter(self.semaphore, self.limiter),
            GitHubAdvisoryAdapter(self.semaphore, self.limiter),
            CISAKEVAdapter(self.semaphore, self.limiter),
            ExploitDBAdapter(self.semaphore, self.limiter),
            BugcrowdAdapter(self.semaphore, self.limiter),
        ]

    @staticmethod
    def _metric_key(value: str) -> str:
        return "".join(character if character.isalnum() else "_" for character in value.lower())

    def _write_sample(self, sample: IngestedSample) -> None:
        date_folder = sample.ingested_at.date().isoformat()
        destination = self.raw_root / sample.source / date_folder
        destination.mkdir(parents=True, exist_ok=True)
        target_path = destination / f"{sample.sha256_hash}.json"
        temp_path = target_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(sample_to_dict(sample), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp_path, target_path)

    async def run_cycle(self) -> IngestCycleResult:
        self.dedup.load()
        start_time = time.monotonic()
        total_seen = 0
        new_count = 0
        dupes_found = 0
        errors = 0
        try:
            results = await asyncio.gather(*(adapter.fetch() for adapter in self.adapters), return_exceptions=True)
            for adapter, result in zip(self.adapters, results):
                source = getattr(adapter, "SOURCE", adapter.__class__.__name__.lower())
                metric_key = self._metric_key(source)
                if isinstance(result, Exception):
                    logger.error(
                        "ingest_adapter_error",
                        extra={"event": "ingest_adapter_error", "source": source, "error": str(result)},
                    )
                    metrics_registry.increment("ingest_errors_count")
                    metrics_registry.increment(f"ingest_errors_count_{metric_key}")
                    errors += 1
                    continue

                total_seen += len(result)
                metrics_registry.increment(f"ingest_total_count_{metric_key}", len(result))
                unique_samples: list[IngestedSample] = []
                for sample in result:
                    if self.dedup.is_duplicate(sample.sha256_hash):
                        dupes_found += 1
                        continue
                    self.dedup.mark_seen(sample.sha256_hash, source=source)
                    unique_samples.append(sample)

                normalized_samples = normalize_batch(unique_samples)
                for sample in normalized_samples:
                    self._write_sample(sample)
                    new_count += 1
                if normalized_samples:
                    metrics_registry.increment(f"ingest_new_count_{metric_key}", len(normalized_samples))

            self.dedup.save()
            duration_ms = (time.monotonic() - start_time) * 1000
            duplicate_rate = dupes_found / max(total_seen, 1)
            metrics_registry.increment("ingest_total_count", total_seen)
            metrics_registry.increment("ingest_new_count", new_count)
            metrics_registry.increment("ingest_errors_count", errors)
            metrics_registry.set_gauge("duplicate_rate", duplicate_rate)
            metrics_registry.record("ingest_duration_ms", duration_ms)

            return IngestCycleResult(
                new_count=new_count,
                dupes_found=dupes_found,
                duration_ms=duration_ms,
                errors=errors,
            )
        finally:
            self.dedup.close()


async def run_ingestion_cycle() -> IngestCycleResult:
    ingestor = AsyncIngestor()
    return await ingestor.run_cycle()


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
