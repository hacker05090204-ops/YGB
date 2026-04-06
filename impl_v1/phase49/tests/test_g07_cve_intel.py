# test_g07_cve_intel.py
"""Tests for G07: CVE Intelligence"""

import inspect

import pytest
import backend.cve.cve_pipeline as pipeline_mod
import impl_v1.phase49.governors.g07_cve_intelligence as intel_mod
from impl_v1.phase49.governors.g07_cve_intelligence import (
    CVEIntelligenceEngine,
    CVEIntelligenceRecord,
    CVESeverity,
    CVEStatus,
    CVERecord,
    CVEQueryResult,
    IntelligenceCache,
    clear_cache,
    cache_record,
    get_cached,
    score_to_severity,
    create_cve_record,
    query_cves,
    correlate_target,
)


class FakeBridgeState:
    def __init__(self, samples):
        self._samples = list(samples)

    def read_samples(self, max_samples: int = 0):
        samples = list(self._samples)
        if max_samples:
            return samples[:max_samples]
        return samples


class TestEnumClosure:
    """Verify enums are closed."""
    
    def test_cve_severity_5_members(self):
        assert len(CVESeverity) == 5
    
    def test_cve_status_4_members(self):
        assert len(CVEStatus) == 4


class TestScoreToSeverity:
    """Test CVSS score to severity mapping."""
    
    def test_critical_9_plus(self):
        assert score_to_severity(9.0) == CVESeverity.CRITICAL
        assert score_to_severity(10.0) == CVESeverity.CRITICAL
    
    def test_high_7_to_9(self):
        assert score_to_severity(7.0) == CVESeverity.HIGH
        assert score_to_severity(8.9) == CVESeverity.HIGH
    
    def test_medium_4_to_7(self):
        assert score_to_severity(4.0) == CVESeverity.MEDIUM
        assert score_to_severity(6.9) == CVESeverity.MEDIUM
    
    def test_low_0_to_4(self):
        assert score_to_severity(0.1) == CVESeverity.LOW
        assert score_to_severity(3.9) == CVESeverity.LOW
    
    def test_none_zero(self):
        assert score_to_severity(0.0) == CVESeverity.NONE


class TestCVECache:
    """Test CVE caching."""
    
    def setup_method(self):
        clear_cache()
    
    def test_cache_and_retrieve(self):
        record = create_cve_record(
            cve_id="CVE-2024-1234",
            description="Test vulnerability",
            cvss_score=7.5,
            affected_products=["product-a"],
        )
        cached = get_cached("CVE-2024-1234")
        assert cached is not None
        assert cached.cve_id == "CVE-2024-1234"
    
    def test_get_nonexistent_returns_none(self):
        assert get_cached("CVE-DOES-NOT-EXIST") is None


class TestCreateCVERecord:
    """Test CVE record creation."""
    
    def setup_method(self):
        clear_cache()
    
    def test_basic_creation(self):
        record = create_cve_record(
            cve_id="CVE-2024-5678",
            description="SQL injection in web app",
            cvss_score=9.8,
            affected_products=["webapp-1.0"],
        )
        assert record.cve_id == "CVE-2024-5678"
        assert record.severity == CVESeverity.CRITICAL
        assert record.status == CVEStatus.PUBLISHED
    
    def test_with_references(self):
        record = create_cve_record(
            cve_id="CVE-2024-9999",
            description="Test",
            cvss_score=5.0,
            affected_products=["test"],
            references=["https://example.com/advisory"],
        )
        assert "https://example.com/advisory" in record.references
    
    def test_auto_cached(self):
        record = create_cve_record(
            cve_id="CVE-2024-AUTO",
            description="Auto cache test",
            cvss_score=6.0,
            affected_products=["test"],
        )
        assert get_cached("CVE-2024-AUTO") is not None


class TestQueryCVEs:
    """Test CVE querying."""
    
    def setup_method(self):
        clear_cache()
        # Add some test data
        create_cve_record("CVE-2024-0001", "SQL injection in MySQL", 9.0, ["mysql"])
        create_cve_record("CVE-2024-0002", "XSS in web framework", 7.0, ["webframework"])
        create_cve_record("CVE-2024-0003", "Low severity info leak", 3.0, ["app"])
    
    def test_query_by_description(self):
        result = query_cves("SQL")
        assert result.total_count >= 1
        assert any("SQL" in r.description for r in result.records)
    
    def test_query_by_product(self):
        result = query_cves("mysql")
        assert result.total_count >= 1
    
    def test_query_with_min_score(self):
        result = query_cves("", min_score=7.0)
        for record in result.records:
            assert record.cvss_score >= 7.0
    
    def test_query_result_has_id(self):
        result = query_cves("test")
        assert result.query_id.startswith("QRY-")
    
    def test_result_is_cached_flag(self):
        result = query_cves("test")
        assert result.cached is True

    def test_uses_runtime_pipeline_when_local_cache_empty(self):
        clear_cache()
        pipeline_mod._pipeline = None
        pipeline = pipeline_mod.get_pipeline()
        pipeline.ingest_record(
            cve_id="CVE-2026-1234",
            title="Runtime pipeline issue",
            description="Runtime pipeline vulnerability in edge worker",
            severity="HIGH",
            cvss_score=8.2,
            affected_products=["edge-worker"],
            references=["https://example.test/advisory"],
            is_exploited=False,
            source_id="nvd",
        )

        result = query_cves("edge-worker")

        assert result.total_count == 1
        assert result.cached is False
        assert result.records[0].cve_id == "CVE-2026-1234"


