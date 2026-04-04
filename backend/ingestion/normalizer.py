"""Normalization helpers for ingested text."""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import unicodedata
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from os import cpu_count
from pathlib import Path

from backend.ingestion._integrity import log_module_sha256
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
