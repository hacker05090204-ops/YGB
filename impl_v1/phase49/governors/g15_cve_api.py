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
from typing import Any, Callable, Dict, List, Mapping, Optional, Protocol, Sequence, Tuple
import json
import os
from datetime import datetime, UTC, timedelta
import urllib.error
import urllib.parse
import urllib.request
import uuid

# Import from existing CVE module for types
from .g07_cve_intelligence import (
    CVERecord,
    CVESeverity,
    CVEStatus,
    score_to_severity,
    cache_record,
)


class APIStatus(Enum):
    """CLOSED ENUM - 4 statuses"""
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    OFFLINE = "OFFLINE"
    INVALID_KEY = "INVALID_KEY"


class CVESourceAdapterError(RuntimeError):
    """Base error for passive CVE source adapters."""


class CVESourceAuthError(CVESourceAdapterError):
    """Authentication or authorization failure for a real CVE source."""


class CVESourceTransportError(CVESourceAdapterError):
    """Network or availability failure for a real CVE source."""


class CVESourcePayloadError(CVESourceAdapterError):
    """Payload/schema normalization failure for a real CVE source."""


@dataclass(frozen=True)
class CVEAPIConfig:
    """Configuration for CVE API."""
    api_key: str
    base_url: str = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    timeout: int = 30
    cache_ttl_hours: int = 24

    def get(self, key: str, default=None):
        """Dict-style accessor for older tests and status helpers."""
        return getattr(self, key, default)


class CVESourceAdapter(Protocol):
    """Real passive CVE source adapter contract."""

    source_id: str

    def fetch(self, product: str, config: CVEAPIConfig) -> Mapping[str, Any]:
        """Fetch a real passive-source payload for a product query."""


@dataclass(frozen=True)
class RoutedSourcePayload:
    """Router-selected passive source payload."""

    source_id: str
    payload: Mapping[str, Any]
    fetched_at: str
    router_signals: Tuple[str, ...] = tuple()


@dataclass(frozen=True)
class CVEAPIResult:
    """Result from CVE API call."""
    result_id: str
    status: APIStatus
    records: tuple  # Tuple[CVERecord, ...]
    from_cache: bool
    error_message: Optional[str]
    timestamp: str
    source_id: str = ""
    signals: Tuple[str, ...] = tuple()


# CVE API key: MUST be provided via CVE_API_KEY environment variable.
# No hardcoded defaults — fail closed if missing.
DEFAULT_API_KEY = ""

