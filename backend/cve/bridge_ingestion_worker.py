"""
Bridge Ingestion Worker — Runtime CVE→Training Bridge Producer.

Consumes normalized CVE records from the pipeline and writes to the
C++ training bridge via ctypes bridge_ingest_sample().

Two modes:
  - stream_ingest_new(): called each scheduler cycle for new records
  - backfill(): one-shot batch ingest of all pipeline records

Reliability policy:
  - Canonical sources (CVE Services, NVD): 0.95
  - Corroborated (2+ sources): 0.85
  - Single non-canonical: 0.60
  - Unverifiable / headless-only: DROPPED (not ingested)

Dedup: SHA256 idempotency key per record before bridge write.
"""

import ctypes
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set

logger = logging.getLogger("ygb.bridge_worker")

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_BRIDGE_DIR = _PROJECT_ROOT / "native" / "distributed"
_BRIDGE_LIB = "ingestion_bridge.dll" if os.name == "nt" else "libingestion_bridge.so"
_SECURE_DATA = _PROJECT_ROOT / "secure_data"
_MANIFEST_PATH = _SECURE_DATA / "dataset_manifest.json"

# Reliability tiers
RELIABILITY_CANONICAL = 0.95
RELIABILITY_CORROBORATED = 0.85
RELIABILITY_SINGLE_SOURCE = 0.60
RELIABILITY_DROP_THRESHOLD = 0.40  # Below this → drop

# Canonical source names (from cve_pipeline _SOURCE_CONFIGS)
CANONICAL_SOURCES = {"CVE Services / cve.org", "cve_services"}
HIGH_TRUST_SOURCES = {"NVD API v2", "nvd", "CISA KEV Catalog", "cisa_kev"}
ENRICHMENT_SOURCES = {"CVE Project / GitHub", "cveproject", "Vulners API",
                      "vulners", "VulDB API", "vuldb"}


