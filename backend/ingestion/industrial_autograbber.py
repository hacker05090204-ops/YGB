from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Iterable, Sequence

from backend.ingestion.parallel_autograbber import (
    ExpertRoute,
    ParallelAutoGrabber,
    route_vulnerability_text_to_expert,
)

logger = logging.getLogger("ygb.ingestion.industrial_autograbber")
_SOURCE_TRUST_SCORES = {
    "nvd": 1.0,
    "cisa": 0.95,
    "osv": 0.85,
    "github": 0.75,
}


@dataclass(frozen=True)
class RawSample:
    source: str
    cve_id: str
    title: str
    severity: str
    cvss_score: float | None
    description: str
    published_at: str
    has_public_exploit: bool
    raw_hash: str
    fetched_at: str

    def combined_text(self) -> str:
        return " ".join(
            part.strip()
            for part in (self.title, self.description)
            if str(part or "").strip()
        )


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    reason: str
    score: float
    token_count: int
    expert_id: int
    expert_label: str
    normalized_text: str


@dataclass(frozen=True)
class TokenBatch:
    samples: tuple[RawSample, ...]
    token_count: int

    @classmethod
    def build(
        cls,
        samples: Iterable[RawSample],
        *,
        max_tokens: int = 4096,
    ) -> tuple["TokenBatch", ...]:
        batches: list[TokenBatch] = []
        current: list[RawSample] = []
        running_tokens = 0
        for sample in samples:
            sample_tokens = max(1, len(sample.combined_text().split()))
            if current and running_tokens + sample_tokens > max_tokens:
                batches.append(cls(samples=tuple(current), token_count=running_tokens))
                current = []
                running_tokens = 0
            current.append(sample)
            running_tokens += sample_tokens
        if current:
            batches.append(cls(samples=tuple(current), token_count=running_tokens))
        return tuple(batches)