# In-memory cache with TTL
_api_cache: Dict[str, tuple] = {}  # {query: (records, timestamp)}
_default_router: Optional["CVEAPISourceRouter"] = None


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _dedupe_strings(values: Sequence[str]) -> Tuple[str, ...]:
    seen = set()
    ordered: List[str] = []
    for value in values:
        token = str(value or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return tuple(ordered)


class NVDCVEAPIAdapter:
    """Real NVD passive adapter with injectable opener for tests."""

    source_id = "nvd"

    def __init__(self, opener: Optional[Callable[..., Any]] = None):
        self._opener = opener or urllib.request.urlopen

    def fetch(self, product: str, config: CVEAPIConfig) -> Mapping[str, Any]:
        query = urllib.parse.quote(product)
        url = f"{config.base_url}?keywordSearch={query}"
        request = urllib.request.Request(
            url,
            headers={
                "apiKey": config.api_key,
                "User-Agent": "YGB-CVE-Scanner/2.0",
                "Accept": "application/json",
            },
        )

        try:
            response = self._opener(request, timeout=config.timeout)
            payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise CVESourcePayloadError("NVD payload must be a JSON object")
            return payload
        except urllib.error.HTTPError as exc:
            if exc.code == 403:
                raise CVESourceAuthError(f"NVD API HTTP {exc.code}: {exc.reason}") from exc
            raise CVESourceTransportError(
                f"NVD API HTTP {exc.code}: {exc.reason}"
            ) from exc
        except urllib.error.URLError as exc:
            raise CVESourceTransportError(
                f"NVD API connection failed: {exc.reason}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise CVESourcePayloadError(f"NVD API invalid JSON: {exc}") from exc
        except CVESourceAdapterError:
            raise
        except Exception as exc:
            raise CVESourceTransportError(f"NVD API error: {exc}") from exc


class CVEAPISourceRouter:
    """Routes passive CVE lookups through real-source adapters only."""

    def __init__(self, adapters: Optional[Sequence[CVESourceAdapter]] = None):
        self._adapters: Tuple[CVESourceAdapter, ...] = tuple(adapters or (NVDCVEAPIAdapter(),))

    def fetch(self, product: str, config: CVEAPIConfig) -> RoutedSourcePayload:
        if not self._adapters:
            raise CVESourceTransportError("No passive CVE source adapters configured")

        adapter_errors: List[str] = []
        for adapter in self._adapters:
            try:
                payload = adapter.fetch(product, config)
                return RoutedSourcePayload(
                    source_id=adapter.source_id,
                    payload=payload,
                    fetched_at=_utcnow_iso(),
                    router_signals=_dedupe_strings(
                        (
                            f"adapter:{adapter.source_id}",
                            "router:real_source",
                            "mode:passive",
                        )
                    ),
                )
            except CVESourceAuthError:
                raise
            except CVESourceAdapterError as exc:
                adapter_errors.append(f"{adapter.source_id}:{exc}")

        raise CVESourceTransportError("; ".join(adapter_errors))


def get_default_router() -> CVEAPISourceRouter:
    """Get or create the passive-source router singleton."""
    global _default_router
    if _default_router is None:
        _default_router = CVEAPISourceRouter()
    return _default_router


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
        timestamp=_utcnow_iso(),
        source_id="cache",
        signals=("cache:hit", f"records_normalized:{len(records)}"),
    )


def store_in_cache(query: str, records: tuple):
    """Store records in cache."""
    _api_cache[query] = (records, _utcnow_iso())


def _extract_description(cve: Mapping[str, Any]) -> str:
    descriptions = cve.get("descriptions", [])
    if isinstance(descriptions, list):
        for entry in descriptions:
            if str(entry.get("lang", "")).lower() == "en":
                return str(entry.get("value", "") or "")
        if descriptions:
            return str(descriptions[0].get("value", "") or "")
    return ""


def _extract_references(cve: Mapping[str, Any]) -> Tuple[str, ...]:
    references = cve.get("references", [])
    if isinstance(references, dict):
        references = references.get("referenceData", [])

    urls: List[str] = []
    if isinstance(references, list):
        for reference in references:
            url = str(reference.get("url", "") or "").strip()
            if url:
                urls.append(url)
    return _dedupe_strings(urls)


def _extract_affected_products(query: str, cve: Mapping[str, Any]) -> Tuple[str, ...]:
    products: List[str] = []
    configurations = cve.get("configurations", [])
    if isinstance(configurations, list):
        for configuration in configurations:
            nodes = configuration.get("nodes", [])
            if not isinstance(nodes, list):
                continue
            for node in nodes:
                matches = node.get("cpeMatch", [])
                if not isinstance(matches, list):
                    continue
                for match in matches:
                    criteria = str(match.get("criteria", "") or "")
                    parts = criteria.split(":")
                    if len(parts) >= 5:
                        vendor = parts[3].strip()
                        product = parts[4].strip()
                        if vendor and vendor != "*" and product and product != "*":
                            products.append(f"{vendor}/{product}")
                        elif product and product != "*":
                            products.append(product)

    if not products:
        products = [token for token in query.split() if token]
    return _dedupe_strings(products)


def _extract_metric_bundle(cve: Mapping[str, Any]) -> Tuple[float, CVESeverity, Tuple[str, ...]]:
    metrics = cve.get("metrics", {})
    if not isinstance(metrics, dict):
        return 0.0, CVESeverity.NONE, ("metric:none",)

    for metric_key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        metric_entries = metrics.get(metric_key, [])
        if not isinstance(metric_entries, list):
            continue
        for metric_entry in metric_entries:
            cvss_data = metric_entry.get("cvssData", {})
            if not isinstance(cvss_data, dict):
                continue
            base_score = cvss_data.get("baseScore")
            if base_score is None:
                continue
            score = float(base_score)
            return score, score_to_severity(score), (f"metric:{metric_key.lower()}",)

    return 0.0, CVESeverity.NONE, ("metric:none",)


def _normalize_status(raw_status: str) -> CVEStatus:
    value = str(raw_status or "").strip().upper()
    if "REJECT" in value:
        return CVEStatus.REJECTED
    if "MOD" in value:
        return CVEStatus.MODIFIED
    if "AWAIT" in value or "RESERVED" in value:
        return CVEStatus.AWAITING
    return CVEStatus.PUBLISHED


def _normalize_record(
    query: str,
    source_id: str,
    raw_item: Mapping[str, Any],
) -> Tuple[Optional[CVERecord], Tuple[str, ...]]:
    cve = raw_item.get("cve", raw_item)
    if not isinstance(cve, dict):
        return None, ("record:invalid_schema",)

    cve_id = str(cve.get("id") or cve.get("cveId") or "").strip().upper()
    if not cve_id:
        return None, ("record:missing_cve_id",)

    cvss_score, severity, metric_signals = _extract_metric_bundle(cve)
    status = _normalize_status(str(cve.get("vulnStatus") or cve.get("state") or "PUBLISHED"))
    published = str(cve.get("published") or _utcnow_iso())
    last_modified = str(
        cve.get("lastModified") or cve.get("lastModifiedDate") or published
    )

    record = CVERecord(
        cve_id=cve_id,
        description=_extract_description(cve),
        severity=severity,
        cvss_score=cvss_score,
        status=status,
        affected_products=_extract_affected_products(query, cve),
        references=_extract_references(cve),
        published_date=published,
        last_modified=last_modified,
    )
    record_signals = _dedupe_strings(
        (
            f"source:{source_id}",
            f"status:{status.value.lower()}",
            *metric_signals,
        )
    )
    return record, record_signals


def _normalize_router_payload(
    query: str,
    routed_payload: RoutedSourcePayload,
) -> Tuple[Tuple[CVERecord, ...], Tuple[str, ...]]:
    payload = routed_payload.payload
    raw_records = payload.get("vulnerabilities", payload.get("cveRecords", []))
    if not isinstance(raw_records, list):
        raise CVESourcePayloadError("Passive CVE payload did not contain a record list")

    records: List[CVERecord] = []
    signals: List[str] = [
        *routed_payload.router_signals,
        f"query:{query.lower()}",
        f"source:{routed_payload.source_id}",
        f"total_results:{int(payload.get('totalResults', len(raw_records)) or len(raw_records))}",
    ]
    discarded = 0
    for raw_item in raw_records:
        if not isinstance(raw_item, dict):
            discarded += 1
            signals.append("record:invalid_schema")
            continue

        record, record_signals = _normalize_record(query, routed_payload.source_id, raw_item)
        signals.extend(record_signals)
        if record is None:
            discarded += 1
            continue

        records.append(record)
        cache_record(record)

    normalized_records = tuple(records)
    store_in_cache(query, normalized_records)
    signals.extend(
        (
            f"records_normalized:{len(normalized_records)}",
            f"records_discarded:{discarded}",
        )
    )
    return normalized_records, _dedupe_strings(signals)


def fetch_cves_passive(
    product: str,
    config: Optional[CVEAPIConfig] = None,
    source_router: Optional[CVEAPISourceRouter] = None,
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
        source_router: Optional real-source router injection for tests
    
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
                timestamp=_utcnow_iso(),
                source_id="config",
                signals=("config:missing_api_key",),
            )
    
    # Check cache first
    cached = get_from_cache(product, config)
    if cached:
        return cached
    
    router = source_router or get_default_router()

    try:
        routed_payload = router.fetch(product, config)
        records, signals = _normalize_router_payload(product, routed_payload)
        return CVEAPIResult(
            result_id=f"API-{uuid.uuid4().hex[:16].upper()}",
            status=APIStatus.CONNECTED,
            records=records,
            from_cache=False,
            error_message=None,
            timestamp=_utcnow_iso(),
            source_id=routed_payload.source_id,
            signals=signals,
        )
    except CVESourceAuthError as exc:
        status = APIStatus.INVALID_KEY
        error_msg = str(exc)
        signals = ("fetch:auth_error",)
    except CVESourceTransportError as exc:
        status = APIStatus.OFFLINE
        error_msg = str(exc)
        signals = ("fetch:transport_error",)
    except CVESourcePayloadError as exc:
        status = APIStatus.DEGRADED
        error_msg = str(exc)
        signals = ("fetch:payload_error",)
    except Exception as exc:
        status = APIStatus.DEGRADED
        error_msg = f"NVD API error: {exc}"
        signals = ("fetch:unexpected_error",)

    return CVEAPIResult(
        result_id=f"ERR-{uuid.uuid4().hex[:16].upper()}",
        status=status,
        records=tuple(),
        from_cache=False,
        error_message=error_msg,
        timestamp=_utcnow_iso(),
        source_id="nvd",
        signals=signals,
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
