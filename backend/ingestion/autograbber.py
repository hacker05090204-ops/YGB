"""End-to-end ingestion controller for scheduled multi-source grabs."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.cve.bridge_ingestion_worker import get_bridge_worker
from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.dedup import DedupIndex
from backend.ingestion.models import IngestedSample, detect_language, make_sample
from backend.ingestion.normalizer import (
    QualityRejectionLog,
    SampleQualityScorer,
    normalize_text,
)
from backend.ingestion.scrapers import (
    BaseScraper,
    CISAScraper,
    GitHubAdvisoryScraper,
    NVDScraper,
    OSVScraper,
    ScrapedSample,
)
import backend.training.feature_extractor as feature_extractor
from backend.training.safetensors_store import SafetensorsFeatureStore

logger = logging.getLogger("ygb.ingestion.autograbber")
DEFAULT_SOURCE_NAMES = ["nvd", "cisa", "osv", "github"]
SCRAPER_TYPES_BY_SOURCE: dict[str, type[BaseScraper]] = {
    "nvd": NVDScraper,
    "cisa": CISAScraper,
    "osv": OSVScraper,
    "github": GitHubAdvisoryScraper,
}


class RealBackendNotConfiguredError(RuntimeError):
    """Raised when a required real backend dependency is not configured."""


@dataclass(frozen=True)
class AutoGrabberConfig:
    sources: list[str] = field(default_factory=lambda: list(DEFAULT_SOURCE_NAMES))
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
    features_stored: int
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
        self._scraper_types = self._resolve_scraper_types(config.sources)
        self._dedup_path = os.environ.get(
            "YGB_CVE_DEDUP_STORE_PATH",
            "data/dedup_store.json",
        )
        self._feature_store_root = Path(
            os.environ.get(
                "YGB_AUTOGRABBER_FEATURE_STORE_PATH",
                "training/features_safetensors",
            )
        )
        self._feature_store = SafetensorsFeatureStore(self._feature_store_root)

    @staticmethod
    def _available_scraper_types() -> dict[str, type[BaseScraper]]:
        return dict(SCRAPER_TYPES_BY_SOURCE)

    def _resolve_scraper_types(self, sources: list[str]) -> tuple[type[BaseScraper], ...]:
        available = self._available_scraper_types()
        selected: list[type[BaseScraper]] = []
        missing: list[str] = []
        for source in sources:
            scraper_type = available.get(source)
            if scraper_type is None:
                missing.append(source)
                continue
            selected.append(scraper_type)
        if missing:
            raise RealBackendNotConfiguredError(
                "No real ingestion scraper is configured for source(s): " + ", ".join(missing)
            )
        return tuple(selected)

    def _next_cycle_id(self) -> str:
        with self._results_lock:
            self._cycle_sequence += 1
            return f"AGC-{self._cycle_sequence:06d}"

    @staticmethod
    def _label_for_sample(sample: IngestedSample) -> int:
        return 1 if sample.severity in {"CRITICAL", "HIGH", "MEDIUM"} else 0

    @staticmethod
    def _compress_feature_tensor(feature_tensor: Any) -> np.ndarray:
        feature_cpu = feature_tensor.detach().cpu().to(dtype=feature_tensor.dtype).reshape(-1)
        feature_array = feature_cpu.numpy().astype(np.float32, copy=False)
        if feature_array.shape != (512,):
            raise RuntimeError(
                f"REAL_DATA_REQUIRED: feature tensor must have shape (512,), got {feature_array.shape}"
            )
        compressed = feature_array.reshape(256, 2).mean(axis=1, dtype=np.float32)
        return compressed.reshape(1, 256)

    def _feature_metadata(self, sample: IngestedSample) -> dict[str, object]:
        return {
            "sample_sha256": sample.sha256_hash,
            "sample_source": sample.source,
            "sample_cve_id": sample.cve_id,
            "sample_severity": sample.severity,
            "sample_url": sample.url,
            "sample_ingested_at": sample.ingested_at.isoformat(),
            "sample_token_count": sample.token_count,
            "label": self._label_for_sample(sample),
            "original_feature_dim": 512,
            "stored_feature_dim": 256,
            "compression": "pairwise_mean_repeat_v1",
        }

    def _store_feature_artifact(self, sample: IngestedSample) -> None:
        feature_tensor = feature_extractor.extract(sample)
        compressed_feature = self._compress_feature_tensor(feature_tensor)
        labels = np.asarray([self._label_for_sample(sample)], dtype=np.int64)
        self._feature_store.write(
            sample.sha256_hash,
            compressed_feature,
            labels,
            metadata=self._feature_metadata(sample),
        )

    @staticmethod
    def _scraped_sample_to_payload(sample: ScrapedSample) -> dict[str, object]:
        raw_text_parts = [
            str(part).strip()
            for part in (
                f"{sample.vendor} {sample.product}".strip() if sample.vendor or sample.product else "",
                sample.description,
            )
            if str(part or "").strip()
        ]
        normalized_text = normalize_text(" ".join(raw_text_parts))
        unique_tags = list(
            dict.fromkeys(
                [
                    tag
                    for tag in (*sample.tags, *sample.aliases)
                    if str(tag or "").strip() and str(tag or "").strip() != sample.cve_id
                ]
            )
        )
        return {
            "source": sample.source,
            "description": normalized_text,
            "raw_text": normalized_text,
            "url": sample.url,
            "cve_id": sample.cve_id,
            "severity": sample.severity,
            "cvss_score": sample.cvss_score,
            "is_exploited": sample.is_exploited,
            "tags": unique_tags,
            "aliases": list(sample.aliases),
            "references": list(sample.references),
            "published_at": sample.published_at,
            "modified_at": sample.modified_at,
            "token_count": len(normalized_text.split()),
            "lang": detect_language(normalized_text),
        }

    @staticmethod
    def _payload_to_ingested_sample(payload: dict[str, object]) -> IngestedSample:
        return make_sample(
            source=str(payload.get("source", "") or ""),
            raw_text=str(payload.get("raw_text", payload.get("description", "")) or ""),
            url=str(payload.get("url", "") or ""),
            cve_id=str(payload.get("cve_id", "") or ""),
            severity=str(payload.get("severity", "UNKNOWN") or "UNKNOWN"),
            tags=[str(tag) for tag in payload.get("tags", []) if str(tag or "").strip()],
        )

    def _fetch_scraper_results(self, scraper_type: type[BaseScraper], max_items: int) -> tuple[str, object]:
        source = str(getattr(scraper_type, "SOURCE", scraper_type.__name__)).strip().lower()
        scraper = scraper_type()
        try:
            return source, list(scraper.fetch(max_items))
        except Exception as exc:
            return source, exc
        finally:
            close_method = getattr(scraper, "close", None)
            if callable(close_method):
                close_method()

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
        features_stored = 0
        bridge_published = 0
        accepted_samples: list[IngestedSample] = []

        dedup_store = DedupIndex(self._dedup_path)
        quality_scorer = SampleQualityScorer(
            dedup_store=dedup_store,
            rejection_log=QualityRejectionLog(),
        )

        try:
            per_source_limit = self.config.max_per_cycle // len(self._scraper_types)
            fetched_results = [
                self._fetch_scraper_results(scraper_type, per_source_limit)
                for scraper_type in self._scraper_types
            ]
            for source, fetch_result in fetched_results:
                sources_attempted += 1
                if isinstance(fetch_result, Exception):
                    error_message = f"{source}: fetch failed: {type(fetch_result).__name__}: {fetch_result}"
                    logger.error("autograbber_fetch_failed %s", error_message)
                    errors.append(error_message)
                    continue

                source_samples = list(fetch_result)[: max(per_source_limit, 0)]
                samples_fetched += len(source_samples)
                for scraped_sample in source_samples:
                    try:
                        payload = self._scraped_sample_to_payload(scraped_sample)
                        if self.config.dedup_enabled:
                            accepted = quality_scorer.is_acceptable(payload)
                        else:
                            accepted, _, _ = quality_scorer.evaluate(payload, ignore_duplicates=True)
                        score = quality_scorer.last_score
                        rejection_reason = quality_scorer.last_rejection_reason
                        if accepted and score < self.config.quality_threshold:
                            accepted = False
                            rejection_reason = "quality_threshold_not_met"
                            quality_scorer.rejection_log.append(
                                str(payload.get("cve_id", "") or ""),
                                rejection_reason,
                                score,
                            )
                        if not accepted:
                            samples_rejected += 1
                            logger.warning(
                                "autograbber_sample_rejected source=%s advisory_id=%s cve_id=%s reason=%s score=%.6f",
                                source,
                                scraped_sample.advisory_id,
                                scraped_sample.cve_id,
                                rejection_reason or "quality_rejected",
                                score,
                            )
                            continue
                        if self.config.dedup_enabled:
                            quality_scorer.record_seen(payload)
                        ingested_sample = self._payload_to_ingested_sample(payload)
                        accepted_samples.append(ingested_sample)
                        samples_accepted += 1
                        try:
                            self._store_feature_artifact(ingested_sample)
                            features_stored += 1
                        except Exception as exc:
                            error_message = (
                                f"{source}: feature storage failed for "
                                f"{ingested_sample.cve_id or ingested_sample.sha256_hash}: "
                                f"{type(exc).__name__}: {exc}"
                            )
                            logger.error("autograbber_feature_storage_failed %s", error_message)
                            errors.append(error_message)
                    except Exception as exc:
                        error_message = (
                            f"{source}: sample processing failed for "
                            f"{scraped_sample.cve_id or scraped_sample.advisory_id or '<missing-id>'}: "
                            f"{type(exc).__name__}: {exc}"
                        )
                        logger.error("autograbber_sample_processing_failed %s", error_message)
                        errors.append(error_message)
                sources_succeeded += 1

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
                features_stored=features_stored,
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
