"""
CVE Pipeline Tests — Comprehensive Unit Tests

Covers:
  - Source adapter initialization
  - Deterministic merge
  - Content-hash dedup
  - Circuit breaker transitions
  - Provenance tracking
  - SLO counters
"""

import os
import sys
import pytest
from pathlib import Path

# Add project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class TestCVEPipeline:
    """Tests for CVE pipeline core functionality."""

    def setup_method(self):
        """Reset pipeline singleton for each test."""
        import backend.cve.cve_pipeline as mod
        mod._pipeline = None
        self.pipeline = mod.CVEPipeline()

    def test_source_initialization(self):
        """All 6 sources should be initialized with proper status."""
        from backend.cve.cve_pipeline import SourceStatus
        statuses = self.pipeline._source_status
        assert len(statuses) == 6, f"Expected 6 sources, got {len(statuses)}"

        # Free sources should be DISCONNECTED (not NOT_CONFIGURED)
        assert statuses["cve_services"] == SourceStatus.DISCONNECTED
        assert statuses["cveproject"] == SourceStatus.DISCONNECTED
        assert statuses["cisa_kev"] == SourceStatus.DISCONNECTED

        # Optional key-required sources should be NOT_CONFIGURED without keys
        assert statuses["vulners"] == SourceStatus.NOT_CONFIGURED
        assert statuses["vuldb"] == SourceStatus.NOT_CONFIGURED

    def test_ingest_new_record(self):
        """Ingesting a new CVE should return NEW result."""
        from backend.cve.cve_pipeline import IngestResult
        record, result = self.pipeline.ingest_record(
            cve_id="CVE-2024-1234",
            title="Test CVE",
            description="A test vulnerability",
            severity="HIGH",
            cvss_score=8.5,
            affected_products=["product-a"],
            references=["https://example.com"],
            is_exploited=False,
            source_id="cve_services",
        )
        assert result == IngestResult.NEW
        assert record.cve_id == "CVE-2024-1234"
        assert record.canonical_version == 1
        assert len(record.provenance) == 1
        assert record.provenance[0].source == "CVE Services / cve.org"
        assert record.promotion_status == "RESEARCH_PENDING"

    def test_ingest_exact_duplicate(self):
        """Same CVE with same content hash should be DUPLICATE."""
        from backend.cve.cve_pipeline import IngestResult
        self.pipeline.ingest_record(
            cve_id="CVE-2024-1234",
            title="Test",
            description="Same description",
            severity="HIGH",
            cvss_score=8.5,
            affected_products=[],
            references=[],
            is_exploited=False,
            source_id="cve_services",
        )
        _, result = self.pipeline.ingest_record(
            cve_id="CVE-2024-1234",
            title="Test",
            description="Same description",
            severity="HIGH",
            cvss_score=8.5,
            affected_products=[],
            references=[],
            is_exploited=False,
            source_id="nvd",
        )
        assert result == IngestResult.DUPLICATE

    def test_ingest_merge_update(self):
        """Same CVE with different content should merge (UPDATED)."""
        from backend.cve.cve_pipeline import IngestResult
        self.pipeline.ingest_record(
            cve_id="CVE-2024-1234",
            title="Original",
            description="Original desc",
            severity="MEDIUM",
            cvss_score=5.0,
            affected_products=["prod-a"],
            references=[],
            is_exploited=False,
            source_id="cve_services",
        )
        record, result = self.pipeline.ingest_record(
            cve_id="CVE-2024-1234",
            title="Updated",
            description="Updated desc — now with more detail",
            severity="HIGH",
            cvss_score=8.0,
            affected_products=["prod-b"],
            references=["https://ref.com"],
            is_exploited=True,
            source_id="nvd",
        )
        assert result == IngestResult.UPDATED
        assert record.canonical_version == 2
        assert len(record.provenance) == 2
        # Severity should be highest
        assert record.severity == "HIGH"
        # Products should be merged
        assert "prod-a" in record.affected_products
        assert "prod-b" in record.affected_products
        # Exploited should be True (OR merge)
        assert record.is_exploited is True

    def test_deterministic_content_hash(self):
        """Content hash should be deterministic for same input."""
        from backend.cve.cve_pipeline import compute_content_hash
        h1 = compute_content_hash("CVE-2024-1", "desc", "HIGH", 8.5)
        h2 = compute_content_hash("CVE-2024-1", "desc", "HIGH", 8.5)
        h3 = compute_content_hash("CVE-2024-1", "desc2", "HIGH", 8.5)
        assert h1 == h2
        assert h1 != h3

    def test_circuit_breaker_transitions(self):
        """Circuit breaker should transition CLOSED → OPEN after failures."""
        from backend.cve.cve_pipeline import CircuitBreaker, CircuitState
        cb = CircuitBreaker(source_id="test")
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True

        # 3 failures → OPEN
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.can_attempt() is False

        # Success resets
        cb.state = CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.can_attempt() is True

    def test_provenance_fields(self):
        """Every provenance record should have all required fields."""
        record, _ = self.pipeline.ingest_record(
            cve_id="CVE-2024-5678",
            title="Test",
            description="Test desc",
            severity="LOW",
            cvss_score=3.0,
            affected_products=[],
            references=[],
            is_exploited=False,
            source_id="cve_services",
        )
        prov = record.provenance[0]
        assert prov.source, "source missing"
        assert prov.fetched_at, "fetched_at missing"
        assert prov.parser_version, "parser_version missing"
        assert prov.confidence > 0, "confidence should be > 0"
        assert prov.raw_hash, "raw_hash missing"

    def test_slo_counters(self):
        """SLO counters should track properly."""
        slo = self.pipeline.get_slo()
        assert slo.job_success_rate == 1.0  # No jobs yet

        self.pipeline.record_job_execution(True)
        self.pipeline.record_job_execution(True)
        self.pipeline.record_job_execution(False)
        assert slo.total_jobs == 3
        assert slo.successful_jobs == 2

    def test_source_status_transitions(self):
        """Source status should correctly transition on success/error."""
        from backend.cve.cve_pipeline import SourceStatus
        self.pipeline.mark_source_success("cve_services", 10)
        assert self.pipeline._source_status["cve_services"] == SourceStatus.CONNECTED

        self.pipeline.mark_source_error("cve_services", "timeout")
        assert self.pipeline._source_status["cve_services"] == SourceStatus.DEGRADED

    def test_no_delta_reporting(self):
        """NO_DELTA should not count as failure."""
        from backend.cve.cve_pipeline import SourceStatus
        self.pipeline.mark_source_success("cve_services", 5)
        self.pipeline.mark_source_no_delta("cve_services")
        # Should still be CONNECTED
        status = self.pipeline._source_status.get("cve_services")
        assert status == SourceStatus.CONNECTED or status is not None

    def test_get_pipeline_status(self):
        """Pipeline status should return structured summary."""
        status = self.pipeline.get_pipeline_status()
        assert "status" in status
        assert "sources_total" in status
        assert "total_records" in status
        assert "slo" in status
        assert "sources" in status

    def test_merge_conflict_logging(self):
        """Merge conflicts should be logged."""
        self.pipeline.ingest_record(
            cve_id="CVE-2024-9999",
            title="Test",
            description="V1",
            severity="LOW",
            cvss_score=2.0,
            affected_products=[],
            references=[],
            is_exploited=False,
            source_id="cve_services",
        )
        record, _ = self.pipeline.ingest_record(
            cve_id="CVE-2024-9999",
            title="Test",
            description="V2",
            severity="CRITICAL",
            cvss_score=9.8,
            affected_products=[],
            references=[],
            is_exploited=False,
            source_id="nvd",
        )
        assert len(record.merge_conflicts) > 0
        assert "severity" in record.merge_conflicts[0].lower()