class FilterPipeline:
    """Deterministic 11-stage industrial filter pipeline for raw CVE samples."""

    STAGES: tuple[str, ...] = (
        "identifier",
        "text_normalization",
        "description_length",
        "noise_rejection",
        "deduplication",
        "source_trust",
        "severity_scoring",
        "cvss_scoring",
        "exploit_signal",
        "recency_scoring",
        "expert_routing",
    )

    @staticmethod
    def _normalize_text(sample: RawSample) -> str:
        return " ".join(sample.combined_text().split())

    @staticmethod
    def _require_identifier(sample: RawSample) -> tuple[bool, str]:
        if str(sample.cve_id or "").strip() or str(sample.raw_hash or "").strip():
            return True, "ok"
        return False, "missing_identifier"

    @staticmethod
    def _require_description_length(text: str) -> tuple[bool, str]:
        if len(text) >= 80:
            return True, "ok"
        return False, "description_too_short"

    @staticmethod
    def _reject_noise(text: str) -> tuple[bool, str]:
        lowered = text.lower()
        if any(marker in lowered for marker in ("lorem ipsum", "placeholder", "dummy", "todo")):
            return False, "template_noise"
        return True, "ok"

    @staticmethod
    def _dedup_key(sample: RawSample, normalized_text: str) -> str:
        if str(sample.raw_hash or "").strip():
            return str(sample.raw_hash).strip()
        return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    @staticmethod
    def _source_trust(sample: RawSample) -> float:
        source = str(sample.source or "").strip().lower()
        for key, score in _SOURCE_TRUST_SCORES.items():
            if key in source:
                return float(score)
        return 0.60

    @staticmethod
    def _severity_score(sample: RawSample) -> float:
        severity = str(sample.severity or "").strip().upper()
        mapping = {
            "CRITICAL": 1.0,
            "HIGH": 0.85,
            "MEDIUM": 0.60,
            "LOW": 0.30,
            "INFORMATIONAL": 0.15,
        }
        return mapping.get(severity, 0.45)

    @staticmethod
    def _cvss_score(sample: RawSample) -> float:
        try:
            value = float(sample.cvss_score or 0.0)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(value / 10.0, 1.0))

    @staticmethod
    def _exploit_score(sample: RawSample) -> float:
        return 1.0 if bool(sample.has_public_exploit) else 0.0

    @staticmethod
    def _recency_score(sample: RawSample) -> float:
        published_text = str(sample.published_at or "").strip()
        if not published_text:
            return 0.25
        try:
            published = datetime.fromisoformat(published_text.replace("Z", "+00:00"))
        except ValueError:
            try:
                published = datetime.strptime(published_text[:10], "%Y-%m-%d").replace(tzinfo=UTC)
            except ValueError:
                return 0.25
        age_days = max((datetime.now(UTC) - published.astimezone(UTC)).days, 0)
        if age_days <= 30:
            return 1.0
        if age_days <= 180:
            return 0.8
        if age_days <= 365:
            return 0.6
        if age_days <= 730:
            return 0.4
        return 0.2

    @staticmethod
    def _token_score(token_count: int) -> float:
        if token_count >= 64:
            return 1.0
        if token_count >= 40:
            return 0.8
        if token_count >= 24:
            return 0.6
        if token_count >= 12:
            return 0.4
        return 0.1

    @classmethod
    def run_all(cls, sample: RawSample, dedup_seen: set[str]) -> FilterDecision:
        ok, reason = cls._require_identifier(sample)
        if not ok:
            return FilterDecision(False, reason, 0.0, 0, 0, "general_triage", "")

        normalized_text = cls._normalize_text(sample)
        ok, reason = cls._require_description_length(normalized_text)
        if not ok:
            return FilterDecision(False, reason, 0.0, len(normalized_text.split()), 0, "general_triage", normalized_text)

        ok, reason = cls._reject_noise(normalized_text)
        if not ok:
            return FilterDecision(False, reason, 0.0, len(normalized_text.split()), 0, "general_triage", normalized_text)

        dedup_key = cls._dedup_key(sample, normalized_text)
        if dedup_key in dedup_seen:
            return FilterDecision(False, "duplicate_sample", 0.0, len(normalized_text.split()), 0, "general_triage", normalized_text)
        dedup_seen.add(dedup_key)

        token_count = len(normalized_text.split())
        route: ExpertRoute = route_vulnerability_text_to_expert(
            normalized_text,
            tags=(str(sample.severity or ""),),
            source=sample.source,
        )
        score = (
            0.15 * cls._source_trust(sample)
            + 0.20 * cls._severity_score(sample)
            + 0.20 * cls._cvss_score(sample)
            + 0.20 * cls._exploit_score(sample)
            + 0.10 * cls._recency_score(sample)
            + 0.15 * cls._token_score(token_count)
        )
        accepted = token_count >= 12 and score >= 0.55
        return FilterDecision(
            accepted=accepted,
            reason="accepted" if accepted else "quality_threshold",
            score=float(round(score, 4)),
            token_count=token_count,
            expert_id=int(route.expert_id),
            expert_label=str(route.expert_label),
            normalized_text=normalized_text,
        )


class IndustrialAutoGrabber(ParallelAutoGrabber):
    """Async source-fetching wrapper around the production parallel autograbber."""

    async def _fetch_source_async(self, scraper_type, per_source_limit: int):
        return await asyncio.to_thread(
            self._fetch_scraper_results,
            scraper_type,
            per_source_limit,
        )

    async def _fetch_all_sources(self, per_source_limit: int):
        tasks = [
            self._fetch_source_async(scraper_type, per_source_limit)
            for scraper_type in self._scraper_types
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ordered_results: list[tuple[str, object] | None] = [None] * len(self._scraper_types)
        for index, result in enumerate(results):
            scraper_type = self._scraper_types[index]
            source_name = str(getattr(scraper_type, "SOURCE", scraper_type.__name__)).strip().lower()
            if isinstance(result, Exception):
                ordered_results[index] = (source_name, result)
            else:
                ordered_results[index] = result
        return [result for result in ordered_results if result is not None]

    def _fetch_all_scraper_results(self, per_source_limit: int):
        if not self._scraper_types:
            return [], False, 1
        worker_count = self._resolve_max_workers()
        loop = asyncio.new_event_loop()
        try:
            return (
                loop.run_until_complete(self._fetch_all_sources(per_source_limit)),
                True,
                worker_count,
            )
        finally:
            loop.close()


__all__ = [
    "FilterDecision",
    "FilterPipeline",
    "IndustrialAutoGrabber",
    "RawSample",
    "TokenBatch",
]
