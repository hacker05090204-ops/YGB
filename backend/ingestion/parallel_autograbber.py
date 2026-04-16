"""Industrial parallel autograbber for Phase 8 ingestion."""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import backend.ingestion.autograbber as autograbber_module
from backend.cve.bridge_ingestion_worker import get_bridge_worker
from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.autograbber import (
    AutoGrabber,
    AutoGrabberConfig,
    GrabberCycleResult,
    RealBackendNotConfiguredError,
    VALIDATOR_REJECTION_KEYS,
)
from backend.ingestion.dedup import DedupIndex
from backend.ingestion.models import IngestedSample
from backend.ingestion.normalizer import QualityRejectionLog, SampleQualityScorer
from backend.ingestion.scrapers import BaseScraper, ScrapedSample
from backend.training.data_purity import AllRowsRejectedError

logger = logging.getLogger("ygb.ingestion.parallel_autograbber")

DEFAULT_SOURCE_NAMES = list(autograbber_module.DEFAULT_SOURCE_NAMES)
SCRAPER_TYPES_BY_SOURCE: dict[str, type[BaseScraper]] = dict(
    autograbber_module.SCRAPER_TYPES_BY_SOURCE
)


@dataclass(frozen=True)
class ParallelAutoGrabberConfig(AutoGrabberConfig):
    """Phase 8 autograbber configuration with explicit fetch parallelism."""

    max_workers: int | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.max_workers is not None and int(self.max_workers) <= 0:
            raise ValueError("max_workers must be greater than zero when provided")


@dataclass(frozen=True)
class ExpertRoute:
    """Resolved expert route for an accepted vulnerability sample."""

    expert_id: int
    expert_label: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationFailure:
    """Observable validation failure for Phase 8 result reporting."""

    source: str
    sample_identifier: str
    validator_key: str
    reason: str
    score: float | None = None


@dataclass(frozen=True)
class ParallelGrabberCycleResult(GrabberCycleResult):
    """Cycle result with Phase 8 routing and failure visibility."""

    parallel_fetch_used: bool = False
    fetch_worker_count: int = 0
    expert_route_counts: dict[int, int] = field(default_factory=dict)
    expert_routes: dict[str, int] = field(default_factory=dict)
    source_failures: dict[str, str] = field(default_factory=dict)
    validation_failures: tuple[ValidationFailure, ...] = field(default_factory=tuple)


_EXPERT_SIGNAL_GROUPS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        1,
        "database_injection",
        (
            "sql injection",
            "sqli",
            "union select",
            "blind sql",
            "sql syntax",
            "database error",
            "cwe-89",
        ),
    ),
    (
        2,
        "cross_site_scripting",
        (
            "cross site scripting",
            "xss",
            "script injection",
            "dom-based xss",
        ),
    ),
    (
        3,
        "remote_code_execution",
        (
            "remote code execution",
            "rce",
            "command injection",
            "arbitrary code execution",
        ),
    ),
    (
        4,
        "auth_bypass",
        (
            "authentication bypass",
            "authorization bypass",
            "auth bypass",
            "account takeover",
        ),
    ),
    (
        5,
        "server_side_request_forgery",
        (
            "server-side request forgery",
            "server side request forgery",
            "ssrf",
        ),
    ),
    (
        6,
        "csrf",
        (
            "cross-site request forgery",
            "cross site request forgery",
            "csrf",
        ),
    ),
    (
        7,
        "file_upload",
        (
            "file upload",
            "multipart upload",
            "unrestricted upload",
        ),
    ),
    (
        8,
        "graphql_abuse",
        (
            "graphql",
            "introspection",
            "resolver abuse",
        ),
    ),
    (
        9,
        "cloud_misconfig",
        (
            "aws",
            "azure",
            "gcp",
            "cloud misconfig",
            "storage bucket",
        ),
    ),
    (
        10,
        "mobile",
        (
            "android",
            "ios",
            "mobile",
            "apk",
        ),
    ),
)
_DEFAULT_EXPERT_ROUTE = ExpertRoute(
    expert_id=0,
    expert_label="general_triage",
    reasons=("default_general_triage",),
)


