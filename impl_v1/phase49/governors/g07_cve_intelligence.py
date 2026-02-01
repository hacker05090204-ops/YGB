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

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Dict
import uuid
from datetime import datetime, UTC


class CVESeverity(Enum):
    """CLOSED ENUM - 5 severities (CVSS v3)"""
    CRITICAL = "CRITICAL"  # 9.0-10.0
    HIGH = "HIGH"          # 7.0-8.9
    MEDIUM = "MEDIUM"      # 4.0-6.9
    LOW = "LOW"            # 0.1-3.9
    NONE = "NONE"          # 0.0


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
    affected_products: tuple  # Tuple of product strings
    references: tuple         # Tuple of reference URLs
    published_date: str
    last_modified: str


@dataclass(frozen=True)
class CVEQueryResult:
    """Result of CVE query."""
    query_id: str
    query_term: str
    records: tuple  # Tuple[CVERecord, ...]
    total_count: int
    timestamp: str
    cached: bool


# Local cache (in-memory for governance layer)
_cve_cache: Dict[str, CVERecord] = {}


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
    """Create a CVE record."""
    now = datetime.now(UTC).isoformat()
    
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
    
    # Cache it
    cache_record(record)
    
    return record


def query_cves(
    search_term: str,
    min_score: float = 0.0,
    max_results: int = 50,
) -> CVEQueryResult:
    """
    Query CVE records.
    
    NOTE: This is a mock implementation for governance testing.
    Real implementation would query NVD API.
    """
    matching = []
    
    for cve_id, record in _cve_cache.items():
        if record.cvss_score < min_score:
            continue
        
        # Simple text search
        if search_term.lower() in record.description.lower():
            matching.append(record)
        elif search_term.upper() in cve_id.upper():
            matching.append(record)
        elif any(search_term.lower() in p.lower() for p in record.affected_products):
            matching.append(record)
    
    # Sort by score descending
    matching.sort(key=lambda r: r.cvss_score, reverse=True)
    
    # Limit results
    matching = matching[:max_results]
    
    return CVEQueryResult(
        query_id=f"QRY-{uuid.uuid4().hex[:16].upper()}",
        query_term=search_term,
        records=tuple(matching),
        total_count=len(matching),
        timestamp=datetime.now(UTC).isoformat(),
        cached=True,
    )


def correlate_target(
    target_name: str,
    products: List[str],
) -> CVEQueryResult:
    """
    Correlate target with CVE database.
    
    Returns relevant CVEs for the target.
    """
    all_matches = []
    
    for product in products:
        result = query_cves(product)
        all_matches.extend(result.records)
    
    # Also search target name
    name_result = query_cves(target_name)
    all_matches.extend(name_result.records)
    
    # Dedupe
    seen = set()
    unique = []
    for record in all_matches:
        if record.cve_id not in seen:
            seen.add(record.cve_id)
            unique.append(record)
    
    # Sort by severity
    unique.sort(key=lambda r: r.cvss_score, reverse=True)
    
    return CVEQueryResult(
        query_id=f"COR-{uuid.uuid4().hex[:16].upper()}",
        query_term=f"target:{target_name}",
        records=tuple(unique[:50]),
        total_count=len(unique),
        timestamp=datetime.now(UTC).isoformat(),
        cached=True,
    )