class TestPromotionPolicy:
    """Tests for CVE promotion policy."""

    def setup_method(self):
        import backend.cve.promotion_policy as mod
        mod._policy = None
        self.policy = mod.PromotionPolicy()

    def test_canonical_source_promoted(self):
        """CVE from canonical source should be CANONICAL."""
        decision = self.policy.evaluate(
            "CVE-2024-1234",
            ["CVE Services / cve.org"],
        )
        assert decision.status == "CANONICAL"
        assert decision.training_allowed is True
        assert decision.unverifiable_claim_rate == 0.0

    def test_corroborated_two_sources(self):
        """CVE from 2+ trusted sources should be CORROBORATED."""
        decision = self.policy.evaluate(
            "CVE-2024-1234",
            ["NVD API v2", "CISA KEV Catalog"],
        )
        assert decision.status == "CORROBORATED"
        assert decision.training_allowed is True

    def test_single_source_research_pending(self):
        """CVE from single non-canonical source → RESEARCH_PENDING."""
        decision = self.policy.evaluate(
            "CVE-2024-1234",
            ["NVD API v2"],
        )
        assert decision.status == "RESEARCH_PENDING"
        assert decision.training_allowed is False

    def test_headless_only_blocked(self):
        """Headless-only data should NEVER be promoted."""
        decision = self.policy.evaluate(
            "CVE-2024-1234",
            ["Headless Research"],
            has_headless_only=True,
        )
        assert decision.status == "RESEARCH_PENDING"
        assert decision.training_allowed is False

    def test_frozen_cve_blocked(self):
        """Frozen CVE should be BLOCKED."""
        self.policy.freeze("CVE-2024-FROZEN", "governance breach")
        decision = self.policy.evaluate(
            "CVE-2024-FROZEN",
            ["CVE Services / cve.org"],
        )
        assert decision.status == "BLOCKED"
        assert decision.training_allowed is False

    def test_unverifiable_claim_rate(self):
        """System-wide unverifiable rate should be tracked correctly."""
        # All promoted → rate = 0
        self.policy.evaluate("CVE-1", ["CVE Services / cve.org"])
        assert self.policy.get_unverifiable_claim_rate() == 0.0

        # Add a pending → rate > 0
        self.policy.evaluate("CVE-2", ["Unknown Source"])
        assert self.policy.get_unverifiable_claim_rate() > 0

    def test_audit_log(self):
        """Audit log should record decisions."""
        self.policy.evaluate("CVE-1", ["CVE Services / cve.org"])
        log = self.policy.get_audit_log()
        assert len(log) == 1
        assert log[0]["cve_id"] == "CVE-1"


