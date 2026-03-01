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
        # Load persistent bridge state
        from backend.bridge.bridge_state import get_bridge_state
        self._bridge_state = get_bridge_state()

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
        """Get current bridge counters from PERSISTED state (cross-process safe)."""
        # Always return persisted state as authoritative source
        counts = self._bridge_state.get_counts()
        return {
            "bridge_count": counts["bridge_count"],
            "bridge_verified_count": counts["bridge_verified_count"],
            "bridge_loaded": self._lib is not None,
        }

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

    @staticmethod
    def _map_cve_to_sample(record) -> Optional[Dict[str, str]]:
        """Map a CVE pipeline record to training sample fields."""
        def _read(key: str, default=None):
            """
            Read from dataclass/object records first, then dict-like records.
            Avoid calling .get() on object records (e.g., CVERecord dataclass).
            """
            if hasattr(record, key):
                val = getattr(record, key)
                if val is not None:
                    return val
            if isinstance(record, dict):
                return record.get(key, default)
            return default

        cve_id = _read("cve_id", "")
        if not cve_id:
            return None

        # Determine affected products string
        products = _read("affected_products", [])
        if isinstance(products, list):
            products_str = json.dumps(products)[:511]
        else:
            products_str = str(products)[:511]

        # Description
        desc = _read("description", "")
        desc = str(desc)[:511]

        # Severity / impact
        severity = _read("severity", "UNKNOWN")
        cvss = _read("cvss_score", None)
        if cvss is not None:
            impact = f"{severity}|CVSS:{cvss}"
        else:
            impact = str(severity)

        # Source tag
        provenance = getattr(record, "provenance", None)
        sources = []
        if provenance:
            if isinstance(provenance, list):
                for p in provenance:
                    s = getattr(p, "source", None) or (
                        p.get("source", "") if isinstance(p, dict) else "")
                    if s:
                        sources.append(s)
            elif isinstance(provenance, dict):
                s = provenance.get("source", "")
                if s:
                    sources.append(s)
        source_tag = "|".join(sources) if sources else _read("source_id", "UNKNOWN")

        promotion_status = _read("promotion_status", "RESEARCH_PENDING")

        return {
            "endpoint": cve_id,
            "parameters": products_str,
            "exploit_vector": desc,
            "impact": impact[:511],
            "source_tag": source_tag[:511],
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

    def stream_ingest_new(self, pipeline) -> int:
        """
        Stream-ingest new records from the pipeline into the bridge.
        Called each scheduler cycle. Returns count of new samples ingested.
        """
        if not self._lib:
            return 0

        ingested = 0
        records = getattr(pipeline, "_records", {})
        if not records:
            return 0

        for cve_id, record in records.items():
            fields = self._map_cve_to_sample(record)
            if not fields:
                continue

            # Compute idempotency key
            ik = self._compute_idempotency_key(
                fields["endpoint"], fields["exploit_vector"]
            )
            if ik in self._ingested_keys:
                self._total_deduped += 1
                continue

            # Compute reliability
            reliability = self._compute_reliability(
                fields.get("sources", []),
                fields.get("promotion_status", "RESEARCH_PENDING"),
            )
            if reliability < RELIABILITY_DROP_THRESHOLD:
                self._total_dropped += 1
                continue

            # Ingest
            rc = self._ingest_one(fields, reliability)
            if rc == 0:
                ingested += 1
                self._ingested_keys.add(ik)
                self._total_ingested += 1
                # Persist sample
                self._bridge_state.append_sample({
                    "endpoint": fields["endpoint"],
                    "parameters": fields["parameters"],
                    "exploit_vector": fields["exploit_vector"],
                    "impact": fields["impact"],
                    "source_tag": fields["source_tag"],
                    "reliability": reliability,
                })
            elif rc == -3:
                self._total_deduped += 1
                self._ingested_keys.add(ik)

        if ingested > 0:
            self._last_ingest_at = datetime.now(timezone.utc).isoformat()
            # Persist counters
            self._bridge_state.record_ingest_batch(ingested, ingested)
            self._bridge_state.flush_samples()

        return ingested

    def backfill(self, pipeline, max_samples: int = 0) -> Dict[str, Any]:
        """
        One-shot backfill: ingest all pipeline records into bridge.
        Returns progress dict.
        """
        if not self._lib:
            return {
                "success": False,
                "reason": "Bridge DLL not loaded",
                "ingested": 0,
            }

        t0 = time.time()
        ingested = 0
        dropped = 0
        deduped = 0

        records = getattr(pipeline, "_records", {})
        total = len(records)

        for cve_id, record in records.items():
            if max_samples and ingested >= max_samples:
                break

            fields = self._map_cve_to_sample(record)
            if not fields:
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
                # Persist sample
                self._bridge_state.append_sample({
                    "endpoint": fields["endpoint"],
                    "parameters": fields["parameters"],
                    "exploit_vector": fields["exploit_vector"],
                    "impact": fields["impact"],
                    "source_tag": fields["source_tag"],
                    "reliability": reliability,
                })
            elif rc == -3:
                deduped += 1
                self._ingested_keys.add(ik)
                self._total_deduped += 1

        elapsed = time.time() - t0
        self._last_ingest_at = datetime.now(timezone.utc).isoformat()

        # Flush samples and persist counters
        self._bridge_state.flush_samples()
        if self._lib:
            self._bridge_state.set_counts(
                bridge_count=self._lib.bridge_get_count(),
                bridge_verified_count=self._lib.bridge_get_verified_count(),
                total_ingested=self._total_ingested,
                total_dropped=self._total_dropped,
                total_deduped=self._total_deduped,
            )

        # Update manifest after backfill
        self.update_manifest()

        counts = self.get_bridge_counts()
        return {
            "success": True,
            "total_available": total,
            "ingested": ingested,
            "dropped": dropped,
            "deduped": deduped,
            "elapsed_seconds": round(elapsed, 2),
            "bridge_count": counts.get("bridge_count", 0),
            "bridge_verified_count": counts.get("bridge_verified_count", 0),
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
