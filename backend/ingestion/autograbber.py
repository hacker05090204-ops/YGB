"""End-to-end ingestion controller for scheduled multi-source grabs."""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from aiolimiter import AsyncLimiter

from backend.cve.bridge_ingestion_worker import get_bridge_worker
from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.async_ingestor import DEFAULT_ADAPTER_TYPES
from backend.ingestion.dedup import DedupIndex
from backend.ingestion.models import IngestedSample
from backend.ingestion.normalizer import (
    QualityRejectionLog,
    SampleQualityScorer,
    normalize_batch_with_report,
    normalize_sample_with_quality,
)

logger = logging.getLogger("ygb.ingestion.autograbber")


class RealBackendNotConfiguredError(RuntimeError):
    """Raised when a required real backend dependency is not configured."""


@dataclass(frozen=True)
class AutoGrabberConfig:
    sources: list[str]
    cycle_interval_seconds: int = 3600
    quality_threshold: float = 0.4
    max_per_cycle: int = 500
    dedup_enabled: bool = True

    def __post_init__(self) -> None:
        normalized_sources: list[str] = []
        seen_sources: set[str] = set()
        for source in self.sources:
            normalized = str(source or "").strip().lower()
            if not normalized:
                raise ValueError("AutoGrabberConfig.sources must not contain blank values")
            if normalized in seen_sources:
                raise ValueError(f"AutoGrabberConfig.sources contains duplicate source: {normalized}")
            seen_sources.add(normalized)
            normalized_sources.append(normalized)
        if not normalized_sources:
            raise ValueError("AutoGrabberConfig.sources must contain at least one source")
        if self.cycle_interval_seconds <= 0:
            raise ValueError("cycle_interval_seconds must be greater than zero")
        if not 0.0 <= self.quality_threshold <= 1.0:
            raise ValueError("quality_threshold must be between 0.0 and 1.0")
        if self.max_per_cycle <= 0:
            raise ValueError("max_per_cycle must be greater than zero")
        object.__setattr__(self, "sources", normalized_sources)


@dataclass(frozen=True)
class GrabberCycleResult:
    cycle_id: str
    started_at: str
    completed_at: str
    sources_attempted: int
    sources_succeeded: int
    samples_fetched: int
    samples_accepted: int
    samples_rejected: int
    bridge_published: int
    errors: list[str]