class BridgeIngestionWorker:
    """Runtime producer: CVE records → C++ training bridge."""

    def __init__(self):
        self._lib: Optional[ctypes.CDLL] = None
        self._ingested_keys: Set[str] = set()  # idempotency keys
        self._total_ingested: int = 0
        self._total_dropped: int = 0
        self._total_deduped: int = 0
        self._last_ingest_at: Optional[str] = None
        self._load_bridge()

    def _load_bridge(self):
        """Try to load the ingestion bridge DLL."""
        lib_path = _BRIDGE_DIR / _BRIDGE_LIB
        if not lib_path.exists():
            logger.warning(
                f"[BRIDGE] DLL not found: {lib_path}. "
                f"Bridge ingestion will be unavailable."
            )
            return

        try:
            self._lib = ctypes.CDLL(str(lib_path))

            self._lib.bridge_init.restype = ctypes.c_int
            self._lib.bridge_init.argtypes = []

            self._lib.bridge_get_count.restype = ctypes.c_int
            self._lib.bridge_get_count.argtypes = []

            self._lib.bridge_get_verified_count.restype = ctypes.c_int
            self._lib.bridge_get_verified_count.argtypes = []

            self._lib.bridge_ingest_sample.restype = ctypes.c_int
            self._lib.bridge_ingest_sample.argtypes = [
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
                ctypes.c_char_p, ctypes.c_char_p, ctypes.c_double,
            ]

            logger.info("[BRIDGE] Ingestion bridge DLL loaded")
        except Exception as e:
            logger.error(f"[BRIDGE] Failed to load DLL: {e}")
            self._lib = None

    @property
    def is_bridge_loaded(self) -> bool:
        return self._lib is not None

    def get_bridge_counts(self) -> Dict[str, int]:
        """Get current bridge counters."""
        if not self._lib:
            return {"bridge_count": 0, "bridge_verified_count": 0,
                    "bridge_loaded": False}
        try:
            return {
                "bridge_count": self._lib.bridge_get_count(),
                "bridge_verified_count": self._lib.bridge_get_verified_count(),
                "bridge_loaded": True,
            }
        except Exception:
            return {"bridge_count": 0, "bridge_verified_count": 0,
                    "bridge_loaded": True}

    def get_status(self) -> Dict[str, Any]:
        """Get worker status."""
        counts = self.get_bridge_counts()
        return {
            "bridge_loaded": self.is_bridge_loaded,
            "total_ingested": self._total_ingested,
            "total_dropped": self._total_dropped,
            "total_deduped": self._total_deduped,
            "last_ingest_at": self._last_ingest_at,
            "idempotency_keys_cached": len(self._ingested_keys),
            **counts,
        }

    # =========================================================================
    # SAFE FIELD ACCESSOR (dataclass + dict support)
    # =========================================================================

    @staticmethod
    def _get(record, key: str, default=None):
        """Safe accessor: works for both dataclass objects and dicts."""
        if isinstance(record, dict):
            return record.get(key, default)
        val = getattr(record, key, default)
        return val if val is not None else default

    # =========================================================================
    # FIELD MAPPING
    # =========================================================================

    @staticmethod
    def _compute_idempotency_key(cve_id: str, description: str) -> str:
        """Deterministic dedup key from CVE content."""
        content = f"{cve_id}|{description[:256]}".encode("utf-8")
        return hashlib.sha256(content).hexdigest()[:32]

    @staticmethod
    def _compute_reliability(source_ids: list, promotion_status: str) -> float:
        """Map provenance to reliability score."""
        sources_set = set(source_ids) if source_ids else set()

        # Canonical source → highest
        if sources_set & CANONICAL_SOURCES:
            return RELIABILITY_CANONICAL

        # Multiple high-trust / corroborated
        trusted = sources_set & HIGH_TRUST_SOURCES
        if len(trusted) >= 2 or promotion_status in ("CANONICAL", "CORROBORATED"):
            return RELIABILITY_CORROBORATED

        # Single high-trust
        if trusted:
            return RELIABILITY_SINGLE_SOURCE

        # Enrichment only
        if sources_set & ENRICHMENT_SOURCES:
            return RELIABILITY_SINGLE_SOURCE

        # Unknown / headless-only → drop
        return 0.0

    def _map_cve_to_sample(self, record) -> Optional[Dict[str, str]]:
        """Map a CVE pipeline record to training sample fields.

        Supports BOTH:
          - dataclass CVERecord objects (getattr)
          - plain dict records (.get)
        Never raises AttributeError.
        """
        _g = self._get
        cve_id = _g(record, "cve_id", "")
        if not cve_id:
            return None

        # Affected products
        products = _g(record, "affected_products", [])
        if isinstance(products, list):
            products_str = json.dumps(products)[:511]
        else:
            products_str = str(products)[:511]

        # Description
        desc = str(_g(record, "description", "") or "")[:511]

        # Severity / impact
        severity = _g(record, "severity", "UNKNOWN") or "UNKNOWN"
        cvss = _g(record, "cvss_score", None)
        if cvss is not None:
            impact = f"{severity}|CVSS:{cvss}"
        else:
            impact = str(severity)

        # Source tag from provenance chain
        provenance = _g(record, "provenance", None)
        sources = []
        if provenance:
            if isinstance(provenance, list):
                for p in provenance:
                    s = self._get(p, "source", "")
                    if s:
                        sources.append(s)
            elif isinstance(provenance, dict):
                s = provenance.get("source", "")
                if s:
                    sources.append(s)
        source_tag = "|".join(sources) if sources else _g(record, "source_id", "UNKNOWN")

        promotion_status = _g(record, "promotion_status", "RESEARCH_PENDING") or "RESEARCH_PENDING"

        return {
            "endpoint": cve_id,
            "parameters": products_str,
            "exploit_vector": desc,
            "impact": impact[:511],
            "source_tag": str(source_tag)[:511],
            "sources": sources,
            "promotion_status": promotion_status,
        }

    # =========================================================================
    # INGEST OPERATIONS
    # =========================================================================

    def _ingest_one(self, fields: Dict[str, str], reliability: float) -> int:
        """Ingest a single sample into the bridge. Returns 0=ok, -3=dup, <0=err."""
        if not self._lib:
            return -1
        try:
            rc = self._lib.bridge_ingest_sample(
                fields["endpoint"].encode("utf-8"),
                fields["parameters"].encode("utf-8"),
                fields["exploit_vector"].encode("utf-8"),
                fields["impact"].encode("utf-8"),
                fields["source_tag"].encode("utf-8"),
                reliability,
            )
            return rc
        except Exception as e:
            logger.error(f"[BRIDGE] ingest error: {e}")
            return -99

    def stream_ingest_new(self, pipeline) -> Dict[str, Any]:
        """
        Stream-ingest new records from the pipeline into the bridge.
        Called each scheduler cycle.
        Returns dict with debug counters.
        """
        result = {
            "ingested_ok": 0,
            "dropped_low_reliability": 0,
            "dropped_mapping_invalid": 0,
            "dropped_missing_id": 0,
            "deduped": 0,
            "total_scanned": 0,
            "bridge_loaded": self.is_bridge_loaded,
        }

        if not self._lib:
            return result

        records = getattr(pipeline, "_records", {})
        if not records:
            return result

        for cve_id, record in records.items():
            result["total_scanned"] += 1

            fields = self._map_cve_to_sample(record)
            if fields is None:
                result["dropped_missing_id"] += 1
                self._total_dropped += 1
                continue

            if not fields.get("endpoint") or not fields.get("exploit_vector"):
                result["dropped_mapping_invalid"] += 1
                self._total_dropped += 1
                continue

            # Compute idempotency key
            ik = self._compute_idempotency_key(
                fields["endpoint"], fields["exploit_vector"]
            )
            if ik in self._ingested_keys:
                result["deduped"] += 1
                self._total_deduped += 1
                continue

            # Compute reliability
            reliability = self._compute_reliability(
                fields.get("sources", []),
                fields.get("promotion_status", "RESEARCH_PENDING"),
            )
            if reliability < RELIABILITY_DROP_THRESHOLD:
                result["dropped_low_reliability"] += 1
                self._total_dropped += 1
                continue

            # Ingest
            rc = self._ingest_one(fields, reliability)
            if rc == 0:
                result["ingested_ok"] += 1
                self._ingested_keys.add(ik)
                self._total_ingested += 1
            elif rc == -3:
                result["deduped"] += 1
                self._total_deduped += 1
                self._ingested_keys.add(ik)

        if result["ingested_ok"] > 0:
            self._last_ingest_at = datetime.now(timezone.utc).isoformat()
            # Auto-sync manifest when new samples ingested
            self.update_manifest()

        return result

    def backfill(self, pipeline, max_samples: int = 0) -> Dict[str, Any]:
        """
        One-shot backfill: ingest all pipeline records into bridge.
        Returns truthful structured result.
        """
        if not self._lib:
            return {
                "success": False,
                "reason": "Bridge DLL not loaded",
                "total_available": 0,
                "attempted": 0,
                "ingested": 0,
                "dropped": 0,
                "deduped": 0,
                "bridge_count": 0,
                "bridge_verified_count": 0,
                "duration_ms": 0,
            }

        t0 = time.time()
        ingested = 0
        dropped = 0
        deduped = 0
        attempted = 0
        dropped_missing = 0
        dropped_invalid = 0

        records = getattr(pipeline, "_records", {})
        total = len(records)

        for cve_id, record in records.items():
            if max_samples and ingested >= max_samples:
                break

            attempted += 1
            fields = self._map_cve_to_sample(record)
            if fields is None:
                dropped_missing += 1
                dropped += 1
                continue

            if not fields.get("endpoint") or not fields.get("exploit_vector"):
                dropped_invalid += 1
                dropped += 1
                continue

            ik = self._compute_idempotency_key(
                fields["endpoint"], fields["exploit_vector"]
            )
            if ik in self._ingested_keys:
                deduped += 1
                continue

            reliability = self._compute_reliability(
                fields.get("sources", []),
                fields.get("promotion_status", "RESEARCH_PENDING"),
            )
            if reliability < RELIABILITY_DROP_THRESHOLD:
                dropped += 1
                self._total_dropped += 1
                continue

            rc = self._ingest_one(fields, reliability)
            if rc == 0:
                ingested += 1
                self._ingested_keys.add(ik)
                self._total_ingested += 1
            elif rc == -3:
                deduped += 1
                self._ingested_keys.add(ik)
                self._total_deduped += 1

        elapsed_ms = int((time.time() - t0) * 1000)
        self._last_ingest_at = datetime.now(timezone.utc).isoformat()

        # Update manifest after backfill
        self.update_manifest()

        counts = self.get_bridge_counts()
        return {
            "success": True,
            "total_available": total,
            "attempted": attempted,
            "ingested": ingested,
            "dropped": dropped,
            "dropped_missing_id": dropped_missing,
            "dropped_mapping_invalid": dropped_invalid,
            "deduped": deduped,
            "bridge_count": counts.get("bridge_count", 0),
            "bridge_verified_count": counts.get("bridge_verified_count", 0),
            "duration_ms": elapsed_ms,
        }

    # =========================================================================
    # MANIFEST
    # =========================================================================

    def update_manifest(self):
        """Auto-generate/update secure_data/dataset_manifest.json."""
        counts = self.get_bridge_counts()
        _SECURE_DATA.mkdir(parents=True, exist_ok=True)

        # Source mix from ingested keys
        source_mix = {}
        try:
            from backend.cve.cve_pipeline import get_pipeline
            pipeline = get_pipeline()
            for cve_id, record in getattr(pipeline, "_records", {}).items():
                provenance = getattr(record, "provenance", [])
                if isinstance(provenance, list):
                    for p in provenance:
                        src = getattr(p, "source", None)
                        if src:
                            source_mix[src] = source_mix.get(src, 0) + 1
        except Exception:
            pass

        manifest = {
            "total_samples": counts.get("bridge_count", 0),
            "verified_samples": counts.get("bridge_verified_count", 0),
            "per_field_counts": {
                "endpoint": self._total_ingested,
                "parameters": self._total_ingested,
                "exploit_vector": self._total_ingested,
                "impact": self._total_ingested,
                "source_tag": self._total_ingested,
                "reliability": self._total_ingested,
            },
            "source_mix": source_mix,
            "strict_real_mode": os.environ.get(
                "YGB_STRICT_REAL_MODE", "true"
            ).lower() != "false",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "ingestion_manifest_hash": hashlib.sha256(
                json.dumps({
                    "total": self._total_ingested,
                    "dropped": self._total_dropped,
                    "deduped": self._total_deduped,
                }).encode()
            ).hexdigest()[:16],
            "worker_stats": {
                "total_ingested": self._total_ingested,
                "total_dropped": self._total_dropped,
                "total_deduped": self._total_deduped,
            },
        }

        try:
            with open(_MANIFEST_PATH, "w") as f:
                json.dump(manifest, f, indent=2)
            logger.info(f"[MANIFEST] Written to {_MANIFEST_PATH}")
        except Exception as e:
            logger.error(f"[MANIFEST] Write failed: {e}")

        return manifest


# =============================================================================
# SINGLETON
# =============================================================================

_worker: Optional[BridgeIngestionWorker] = None


def get_bridge_worker() -> BridgeIngestionWorker:
    """Get or create the bridge worker singleton."""
    global _worker
    if _worker is None:
        _worker = BridgeIngestionWorker()
    return _worker
