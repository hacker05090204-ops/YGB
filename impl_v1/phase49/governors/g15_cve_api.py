# G15: CVE API Integration (Passive Mode)
"""
Real NVD CVE API integration in PASSIVE MODE ONLY.

RULES:
- API key injectable via env/config
- Graceful degradation on failure
- Cache last known CVE data
- CVE used ONLY for:
  - Risk scoring
  - Context
  - Method suggestions

FORBIDDEN:
- Trigger execution
- Trigger browser
- Auto exploit logic
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict
import uuid
import os
from datetime import datetime, UTC, timedelta
import json

# Import from existing CVE module for types
from .g07_cve_intelligence import (
    CVERecord,
    CVEQueryResult,
    CVESeverity,
    CVEStatus,
    score_to_severity,
    cache_record,
    get_cached,
)


class APIStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    INVALID_KEY = "INVALID_KEY"


@dataclass(frozen=True)
class CVEAPIConfig:
    """Configuration for CVE API."""
    api_key: str
    base_url: str = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    timeout: int = 30
    cache_ttl_hours: int = 24


@dataclass(frozen=True)
class CVEAPIResult:
    """Result from CVE API call."""
    result_id: str
    status: APIStatus
    records: tuple  # Tuple[CVERecord, ...]
    from_cache: bool
    error_message: Optional[str]
    timestamp: str


# CVE API key: MUST be provided via CVE_API_KEY environment variable.
# No hardcoded defaults — fail closed if missing.
DEFAULT_API_KEY = ""

# In-memory cache with TTL
_api_cache: Dict[str, tuple] = {}  # {query: (records, timestamp)}


def get_config() -> CVEAPIConfig:
    """Get CVE API configuration from environment. Fails if key missing."""
    api_key = os.environ.get("CVE_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "CVE_API_KEY environment variable required but not set. "
            "Register at https://nvd.nist.gov/developers/request-an-api-key"
        )
    return CVEAPIConfig(
        api_key=api_key,
        base_url=os.environ.get("CVE_API_URL", "https://services.nvd.nist.gov/rest/json/cves/2.0"),
        timeout=int(os.environ.get("CVE_API_TIMEOUT", "30")),
        cache_ttl_hours=int(os.environ.get("CVE_CACHE_TTL", "24")),
    )


def clear_api_cache():
    """Clear API cache (for testing)."""
    _api_cache.clear()


def is_cache_valid(cache_time: str, ttl_hours: int) -> bool:
    """Check if cache entry is still valid."""
    try:
        cached_dt = datetime.fromisoformat(cache_time.replace("Z", "+00:00"))
        now = datetime.now(UTC)
        return (now - cached_dt) < timedelta(hours=ttl_hours)
    except (ValueError, TypeError):
        return False


def get_from_cache(query: str, config: CVEAPIConfig) -> Optional[CVEAPIResult]:
    """Get cached result if valid."""
    if query not in _api_cache:
        return None
    
    records, timestamp = _api_cache[query]
    if not is_cache_valid(timestamp, config.cache_ttl_hours):
        del _api_cache[query]
        return None
    
    return CVEAPIResult(
        result_id=f"CACHE-{uuid.uuid4().hex[:16].upper()}",
        status=APIStatus.CONNECTED,
        records=records,
        from_cache=True,
        error_message=None,
        timestamp=datetime.now(UTC).isoformat(),
    )


def store_in_cache(query: str, records: tuple):
    """Store records in cache."""
    _api_cache[query] = (records, datetime.now(UTC).isoformat())


def fetch_cves_passive(
    product: str,
    config: Optional[CVEAPIConfig] = None,
    _mock_response: Optional[Dict] = None,  # For testing
) -> CVEAPIResult:
    """
    Fetch CVEs from NVD API in PASSIVE MODE.
    
    This function:
    1. Checks cache first
    2. If API fails, gracefully degrades to cached data
    3. NEVER triggers any execution
    
    Args:
        product: Product name to search for
        config: API configuration (uses defaults if None)
        _mock_response: Mock response for testing (internal use)
    
    Returns:
        CVEAPIResult with records or error
    """
    if config is None:
        try:
            config = get_config()
        except RuntimeError as e:
            return CVEAPIResult(
                result_id=f"ERR-{uuid.uuid4().hex[:16].upper()}",
                status=APIStatus.INVALID_KEY,
                records=tuple(),
                from_cache=False,
                error_message=str(e),
                timestamp=datetime.now(UTC).isoformat(),
            )
    
    # Check cache first
    cached = get_from_cache(product, config)
    if cached:
        return cached
    
    # Mock for testing - simulates API response
    if _mock_response is not None:
        return _handle_mock_response(product, _mock_response, config)
    
    # In real implementation, would make HTTP request here
    # For governance testing, return degraded status
    return CVEAPIResult(
        result_id=f"API-{uuid.uuid4().hex[:16].upper()}",
        status=APIStatus.DEGRADED,
        records=tuple(),
        from_cache=False,
        error_message="API call not implemented in governance layer - use mock for testing",
        timestamp=datetime.now(UTC).isoformat(),
    )


def _handle_mock_response(
    query: str,
    mock_response: Dict,
    config: CVEAPIConfig,
) -> CVEAPIResult:
    """Handle mock API response for testing."""
    if mock_response.get("error"):
        return CVEAPIResult(
            result_id=f"ERR-{uuid.uuid4().hex[:16].upper()}",
            status=APIStatus.INVALID_KEY if "key" in mock_response.get("error", "").lower() else APIStatus.OFFLINE,
            records=tuple(),
            from_cache=False,
            error_message=mock_response["error"],
            timestamp=datetime.now(UTC).isoformat(),
        )
    
    # Parse mock CVE records
    records = []
    for cve_data in mock_response.get("vulnerabilities", []):
        cve = cve_data.get("cve", {})
        metrics = cve.get("metrics", {}).get("cvssMetricV31", [{}])[0]
        cvss_data = metrics.get("cvssData", {})
        
        record = CVERecord(
            cve_id=cve.get("id", "UNKNOWN"),
            description=cve.get("descriptions", [{}])[0].get("value", ""),
            severity=score_to_severity(cvss_data.get("baseScore", 0.0)),
            cvss_score=cvss_data.get("baseScore", 0.0),
            status=CVEStatus.PUBLISHED,
            affected_products=tuple(query.split()),
            references=tuple(),
            published_date=cve.get("published", datetime.now(UTC).isoformat()),
            last_modified=cve.get("lastModified", datetime.now(UTC).isoformat()),
        )
        records.append(record)
        cache_record(record)
    
    records_tuple = tuple(records)
    store_in_cache(query, records_tuple)
    
    return CVEAPIResult(
        result_id=f"API-{uuid.uuid4().hex[:16].upper()}",
        status=APIStatus.CONNECTED,
        records=records_tuple,
        from_cache=False,
        error_message=None,
        timestamp=datetime.now(UTC).isoformat(),
    )


def can_cve_trigger_execution() -> tuple:
    """Check if CVE data can trigger execution. Returns (can_trigger, reason)."""
    # CVE data can NEVER trigger execution
    return False, "CVE intelligence is PASSIVE ONLY - used for risk scoring and context only"


def get_risk_context(cve_result: CVEAPIResult) -> Dict:
    """Extract risk context from CVE result for dashboard display."""
    if not cve_result.records:
        return {
            "risk_level": "UNKNOWN",
            "cve_count": 0,
            "critical_count": 0,
            "high_count": 0,
            "context": "No CVE data available",
        }
    
    critical = sum(1 for r in cve_result.records if r.severity == CVESeverity.CRITICAL)
    high = sum(1 for r in cve_result.records if r.severity == CVESeverity.HIGH)
    
    if critical > 0:
        risk = "CRITICAL"
    elif high > 0:
        risk = "HIGH"
    elif len(cve_result.records) > 5:
        risk = "MEDIUM"
    else:
        risk = "LOW"
    
    return {
        "risk_level": risk,
        "cve_count": len(cve_result.records),
        "critical_count": critical,
        "high_count": high,
        "context": f"Found {len(cve_result.records)} CVEs ({critical} critical, {high} high)",
    }