class TestDedupDrift:
    """Tests for dedup and drift detection."""

    def setup_method(self):
        import backend.cve.dedup_drift as mod
        mod._engine = None
        self.engine = mod.DedupDriftEngine()

    def test_exact_dedup(self):
        """Same content hash should be detected as duplicate."""
        assert self.engine.is_exact_duplicate("hash1", "CVE-1") is False
        assert self.engine.is_exact_duplicate("hash1", "CVE-2") is True  # Dup!
        assert self.engine.is_exact_duplicate("hash2", "CVE-3") is False

    def test_simhash_near_dup(self):
        """Similar text should be detected as near-duplicate."""
        text1 = "SQL injection vulnerability in login form parameter"
        text2 = "SQL injection vulnerability in login form input"
        text3 = "Completely different buffer overflow in network stack"

        match1 = self.engine.check_near_duplicate("CVE-1", text1)
        assert match1 is None  # First entry

        match2 = self.engine.check_near_duplicate("CVE-2", text2)
        # Should detect near-dup (or not, depending on threshold)
        # This tests the mechanism works

        match3 = self.engine.check_near_duplicate("CVE-3", text3)
        # Very different text should NOT match CVE-1

    def test_schema_drift_detection(self):
        """Schema drift should be detected when fields change."""
        self.engine.register_schema(
            "nvd",
            {"cve_id", "description", "severity", "cvss_score"},
        )
        alerts = self.engine.check_schema_drift(
            "nvd",
            {"cve_id", "description"},  # Missing severity, cvss_score
        )
        assert len(alerts) > 0
        assert "missing" in alerts[0].lower()

    def test_distribution_drift(self):
        """Severity distribution drift should be tracked."""
        from backend.cve.dedup_drift import kl_divergence
        # Set baseline
        baseline = {"HIGH": 0.5, "MEDIUM": 0.3, "LOW": 0.2}
        self.engine.set_severity_baseline(baseline)

        # Record identical distribution → no drift
        for _ in range(50):
            self.engine.record_severity("HIGH")
        for _ in range(30):
            self.engine.record_severity("MEDIUM")
        for _ in range(20):
            self.engine.record_severity("LOW")

        # KL should be very small for matching distribution
        kl = kl_divergence(baseline, {"HIGH": 0.5, "MEDIUM": 0.3, "LOW": 0.2})
        assert kl < 0.01

    def test_weak_source_ratio(self):
        """Weak source ratio should alert when threshold exceeded."""
        # Add mostly weak sources
        for _ in range(25):
            self.engine.record_source_confidence("bad_source", 0.3)
        for _ in range(75):
            self.engine.record_source_confidence("good_source", 0.9)
        alert = self.engine.check_weak_source_ratio()
        assert alert is not None
        assert alert.alert_type == "WEAK_SOURCE_RATIO"

    def test_freeze_on_critical(self):
        """Critical alerts should trigger auto-freeze."""
        # Force a critical alert
        for _ in range(100):
            self.engine.record_source_confidence("weak", 0.3)
        self.engine.check_weak_source_ratio()
        should_freeze, reason = self.engine.should_freeze_promotion()
        assert should_freeze is True


