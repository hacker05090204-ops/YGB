"""Shared models for async ingestion."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from langdetect import DetectorFactory, LangDetectException, detect

from backend.ingestion._integrity import log_module_sha256

logger = logging.getLogger("ygb.ingestion.models")
DetectorFactory.seed = 0
ALLOWED_SEVERITIES = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN"})


@dataclass(frozen=True)
class IngestedSample:
    source: str
    raw_text: str
    url: str
    cve_id: str
    severity: str
    tags: tuple[str, ...]
    ingested_at: datetime
    sha256_hash: str
    token_count: int
    lang: str


def normalize_severity(severity: str) -> str:
    candidate = (severity or "UNKNOWN").strip().upper()
    return candidate if candidate in ALLOWED_SEVERITIES else "UNKNOWN"


def detect_language(raw_text: str) -> str:
    text = raw_text.strip()
    if not text:
        return "en"
    try:
        return detect(text)
    except LangDetectException:
        return "en"


def make_sample(
    source: str,
    raw_text: str,
    url: str,
    cve_id: str,
    severity: str,
    tags: tuple[str, ...] | list[str],
) -> IngestedSample:
    cleaned_text = raw_text.strip()
    digest = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
    return IngestedSample(
        source=source,
        raw_text=cleaned_text,
        url=url,
        cve_id=cve_id or "",
        severity=normalize_severity(severity),
        tags=tuple(tags),
        ingested_at=datetime.now(timezone.utc),
        sha256_hash=digest,
        token_count=len(cleaned_text.split()),
        lang=detect_language(cleaned_text),
    )


def sample_to_dict(sample: IngestedSample) -> dict[str, object]:
    payload = asdict(sample)
    payload["ingested_at"] = sample.ingested_at.isoformat()
    payload["tags"] = list(sample.tags)
    return payload


MODULE_SHA256 = log_module_sha256(__file__, logger, __name__)
