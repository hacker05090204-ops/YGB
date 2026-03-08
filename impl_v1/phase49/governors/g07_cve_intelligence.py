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

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterable, List, Optional
import uuid
from datetime import datetime, UTC

try:
    from backend.cve import get_pipeline as _get_cve_pipeline
except Exception:  # pragma: no cover - backend import may be unavailable in thin envs
    _get_cve_pipeline = None


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


def _query_passive_live(search_term: str, min_score: float) -> List[CVERecord]:
    needle = (search_term or "").strip()
    if len(needle) < 3:
        return []

    try:
        from .g15_cve_api import APIStatus, fetch_cves_passive
    except Exception:
        return []

    try:
        result = fetch_cves_passive(needle)
    except Exception:
        return []

    if result.status not in (APIStatus.CONNECTED, APIStatus.DEGRADED):
        return []

    records: List[CVERecord] = []
    for record in result.records:
        if record.cvss_score < min_score:
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
    3. Passive live NVD lookup via g15, if configured.
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

    live_records = _query_passive_live(search_term, min_score)
    records = _sort_records(live_records, search_term)[:max_results]
    return CVEQueryResult(
        query_id=f"QRY-{uuid.uuid4().hex[:16].upper()}",
        query_term=search_term,
        records=tuple(records),
        total_count=len(records),
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
