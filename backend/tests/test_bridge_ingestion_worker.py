"""
Tests for bridge_ingestion_worker — mapping, stream ingest, backfill, readiness.

Targeted scope:
  - CVERecord dataclass mapping
  - dict mapping
  - missing CVE ID rejection
  - stream_ingest_new dedup + counters
  - backfill structured result
  - readiness consistency
"""

import os
import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass, field
from typing import List, Optional

# Ensure predictable test environment
os.environ["YGB_TEST_MODE"] = "true"

from backend.cve.bridge_ingestion_worker import (
    BridgeIngestionWorker,
    get_bridge_worker,
    RELIABILITY_CANONICAL,
    RELIABILITY_DROP_THRESHOLD,
)
from backend.cve.cve_pipeline import (
    CVERecord,
    SourceProvenance,
    CVEPipeline,
    get_pipeline,
    PARSER_VERSION,
)


# =============================================================================
# FIXTURES
# =============================================================================

def _make_cve_record(
    cve_id="CVE-2025-1234",
    description="Test buffer overflow in example.com component",
    severity="HIGH",
    cvss_score=8.5,
    source_name="NVD API v2",
    promotion_status="RESEARCH_PENDING",
):
    """Create a real CVERecord dataclass."""
    return CVERecord(
        cve_id=cve_id,
        title=cve_id,
        description=description,
        severity=severity,
        cvss_score=cvss_score,
        affected_products=["vendor/product"],
        references=["https://example.com/advisory"],
        is_exploited=False,
        provenance=[
            SourceProvenance(
                source=source_name,
                fetched_at="2026-01-01T00:00:00Z",
                last_modified="2026-01-01T00:00:00Z",
                confidence=0.90,
                merge_policy="PRIMARY_WINS",
                raw_hash="abc123",
                parser_version=PARSER_VERSION,
            )
        ],
        canonical_version=1,
        merged_at="2026-01-01T00:00:00Z",
        content_hash="deadbeef",
        promotion_status=promotion_status,
    )


def _make_cve_dict(
    cve_id="CVE-2025-5678",
    description="Test SQL injection in api endpoint",
    severity="CRITICAL",
    cvss_score=9.8,
):
    """Create a plain dict CVE record."""
    return {
        "cve_id": cve_id,
        "title": cve_id,
        "description": description,
        "severity": severity,
        "cvss_score": cvss_score,
        "affected_products": ["vendor/product"],
        "references": [],
        "is_exploited": True,
        "provenance": [{"source": "CVE Services / cve.org"}],
        "promotion_status": "CANONICAL",
        "source_id": "cve_services",
    }


def _fresh_worker():
    """Create a fresh worker with mocked bridge DLL."""
    worker = BridgeIngestionWorker.__new__(BridgeIngestionWorker)
    worker._lib = None
    worker._ingested_keys = set()
    worker._total_ingested = 0
    worker._total_dropped = 0
    worker._total_deduped = 0
    worker._last_ingest_at = None

    # Mock C++ bridge
    mock_lib = MagicMock()
    mock_lib.bridge_init.return_value = 0
    mock_lib.bridge_get_count.return_value = 0
    mock_lib.bridge_get_verified_count.return_value = 0
    mock_lib.bridge_ingest_sample.return_value = 0  # 0 = success
    worker._lib = mock_lib

    return worker


# =============================================================================
# A) MAPPING TESTS
# =============================================================================

class TestCVERecordMapping:
    """Test _map_cve_to_sample with dataclass + dict inputs."""

    def test_dataclass_cve_record_maps_successfully(self):
        """CVERecord dataclass must map without AttributeError."""
        worker = _fresh_worker()
        record = _make_cve_record()
        result = worker._map_cve_to_sample(record)

        assert result is not None
        assert result["endpoint"] == "CVE-2025-1234"
        assert "buffer overflow" in result["exploit_vector"]
        assert result["impact"].startswith("HIGH")
        assert "NVD API v2" in result["source_tag"]
        assert result["promotion_status"] == "RESEARCH_PENDING"
        assert isinstance(result["sources"], list)

    def test_dict_input_maps_successfully(self):
        """Plain dict record must map without error."""
        worker = _fresh_worker()
        record = _make_cve_dict()
        result = worker._map_cve_to_sample(record)

        assert result is not None
        assert result["endpoint"] == "CVE-2025-5678"
        assert "SQL injection" in result["exploit_vector"]
        assert result["impact"].startswith("CRITICAL")
        assert result["promotion_status"] == "CANONICAL"

    def test_missing_cve_id_rejected(self):
        """Record with no cve_id must be rejected (return None)."""
        worker = _fresh_worker()
        assert worker._map_cve_to_sample({"description": "no id"}) is None
        assert worker._map_cve_to_sample({}) is None

    def test_dataclass_with_no_provenance(self):
        """CVERecord with empty provenance still maps."""
        worker = _fresh_worker()
        record = _make_cve_record()
        object.__setattr__(record, "provenance", [])
        result = worker._map_cve_to_sample(record)
        assert result is not None
        assert result["endpoint"] == "CVE-2025-1234"

    def test_output_schema_fields(self):
        """Output must have all required schema fields."""
        worker = _fresh_worker()
        result = worker._map_cve_to_sample(_make_cve_record())
        required_fields = [
            "endpoint", "parameters", "exploit_vector",
            "impact", "source_tag", "sources", "promotion_status",
        ]
        for f in required_fields:
            assert f in result, f"Missing field: {f}"


# =============================================================================
# B) STREAM INGEST TESTS
# =============================================================================

