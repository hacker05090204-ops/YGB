"""
CVE Pipeline — Multi-Source CVE Feed with Truthful Status

Sources (priority order):
  1. CVEProject/cvelistV5 (official, free)
  2. NVD API v2 (enrichment, rate-limited)
  3. CISA KEV (exploited-in-wild flagging)
  4. Vulners (optional, requires API key)
  5. VulDB (optional, requires API key)

Source provenance per record.
Deduplication by CVE ID.
Freshness SLA monitoring.
Never reports CONNECTED/ACTIVE if fetch/auth fails.
"""

import os
import logging
import hashlib
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("ygb.cve_pipeline")


# =============================================================================
# DATA MODELS
# =============================================================================

class SourceStatus(Enum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DISCONNECTED = "DISCONNECTED"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class MergePolicy(Enum):
    PRIMARY_WINS = "PRIMARY_WINS"       # CVEProject data preferred
    MOST_RECENT = "MOST_RECENT"         # Most recently modified wins
    HIGHEST_SEVERITY = "HIGHEST_SEVERITY"  # Highest severity wins


@dataclass
class SourceProvenance:
    """Provenance metadata per CVE record per source."""
    source: str
    fetched_at: str
    last_modified: str
    confidence: float          # 0.0 - 1.0
    merge_policy: str
    raw_hash: str              # SHA-256 of raw source data


@dataclass
class CVERecord:
    """Canonical CVE record with multi-source provenance."""
    cve_id: str
    title: str
    description: str
    severity: str              # CRITICAL, HIGH, MEDIUM, LOW, UNKNOWN
    cvss_score: Optional[float]
    affected_products: List[str]
    references: List[str]
    is_exploited: bool         # CISA KEV flagged
    provenance: List[SourceProvenance]
    canonical_version: int     # Incremented on merge
    merged_at: str


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


# =============================================================================
# SOURCE REGISTRY
# =============================================================================

_SOURCE_CONFIGS = {
    "cveproject": {
        "name": "CVEProject/cvelistV5",
        "url": "https://github.com/CVEProject/cvelistV5",
        "requires_key": False,
        "staleness_hours": 24,
        "confidence": 0.95,
    },
    "nvd": {
        "name": "NVD API v2",
        "url": "https://services.nvd.nist.gov/rest/json/cves/2.0",
        "requires_key": False,
        "key_env": "NVD_API_KEY",
        "staleness_hours": 6,
        "confidence": 0.90,
    },
    "cisa_kev": {
        "name": "CISA KEV Catalog",
        "url": "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
        "requires_key": False,
        "staleness_hours": 24,
        "confidence": 1.0,
    },
    "vulners": {
        "name": "Vulners",
        "url": "https://vulners.com/api/v3/",
        "requires_key": True,
        "key_env": "VULNERS_API_KEY",
        "staleness_hours": 12,
        "confidence": 0.80,
    },
    "vuldb": {
        "name": "VulDB",
        "url": "https://vuldb.com/api/",
        "requires_key": True,
        "key_env": "VULDB_API_KEY",
        "staleness_hours": 12,
        "confidence": 0.75,
    },
}


# =============================================================================
# CVE PIPELINE
# =============================================================================

class CVEPipeline:
    """Multi-source CVE feed with truthful status reporting."""

    def __init__(self):
        self._records: Dict[str, CVERecord] = {}     # cve_id -> record
        self._freshness: Dict[str, FreshnessSLA] = {}
        self._source_status: Dict[str, SourceStatus] = {}
        self._initialize_sources()

    def _initialize_sources(self):
        """Initialize source status and freshness tracking."""
        for src_id, cfg in _SOURCE_CONFIGS.items():
            # Check if required key is available
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

    def get_source_status(self) -> Dict[str, Any]:
        """Get truthful status of all CVE sources."""
        result = {}
        for src_id, cfg in _SOURCE_CONFIGS.items():
            status = self._source_status.get(src_id, SourceStatus.DISCONNECTED)
            freshness = self._freshness.get(src_id)
            result[src_id] = {
                "name": cfg["name"],
                "status": status.value,
                "requires_key": cfg.get("requires_key", False),
                "staleness_hours": cfg["staleness_hours"],
                "is_stale": freshness.is_stale if freshness else True,
                "last_fetch_at": freshness.last_fetch_at if freshness else None,
                "last_success_at": freshness.last_success_at if freshness else None,
                "records_fetched": freshness.records_fetched if freshness else 0,
                "last_error": freshness.last_error if freshness else None,
            }
        return result

    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get overall pipeline status."""
        statuses = self._source_status
        connected = sum(1 for s in statuses.values() if s == SourceStatus.CONNECTED)
        configured = sum(1 for s in statuses.values() if s != SourceStatus.NOT_CONFIGURED)
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
            "sources": self.get_source_status(),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def _make_provenance(self, source_id: str, raw_data: str) -> SourceProvenance:
        """Create provenance record for a source fetch."""
        cfg = _SOURCE_CONFIGS[source_id]
        return SourceProvenance(
            source=cfg["name"],
            fetched_at=datetime.now(timezone.utc).isoformat(),
            last_modified=datetime.now(timezone.utc).isoformat(),
            confidence=cfg["confidence"],
            merge_policy=MergePolicy.PRIMARY_WINS.value,
            raw_hash=hashlib.sha256(raw_data.encode()).hexdigest(),
        )

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
    ) -> CVERecord:
        """Ingest a CVE record, deduplicating by CVE ID."""
        provenance = self._make_provenance(source_id, raw_data or cve_id)

        if cve_id in self._records:
            existing = self._records[cve_id]
            # Merge: append provenance, increment version
            new_provenance = list(existing.provenance) + [provenance]
            # Use highest severity
            sev_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "UNKNOWN": 0}
            if sev_order.get(severity, 0) > sev_order.get(existing.severity, 0):
                merged_severity = severity
                merged_cvss = cvss_score or existing.cvss_score
            else:
                merged_severity = existing.severity
                merged_cvss = existing.cvss_score or cvss_score

            merged = CVERecord(
                cve_id=cve_id,
                title=title or existing.title,
                description=description or existing.description,
                severity=merged_severity,
                cvss_score=merged_cvss,
                affected_products=list(set(existing.affected_products + affected_products)),
                references=list(set(existing.references + references)),
                is_exploited=existing.is_exploited or is_exploited,
                provenance=new_provenance,
                canonical_version=existing.canonical_version + 1,
                merged_at=datetime.now(timezone.utc).isoformat(),
            )
            self._records[cve_id] = merged
            return merged
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
            )
            self._records[cve_id] = record
            return record

    def mark_source_success(self, source_id: str, records_count: int):
        """Mark a source as successfully fetched."""
        now = datetime.now(timezone.utc).isoformat()
        self._source_status[source_id] = SourceStatus.CONNECTED
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
            )

    def mark_source_error(self, source_id: str, error: str):
        """Mark a source as failed."""
        now = datetime.now(timezone.utc).isoformat()
        prev = self._source_status.get(source_id, SourceStatus.DISCONNECTED)
        # Degrade but don't disconnect if was previously connected
        if prev == SourceStatus.CONNECTED:
            self._source_status[source_id] = SourceStatus.DEGRADED
        else:
            self._source_status[source_id] = SourceStatus.DISCONNECTED

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
            )

    def get_records(self, severity_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all CVE records as dicts, optionally filtered by severity."""
        records = list(self._records.values())
        if severity_filter:
            records = [r for r in records if r.severity == severity_filter.upper()]

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
            }
            for r in records
        ]


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