class FieldRouter:
    """Expert routing based on CVE content analysis with 23-expert field mapping."""

    ROUTING_KEYWORDS: dict[int, tuple[str, ...]] = {
        0: ("general", "triage", "unknown", "unclassified"),
        1: ("sql injection", "sqli", "union select", "blind sql", "database error", "cwe-89"),
        2: ("cross site scripting", "xss", "script injection", "dom-based xss", "stored xss", "reflected xss"),
        3: ("remote code execution", "rce", "command injection", "arbitrary code execution", "code exec"),
        4: ("authentication bypass", "authorization bypass", "auth bypass", "account takeover", "privilege escalation"),
        5: ("server-side request forgery", "server side request forgery", "ssrf"),
        6: ("cross-site request forgery", "cross site request forgery", "csrf", "xsrf"),
        7: ("file upload", "multipart upload", "unrestricted upload", "arbitrary file upload"),
        8: ("graphql", "introspection", "resolver abuse", "graphql injection"),
        9: ("aws", "azure", "gcp", "cloud misconfig", "storage bucket", "s3 bucket", "cloud storage"),
        10: ("android", "ios", "mobile", "apk", "mobile app", "mobile application"),
        11: ("idor", "insecure direct object reference", "object reference"),
        12: ("deserialization", "unsafe deserialization", "pickle", "yaml deserialization"),
        13: ("rest", "rest api", "api endpoint", "api abuse"),
        14: ("web application", "web app", "web vulnerability", "http"),
        15: ("api testing", "api security", "api vulnerability"),
        16: ("blockchain", "smart contract", "cryptocurrency", "ethereum", "solidity"),
        17: ("iot", "internet of things", "embedded device", "iot device"),
        18: ("hardware", "hardware vulnerability", "physical access"),
        19: ("firmware", "firmware vulnerability", "embedded firmware"),
        20: ("cryptography", "encryption", "weak cipher", "crypto", "hash collision"),
        21: ("subdomain takeover", "subdomain", "dns takeover", "cname"),
        22: ("race condition", "time-of-check", "toctou", "concurrent access"),
    }

    @classmethod
    def route(cls, sample: dict[str, object]) -> int:
        """Route sample to expert_id (0-22) based on CVE content."""
        description = str(sample.get("description", "") or "").lower()
        title = str(sample.get("title", "") or "").lower()
        tags = sample.get("tags", [])
        
        haystack = " ".join([
            description,
            title,
            " ".join(str(tag).lower() for tag in (tags if isinstance(tags, (list, tuple)) else []))
        ])
        
        if not haystack.strip():
            return 0
        
        best_expert = 0
        best_score = 0
        
        for expert_id, keywords in cls.ROUTING_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in haystack)
            if score > best_score:
                best_score = score
                best_expert = expert_id
        
        return best_expert


def route_vulnerability_text_to_expert(
    text: str,
    *,
    tags: Sequence[str] | None = None,
    source: str = "",
) -> ExpertRoute:
    """Route vulnerability text to a deterministic Phase 8 expert id."""

    haystack = " ".join(
        part
        for part in (
            str(text or ""),
            " ".join(str(tag or "") for tag in (tags or ())),
            str(source or ""),
        )
        if str(part or "").strip()
    ).lower()
    if not haystack:
        return _DEFAULT_EXPERT_ROUTE

    best_route = _DEFAULT_EXPERT_ROUTE
    best_score = 0
    for expert_id, expert_label, signals in _EXPERT_SIGNAL_GROUPS:
        matches = tuple(signal for signal in signals if signal in haystack)
        if len(matches) <= best_score:
            continue
        best_route = ExpertRoute(
            expert_id=expert_id,
            expert_label=expert_label,
            reasons=matches,
        )
        best_score = len(matches)
    return best_route


