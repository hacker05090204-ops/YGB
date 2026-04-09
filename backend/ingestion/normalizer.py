"""Normalization helpers for ingested text."""

from __future__ import annotations

import atexit
import hashlib
import json
import logging
import math
import os
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from html.parser import HTMLParser
from os import cpu_count
from pathlib import Path

from backend.ingestion._integrity import log_module_sha256
from backend.ingestion.dedup import DedupIndex
from backend.ingestion.models import IngestedSample, detect_language
from impl_v1.phase49.governors.g38_self_trained_model import can_ai_execute

logger = logging.getLogger("ygb.ingestion.normalizer")
NORMALIZED_ROOT = Path("data/normalized")
_POOL: ProcessPoolExecutor | None = None
_POOL_DISABLED = False


@dataclass(frozen=True)
class NormalizationReport:
    """Structured normalization reporting for back-pressure visibility."""

    requested: int
    cache_hits: int
    cache_misses: int
    normalized: int
    emitted: int
    used_process_pool: bool
    pool_disabled: bool
    backpressure_applied: bool
    chunk_count: int


@dataclass(frozen=True)
class QualityRejectionEntry:
    """Single append-only quality rejection event."""

    cve_id: str
    reason: str
    score: float
    timestamp: str


class QualityRejectionLog:
    """Bounded append-only quality rejection log."""

    def __init__(self, max_entries: int = 10_000, rotate_to: int = 5_000) -> None:
        self.max_entries = max_entries
        self.rotate_to = rotate_to
        self._entries: list[QualityRejectionEntry] = []

    def append(self, cve_id: str, reason: str, score: float) -> None:
        self._entries.append(
            QualityRejectionEntry(
                cve_id=str(cve_id or ""),
                reason=str(reason),
                score=float(score),
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
        )
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.rotate_to:]

    def entries(self) -> tuple[QualityRejectionEntry, ...]:
        return tuple(self._entries)