class TestStreamIngest:
    """Test stream_ingest_new behavior."""

    def test_ingests_valid_records(self):
        """Valid records are ingested with ingested_ok > 0."""
        worker = _fresh_worker()
        pipeline = MagicMock()
        pipeline._records = {
            "CVE-2025-1234": _make_cve_record(source_name="NVD API v2"),
        }

        result = worker.stream_ingest_new(pipeline)
        assert isinstance(result, dict)
        assert result["ingested_ok"] == 1
        assert result["total_scanned"] == 1
        assert worker._total_ingested == 1

    def test_dedups_repeated_records(self):
        """Already-ingested records must be deduped."""
        worker = _fresh_worker()
        record = _make_cve_record(source_name="NVD API v2")
        pipeline = MagicMock()
        pipeline._records = {"CVE-2025-1234": record}

        # First ingest
        r1 = worker.stream_ingest_new(pipeline)
        assert r1["ingested_ok"] == 1

        # Second ingest — same records
        r2 = worker.stream_ingest_new(pipeline)
        assert r2["ingested_ok"] == 0
        assert r2["deduped"] == 1

    def test_updates_status_counters(self):
        """stream_ingest_new updates total_ingested, total_dropped, total_deduped."""
        worker = _fresh_worker()
        pipeline = MagicMock()
        pipeline._records = {
            "CVE-2025-1": _make_cve_record(
                cve_id="CVE-2025-1", source_name="NVD API v2"
            ),
            "CVE-2025-2": _make_cve_record(
                cve_id="CVE-2025-2", source_name="NVD API v2"
            ),
        }

        result = worker.stream_ingest_new(pipeline)
        assert result["ingested_ok"] == 2
        assert worker._total_ingested == 2
        assert worker._last_ingest_at is not None

    def test_drops_low_reliability(self):
        """Records with unknown sources are dropped."""
        worker = _fresh_worker()
        record = _make_cve_record()
        object.__setattr__(record, "provenance", [])
        pipeline = MagicMock()
        pipeline._records = {"CVE-2025-X": record}

        result = worker.stream_ingest_new(pipeline)
        assert result["ingested_ok"] == 0
        assert result["dropped_low_reliability"] == 1

    def test_bridge_not_loaded_returns_zero(self):
        """When bridge DLL not loaded, returns zero counts."""
        worker = _fresh_worker()
        worker._lib = None
        pipeline = MagicMock()
        pipeline._records = {"CVE-2025-1": _make_cve_record()}

        result = worker.stream_ingest_new(pipeline)
        assert result["ingested_ok"] == 0
        assert result["bridge_loaded"] is False


# =============================================================================
# C) BACKFILL TESTS
# =============================================================================

class TestBackfill:
    """Test backfill structured result."""

    def test_backfill_returns_structured_result(self):
        """Backfill returns full structured payload."""
        worker = _fresh_worker()
        worker._lib.bridge_get_count.return_value = 1
        worker._lib.bridge_get_verified_count.return_value = 0

        pipeline = MagicMock()
        pipeline._records = {
            "CVE-2025-1": _make_cve_record(
                cve_id="CVE-2025-1", source_name="NVD API v2"
            ),
        }

        result = worker.backfill(pipeline)
        assert result["success"] is True
        assert result["ingested"] == 1
        assert result["total_available"] == 1
        assert "duration_ms" in result
        assert "bridge_count" in result
        assert "bridge_verified_count" in result
        assert "attempted" in result
        assert "dropped" in result
        assert "deduped" in result

    def test_backfill_no_bridge_returns_failure(self):
        """Backfill without bridge DLL returns failure payload."""
        worker = _fresh_worker()
        worker._lib = None

        result = worker.backfill(MagicMock())
        assert result["success"] is False
        assert "Bridge DLL not loaded" in result.get("reason", "")
        assert result["ingested"] == 0


# =============================================================================
# D) READINESS CONSISTENCY
# =============================================================================

class TestReadinessConsistency:
    """Test bridge counters match readiness reporting."""

    def test_status_counters_consistent(self):
        """Worker status counters must be internally consistent."""
        worker = _fresh_worker()
        worker._lib.bridge_get_count.return_value = 5
        worker._lib.bridge_get_verified_count.return_value = 3

        pipeline = MagicMock()
        pipeline._records = {
            f"CVE-2025-{i}": _make_cve_record(
                cve_id=f"CVE-2025-{i}",
                description=f"Vuln {i}",
                source_name="NVD API v2",
            )
            for i in range(5)
        }

        worker.stream_ingest_new(pipeline)
        status = worker.get_status()

        assert status["total_ingested"] == 5
        assert status["bridge_count"] == 5
        assert status["bridge_verified_count"] == 3
        assert status["bridge_loaded"] is True

    def test_manifest_updates_after_ingest(self):
        """Manifest is updated after stream ingest with new samples."""
        worker = _fresh_worker()
        worker._lib.bridge_get_count.return_value = 1

        pipeline = MagicMock()
        pipeline._records = {
            "CVE-2025-1": _make_cve_record(source_name="NVD API v2"),
        }

        with patch.object(worker, "update_manifest") as mock_manifest:
            worker.stream_ingest_new(pipeline)
            mock_manifest.assert_called_once()

    def test_idempotency_key_deterministic(self):
        """Same content produces same idempotency key across calls."""
        k1 = BridgeIngestionWorker._compute_idempotency_key(
            "CVE-2025-1234", "buffer overflow"
        )
        k2 = BridgeIngestionWorker._compute_idempotency_key(
            "CVE-2025-1234", "buffer overflow"
        )
        assert k1 == k2

    def test_idempotency_key_differs_for_different_content(self):
        """Different content produces different idempotency key."""
        k1 = BridgeIngestionWorker._compute_idempotency_key(
            "CVE-2025-1234", "buffer overflow"
        )
        k2 = BridgeIngestionWorker._compute_idempotency_key(
            "CVE-2025-9999", "sql injection"
        )
        assert k1 != k2