class AutoGrabber:
    """Single controller that fetches, normalizes, gates, deduplicates, and bridges samples."""

    def __init__(self, config: AutoGrabberConfig) -> None:
        self.config = config
        self._cycle_sequence = 0
        self._results: list[GrabberCycleResult] = []
        self._last_cycle_result: GrabberCycleResult | None = None
        self._results_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._adapter_types = self._resolve_adapter_types(config.sources)
        self._dedup_path = os.environ.get(
            "YGB_CVE_DEDUP_STORE_PATH",
            "data/dedup_store.json",
        )

    @staticmethod
    def _available_adapter_types() -> dict[str, type[object]]:
        return {
            str(getattr(adapter_type, "SOURCE", adapter_type.__name__)).strip().lower(): adapter_type
            for adapter_type in DEFAULT_ADAPTER_TYPES
        }

    def _resolve_adapter_types(self, sources: list[str]) -> tuple[type[object], ...]:
        available = self._available_adapter_types()
        selected: list[type[object]] = []
        missing: list[str] = []
        for source in sources:
            adapter_type = available.get(source)
            if adapter_type is None:
                missing.append(source)
                continue
            selected.append(adapter_type)
        if missing:
            raise RealBackendNotConfiguredError(
                "No real ingestion adapter is configured for source(s): " + ", ".join(missing)
            )
        return tuple(selected)

    def _next_cycle_id(self) -> str:
        with self._results_lock:
            self._cycle_sequence += 1
            return f"AGC-{self._cycle_sequence:06d}"

    async def _fetch_all_sources(self) -> list[tuple[str, object]]:
        semaphore = asyncio.Semaphore(10)
        limiter = AsyncLimiter(2, 1)
        adapters = [
            adapter_type(semaphore, limiter)
            for adapter_type in self._adapter_types
        ]
        results = await asyncio.gather(
            *(adapter.fetch() for adapter in adapters),
            return_exceptions=True,
        )
        return [
            (
                str(getattr(adapter, "SOURCE", adapter.__class__.__name__)).strip().lower(),
                result,
            )
            for adapter, result in zip(adapters, results)
        ]

    @staticmethod
    def _quality_payload(sample: IngestedSample) -> dict[str, object]:
        return {
            "source": sample.source,
            "description": sample.raw_text,
            "raw_text": sample.raw_text,
            "url": sample.url,
            "cve_id": sample.cve_id,
            "severity": sample.severity,
            "tags": list(sample.tags),
            "token_count": sample.token_count,
            "lang": sample.lang,
            "sha256_hash": sample.sha256_hash,
        }

    def _store_result(self, result: GrabberCycleResult) -> None:
        with self._results_lock:
            self._last_cycle_result = result
            self._results.append(result)
            self._results = self._results[-100:]

    def run_cycle(self) -> GrabberCycleResult:
        cycle_id = self._next_cycle_id()
        started_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []
        sources_attempted = 0
        sources_succeeded = 0
        samples_fetched = 0
        samples_accepted = 0
        samples_rejected = 0
        bridge_published = 0
        processed_candidates = 0
        accepted_samples: list[IngestedSample] = []

        dedup_store = DedupIndex(self._dedup_path)
        quality_scorer = SampleQualityScorer(
            dedup_store=dedup_store,
            rejection_log=QualityRejectionLog(),
        )

        try:
            fetched_results = asyncio.run(self._fetch_all_sources())
            for source, fetch_result in fetched_results:
                sources_attempted += 1
                if isinstance(fetch_result, Exception):
                    error_message = f"{source}: fetch failed: {type(fetch_result).__name__}: {fetch_result}"
                    logger.error("autograbber_fetch_failed %s", error_message)
                    errors.append(error_message)
                    continue

                source_samples = list(fetch_result)
                samples_fetched += len(source_samples)

                try:
                    if processed_candidates >= self.config.max_per_cycle:
                        if source_samples:
                            logger.info(
                                "autograbber_cycle_capacity_reached source=%s fetched=%s",
                                source,
                                len(source_samples),
                            )
                        sources_succeeded += 1
                        continue

                    remaining_capacity = self.config.max_per_cycle - processed_candidates
                    samples_to_process = source_samples[:remaining_capacity]
                    if len(source_samples) > len(samples_to_process):
                        logger.info(
                            "autograbber_source_capped source=%s fetched=%s processed=%s",
                            source,
                            len(source_samples),
                            len(samples_to_process),
                        )

                    normalized_samples, _ = normalize_batch_with_report(samples_to_process)
                    processed_candidates += len(samples_to_process)

                    for sample in normalized_samples:
                        try:
                            normalized_payload, accepted, rejection_reason, score = normalize_sample_with_quality(
                                self._quality_payload(sample),
                                scorer=quality_scorer,
                                ignore_duplicates=not self.config.dedup_enabled,
                            )
                        except Exception as exc:
                            error_message = (
                                f"{source}: sample processing failed for {sample.cve_id or '<missing-cve-id>'}: "
                                f"{type(exc).__name__}: {exc}"
                            )
                            logger.error("autograbber_sample_processing_failed %s", error_message)
                            errors.append(error_message)
                            continue

                        if accepted and score < self.config.quality_threshold:
                            accepted = False
                            rejection_reason = "quality_threshold_not_met"

                        if not accepted:
                            samples_rejected += 1
                            logger.warning(
                                "autograbber_sample_rejected source=%s cve_id=%s reason=%s score=%.6f",
                                source,
                                sample.cve_id,
                                rejection_reason or "quality_rejected",
                                score,
                            )
                            continue

                        if self.config.dedup_enabled:
                            quality_scorer.record_seen(normalized_payload)

                        accepted_samples.append(
                            replace(
                                sample,
                                raw_text=str(normalized_payload.get("raw_text", sample.raw_text)),
                                token_count=int(normalized_payload.get("token_count", sample.token_count)),
                                lang=str(normalized_payload.get("lang", sample.lang)),
                            )
                        )
                        samples_accepted += 1

                    sources_succeeded += 1
                except Exception as exc:
                    error_message = f"{source}: processing failed: {type(exc).__name__}: {exc}"
                    logger.error("autograbber_source_processing_failed %s", error_message)
                    errors.append(error_message)

            if accepted_samples:
                bridge_worker = get_bridge_worker()
                if not bridge_worker.is_bridge_loaded:
                    raise RealBackendNotConfiguredError(
                        "Bridge ingestion backend is not configured; accepted samples cannot be published."
                    )
                try:
                    bridge_published = int(bridge_worker.publish_ingestion_samples(accepted_samples))
                except Exception as exc:
                    bridge_published = 0
                    error_message = f"bridge publish failed: {type(exc).__name__}: {exc}"
                    logger.critical("autograbber_bridge_publish_failed %s", error_message)
                    errors.append(error_message)

                try:
                    bridge_worker.update_manifest()
                except RuntimeError as exc:
                    if "SYSTEM NOT READY" in str(exc) or "Missing authority key" in str(exc):
                        raise RealBackendNotConfiguredError(
                            "Accepted samples require manifest signing, but the real signing backend is not configured."
                        ) from exc
                    raise

            result = GrabberCycleResult(
                cycle_id=cycle_id,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc).isoformat(),
                sources_attempted=sources_attempted,
                sources_succeeded=sources_succeeded,
                samples_fetched=samples_fetched,
                samples_accepted=samples_accepted,
                samples_rejected=samples_rejected,
                bridge_published=bridge_published,
                errors=list(errors),
            )
            self._store_result(result)
            return result
        finally:
            dedup_store.close()

    def get_last_cycle_result(self) -> GrabberCycleResult | None:
        with self._results_lock:
            return self._last_cycle_result

    def get_all_results(self) -> list[GrabberCycleResult]:
        with self._results_lock:
            return list(self._results)

    def start_scheduled(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()

        def _runner() -> None:
            while not self._stop_event.is_set():
                try:
                    self.run_cycle()
                except RealBackendNotConfiguredError as exc:
                    logger.error("autograbber_cycle_backend_unavailable %s", exc)
                except Exception as exc:
                    logger.exception("autograbber_cycle_failed: %s", exc)

                if self._stop_event.wait(self.config.cycle_interval_seconds):
                    break

        self._thread = threading.Thread(
            target=_runner,
            name="autograbber-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1, self.config.cycle_interval_seconds))
            self._thread = None


_grabber: AutoGrabber | None = None


def get_autograbber() -> AutoGrabber:
    """Return the configured autograbber singleton."""
    if _grabber is None:
        raise RealBackendNotConfiguredError(
            "AutoGrabber is not initialized. Call initialize_autograbber() with a real configuration first."
        )
    return _grabber


def initialize_autograbber(config: AutoGrabberConfig) -> AutoGrabber:
    """Initialize the autograbber singleton with a concrete configuration."""
    global _grabber
    if _grabber is not None:
        _grabber.stop()
    _grabber = AutoGrabber(config)
    return _grabber


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