class SampleQualityScorer:
    """Deterministic quality scoring and acceptance rules for CVE samples."""

    def __init__(
        self,
        dedup_store: DedupIndex | None = None,
        rejection_log: QualityRejectionLog | None = None,
    ) -> None:
        self.dedup_store = dedup_store or DedupIndex("data/dedup_store.json")
        self.dedup_store.load()
        self.rejection_log = rejection_log or QualityRejectionLog()
        self.accepted = 0
        self.rejected = 0
        self._score_total = 0.0
        self._score_count = 0
        self._rejection_reasons: dict[str, int] = {}
        self.last_rejection_reason: str | None = None
        self.last_score = 0.0
        self.last_text_hash = ""

    @staticmethod
    def compute_text_hash(text: str) -> str:
        return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _coerce_sample(sample: dict[str, object] | IngestedSample) -> dict[str, object]:
        if isinstance(sample, IngestedSample):
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
        return dict(sample)

    @staticmethod
    def _apply_annotations(
        sample: dict[str, object] | IngestedSample,
        payload: dict[str, object],
    ) -> None:
        if isinstance(sample, dict):
            sample.update(payload)

    @staticmethod
    def _extract_text(payload: dict[str, object]) -> str:
        return str(
            payload.get("description")
            or payload.get("raw_text")
            or ""
        )

    @staticmethod
    def _extract_source(payload: dict[str, object]) -> str:
        return str(
            payload.get("source")
            or payload.get("source_id")
            or payload.get("source_tag")
            or ""
        )

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, value))

    @classmethod
    def _source_trust_score(cls, payload: dict[str, object]) -> float:
        source = cls._extract_source(payload).strip().lower()
        if "nvd" in source:
            return 1.0
        if "cisa" in source:
            return 0.95
        if "osv" in source:
            return 0.85
        if "github" in source:
            return 0.75
        return 0.5

    @staticmethod
    def _exploit_info_score(payload: dict[str, object]) -> float:
        exploit_keys = (
            "is_exploited",
            "has_public_exploit",
            "exploit_info",
            "exploit_status",
            "exploit_available",
            "exploit_vector",
        )
        saw_unknown = False
        for key in exploit_keys:
            if key not in payload:
                continue
            value = payload.get(key)
            if isinstance(value, bool):
                return 1.0 if value else 0.0
            if value is None:
                saw_unknown = True
                continue
            if isinstance(value, (list, tuple, set, dict)):
                return 1.0 if len(value) > 0 else 0.0
            text = str(value).strip()
            if not text:
                saw_unknown = True
                continue
            lowered = text.lower()
            if lowered in {"unknown", "unclear", "undetermined", "pending"}:
                saw_unknown = True
                continue
            if lowered in {"none", "no", "false", "absent"}:
                return 0.0
            return 1.0
        tags = payload.get("tags", ())
        if isinstance(tags, (list, tuple, set)):
            lowered_tags = {str(tag).strip().lower() for tag in tags}
            if any("exploit" in tag for tag in lowered_tags):
                return 1.0
        return 0.5 if saw_unknown else 0.0

    @staticmethod
    def _coerce_cvss_score(payload: dict[str, object]) -> float | None:
        raw_score = payload.get("cvss_score")
        if raw_score in (None, ""):
            return None
        try:
            return float(raw_score)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _normalize_severity(cls, payload: dict[str, object]) -> str:
        severity = str(payload.get("severity", "") or "").strip().upper()
        if severity and severity != "UNKNOWN":
            return severity

        cvss_score = cls._coerce_cvss_score(payload)
        if cvss_score is not None:
            if cvss_score >= 9.0:
                return "CRITICAL"
            if cvss_score >= 7.0:
                return "HIGH"
            if cvss_score >= 4.0:
                return "MEDIUM"
            return "LOW"

        return "INFORMATIONAL"

    def score(self, sample: dict[str, object] | IngestedSample) -> float:
        payload = self._coerce_sample(sample)
        text = self._extract_text(payload)
        text_length = len(text)
        if text_length <= 1:
            text_length_score = 0.0
        else:
            text_length_score = self._clamp(
                math.log(text_length) / math.log(2000)
            )
        has_cvss_score = 1.0 if payload.get("cvss_score") not in (None, "") else 0.0
        has_exploit_info = self._exploit_info_score(payload)
        source_trust_score = self._source_trust_score(payload)
        quality_score = (
            text_length_score
            + has_cvss_score
            + has_exploit_info
            + source_trust_score
        ) / 4.0
        payload["quality_score"] = quality_score
        payload["text_hash"] = self.compute_text_hash(text)
        self._apply_annotations(sample, payload)
        return quality_score

    def record_seen(self, sample: dict[str, object] | IngestedSample) -> None:
        payload = self._coerce_sample(sample)
        text_hash = str(
            payload.get("text_hash")
            or self.compute_text_hash(self._extract_text(payload))
        )
        cve_id = str(payload.get("cve_id", "") or "")
        source = self._extract_source(payload)
        self.dedup_store.record_seen(cve_id, text_hash, source=source)

    def evaluate(
        self,
        sample: dict[str, object] | IngestedSample,
        *,
        ignore_duplicates: bool = False,
    ) -> tuple[bool, str | None, float]:
        payload = self._coerce_sample(sample)
        quality_score = self.score(payload)
        payload["severity"] = self._normalize_severity(payload)
        self._apply_annotations(sample, payload)
        self.last_score = quality_score
        self.last_text_hash = str(payload.get("text_hash", "") or "")
        self._score_total += quality_score
        self._score_count += 1

        description = self._extract_text(payload).strip()
        cve_id = str(payload.get("cve_id", "") or "").strip()
        duplicate = False
        duplicate_reason = ""
        if not ignore_duplicates and (cve_id or self.last_text_hash):
            duplicate = self.dedup_store.is_duplicate(cve_id, self.last_text_hash)
            if duplicate:
                duplicate_reason = (
                    "duplicate_cve_id"
                    if self.dedup_store.has_cve_id(cve_id)
                    else "duplicate_text_hash"
                )

        reason: str | None = None
        if not description or len(description) < 50:
            reason = "description_too_short"
        elif not cve_id:
            reason = "missing_cve_id"
        elif quality_score < 0.4:
            reason = "low_quality_score"
        elif duplicate:
            reason = duplicate_reason

        if reason is not None:
            self.rejected += 1
            self._rejection_reasons[reason] = self._rejection_reasons.get(reason, 0) + 1
            self.last_rejection_reason = reason
            self.rejection_log.append(cve_id, reason, quality_score)
            logger.warning(
                "sample_quality_rejected cve_id=%s reason=%s score=%.6f",
                cve_id or "",
                reason,
                quality_score,
            )
            return False, reason, quality_score

        self.accepted += 1
        self.last_rejection_reason = None
        return True, None, quality_score

    def is_acceptable(self, sample: dict[str, object] | IngestedSample) -> bool:
        accepted, _, _ = self.evaluate(sample)
        return accepted

    def get_quality_stats(self) -> dict[str, object]:
        mean_score = self._score_total / self._score_count if self._score_count else 0.0
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "mean_score": mean_score,
            "rejection_reasons": dict(self._rejection_reasons),
        }


