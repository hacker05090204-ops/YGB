# G07: CVE Intelligence
"""
READ-ONLY CVE/NVD intelligence integration.

STRICT RULE: CVE data NEVER triggers execution.
Used for:
- Target intelligence
- Risk scoring
- Method suggestion

NOT used for:
- Auto-exploitation
- Direct action triggering
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import json
import re
import time
from datetime import datetime, UTC
from typing import Any, Callable, Dict, Iterable, List, Optional
import uuid

try:
    from backend.cve import get_pipeline as _get_cve_pipeline
except Exception:  # pragma: no cover - backend import may be unavailable in thin envs
    _get_cve_pipeline = None

try:
    from backend.bridge.bridge_state import get_bridge_state as _get_bridge_state
except Exception:  # pragma: no cover - bridge import may be unavailable in thin envs
    _get_bridge_state = None


class CVESeverity(Enum):
    """CLOSED ENUM - 5 severities (CVSS v3)"""

    CRITICAL = "CRITICAL"  # 9.0-10.0
    HIGH = "HIGH"  # 7.0-8.9
    MEDIUM = "MEDIUM"  # 4.0-6.9
    LOW = "LOW"  # 0.1-3.9
    NONE = "NONE"  # 0.0


class CVEStatus(Enum):
    """CLOSED ENUM - 4 statuses"""

    PUBLISHED = "PUBLISHED"
    MODIFIED = "MODIFIED"
    REJECTED = "REJECTED"
    AWAITING = "AWAITING"


@dataclass(frozen=True)
class CVERecord:
    """Immutable CVE record."""

    cve_id: str
    description: str
    severity: CVESeverity
    cvss_score: float
    status: CVEStatus
    affected_products: tuple
    references: tuple
    published_date: str
    last_modified: str


@dataclass(frozen=True)
class CVEQueryResult:
    """Result of CVE query."""

    query_id: str
    query_term: str
    records: tuple
    total_count: int
    timestamp: str
    cached: bool


@dataclass(frozen=True)
class CVEIntelligenceRecord:
    """Local CVE enrichment sourced only from ingested runtime state."""

    cve_id: str
    severity_score: float
    affected_products: list[str]
    published_at: str
    intelligence_source: str
    has_public_exploit: bool


@dataclass(frozen=True)
class _IntelligenceCacheEntry:
    record: CVEIntelligenceRecord
    expires_at: float


class IntelligenceCache:
    """TTL cache for local CVE intelligence lookups."""

    def __init__(
        self,
        ttl_seconds: int = 24 * 60 * 60,
        max_entries: int = 10_000,
        time_fn: Optional[Callable[[], float]] = None,
    ):
        self.ttl_seconds = int(ttl_seconds)
        self.max_entries = int(max_entries)
        self._time_fn = time_fn or time.time
        self._entries: OrderedDict[str, _IntelligenceCacheEntry] = OrderedDict()

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self):
        self._entries.clear()

    def get(self, cve_id: str) -> CVEIntelligenceRecord | None:
        now = self._time_fn()
        self._purge_expired(now)
        key = str(cve_id or "").strip().upper()
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            self._entries.pop(key, None)
            return None
        return entry.record

    def set(self, cve_id: str, record: CVEIntelligenceRecord):
        key = str(cve_id or "").strip().upper()
        if not key:
            return
        now = self._time_fn()
        self._purge_expired(now)
        self._entries.pop(key, None)
        self._entries[key] = _IntelligenceCacheEntry(
            record=record,
            expires_at=now + self.ttl_seconds,
        )
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def _purge_expired(self, now: float):
        expired_keys = [
            key for key, entry in self._entries.items() if entry.expires_at <= now
        ]
        for key in expired_keys:
            self._entries.pop(key, None)


_CVSS_SCORE_RE = re.compile(r"CVSS:(?P<score>[0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)


_cve_cache: Dict[str, CVERecord] = {}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def clear_cache():
    """Clear CVE cache (for testing)."""

    _cve_cache.clear()


def cache_record(record: CVERecord):
    """Add record to cache."""

    _cve_cache[record.cve_id] = record


def get_cached(cve_id: str) -> Optional[CVERecord]:
    """Get record from cache."""

    return _cve_cache.get(cve_id)


def score_to_severity(score: float) -> CVESeverity:
    """Convert CVSS score to severity."""

    if score >= 9.0:
        return CVESeverity.CRITICAL
    if score >= 7.0:
        return CVESeverity.HIGH
    if score >= 4.0:
        return CVESeverity.MEDIUM
    if score > 0:
        return CVESeverity.LOW
    return CVESeverity.NONE


def create_cve_record(
    cve_id: str,
    description: str,
    cvss_score: float,
    affected_products: List[str],
    references: Optional[List[str]] = None,
    status: CVEStatus = CVEStatus.PUBLISHED,
) -> CVERecord:
    """Create and locally cache a CVE record."""

    now = _now_iso()
    record = CVERecord(
        cve_id=cve_id,
        description=description,
        severity=score_to_severity(cvss_score),
        cvss_score=cvss_score,
        status=status,
        affected_products=tuple(affected_products),
        references=tuple(references or []),
        published_date=now,
        last_modified=now,
    )
    cache_record(record)
    return record


def _iter_local_matches(search_term: str, min_score: float) -> Iterable[CVERecord]:
    needle = (search_term or "").strip().lower()
    for record in _cve_cache.values():
        if record.cvss_score < min_score:
            continue
        if not needle:
            yield record
            continue
        if needle in record.description.lower():
            yield record
            continue
        if needle in record.cve_id.lower():
            yield record
            continue
        if any(needle in product.lower() for product in record.affected_products):
            yield record


def _pipeline_record_to_cve(record: object) -> Optional[CVERecord]:
    if record is None:
        return None

    cve_id = str(getattr(record, "cve_id", "") or "").strip()
    if not cve_id:
        return None

    cvss_score = float(getattr(record, "cvss_score", 0.0) or 0.0)
    merged_at = str(getattr(record, "merged_at", "") or _now_iso())

    return CVERecord(
        cve_id=cve_id,
        description=str(getattr(record, "description", "") or ""),
        severity=score_to_severity(cvss_score),
        cvss_score=cvss_score,
        status=CVEStatus.MODIFIED if getattr(record, "canonical_version", 1) > 1 else CVEStatus.PUBLISHED,
        affected_products=tuple(getattr(record, "affected_products", []) or ()),
        references=tuple(getattr(record, "references", []) or ()),
        published_date=merged_at,
        last_modified=merged_at,
    )


def _read_field(data: object, key: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        value = data.get(key, default)
    else:
        value = getattr(data, key, default)
    return default if value is None else value


def _as_str_list(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, (list, tuple, set)):
        raw_items = values
    else:
        raw_items = [values]
    items: list[str] = []
    for value in raw_items:
        text = str(value).strip()
        if text:
            items.append(text)
    return items


def _parse_bridge_products(sample: Dict[str, Any]) -> list[str]:
    if "affected_products" in sample:
        return _as_str_list(sample.get("affected_products"))

    raw_parameters = sample.get("parameters", [])
    if isinstance(raw_parameters, str):
        text = raw_parameters.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                decoded = json.loads(text)
            except (TypeError, ValueError):
                decoded = None
            if isinstance(decoded, list):
                return _as_str_list(decoded)
        return [text]

    return _as_str_list(raw_parameters)


def _parse_bridge_score(sample: Dict[str, Any]) -> float:
    for key in ("severity_score", "cvss_score"):
        raw_value = sample.get(key)
        if raw_value in (None, ""):
            continue
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            continue

    impact = str(sample.get("impact", "") or "")
    match = _CVSS_SCORE_RE.search(impact)
    if match:
        try:
            return float(match.group("score"))
        except (TypeError, ValueError):
            return 0.0
    return 0.0


def _parse_bool_flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


class CVEIntelligenceEngine:
    """Local-only CVE enrichment backed by pipeline and bridge state."""

    def __init__(
        self,
        pipeline_getter: Optional[Callable[[], Any]] = _get_cve_pipeline,
        bridge_state_getter: Optional[Callable[[], Any]] = _get_bridge_state,
        cache: Optional[IntelligenceCache] = None,
    ):
        self._pipeline_getter = pipeline_getter
        self._bridge_state_getter = bridge_state_getter
        self._cache = cache if cache is not None else IntelligenceCache()

    def enrich(self, cve_id: str) -> CVEIntelligenceRecord | None:
        normalized_id = str(cve_id or "").strip().upper()
        if not normalized_id:
            return None

        cached = self._cache.get(normalized_id)
        if cached is not None:
            return cached

        record = self._read_from_pipeline(normalized_id)
        if record is None:
            record = self._read_from_bridge_state(normalized_id)
        if record is None:
            return None

        self._cache.set(normalized_id, record)
        return record

    def _read_from_pipeline(self, cve_id: str) -> CVEIntelligenceRecord | None:
        if self._pipeline_getter is None:
            return None

        try:
            pipeline = self._pipeline_getter()
        except Exception:
            return None

        if pipeline is None or not hasattr(pipeline, "get_record"):
            return None

        try:
            record = pipeline.get_record(cve_id)
        except Exception:
            return None
        return self._pipeline_record_to_intelligence(record)

    def _read_from_bridge_state(self, cve_id: str) -> CVEIntelligenceRecord | None:
        if self._bridge_state_getter is None:
            return None

        try:
            bridge_state = self._bridge_state_getter()
        except Exception:
            return None

        if bridge_state is None or not hasattr(bridge_state, "read_samples"):
            return None

        try:
            samples = bridge_state.read_samples()
        except TypeError:
            try:
                samples = bridge_state.read_samples(0)
            except Exception:
                return None
        except Exception:
            return None

        for sample in reversed(list(samples or [])):
            if not isinstance(sample, dict):
                continue
            endpoint = str(sample.get("endpoint", sample.get("cve_id", "")) or "").strip().upper()
            if endpoint != cve_id:
                continue
            return self._bridge_sample_to_intelligence(sample)
        return None

    @staticmethod
    def _pipeline_record_to_intelligence(record: object) -> CVEIntelligenceRecord | None:
        if record is None:
            return None

        cve_id = str(_read_field(record, "cve_id", "") or "").strip().upper()
        if not cve_id:
            return None

        return CVEIntelligenceRecord(
            cve_id=cve_id,
            severity_score=float(_read_field(record, "cvss_score", 0.0) or 0.0),
            affected_products=_as_str_list(_read_field(record, "affected_products", [])),
            published_at=str(
                _read_field(record, "merged_at", "")
                or _read_field(record, "last_modified", "")
                or ""
            ),
            intelligence_source="local_pipeline",
            has_public_exploit=bool(_read_field(record, "is_exploited", False)),
        )

    @staticmethod
    def _bridge_sample_to_intelligence(sample: Dict[str, Any]) -> CVEIntelligenceRecord | None:
        cve_id = str(sample.get("endpoint", sample.get("cve_id", "")) or "").strip().upper()
        if not cve_id:
            return None

        return CVEIntelligenceRecord(
            cve_id=cve_id,
            severity_score=_parse_bridge_score(sample),
            affected_products=_parse_bridge_products(sample),
            published_at=str(
                sample.get("published_at")
                or sample.get("merged_at")
                or sample.get("timestamp")
                or ""
            ),
            intelligence_source="local_pipeline",
            has_public_exploit=_parse_bool_flag(
                sample.get("has_public_exploit", sample.get("is_exploited", False))
            ),
        )


def _query_pipeline(search_term: str, min_score: float) -> List[CVERecord]:
    if _get_cve_pipeline is None:
        return []

    try:
        pipeline = _get_cve_pipeline()
    except Exception:
        return []

    if pipeline is None:
        return []

    cve_ids: List[str] = []
    needle = (search_term or "").strip()
    if needle:
        cve_ids = [entry.get("cve_id", "") for entry in pipeline.search(needle)]
    else:
        cve_ids = [entry.get("cve_id", "") for entry in pipeline.get_records()]

    records: List[CVERecord] = []
    seen = set()
    for cve_id in cve_ids:
        if not cve_id or cve_id in seen:
            continue
        seen.add(cve_id)
        record = _pipeline_record_to_cve(pipeline.get_record(cve_id))
        if record is None or record.cvss_score < min_score:
            continue
        records.append(record)
    return records


def _sort_records(records: Iterable[CVERecord], search_term: str) -> List[CVERecord]:
    needle = (search_term or "").strip().lower()
    unique: Dict[str, CVERecord] = {}
    for record in records:
        existing = unique.get(record.cve_id)
        if existing is None or record.cvss_score > existing.cvss_score:
            unique[record.cve_id] = record

    def rank(record: CVERecord) -> tuple:
        exact = 1 if needle and record.cve_id.lower() == needle else 0
        cve_match = 1 if needle and needle in record.cve_id.lower() else 0
        text_match = 1 if needle and needle in record.description.lower() else 0
        return (
            -exact,
            -cve_match,
            -text_match,
            -record.cvss_score,
            record.cve_id,
        )

    return sorted(unique.values(), key=rank)


def query_cves(
    search_term: str,
    min_score: float = 0.0,
    max_results: int = 50,
) -> CVEQueryResult:
    """
    Query CVE records.

    Resolution order:
    1. Local authoritative cache, when present.
    2. Canonical runtime CVE pipeline.

    No live fetches are issued from this layer.
    """

    local_records = list(_iter_local_matches(search_term, min_score))
    if _cve_cache:
        records = _sort_records(local_records, search_term)[:max_results]
        return CVEQueryResult(
            query_id=f"QRY-{uuid.uuid4().hex[:16].upper()}",
            query_term=search_term,
            records=tuple(records),
            total_count=len(records),
            timestamp=_now_iso(),
            cached=True,
        )

    pipeline_records = _query_pipeline(search_term, min_score)
    if pipeline_records:
        records = _sort_records(pipeline_records, search_term)[:max_results]
        return CVEQueryResult(
            query_id=f"QRY-{uuid.uuid4().hex[:16].upper()}",
            query_term=search_term,
            records=tuple(records),
            total_count=len(records),
            timestamp=_now_iso(),
            cached=False,
        )

    return CVEQueryResult(
        query_id=f"QRY-{uuid.uuid4().hex[:16].upper()}",
        query_term=search_term,
        records=tuple(),
        total_count=0,
        timestamp=_now_iso(),
        cached=False,
    )


def correlate_target(
    target_name: str,
    products: List[str],
) -> CVEQueryResult:
    """Correlate a target against local/runtime CVE intelligence."""

    all_matches: List[CVERecord] = []
    cached = True

    for product in products:
        result = query_cves(product)
        cached = cached and result.cached
        all_matches.extend(result.records)

    name_result = query_cves(target_name)
    cached = cached and name_result.cached
    all_matches.extend(name_result.records)

    records = _sort_records(all_matches, target_name)[:50]
    return CVEQueryResult(
        query_id=f"COR-{uuid.uuid4().hex[:16].upper()}",
        query_term=f"target:{target_name}",
        records=tuple(records),
        total_count=len(records),
        timestamp=_now_iso(),
        cached=cached,
    )