class TestCVEIntelligenceEngine:
    def setup_method(self):
        clear_cache()

    def test_unknown_cve_returns_none(self):
        pipeline = pipeline_mod.CVEPipeline()
        engine = CVEIntelligenceEngine(
            pipeline_getter=lambda: pipeline,
            bridge_state_getter=lambda: FakeBridgeState([]),
        )

        assert engine.enrich("CVE-2099-0001") is None

    def test_enrich_reads_local_pipeline_record(self):
        pipeline = pipeline_mod.CVEPipeline()
        pipeline.ingest_record(
            cve_id="CVE-2026-2001",
            title="Edge worker issue",
            description="Runtime pipeline vulnerability in edge worker",
            severity="HIGH",
            cvss_score=8.7,
            affected_products=["edge-worker"],
            references=["https://example.test/advisory"],
            is_exploited=True,
            source_id="nvd",
        )
        engine = CVEIntelligenceEngine(
            pipeline_getter=lambda: pipeline,
            bridge_state_getter=lambda: FakeBridgeState([]),
        )

        result = engine.enrich("CVE-2026-2001")

        assert isinstance(result, CVEIntelligenceRecord)
        assert result is not None
        assert result.cve_id == "CVE-2026-2001"
        assert result.severity_score == pytest.approx(8.7)
        assert result.affected_products == ["edge-worker"]
        assert result.intelligence_source == "local_pipeline"
        assert result.has_public_exploit is True

    def test_enrich_reads_bridge_state_when_pipeline_misses(self):
        pipeline = pipeline_mod.CVEPipeline()
        bridge_state = FakeBridgeState(
            [
                {
                    "endpoint": "CVE-2026-3001",
                    "parameters": '["bridge-app", "shared-lib"]',
                    "impact": "HIGH|CVSS:8.8",
                    "published_at": "2026-04-05T00:00:00+00:00",
                    "has_public_exploit": True,
                }
            ]
        )
        engine = CVEIntelligenceEngine(
            pipeline_getter=lambda: pipeline,
            bridge_state_getter=lambda: bridge_state,
        )

        result = engine.enrich("CVE-2026-3001")

        assert result is not None
        assert result.cve_id == "CVE-2026-3001"
        assert result.severity_score == pytest.approx(8.8)
        assert result.affected_products == ["bridge-app", "shared-lib"]
        assert result.published_at == "2026-04-05T00:00:00+00:00"
        assert result.intelligence_source == "local_pipeline"
        assert result.has_public_exploit is True

    def test_cache_ttl_is_respected(self):
        clock = {"now": 10_000.0}
        cache = IntelligenceCache(time_fn=lambda: clock["now"])
        pipeline = pipeline_mod.CVEPipeline()
        pipeline.ingest_record(
            cve_id="CVE-2026-4001",
            title="Initial record",
            description="Initial severity snapshot",
            severity="HIGH",
            cvss_score=7.1,
            affected_products=["cache-app"],
            references=[],
            is_exploited=False,
            source_id="nvd",
        )
        engine = CVEIntelligenceEngine(
            pipeline_getter=lambda: pipeline,
            bridge_state_getter=lambda: FakeBridgeState([]),
            cache=cache,
        )

        first = engine.enrich("CVE-2026-4001")
        pipeline.ingest_record(
            cve_id="CVE-2026-4001",
            title="Updated record",
            description="Updated severity snapshot",
            severity="CRITICAL",
            cvss_score=9.9,
            affected_products=["cache-app"],
            references=[],
            is_exploited=True,
            source_id="nvd",
        )

        cached = engine.enrich("CVE-2026-4001")
        clock["now"] += 24 * 60 * 60 + 1
        refreshed = engine.enrich("CVE-2026-4001")

        assert first is not None
        assert cached is not None
        assert refreshed is not None
        assert first.severity_score == pytest.approx(7.1)
        assert cached.severity_score == pytest.approx(7.1)
        assert refreshed.severity_score == pytest.approx(9.9)
        assert refreshed.has_public_exploit is True


class TestProductionSourcePath:
    def test_production_path_has_no_mock_or_live_fetch_language(self):
        source = inspect.getsource(intel_mod)

        assert "mock" not in source.lower()
        assert "fetch_cves_passive" not in source


class TestCorrelateTarget:
    """Test target correlation."""
    
    def setup_method(self):
        clear_cache()
        create_cve_record("CVE-2024-0001", "Vulnerability in ProductA", 8.0, ["ProductA"])
        create_cve_record("CVE-2024-0002", "Issue in ProductB", 6.0, ["ProductB"])
    
    def test_correlate_by_product(self):
        result = correlate_target("TargetCorp", ["ProductA"])
        assert result.total_count >= 1
    
    def test_correlation_result_has_id(self):
        result = correlate_target("Test", ["test"])
        assert result.query_id.startswith("COR-")
    
    def test_correlation_dedupes(self):
        result = correlate_target("ProductA", ["ProductA", "ProductA"])
        cve_ids = [r.cve_id for r in result.records]
        assert len(cve_ids) == len(set(cve_ids))  # No duplicates


class TestDataclassFrozen:
    """Verify dataclasses are frozen."""
    
    def setup_method(self):
        clear_cache()
    
    def test_cve_record_frozen(self):
        record = create_cve_record("CVE-TEST", "Test", 5.0, ["test"])
        with pytest.raises(AttributeError):
            record.cve_id = "CVE-MODIFIED"
    
    def test_query_result_frozen(self):
        result = query_cves("test")
        with pytest.raises(AttributeError):
            result.total_count = 999
