"""Async orchestration for multi-source ingestion."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from aiolimiter import AsyncLimiter

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.adapters import (
    BugcrowdAdapter,
    CISAKEVAdapter,
    CIRCLCVEAdapter,
    ExploitDBAdapter,
    GitHubAdvisoryAdapter,
    HackerOneAdapter,
    NVDAdapter,
    OSVAdapter,
)
from backend.ingestion.dedup import DedupIndex
from backend.ingestion.models import IngestedSample, sample_to_dict
from backend.ingestion.normalizer import (
    QualityRejectionLog,
    SampleQualityScorer,
    normalize_batch_with_report,
)
from backend.observability.metrics import metrics_registry

logger = logging.getLogger("ygb.ingestion.async_ingestor")


DEFAULT_ADAPTER_TYPES = (
    HackerOneAdapter,
    NVDAdapter,
    GitHubAdvisoryAdapter,
    CISAKEVAdapter,
    CIRCLCVEAdapter,
    ExploitDBAdapter,
    BugcrowdAdapter,
    OSVAdapter,
)


@dataclass(frozen=True)
class IngestCycleResult:
    new_count: int
    dupes_found: int
    duration_ms: float
    errors: int
    normalized_count: int = 0
    normalization_cache_hits: int = 0
    backpressure_events: int = 0
    max_pending_depth: int = 0
    normalization_reports: tuple[dict[str, object], ...] = ()


class AsyncIngestor:
    def __init__(
        self,
        raw_root: str = "data/raw",
        dedup_index_path: str = "data/dedup_store.json",
        adapters: list[object] | None = None,
    ) -> None:
        self.raw_root = Path(raw_root)
        self.semaphore = asyncio.Semaphore(10)
        self.limiter = AsyncLimiter(2, 1)
        self.dedup = DedupIndex(dedup_index_path)
        self.max_pending_samples = max(
            1,
            int(os.environ.get("INGEST_MAX_PENDING_SAMPLES", "500")),
        )
        self.max_normalize_batch = max(
            1,
            int(os.environ.get("INGEST_MAX_NORMALIZE_BATCH", "250")),
        )
        self.adapters = adapters or [
            adapter_type(self.semaphore, self.limiter)
            for adapter_type in DEFAULT_ADAPTER_TYPES
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
        quality_scorer = SampleQualityScorer(
            dedup_store=self.dedup,
            rejection_log=QualityRejectionLog(),
        )
        start_time = time.monotonic()
        total_seen = 0
        new_count = 0
        dupes_found = 0
        errors = 0
        normalized_count = 0
        normalization_cache_hits = 0
        backpressure_events = 0
        max_pending_depth = 0
        normalization_reports: list[dict[str, object]] = []
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
                accepted_for_source = 0
                pending_cve_ids: set[str] = set()
                pending_hashes: set[str] = set()
                for sample in result:
                    normalized_cve_id = str(sample.cve_id or "")
                    normalized_text_hash = str(sample.sha256_hash or "")
                    is_pending_duplicate = False
                    if normalized_cve_id and normalized_cve_id in pending_cve_ids:
                        is_pending_duplicate = True
                    elif normalized_text_hash and normalized_text_hash in pending_hashes:
                        is_pending_duplicate = True
                    elif self.dedup.is_duplicate(normalized_cve_id, normalized_text_hash):
                        is_pending_duplicate = True
                    if is_pending_duplicate:
                        dupes_found += 1
                        continue
                    if normalized_cve_id:
                        pending_cve_ids.add(normalized_cve_id)
                    if normalized_text_hash:
                        pending_hashes.add(normalized_text_hash)
                    unique_samples.append(sample)

                max_pending_depth = max(max_pending_depth, len(unique_samples))
                chunks = [
                    unique_samples[index:index + self.max_pending_samples]
                    for index in range(0, len(unique_samples), self.max_pending_samples)
                ] or [[]]
                source_backpressure = len(unique_samples) > self.max_pending_samples

                for chunk_index, chunk in enumerate(chunks, start=1):
                    if not chunk:
                        continue
                    normalized_samples, normalization_report = normalize_batch_with_report(
                        chunk,
                        batch_limit=self.max_normalize_batch,
                        quality_scorer=quality_scorer,
                    )
                    normalized_count += normalization_report.emitted
                    normalization_cache_hits += normalization_report.cache_hits
                    source_backpressure = (
                        source_backpressure or normalization_report.backpressure_applied
                    )
                    normalization_reports.append(
                        {
                            "source": source,
                            "chunk_index": chunk_index,
                            **asdict(normalization_report),
                        }
                    )
                    metrics_registry.increment(
                        "ingest_normalization_cache_hits",
                        normalization_report.cache_hits,
                    )
                    metrics_registry.increment(
                        f"ingest_normalization_cache_hits_{metric_key}",
                        normalization_report.cache_hits,
                    )
                    metrics_registry.increment(
                        "ingest_normalized_count",
                        normalization_report.emitted,
                    )
                    for sample in normalized_samples:
                        self.dedup.record_seen(sample.cve_id, sample.sha256_hash, source=source)
                        self._write_sample(sample)
                        new_count += 1
                        accepted_for_source += 1

                if source_backpressure:
                    backpressure_events += 1
                    logger.warning(
                        "ingest_backpressure_applied",
                        extra={
                            "event": "ingest_backpressure_applied",
                            "source": source,
                            "pending": len(unique_samples),
                            "chunks": len([chunk for chunk in chunks if chunk]),
                        },
                    )
                    metrics_registry.increment("ingest_backpressure_events")
                    metrics_registry.increment(
                        f"ingest_backpressure_events_{metric_key}"
                    )

                if accepted_for_source:
                    metrics_registry.increment(f"ingest_new_count_{metric_key}", accepted_for_source)

            self.dedup.save()
            duration_ms = (time.monotonic() - start_time) * 1000
            duplicate_rate = dupes_found / max(total_seen, 1)
            metrics_registry.increment("ingest_total_count", total_seen)
            metrics_registry.increment("ingest_new_count", new_count)
            metrics_registry.increment("ingest_errors_count", errors)
            metrics_registry.set_gauge("duplicate_rate", duplicate_rate)
            metrics_registry.set_gauge("ingest_max_pending_depth", max_pending_depth)
            metrics_registry.record("ingest_duration_ms", duration_ms)

            return IngestCycleResult(
                new_count=new_count,
                dupes_found=dupes_found,
                duration_ms=duration_ms,
                errors=errors,
                normalized_count=normalized_count,
                normalization_cache_hits=normalization_cache_hits,
                backpressure_events=backpressure_events,
                max_pending_depth=max_pending_depth,
                normalization_reports=tuple(normalization_reports),
            )
        finally:
            self.dedup.close()


async def run_ingestion_cycle() -> IngestCycleResult:
    ingestor = AsyncIngestor()
    return await ingestor.run_cycle()


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
