"""
CVE Pipeline — Multi-Source Canonical CVE Feed with Deterministic Merge

Sources (priority order):
  1. CVE Services / cve.org canonical API (primary)
  2. CVEProject/cvelistV5 mirror (secondary reconciliation)
  3. NVD API v2 (enrichment)
  4. CISA KEV JSON feed (exploited-in-wild flagging)
  5. Vulners (optional, requires API key)
  6. VulDB (optional, requires API key)

Design:
  - Canonical key = cve_id + last_modified + content_hash
  - Deterministic source-priority merge policy with conflict logging
  - Per-source provenance: source, fetched_at, parser_version, confidence
  - Delta/watermark strategy per source (If-Modified-Since / ETag / last_seen)
  - Circuit breaker per source (3 failures → OPEN, 5 min cooldown)
  - NO_DELTA reporting when source has no new data
  - Never reports CONNECTED/ACTIVE if fetch/auth truly fails
"""

import os
import logging
import hashlib
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

logger = logging.getLogger("ygb.cve_pipeline")

PARSER_VERSION = "2.0.0"


# =============================================================================
# DATA MODELS
# =============================================================================

class SourceStatus(Enum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class IngestResult(Enum):
    NEW = "NEW"               # First time seeing this CVE
    UPDATED = "UPDATED"       # CVE existed, merged new data
    NO_DELTA = "NO_DELTA"     # Source had no new data
    DUPLICATE = "DUPLICATE"   # Exact duplicate, skipped
    ERROR = "ERROR"           # Fetch/parse error


class MergePolicy(Enum):
    PRIMARY_WINS = "PRIMARY_WINS"
    MOST_RECENT = "MOST_RECENT"
    HIGHEST_SEVERITY = "HIGHEST_SEVERITY"


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class PromotionStatus(Enum):
    CANONICAL = "CANONICAL"
    CORROBORATED = "CORROBORATED"
    RESEARCH_PENDING = "RESEARCH_PENDING"
    BLOCKED = "BLOCKED"


@dataclass
class SourceProvenance:
    """Provenance metadata per CVE record per source."""
    source: str
    fetched_at: str
    last_modified: str
    confidence: float
    merge_policy: str
    raw_hash: str
    parser_version: str = PARSER_VERSION


@dataclass
class CVERecord:
    """Canonical CVE record with multi-source provenance."""
    cve_id: str
    title: str
    description: str
    severity: str
    cvss_score: Optional[float]
    affected_products: List[str]
    references: List[str]
    is_exploited: bool
    provenance: List[SourceProvenance]
    canonical_version: int
    merged_at: str
    content_hash: str = ""
    promotion_status: str = "RESEARCH_PENDING"
    block_reason: str = ""
    merge_conflicts: List[str] = field(default_factory=list)


@dataclass
class FreshnessSLA:
    """Freshness SLA state for a source."""
    source: str
    last_fetch_at: Optional[str]
    last_success_at: Optional[str]
    staleness_threshold_hours: int
    is_stale: bool
    records_fetched: int
    last_error: Optional[str]
    last_etag: Optional[str] = None
    last_modified_header: Optional[str] = None
    last_seen_timestamp: Optional[str] = None


@dataclass
class CircuitBreaker:
    """Per-source circuit breaker."""
    source_id: str
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    failure_threshold: int = 3
    last_failure_at: Optional[float] = None
    cooldown_seconds: float = 300.0  # 5 min
    half_open_attempts: int = 0

    def record_success(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.half_open_attempts = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_at = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"[CIRCUIT_BREAKER] {self.source_id} → OPEN "
                f"(failures={self.failure_count})"
            )

    def can_attempt(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if self.last_failure_at and (
                time.monotonic() - self.last_failure_at >= self.cooldown_seconds
            ):
                self.state = CircuitState.HALF_OPEN
                self.half_open_attempts = 0
                logger.info(
                    f"[CIRCUIT_BREAKER] {self.source_id} → HALF_OPEN"
                )
                return True
            return False
        # HALF_OPEN: allow 1 attempt
        return self.half_open_attempts < 1


@dataclass
class SLOCounter:
    """SLO tracking counters."""
    total_jobs: int = 0
    successful_jobs: int = 0
    failed_jobs: int = 0
    total_ingests: int = 0
    successful_ingests: int = 0
    no_delta_ingests: int = 0

    @property
    def job_success_rate(self) -> float:
        if self.total_jobs == 0:
            return 1.0
        return self.successful_jobs / self.total_jobs

    @property
    def ingest_success_rate(self) -> float:
        if self.total_ingests == 0:
            return 1.0
        return (self.successful_ingests + self.no_delta_ingests) / self.total_ingests


# =============================================================================
# SOURCE REGISTRY
# =============================================================================

_SOURCE_CONFIGS = {
    "cve_services": {
        "name": "CVE Services / cve.org",
        "url": "https://cveawg.mitre.org/api/cve",
        "requires_key": False,
        "staleness_hours": 6,
        "confidence": 0.98,
        "priority": 1,
        "is_canonical": True,
    },
    "cveproject": {
        "name": "CVEProject/cvelistV5",
        "url": "https://github.com/CVEProject/cvelistV5",
        "requires_key": False,
        "staleness_hours": 24,
        "confidence": 0.95,
        "priority": 2,
        "is_canonical": True,
    },
    "nvd": {
        "name": "NVD API v2",
        "url": "https://services.nvd.nist.gov/rest/json/cves/2.0",
        "requires_key": False,
        "key_env": "NVD_API_KEY",
        "staleness_hours": 6,
        "confidence": 0.90,
        "priority": 3,
        "is_canonical": False,
    },
    "cisa_kev": {
        "name": "CISA KEV Catalog",
        "url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        "requires_key": False,
        "staleness_hours": 24,
        "confidence": 1.0,
        "priority": 4,
        "is_canonical": False,
    },
    "vulners": {
        "name": "Vulners",
        "url": "https://vulners.com/api/v3/",
        "requires_key": True,
        "key_env": "VULNERS_API_KEY",
        "staleness_hours": 12,
        "confidence": 0.80,
        "priority": 5,
        "is_canonical": False,
    },
    "vuldb": {
        "name": "VulDB",
        "url": "https://vuldb.com/api/",
        "requires_key": True,
        "key_env": "VULDB_API_KEY",
        "staleness_hours": 12,
        "confidence": 0.75,
        "priority": 6,
        "is_canonical": False,
    },
}


def compute_content_hash(cve_id: str, description: str, severity: str,
                         cvss_score: Optional[float]) -> str:
    """Deterministic content hash for dedup."""
    raw = f"{cve_id}|{description}|{severity}|{cvss_score or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# =============================================================================
# CVE PIPELINE
# =============================================================================

class CVEPipeline:
    """Multi-source CVE feed with deterministic merge and truthful status."""

    def __init__(self):
        self._records: Dict[str, CVERecord] = {}
        self._freshness: Dict[str, FreshnessSLA] = {}
        self._source_status: Dict[str, SourceStatus] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._slo: SLOCounter = SLOCounter()
        self._merge_log: List[Dict[str, Any]] = []
        self._initialize_sources()

    def _initialize_sources(self):
        """Initialize source status, freshness, and circuit breakers."""
        for src_id, cfg in _SOURCE_CONFIGS.items():
            if cfg.get("requires_key"):
                key_env = cfg.get("key_env", "")
                key_val = os.environ.get(key_env, "")
                if not key_val:
                    self._source_status[src_id] = SourceStatus.NOT_CONFIGURED
                    self._freshness[src_id] = FreshnessSLA(
                        source=cfg["name"],
                        last_fetch_at=None,
                        last_success_at=None,
                        staleness_threshold_hours=cfg["staleness_hours"],
                        is_stale=True,
                        records_fetched=0,
                        last_error=f"{key_env} not set",
                    )
                    continue

            self._source_status[src_id] = SourceStatus.DISCONNECTED
            self._freshness[src_id] = FreshnessSLA(
                source=cfg["name"],
                last_fetch_at=None,
                last_success_at=None,
                staleness_threshold_hours=cfg["staleness_hours"],
                is_stale=True,
                records_fetched=0,
                last_error=None,
            )
            self._circuit_breakers[src_id] = CircuitBreaker(source_id=src_id)

    # ─── Status Reporting ────────────────────────────────────────────

    def get_source_status(self) -> Dict[str, Any]:
        """Get truthful status of all CVE sources."""
        result = {}
        for src_id, cfg in _SOURCE_CONFIGS.items():
            status = self._source_status.get(src_id, SourceStatus.DISCONNECTED)
            freshness = self._freshness.get(src_id)
            cb = self._circuit_breakers.get(src_id)
            result[src_id] = {
                "name": cfg["name"],
                "status": status.value,
                "priority": cfg["priority"],
                "is_canonical": cfg.get("is_canonical", False),
                "requires_key": cfg.get("requires_key", False),
                "staleness_hours": cfg["staleness_hours"],
                "is_stale": freshness.is_stale if freshness else True,
                "last_fetch_at": freshness.last_fetch_at if freshness else None,
                "last_success_at": freshness.last_success_at if freshness else None,
                "records_fetched": freshness.records_fetched if freshness else 0,
                "last_error": freshness.last_error if freshness else None,
                "circuit_breaker": cb.state.value if cb else "N/A",
                "last_etag": freshness.last_etag if freshness else None,
            }
        return result

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get overall pipeline status."""
        statuses = self._source_status
        connected = sum(
            1 for s in statuses.values() if s == SourceStatus.CONNECTED
        )
        configured = sum(
            1 for s in statuses.values() if s != SourceStatus.NOT_CONFIGURED
        )
        total = len(statuses)

        if connected == 0:
            overall = "DISCONNECTED"
        elif connected < configured:
            overall = "DEGRADED"
        else:
            overall = "CONNECTED"

        return {
            "status": overall,
            "sources_total": total,
            "sources_connected": connected,
            "sources_configured": configured,
            "total_records": len(self._records),
            "slo": {
                "job_success_rate": round(self._slo.job_success_rate, 4),
                "ingest_success_rate": round(self._slo.ingest_success_rate, 4),
                "total_jobs": self._slo.total_jobs,
                "successful_jobs": self._slo.successful_jobs,
                "no_delta_count": self._slo.no_delta_ingests,
            },
            "sources": self.get_source_status(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def get_slo(self) -> SLOCounter:
        """Get SLO counters."""
        return self._slo

    # ─── Circuit Breaker ─────────────────────────────────────────────

    def can_fetch_source(self, source_id: str) -> bool:
        """Check if circuit breaker allows fetching this source."""
        cb = self._circuit_breakers.get(source_id)
        if cb is None:
            return False
        return cb.can_attempt()

    # ─── Provenance ──────────────────────────────────────────────────

    def _make_provenance(self, source_id: str, raw_data: str,
                         last_modified: str = "") -> SourceProvenance:
        """Create provenance record for a source fetch."""
        cfg = _SOURCE_CONFIGS[source_id]
        return SourceProvenance(
            source=cfg["name"],
            fetched_at=datetime.now(timezone.utc).isoformat(),
            last_modified=last_modified or datetime.now(timezone.utc).isoformat(),
            confidence=cfg["confidence"],
            merge_policy=MergePolicy.PRIMARY_WINS.value,
            raw_hash=hashlib.sha256(raw_data.encode()).hexdigest(),
            parser_version=PARSER_VERSION,
        )

    # ─── Deterministic Merge ─────────────────────────────────────────

    def ingest_record(
        self,
        cve_id: str,
        title: str,
        description: str,
        severity: str,
        cvss_score: Optional[float],
        affected_products: List[str],
        references: List[str],
        is_exploited: bool,
        source_id: str,
        raw_data: str = "",
        last_modified: str = "",
    ) -> Tuple[CVERecord, IngestResult]:
        """Ingest a CVE record with deterministic merge and dedup."""
        content_hash = compute_content_hash(
            cve_id, description, severity, cvss_score
        )
        provenance = self._make_provenance(
            source_id, raw_data or cve_id, last_modified
        )

        if cve_id in self._records:
            existing = self._records[cve_id]

            # Exact dedup: same content hash → skip
            if existing.content_hash == content_hash:
                return existing, IngestResult.DUPLICATE

            # Merge: append provenance, increment version
            conflicts = []
            new_provenance = list(existing.provenance) + [provenance]

            # Severity: highest wins
            sev_order = {
                "CRITICAL": 4, "HIGH": 3, "MEDIUM": 2,
                "LOW": 1, "UNKNOWN": 0,
            }
            if sev_order.get(severity, 0) > sev_order.get(existing.severity, 0):
                if existing.severity != severity:
                    conflicts.append(
                        f"severity: {existing.severity} → {severity} "
                        f"(source: {provenance.source})"
                    )
                merged_severity = severity
                merged_cvss = cvss_score or existing.cvss_score
            else:
                merged_severity = existing.severity
                merged_cvss = existing.cvss_score or cvss_score

            # CVSS score conflict
            if (cvss_score and existing.cvss_score and
                    abs(cvss_score - existing.cvss_score) > 0.5):
                conflicts.append(
                    f"cvss: {existing.cvss_score} vs {cvss_score} "
                    f"(source: {provenance.source})"
                )

            merged = CVERecord(
                cve_id=cve_id,
                title=title or existing.title,
                description=description or existing.description,
                severity=merged_severity,
                cvss_score=merged_cvss,
                affected_products=list(set(
                    existing.affected_products + affected_products
                )),
                references=list(set(existing.references + references)),
                is_exploited=existing.is_exploited or is_exploited,
                provenance=new_provenance,
                canonical_version=existing.canonical_version + 1,
                merged_at=datetime.now(timezone.utc).isoformat(),
                content_hash=content_hash,
                promotion_status=existing.promotion_status,
                block_reason=existing.block_reason,
                merge_conflicts=existing.merge_conflicts + conflicts,
            )
            self._records[cve_id] = merged

            if conflicts:
                self._merge_log.append({
                    "cve_id": cve_id,
                    "conflicts": conflicts,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            return merged, IngestResult.UPDATED
        else:
            record = CVERecord(
                cve_id=cve_id,
                title=title,
                description=description,
                severity=severity,
                cvss_score=cvss_score,
                affected_products=affected_products,
                references=references,
                is_exploited=is_exploited,
                provenance=[provenance],
                canonical_version=1,
                merged_at=datetime.now(timezone.utc).isoformat(),
                content_hash=content_hash,
                promotion_status="RESEARCH_PENDING",
            )
            self._records[cve_id] = record
            return record, IngestResult.NEW

    # ─── Source Status ───────────────────────────────────────────────

    def mark_source_success(self, source_id: str, records_count: int,
                            etag: str = "", last_modified_header: str = ""):
        """Mark a source as successfully fetched."""
        now = datetime.now(timezone.utc).isoformat()
        self._source_status[source_id] = SourceStatus.CONNECTED
        cb = self._circuit_breakers.get(source_id)
        if cb:
            cb.record_success()

        if source_id in self._freshness:
            f = self._freshness[source_id]
            self._freshness[source_id] = FreshnessSLA(
                source=f.source,
                last_fetch_at=now,
                last_success_at=now,
                staleness_threshold_hours=f.staleness_threshold_hours,
                is_stale=False,
                records_fetched=records_count,
                last_error=None,
                last_etag=etag or f.last_etag,
                last_modified_header=last_modified_header or f.last_modified_header,
                last_seen_timestamp=now,
            )

        self._slo.successful_ingests += 1

    def mark_source_no_delta(self, source_id: str):
        """Mark a source as having no new data (NOT a failure)."""
        now = datetime.now(timezone.utc).isoformat()
        # Keep CONNECTED status — no delta is not an error
        if source_id in self._freshness:
            f = self._freshness[source_id]
            self._freshness[source_id] = FreshnessSLA(
                source=f.source,
                last_fetch_at=now,
                last_success_at=f.last_success_at,
                staleness_threshold_hours=f.staleness_threshold_hours,
                is_stale=f.is_stale,
                records_fetched=f.records_fetched,
                last_error=None,
                last_etag=f.last_etag,
                last_modified_header=f.last_modified_header,
                last_seen_timestamp=now,
            )
        self._slo.no_delta_ingests += 1

    def mark_source_error(self, source_id: str, error: str):
        """Mark a source as failed."""
        now = datetime.now(timezone.utc).isoformat()
        prev = self._source_status.get(source_id, SourceStatus.DISCONNECTED)
        if prev == SourceStatus.CONNECTED:
            self._source_status[source_id] = SourceStatus.DEGRADED
        else:
            self._source_status[source_id] = SourceStatus.DISCONNECTED

        cb = self._circuit_breakers.get(source_id)
        if cb:
            cb.record_failure()

        if source_id in self._freshness:
            f = self._freshness[source_id]
            self._freshness[source_id] = FreshnessSLA(
                source=f.source,
                last_fetch_at=now,
                last_success_at=f.last_success_at,
                staleness_threshold_hours=f.staleness_threshold_hours,
                is_stale=True,
                records_fetched=f.records_fetched,
                last_error=error,
                last_etag=f.last_etag,
                last_modified_header=f.last_modified_header,
                last_seen_timestamp=f.last_seen_timestamp,
            )

        self._slo.failed_jobs += 1

    # ─── Record Access ───────────────────────────────────────────────

    def get_records(self, severity_filter: Optional[str] = None,
                    promotion_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all CVE records as dicts."""
        records = list(self._records.values())
        if severity_filter:
            records = [
                r for r in records if r.severity == severity_filter.upper()
            ]
        if promotion_filter:
            records = [
                r for r in records
                if r.promotion_status == promotion_filter.upper()
            ]

        return [
            {
                "cve_id": r.cve_id,
                "title": r.title,
                "description": r.description[:200],
                "severity": r.severity,
                "cvss_score": r.cvss_score,
                "is_exploited": r.is_exploited,
                "sources": [p.source for p in r.provenance],
                "canonical_version": r.canonical_version,
                "merged_at": r.merged_at,
                "content_hash": r.content_hash[:16],
                "promotion_status": r.promotion_status,
                "block_reason": r.block_reason,
            }
            for r in records
        ]

    def get_record(self, cve_id: str) -> Optional[CVERecord]:
        return self._records.get(cve_id)

    def get_merge_log(self) -> List[Dict[str, Any]]:
        return list(self._merge_log)

    def update_promotion_status(self, cve_id: str, status: str,
                                reason: str = ""):
        """Update promotion status of a CVE record."""
        rec = self._records.get(cve_id)
        if rec:
            rec.promotion_status = status
            rec.block_reason = reason

    def record_job_execution(self, success: bool):
        """Track a scheduler job execution for SLO."""
        self._slo.total_jobs += 1
        self._slo.total_ingests += 1
        if success:
            self._slo.successful_jobs += 1


# =============================================================================
# SINGLETON
# =============================================================================

_pipeline: Optional[CVEPipeline] = None


def get_pipeline() -> CVEPipeline:
    """Get or create the CVE pipeline singleton."""
    global _pipeline
    if _pipeline is None:
        _pipeline = CVEPipeline()
    return _pipeline