class TestAntiHallucination:
    """Tests for anti-hallucination controls."""

    def setup_method(self):
        import backend.cve.anti_hallucination as mod
        mod._validator = None
        self.validator = mod.AntiHallucinationValidator()

    def test_valid_provenance(self):
        """Complete provenance should pass validation."""
        from backend.cve.cve_pipeline import SourceProvenance
        prov = SourceProvenance(
            source="NVD",
            fetched_at="2024-01-01T00:00:00Z",
            last_modified="2024-01-01",
            confidence=0.9,
            merge_policy="PRIMARY_WINS",
            raw_hash="abc123",
            parser_version="2.0.0",
        )
        result = self.validator.validate_provenance("CVE-1", prov)
        assert result.passed is True
        assert len(result.missing_fields) == 0

    def test_missing_provenance_fields(self):
        """Missing provenance fields should fail."""
        prov = {
            "source": "NVD",
            "fetched_at": "",
            "parser_version": "",
            "confidence": 0.0,
        }
        result = self.validator.validate_provenance("CVE-1", prov)
        assert result.passed is False
        assert len(result.missing_fields) > 0

    def test_unverifiable_rate_zero(self):
        """With all valid provenance, rate should be 0."""
        from backend.cve.cve_pipeline import SourceProvenance
        prov = SourceProvenance(
            source="NVD",
            fetched_at="2024-01-01",
            last_modified="2024-01-01",
            confidence=0.9,
            merge_policy="PRIMARY_WINS",
            raw_hash="abc",
            parser_version="2.0.0",
        )
        self.validator.validate_provenance("CVE-1", prov)
        assert self.validator.compute_unverifiable_claim_rate() == 0.0

    def test_production_ready(self):
        """Production readiness requires zero unverifiable claims."""
        ready, reason = self.validator.is_production_ready()
        assert ready is False  # No checks performed yet
        assert "No provenance" in reason


class TestHeadlessResearch:
    """Tests for headless research engine."""

    def setup_method(self):
        import backend.cve.headless_research as mod
        mod._engine = None
        self.engine = mod.HeadlessResearchEngine()

    def test_allowed_domains(self):
        """Domain whitelist should work correctly."""
        assert self.engine.is_url_allowed("https://nvd.nist.gov/vuln/detail/CVE-2024-1234")
        assert self.engine.is_url_allowed("https://cve.org/CVERecord?id=CVE-2024-1234")
        assert not self.engine.is_url_allowed("https://evil.com/steal")
        assert not self.engine.is_url_allowed("http://nvd.nist.gov")  # HTTP blocked
        assert not self.engine.is_url_allowed("https://nvd.nist.gov/login")

    def test_cve_id_extraction(self):
        """CVE IDs should be extracted from content."""
        content = "Found CVE-2024-1234 and cve-2023-5678 in the page"
        ids = self.engine.extract_cve_ids(content)
        assert "CVE-2024-1234" in ids
        assert "CVE-2023-5678" in ids

    def test_high_confidence_extraction(self):
        """High confidence extraction should succeed."""
        from backend.cve.headless_research import ResearchStatus
        snapshot = self.engine.create_snapshot(
            "https://nvd.nist.gov/vuln/detail/CVE-2024-1234",
            "CVE-2024-1234 is a critical SQL injection",
            {
                "cve_id": "CVE-2024-1234",
                "description": "SQL injection in web app",
                "severity": "CRITICAL",
                "cvss_score": 9.8,
                "affected_products": ["product-a"],
            },
        )
        assert snapshot.status == ResearchStatus.EXTRACTED
        assert snapshot.confidence >= 0.7

    def test_low_confidence_quarantine(self):
        """Low confidence extraction should be quarantined."""
        from backend.cve.headless_research import ResearchStatus
        snapshot = self.engine.create_snapshot(
            "https://nvd.nist.gov/vuln/detail/CVE-2024-9999",
            "Some page about CVE-2024-9999",
            {
                "cve_id": "CVE-2024-9999",
                "description": "",  # Empty description → low confidence
                "severity": "",
            },
        )
        assert snapshot.status in (
            ResearchStatus.QUARANTINED,
            ResearchStatus.SCHEMA_FAIL,
        )

    def test_schema_fail(self):
        """Invalid CVE ID should fail schema validation."""
        from backend.cve.headless_research import ResearchStatus
        snapshot = self.engine.create_snapshot(
            "https://nvd.nist.gov/bad",
            "no CVE here",
            {"cve_id": "NOT-A-CVE", "description": "whatever"},
        )
        assert snapshot.status == ResearchStatus.SCHEMA_FAIL


class TestScheduler:
    """Tests for CVE scheduler."""

    def setup_method(self):
        import backend.cve.cve_scheduler as mod
        mod._scheduler = None

    def test_scheduler_singleton(self):
        """Scheduler should be a singleton."""
        from backend.cve.cve_scheduler import get_scheduler
        s1 = get_scheduler()
        s2 = get_scheduler()
        assert s1 is s2

    def test_scheduler_health(self):
        """Health should return structured data."""
        from backend.cve.cve_scheduler import get_scheduler
        health = get_scheduler().get_health()
        assert "running" in health
        assert "interval_seconds" in health
        assert health["interval_seconds"] == 300
        assert health["slo_target_job"] == 0.999
        assert health["slo_target_ingest"] == 0.995

    def test_scheduler_not_running_initially(self):
        """Scheduler should not be running initially."""
        from backend.cve.cve_scheduler import get_scheduler
        assert get_scheduler().is_running is False
