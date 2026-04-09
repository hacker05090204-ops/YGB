"""End-to-end ingestion controller for scheduled multi-source grabs."""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from backend.cve.bridge_ingestion_worker import get_bridge_worker
from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.dedup import DedupIndex
from backend.ingestion.models import IngestedSample, detect_language, make_sample, normalize_severity
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
from backend.training.data_purity import (
    AllRowsRejectedError,
    DataPurityEnforcer,
)
from backend.training.rl_feedback import get_rl_collector
from backend.training.safetensors_store import SafetensorsFeatureStore

logger = logging.getLogger("ygb.ingestion.autograbber")
DEFAULT_SOURCE_NAMES = ["nvd", "cisa", "osv", "github"]
SCRAPER_TYPES_BY_SOURCE: dict[str, type[BaseScraper]] = {
    "nvd": NVDScraper,
    "cisa": CISAScraper,
    "osv": OSVScraper,
    "github": GitHubAdvisoryScraper,
}
VALIDATOR_REJECTION_KEYS = ("structural", "purity", "quality", "dedup", "feature")


class RealBackendNotConfiguredError(RuntimeError):
    """Raised when a required real backend dependency is not configured."""


class DataIntegrityValidator:
    """Deterministic structural validation for scraped and normalized samples."""

    @staticmethod
    def _extract_fields(
        sample: Mapping[str, object] | ScrapedSample | IngestedSample,
    ) -> dict[str, str]:
        if isinstance(sample, ScrapedSample):
            return {
                "source": str(sample.source or "").strip(),
                "description": str(sample.render_text() or "").strip(),
                "cve_id": str(sample.cve_id or "").strip(),
                "severity": str(sample.severity or "").strip(),
            }
        if isinstance(sample, IngestedSample):
            return {
                "source": str(sample.source or "").strip(),
                "description": str(sample.raw_text or "").strip(),
                "cve_id": str(sample.cve_id or "").strip(),
                "severity": str(sample.severity or "").strip(),
            }
        if isinstance(sample, Mapping):
            return {
                "source": str(sample.get("source", "") or "").strip(),
                "description": str(
                    sample.get("description") or sample.get("raw_text") or ""
                ).strip(),
                "cve_id": str(sample.get("cve_id", "") or "").strip(),
                "severity": str(sample.get("severity", "") or "").strip(),
            }
        raise TypeError("DataIntegrityValidator.validate_sample() requires a mapping or sample model")

    def validate_sample(
        self,
        sample: Mapping[str, object] | ScrapedSample | IngestedSample,
    ) -> tuple[bool, str | None]:
        fields = self._extract_fields(sample)
        if not fields["source"]:
            return False, "missing_source"
        if not fields["description"]:
            return False, "missing_description"
        if not fields["cve_id"]:
            return False, "missing_cve_id"
        if not fields["severity"]:
            return False, "missing_severity"
        return True, None


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
    purity_rejected: int
    validator_rejections: dict[str, int]
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
        self._integrity_validator = DataIntegrityValidator()
        self._purity_enforcer = DataPurityEnforcer()
        self._rl_collector = get_rl_collector()
        self._previous_severities_path = Path(
            os.environ.get(
                "YGB_PREVIOUS_SEVERITIES_PATH",
                "data/previous_severities.json",
            )
        )
        self._previous_severities = self._load_previous_severities()

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

    @staticmethod
    def _new_validator_rejections() -> dict[str, int]:
        return {key: 0 for key in VALIDATOR_REJECTION_KEYS}

    @staticmethod
    def _increment_validator_rejection(
        validator_rejections: dict[str, int],
        validator_key: str,
    ) -> None:
        validator_rejections[validator_key] = validator_rejections.get(validator_key, 0) + 1

    @staticmethod
    def _log_sample_rejection(
        *,
        source: str,
        scraped_sample: ScrapedSample,
        validator_key: str,
        reason: str,
        score: float | None = None,
    ) -> None:
        if score is None:
            logger.warning(
                "autograbber_sample_rejected source=%s advisory_id=%s cve_id=%s validator=%s reason=%s",
                source,
                scraped_sample.advisory_id,
                scraped_sample.cve_id,
                validator_key,
                reason,
            )
            return
        logger.warning(
            "autograbber_sample_rejected source=%s advisory_id=%s cve_id=%s validator=%s reason=%s score=%.6f",
            source,
            scraped_sample.advisory_id,
            scraped_sample.cve_id,
            validator_key,
            reason,
            score,
        )

    def _validate_structural_sample(
        self,
        sample: Mapping[str, object] | ScrapedSample | IngestedSample,
    ) -> tuple[bool, str | None]:
        return self._integrity_validator.validate_sample(sample)

    def _enforce_sample_purity(
        self,
        sample: Mapping[str, object] | IngestedSample,
    ) -> tuple[dict[str, object] | IngestedSample | None, Any]:
        return self._purity_enforcer.enforce(sample)

    def _score_sample_quality(
        self,
        payload: dict[str, object],
        quality_scorer: SampleQualityScorer,
    ) -> tuple[bool, str | None, float]:
        accepted, rejection_reason, score = quality_scorer.evaluate(
            payload,
            ignore_duplicates=True,
        )
        if accepted and score < self.config.quality_threshold:
            accepted = False
            rejection_reason = "quality_threshold_not_met"
            quality_scorer.rejection_log.append(
                str(payload.get("cve_id", "") or ""),
                rejection_reason,
                score,
            )
        return accepted, rejection_reason, score

    def _check_duplicate_sample(
        self,
        payload: dict[str, object],
        quality_scorer: SampleQualityScorer,
    ) -> tuple[bool, str | None]:
        if not self.config.dedup_enabled:
            return False, None
        text_hash = str(
            payload.get("text_hash")
            or quality_scorer.compute_text_hash(SampleQualityScorer._extract_text(payload))
        )
        payload["text_hash"] = text_hash
        cve_id = str(payload.get("cve_id", "") or "")
        if not quality_scorer.dedup_store.is_duplicate(cve_id, text_hash):
            return False, None
        rejection_reason = (
            "duplicate_cve_id"
            if quality_scorer.dedup_store.has_cve_id(cve_id)
            else "duplicate_text_hash"
        )
        quality_scorer.last_rejection_reason = rejection_reason
        quality_scorer.rejection_log.append(cve_id, rejection_reason, quality_scorer.last_score)
        return True, rejection_reason

    def _extract_feature_tensor(self, sample: IngestedSample):
        return feature_extractor.extract(sample)

    def _enforce_feature_tensor_purity(
        self,
        sample: IngestedSample,
        feature_tensor: Any,
    ) -> tuple[np.ndarray, np.ndarray, Any]:
        compressed_feature = self._compress_feature_tensor(feature_tensor)
        labels = np.asarray([self._label_for_sample(sample)], dtype=np.int64)
        purified_features, purified_labels, _, purity_result = self._purity_enforcer.enforce_feature_tensor(
            compressed_feature,
            labels,
            [sample.sha256_hash],
        )
        return purified_features, purified_labels, purity_result

    def _write_feature_store(
        self,
        sample: IngestedSample,
        features: np.ndarray,
        labels: np.ndarray,
    ) -> None:
        self._feature_store.write(
            sample.sha256_hash,
            features,
            labels,
            metadata=self._feature_metadata(sample),
        )

    def _store_feature_artifact(self, sample: IngestedSample):
        feature_tensor = self._extract_feature_tensor(sample)
        purified_features, purified_labels, purity_result = self._enforce_feature_tensor_purity(
            sample,
            feature_tensor,
        )
        self._write_feature_store(sample, purified_features, purified_labels)
        return purity_result

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

    def _load_previous_severities(self) -> dict[str, str]:
        if not self._previous_severities_path.exists():
            return {}
        try:
            payload = json.loads(
                self._previous_severities_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "autograbber_previous_severity_load_failed path=%s reason=%s",
                self._previous_severities_path,
                type(exc).__name__,
            )
            return {}
        if not isinstance(payload, dict):
            logger.warning(
                "autograbber_previous_severity_load_failed path=%s reason=not_a_dict",
                self._previous_severities_path,
            )
            return {}
        severities: dict[str, str] = {}
        for cve_id, severity in payload.items():
            normalized_cve_id = str(cve_id or "").strip().upper()
            if not normalized_cve_id:
                continue
            severities[normalized_cve_id] = normalize_severity(str(severity or "UNKNOWN"))
        return severities

    def _save_previous_severities(self) -> None:
        payload = {
            cve_id: normalize_severity(severity)
            for cve_id, severity in sorted(self._previous_severities.items())
            if str(cve_id or "").strip()
        }
        self._previous_severities_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._previous_severities_path.with_suffix(
            f"{self._previous_severities_path.suffix}.tmp"
        )
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temp_path, self._previous_severities_path)

    def _persist_previous_severities(self, errors: list[str] | None = None) -> None:
        try:
            self._save_previous_severities()
        except (OSError, TypeError, ValueError) as exc:
            error_message = (
                f"previous severity persistence failed: {type(exc).__name__}: {exc}"
            )
            logger.error("autograbber_previous_severity_persist_failed %s", error_message)
            if errors is not None:
                errors.append(error_message)

    @staticmethod
    def _extract_cve_ids(samples: list[ScrapedSample]) -> list[str]:
        return sorted(
            {
                str(sample.cve_id or "").strip().upper()
                for sample in samples
                if str(sample.cve_id or "").strip()
            }
        )

    def _process_cisa_rl_feedback(self, source_samples: list[ScrapedSample]) -> None:
        kev_ids = self._extract_cve_ids(source_samples)
        if kev_ids:
            self._rl_collector.process_new_cisa_kev_batch(kev_ids)

    def _process_nvd_severity_feedback(self, source_samples: list[ScrapedSample]) -> None:
        for sample in source_samples:
            cve_id = str(sample.cve_id or "").strip().upper()
            if not cve_id:
                continue
            new_severity = normalize_severity(sample.severity)
            previous_severity = self._previous_severities.get(cve_id)
            if previous_severity is not None and previous_severity != new_severity:
                self._rl_collector.process_severity_update(
                    cve_id,
                    previous_severity,
                    new_severity,
                )
            self._previous_severities[cve_id] = new_severity

    def _record_rl_feedback_prediction(
        self,
        sample: IngestedSample,
        errors: list[str] | None = None,
    ) -> None:
        record_prediction = getattr(self._rl_collector, "record_prediction", None)
        if not callable(record_prediction):
            return
        try:
            record_prediction(
                sample_id=sample.sha256_hash,
                cve_id=sample.cve_id,
                predicted_severity=sample.severity,
            )
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            error_message = (
                f"rl prediction recording failed for {sample.cve_id or sample.sha256_hash}: "
                f"{type(exc).__name__}: {exc}"
            )
            logger.warning("autograbber_rl_prediction_record_failed %s", error_message)
            if errors is not None:
                errors.append(error_message)

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
        purity_rejected = 0
        validator_rejections = self._new_validator_rejections()
        accepted_samples: list[IngestedSample] = []
        previous_severities_persisted = False

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
                try:
                    if source == "cisa":
                        self._process_cisa_rl_feedback(source_samples)
                    elif source == "nvd":
                        self._process_nvd_severity_feedback(source_samples)
                except (OSError, RuntimeError, TypeError, ValueError) as exc:
                    error_message = (
                        f"{source}: rl feedback processing failed: {type(exc).__name__}: {exc}"
                    )
                    logger.error("autograbber_rl_feedback_failed %s", error_message)
                    errors.append(error_message)
                samples_fetched += len(source_samples)
                for scraped_sample in source_samples:
                    score: float | None = None
                    sample_identifier = (
                        scraped_sample.cve_id
                        or scraped_sample.advisory_id
                        or "<missing-id>"
                    )

                    def _reject_sample(
                        validator_key: str,
                        reason: str,
                        *,
                        rejection_score: float | None = None,
                    ) -> None:
                        nonlocal samples_rejected
                        samples_rejected += 1
                        self._increment_validator_rejection(
                            validator_rejections,
                            validator_key,
                        )
                        self._log_sample_rejection(
                            source=source,
                            scraped_sample=scraped_sample,
                            validator_key=validator_key,
                            reason=reason,
                            score=rejection_score,
                        )

                    def _reject_validator_exception(
                        validator_key: str,
                        stage_name: str,
                        exc: Exception,
                        *,
                        rejection_score: float | None = None,
                    ) -> None:
                        error_message = (
                            f"{source}: {stage_name} failed for {sample_identifier}: "
                            f"{type(exc).__name__}: {exc}"
                        )
                        logger.error("autograbber_validator_failed %s", error_message)
                        errors.append(error_message)
                        _reject_sample(
                            validator_key,
                            f"{stage_name}_failed:{type(exc).__name__}",
                            rejection_score=rejection_score,
                        )

                    try:
                        try:
                            structural_valid, structural_reason = self._validate_structural_sample(scraped_sample)
                        except Exception as exc:
                            _reject_validator_exception(
                                "structural",
                                "structural_validation",
                                exc,
                            )
                            continue
                        if not structural_valid:
                            _reject_sample(
                                "structural",
                                structural_reason or "structural_rejected",
                            )
                            continue

                        try:
                            payload = self._scraped_sample_to_payload(scraped_sample)
                        except Exception as exc:
                            _reject_validator_exception(
                                "structural",
                                "payload_normalization",
                                exc,
                            )
                            continue

                        try:
                            purified_payload, purity_result = self._enforce_sample_purity(payload)
                        except Exception as exc:
                            _reject_validator_exception(
                                "purity",
                                "sample_purity_validation",
                                exc,
                            )
                            continue
                        purity_rejected += purity_result.rejected_count
                        if purified_payload is None:
                            rejection_reason = purity_result.first_rejection_reason or "purity_rejected"
                            _reject_sample(
                                "purity",
                                rejection_reason,
                            )
                            continue

                        if isinstance(purified_payload, dict):
                            payload = purified_payload
                        else:
                            payload = SampleQualityScorer._coerce_sample(purified_payload)

                        try:
                            accepted, rejection_reason, score = self._score_sample_quality(
                                payload,
                                quality_scorer,
                            )
                        except Exception as exc:
                            _reject_validator_exception(
                                "quality",
                                "quality_validation",
                                exc,
                            )
                            continue

                        if not accepted:
                            _reject_sample(
                                "quality",
                                rejection_reason or "quality_rejected",
                                rejection_score=score,
                            )
                            continue

                        try:
                            is_duplicate, duplicate_reason = self._check_duplicate_sample(
                                payload,
                                quality_scorer,
                            )
                        except Exception as exc:
                            _reject_validator_exception(
                                "dedup",
                                "dedup_validation",
                                exc,
                                rejection_score=score,
                            )
                            continue
                        if is_duplicate:
                            _reject_sample(
                                "dedup",
                                duplicate_reason or "duplicate_sample",
                                rejection_score=score,
                            )
                            continue

                        ingested_sample = self._payload_to_ingested_sample(payload)
                        try:
                            feature_tensor = self._extract_feature_tensor(ingested_sample)
                        except Exception as exc:
                            logger.warning(
                                "autograbber_feature_extraction_failed source=%s cve_id=%s reason=%s: %s",
                                source,
                                ingested_sample.cve_id,
                                type(exc).__name__,
                                exc,
                            )
                            _reject_sample(
                                "feature",
                                f"feature_extraction_failed:{type(exc).__name__}",
                                rejection_score=score,
                            )
                            continue

                        try:
                            purified_features, purified_labels, feature_purity_result = self._enforce_feature_tensor_purity(
                                ingested_sample,
                                feature_tensor,
                            )
                            purity_rejected += feature_purity_result.rejected_count
                        except AllRowsRejectedError as exc:
                            purity_rejected += exc.result.rejected_count
                            rejection_reason = (
                                exc.result.first_rejection_reason
                                or "feature_tensor_purity_rejected"
                            )
                            logger.warning(
                                "autograbber_feature_purity_rejected source=%s cve_id=%s reasons=%s",
                                source,
                                ingested_sample.cve_id or ingested_sample.sha256_hash,
                                exc.result.rejection_reasons,
                            )
                            _reject_sample(
                                "feature",
                                rejection_reason,
                                rejection_score=score,
                            )
                            continue
                        except Exception as exc:
                            logger.warning(
                                "autograbber_feature_purity_failed source=%s cve_id=%s reason=%s: %s",
                                source,
                                ingested_sample.cve_id or ingested_sample.sha256_hash,
                                type(exc).__name__,
                                exc,
                            )
                            _reject_sample(
                                "feature",
                                f"feature_tensor_purity_failed:{type(exc).__name__}",
                                rejection_score=score,
                            )
                            continue

                        try:
                            self._write_feature_store(
                                ingested_sample,
                                purified_features,
                                purified_labels,
                            )
                        except Exception as exc:
                            logger.warning(
                                "autograbber_feature_store_write_failed source=%s cve_id=%s reason=%s: %s",
                                source,
                                ingested_sample.cve_id or ingested_sample.sha256_hash,
                                type(exc).__name__,
                                exc,
                            )
                            _reject_sample(
                                "feature",
                                f"feature_store_write_failed:{type(exc).__name__}",
                                rejection_score=score,
                            )
                            continue

                        accepted_samples.append(ingested_sample)
                        samples_accepted += 1
                        features_stored += int(feature_purity_result.accepted_count)
                        if self.config.dedup_enabled:
                            try:
                                quality_scorer.record_seen(payload)
                            except Exception as exc:
                                error_message = (
                                    f"{source}: dedup persistence failed for {sample_identifier}: "
                                    f"{type(exc).__name__}: {exc}"
                                )
                                logger.error(
                                    "autograbber_dedup_record_failed %s",
                                    error_message,
                                )
                                errors.append(error_message)
                        self._record_rl_feedback_prediction(ingested_sample, errors)
                    except Exception as exc:
                        samples_rejected += 1
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

            self._persist_previous_severities(errors)
            previous_severities_persisted = True

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
                purity_rejected=purity_rejected,
                validator_rejections=dict(validator_rejections),
                errors=list(errors),
            )
            self._store_result(result)
            return result
        finally:
            dedup_store.close()
            if not previous_severities_persisted:
                self._persist_previous_severities()

    def get_last_cycle_result(self) -> GrabberCycleResult | None:
        with self._results_lock:
            return self._last_cycle_result

    def get_all_results(self) -> list[GrabberCycleResult]:
        with self._results_lock:
            return list(self._results)

    def get_validator_stats(self) -> dict[str, object]:
        with self._results_lock:
            results = list(self._results)
            last_cycle_result = self._last_cycle_result

        aggregated_rejections = self._new_validator_rejections()
        for result in results:
            for validator_key, count in result.validator_rejections.items():
                aggregated_rejections[validator_key] = (
                    aggregated_rejections.get(validator_key, 0) + int(count)
                )

        return {
            "cycles_recorded": len(results),
            "last_cycle_id": last_cycle_result.cycle_id if last_cycle_result is not None else None,
            "samples_accepted": sum(result.samples_accepted for result in results),
            "samples_rejected": sum(result.samples_rejected for result in results),
            "purity_rejected": sum(result.purity_rejected for result in results),
            "validator_rejections": aggregated_rejections,
        }

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