class ParallelAutoGrabber(AutoGrabber):
    """Parallel Phase 8 autograbber with observable routing and failures."""

    def __init__(
        self,
        config: ParallelAutoGrabberConfig | AutoGrabberConfig | None = None,
        *,
        sources: Sequence[str] | None = None,
        cycle_interval_seconds: int = 3600,
        quality_threshold: float = 0.4,
        max_per_cycle: int = 500,
        dedup_enabled: bool = True,
        max_workers: int | None = None,
    ) -> None:
        if config is None:
            resolved_config = ParallelAutoGrabberConfig(
                sources=list(sources or ["nvd"]),
                cycle_interval_seconds=cycle_interval_seconds,
                quality_threshold=quality_threshold,
                max_per_cycle=max_per_cycle,
                dedup_enabled=dedup_enabled,
                max_workers=max_workers,
            )
        else:
            resolved_config = self._coerce_parallel_config(config)
            if max_workers is not None and resolved_config.max_workers != max_workers:
                resolved_config = ParallelAutoGrabberConfig(
                    sources=list(resolved_config.sources),
                    cycle_interval_seconds=resolved_config.cycle_interval_seconds,
                    quality_threshold=resolved_config.quality_threshold,
                    max_per_cycle=resolved_config.max_per_cycle,
                    dedup_enabled=resolved_config.dedup_enabled,
                    max_workers=max_workers,
                )
        super().__init__(resolved_config)
        self.config: ParallelAutoGrabberConfig = resolved_config

    @staticmethod
    def _coerce_parallel_config(
        config: ParallelAutoGrabberConfig | AutoGrabberConfig,
    ) -> ParallelAutoGrabberConfig:
        if isinstance(config, ParallelAutoGrabberConfig):
            return config
        return ParallelAutoGrabberConfig(
            sources=list(config.sources),
            cycle_interval_seconds=config.cycle_interval_seconds,
            quality_threshold=config.quality_threshold,
            max_per_cycle=config.max_per_cycle,
            dedup_enabled=config.dedup_enabled,
        )

    @staticmethod
    def _available_scraper_types() -> dict[str, type[BaseScraper]]:
        return dict(SCRAPER_TYPES_BY_SOURCE)

    def _resolve_max_workers(self) -> int:
        configured = self.config.max_workers
        if configured is not None:
            return max(1, min(int(configured), max(len(self._scraper_types), 1)))
        if not self._scraper_types:
            return 1
        cpu_bound_cap = max((os.cpu_count() or 1) * 2, 1)
        return max(1, min(len(self._scraper_types), cpu_bound_cap))

    def route_sample_to_expert(
        self,
        sample: Mapping[str, object] | ScrapedSample | IngestedSample,
    ) -> ExpertRoute:
        if isinstance(sample, ScrapedSample):
            text = sample.render_text()
            tags = tuple(sample.tags) + tuple(sample.aliases)
            source = sample.source
        elif isinstance(sample, IngestedSample):
            text = sample.raw_text
            tags = sample.tags
            source = sample.source
        elif isinstance(sample, Mapping):
            text = str(sample.get("description") or sample.get("raw_text") or "")
            raw_tags = sample.get("tags") or sample.get("aliases") or ()
            tags = tuple(str(tag or "") for tag in raw_tags) if isinstance(raw_tags, Sequence) else ()
            source = str(sample.get("source") or sample.get("source_id") or "")
        else:
            raise TypeError("route_sample_to_expert() requires a mapping or sample model")
        return route_vulnerability_text_to_expert(text, tags=tags, source=source)

    def _fetch_all_scraper_results(
        self,
        per_source_limit: int,
    ) -> tuple[list[tuple[str, object]], bool, int]:
        if not self._scraper_types:
            return [], False, 0

        worker_count = self._resolve_max_workers()
        if worker_count <= 1 or len(self._scraper_types) <= 1:
            return (
                [
                    self._fetch_scraper_results(scraper_type, per_source_limit)
                    for scraper_type in self._scraper_types
                ],
                False,
                1,
            )

        ordered_results: list[tuple[str, object] | None] = [None] * len(self._scraper_types)
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="parallel-autograbber",
        ) as executor:
            future_map = {
                executor.submit(self._fetch_scraper_results, scraper_type, per_source_limit): index
                for index, scraper_type in enumerate(self._scraper_types)
            }
            for future in as_completed(future_map):
                index = future_map[future]
                scraper_type = self._scraper_types[index]
                source_name = str(
                    getattr(scraper_type, "SOURCE", scraper_type.__name__)
                ).strip().lower()
                try:
                    ordered_results[index] = future.result()
                except Exception as exc:  # pragma: no cover - defensive outer future guard
                    ordered_results[index] = (source_name, exc)

        return (
            [result for result in ordered_results if result is not None],
            True,
            worker_count,
        )

    def run_cycle(self) -> ParallelGrabberCycleResult:
        cycle_id = self._next_cycle_id()
        started_at = datetime.now(timezone.utc).isoformat()
        errors: list[str] = []
        source_failures: dict[str, str] = {}
        validation_failures: list[ValidationFailure] = []
        expert_route_counts: dict[int, int] = {}
        expert_routes: dict[str, int] = {}
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
        parallel_fetch_used = False
        fetch_worker_count = 0

        dedup_store = DedupIndex(self._dedup_path)
        quality_scorer = SampleQualityScorer(
            dedup_store=dedup_store,
            rejection_log=QualityRejectionLog(),
        )
        previous_shard_names = tuple(self._feature_store.list_shards())

        try:
            per_source_limit = self.config.max_per_cycle // len(self._scraper_types)
            fetched_results, parallel_fetch_used, fetch_worker_count = self._fetch_all_scraper_results(
                per_source_limit
            )
            for source, fetch_result in fetched_results:
                sources_attempted += 1
                if isinstance(fetch_result, Exception):
                    error_message = f"{source}: fetch failed: {type(fetch_result).__name__}: {fetch_result}"
                    logger.error("parallel_autograbber_fetch_failed %s", error_message)
                    errors.append(error_message)
                    source_failures[source] = error_message
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
                    logger.error("parallel_autograbber_rl_feedback_failed %s", error_message)
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
                        validation_failures.append(
                            ValidationFailure(
                                source=source,
                                sample_identifier=sample_identifier,
                                validator_key=validator_key,
                                reason=reason,
                                score=rejection_score,
                            )
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
                        logger.error("parallel_autograbber_validator_failed %s", error_message)
                        errors.append(error_message)
                        _reject_sample(
                            validator_key,
                            f"{stage_name}_failed:{type(exc).__name__}",
                            rejection_score=rejection_score,
                        )

                    try:
                        try:
                            structural_valid, structural_reason = self._validate_structural_sample(
                                scraped_sample
                            )
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
                            rejection_reason = (
                                purity_result.first_rejection_reason or "purity_rejected"
                            )
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
                                "parallel_autograbber_feature_extraction_failed source=%s cve_id=%s reason=%s: %s",
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
                                "parallel_autograbber_feature_purity_rejected source=%s cve_id=%s reasons=%s",
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
                                "parallel_autograbber_feature_purity_failed source=%s cve_id=%s reason=%s: %s",
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
                                "parallel_autograbber_feature_store_write_failed source=%s cve_id=%s reason=%s: %s",
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

                        route = self.route_sample_to_expert(ingested_sample)
                        route_key = ingested_sample.cve_id or ingested_sample.sha256_hash
                        expert_routes[route_key] = route.expert_id
                        expert_route_counts[route.expert_id] = (
                            expert_route_counts.get(route.expert_id, 0) + 1
                        )
                        logger.info(
                            "parallel_autograbber_sample_routed source=%s sample=%s expert_id=%s expert_label=%s reasons=%s",
                            source,
                            route_key,
                            route.expert_id,
                            route.expert_label,
                            list(route.reasons),
                        )

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
                                    "parallel_autograbber_dedup_record_failed %s",
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
                        logger.error("parallel_autograbber_sample_processing_failed %s", error_message)
                        errors.append(error_message)
                sources_succeeded += 1

            self._run_adaptive_learning_hook(
                cycle_id=cycle_id,
                accepted_samples=accepted_samples,
                previous_shard_names=previous_shard_names,
                errors=errors,
            )

            if accepted_samples:
                bridge_worker = get_bridge_worker()
                if not bridge_worker.is_bridge_loaded:
                    raise RealBackendNotConfiguredError(
                        "Bridge ingestion backend is not configured; accepted samples cannot be published."
                    )
                try:
                    bridge_published = int(
                        bridge_worker.publish_ingestion_samples(accepted_samples)
                    )
                except Exception as exc:
                    bridge_published = 0
                    error_message = f"bridge publish failed: {type(exc).__name__}: {exc}"
                    logger.critical(
                        "parallel_autograbber_bridge_publish_failed %s",
                        error_message,
                    )
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

            result = ParallelGrabberCycleResult(
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
                parallel_fetch_used=parallel_fetch_used,
                fetch_worker_count=fetch_worker_count,
                expert_route_counts=dict(expert_route_counts),
                expert_routes=dict(expert_routes),
                source_failures=dict(source_failures),
                validation_failures=tuple(validation_failures),
            )
            self._store_result(result)
            return result
        finally:
            dedup_store.close()
            if not previous_severities_persisted:
                self._persist_previous_severities()

    def get_last_cycle_result(self) -> ParallelGrabberCycleResult | None:
        result = super().get_last_cycle_result()
        return result if isinstance(result, ParallelGrabberCycleResult) else None

    def get_all_results(self) -> list[ParallelGrabberCycleResult]:
        return [
            result
            for result in super().get_all_results()
            if isinstance(result, ParallelGrabberCycleResult)
        ]


_parallel_grabber: ParallelAutoGrabber | None = None


def get_parallel_autograbber() -> ParallelAutoGrabber:
    """Return the configured Phase 8 parallel autograbber singleton."""

    if _parallel_grabber is None:
        raise RealBackendNotConfiguredError(
            "ParallelAutoGrabber is not initialized. Call initialize_parallel_autograbber() first."
        )
    return _parallel_grabber


def initialize_parallel_autograbber(
    config: ParallelAutoGrabberConfig | AutoGrabberConfig,
) -> ParallelAutoGrabber:
    """Initialize the Phase 8 parallel autograbber singleton."""

    global _parallel_grabber
    if _parallel_grabber is not None:
        _parallel_grabber.stop()
    _parallel_grabber = ParallelAutoGrabber(config)
    return _parallel_grabber


def phase8_smoke_gate(
    config: ParallelAutoGrabberConfig | AutoGrabberConfig | None = None,
) -> dict[str, object]:
    """Minimal Phase 8 smoke gate for routing and initialization."""

    route = route_vulnerability_text_to_expert(
        "Union-based SQL injection in login endpoint allows authentication bypass and database access."
    )
    grabber = ParallelAutoGrabber(
        config or ParallelAutoGrabberConfig(sources=["nvd"], max_per_cycle=1, max_workers=1)
    )
    return {
        "sql_injection_expert_id": route.expert_id,
        "sql_injection_expert_label": route.expert_label,
        "initialized": isinstance(grabber, ParallelAutoGrabber),
        "parallel_sources": list(grabber.config.sources),
        "max_workers": grabber._resolve_max_workers(),
    }


__all__ = [
    "DEFAULT_SOURCE_NAMES",
    "ExpertRoute",
    "FieldRouter",
    "ParallelAutoGrabber",
    "ParallelAutoGrabberConfig",
    "ParallelGrabberCycleResult",
    "SCRAPER_TYPES_BY_SOURCE",
    "ValidationFailure",
    "get_parallel_autograbber",
    "initialize_parallel_autograbber",
    "phase8_smoke_gate",
    "route_vulnerability_text_to_expert",
]


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