_QUALITY_REJECTION_LOG = QualityRejectionLog()
_QUALITY_SCORER: SampleQualityScorer | None = None


def get_quality_scorer() -> SampleQualityScorer:
    global _QUALITY_SCORER
    if _QUALITY_SCORER is None:
        _QUALITY_SCORER = SampleQualityScorer(rejection_log=_QUALITY_REJECTION_LOG)
    return _QUALITY_SCORER


def normalize_sample_with_quality(
    sample: dict[str, object],
    scorer: SampleQualityScorer | None = None,
    ignore_duplicates: bool = False,
) -> tuple[dict[str, object], bool, str | None, float]:
    normalized = dict(sample)
    text = str(
        normalized.get("description")
        or normalized.get("raw_text")
        or ""
    )
    normalized_text = normalize_text(text)
    normalized["description"] = normalized_text
    if "raw_text" in normalized or "description" not in sample:
        normalized["raw_text"] = normalized_text
    normalized["token_count"] = len(normalized_text.split())
    normalized["lang"] = detect_language(normalized_text)
    quality_scorer = scorer or get_quality_scorer()
    accepted, reason, score = quality_scorer.evaluate(
        normalized,
        ignore_duplicates=ignore_duplicates,
    )
    return (
        normalized,
        accepted,
        reason,
        score,
    )


def get_quality_stats() -> dict[str, object]:
    return get_quality_scorer().get_quality_stats()


class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts)


def normalize_text(raw_text: str) -> str:
    stripper = _HTMLStripper()
    stripper.feed(raw_text)
    text = unicodedata.normalize("NFKC", stripper.get_text())
    collapsed = " ".join(text.split())
    tokens = collapsed.split()
    return " ".join(tokens[:512]).strip()


def _normalize_text_worker(raw_text: str) -> str:
    return normalize_text(raw_text)


def _cache_path(sha256_hash: str) -> Path:
    return NORMALIZED_ROOT / f"{sha256_hash}.json"


def _write_cache(sample: IngestedSample) -> None:
    NORMALIZED_ROOT.mkdir(parents=True, exist_ok=True)
    cache_file = _cache_path(sample.sha256_hash)
    payload = {
        "raw_text": sample.raw_text,
        "token_count": sample.token_count,
        "lang": sample.lang,
    }
    cache_file.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _load_cache(sample: IngestedSample) -> IngestedSample | None:
    cache_file = _cache_path(sample.sha256_hash)
    if not cache_file.exists():
        return None
    payload = json.loads(cache_file.read_text(encoding="utf-8"))
    return replace(
        sample,
        raw_text=payload["raw_text"],
        token_count=int(payload["token_count"]),
        lang=str(payload["lang"]),
    )


def _main_module_supports_spawn() -> bool:
    main_module = sys.modules.get("__main__")
    main_file = getattr(main_module, "__file__", "")
    if not main_file:
        return False
    return main_file not in {"<stdin>", "<string>"}


def get_process_pool() -> ProcessPoolExecutor:
    global _POOL
    if _POOL is None:
        workers = min(max(cpu_count() or 1, 1), 8)
        _POOL = ProcessPoolExecutor(max_workers=workers)
    return _POOL


def _shutdown_process_pool() -> None:
    global _POOL
    if _POOL is not None:
        shutdown = getattr(_POOL, "shutdown", None)
        if callable(shutdown):
            shutdown(wait=False, cancel_futures=True)
        _POOL = None


atexit.register(_shutdown_process_pool)


def _normalize_pending(raw_texts: list[str]) -> list[str]:
    global _POOL_DISABLED
    if _POOL_DISABLED or not _main_module_supports_spawn():
        return [normalize_text(raw_text) for raw_text in raw_texts]

    try:
        return list(get_process_pool().map(_normalize_text_worker, raw_texts))
    except (BrokenProcessPool, OSError, PermissionError, RuntimeError, ValueError):
        logger.warning("normalize_process_pool_unavailable", exc_info=True)
        _POOL_DISABLED = True
        _shutdown_process_pool()
        return [normalize_text(raw_text) for raw_text in raw_texts]


def _resolve_batch_limit(batch_limit: int) -> int:
    if batch_limit > 0:
        return batch_limit
    try:
        configured = int(os.environ.get("INGEST_NORMALIZE_BATCH_LIMIT", "250"))
    except ValueError:
        configured = 250
    return max(1, configured)


def normalize_batch_with_report(
    samples: list[IngestedSample],
    batch_limit: int = 0,
    quality_scorer: SampleQualityScorer | None = None,
) -> tuple[list[IngestedSample], NormalizationReport]:
    """Normalize a batch with cache and back-pressure reporting."""
    if not samples:
        return [], NormalizationReport(
            requested=0,
            cache_hits=0,
            cache_misses=0,
            normalized=0,
            emitted=0,
            used_process_pool=False,
            pool_disabled=_POOL_DISABLED,
            backpressure_applied=False,
            chunk_count=0,
        )

    results: list[IngestedSample | None] = [None] * len(samples)
    pending: list[tuple[int, IngestedSample]] = []
    cache_hits = 0
    for index, sample in enumerate(samples):
        cached = _load_cache(sample)
        if cached is None:
            pending.append((index, sample))
        else:
            cache_hits += 1
            results[index] = cached

    batch_size = _resolve_batch_limit(batch_limit)
    chunk_count = 0
    backpressure_applied = len(pending) > batch_size
    used_process_pool = bool(pending) and not _POOL_DISABLED and _main_module_supports_spawn()

    if pending:
        if can_ai_execute()[0]:
            raise RuntimeError("GUARD")

        for start in range(0, len(pending), batch_size):
            chunk = pending[start:start + batch_size]
            chunk_count += 1
            normalized_texts = _normalize_pending(
                [sample.raw_text for _, sample in chunk]
            )
            for (index, sample), normalized_text in zip(chunk, normalized_texts):
                updated = replace(
                    sample,
                    raw_text=normalized_text,
                    token_count=len(normalized_text.split()),
                    lang=detect_language(normalized_text),
                )
                _write_cache(updated)
                results[index] = updated

    normalized_samples = [sample for sample in results if sample is not None]
    if quality_scorer is not None:
        filtered_samples: list[IngestedSample] = []
        for sample in normalized_samples:
            normalized_payload, accepted, _, _ = normalize_sample_with_quality(
                {
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
                },
                scorer=quality_scorer,
            )
            if not accepted:
                continue
            filtered_samples.append(
                replace(
                    sample,
                    raw_text=str(normalized_payload.get("raw_text", sample.raw_text)),
                    token_count=int(normalized_payload.get("token_count", sample.token_count)),
                    lang=str(normalized_payload.get("lang", sample.lang)),
                )
            )
        normalized_samples = filtered_samples
    report = NormalizationReport(
        requested=len(samples),
        cache_hits=cache_hits,
        cache_misses=len(pending),
        normalized=len(pending),
        emitted=len(normalized_samples),
        used_process_pool=used_process_pool and not _POOL_DISABLED,
        pool_disabled=_POOL_DISABLED,
        backpressure_applied=backpressure_applied,
        chunk_count=chunk_count or (1 if pending else 0),
    )
    return normalized_samples, report


def normalize_batch(samples: list[IngestedSample]) -> list[IngestedSample]:
    normalized_samples, _ = normalize_batch_with_report(samples)
    return normalized_samples


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
