# test_g34_duplicate_intelligence.py
"""Tests for G34 Duplicate Intelligence."""

import pytest

from impl_v1.phase49.governors.g34_duplicate_intelligence import (
    # Enums
    DuplicateConfidence,
    # Data structures
    DuplicateAuditLog,
    DuplicateIntelligenceEngine,
    SimilarReport,
    DuplicateAnalysisResult,
    DuplicateRecord,
    ReportFingerprint,
    # Functions
    create_report_fingerprint,
    analyze_duplicates,
    get_duplicate_stats,
    quick_duplicate_check,
    # Guards
    can_ignore_duplicate_score,
    can_submit_duplicate,
    can_bypass_duplicate_check,
    can_lower_threshold,
)


def _build_report(report_id, title, cve_ids=(), affected_product=()):
    return {
        "report_id": report_id,
        "title": title,
        "cve_ids": list(cve_ids),
        "affected_product": list(affected_product),
    }


class TestDuplicateConfidenceEnum:
    """Tests for DuplicateConfidence enum."""
    
    def test_has_5_levels(self):
        assert len(DuplicateConfidence) == 5
    
    def test_has_certain(self):
        assert DuplicateConfidence.CERTAIN.value == "CERTAIN"
    
    def test_has_unique(self):
        assert DuplicateConfidence.UNIQUE.value == "UNIQUE"


class TestReportFingerprint:
    """Tests for ReportFingerprint dataclass."""
    
    def test_create_fingerprint(self):
        fp = create_report_fingerprint(
            endpoint="/api/users",
            params="id=1&name=test",
            cve_refs=("CVE-2024-1234",),
            reproduction_steps="1. Send request 2. Observe response",
        )
        assert fp.fingerprint_id.startswith("FPR-")
        assert len(fp.endpoint_hash) == 32
        assert "CVE-2024-1234" in fp.cve_refs
    
    def test_is_frozen(self):
        fp = create_report_fingerprint("/api", "", tuple(), "steps")
        with pytest.raises(AttributeError):
            fp.endpoint_hash = "changed"


class TestAnalyzeDuplicates:
    """Tests for analyze_duplicates function."""
    
    def test_detects_exact_duplicate(self):
        current = create_report_fingerprint("/api/users", "id=1", ("CVE-2024-1234",), "steps")
        known = create_report_fingerprint("/api/users", "id=1", ("CVE-2024-1234",), "steps")
        
        result = analyze_duplicates(
            current_fingerprint=current,
            known_reports=(("RPT-001", known),),
            threshold=70,
        )
        
        assert result.is_duplicate == True
        assert result.duplicate_probability >= 70
    
    def test_detects_unique_report(self):
        current = create_report_fingerprint("/api/orders", "order_id=99", tuple(), "different steps")
        known = create_report_fingerprint("/api/users", "id=1", ("CVE-2024-1234",), "steps")
        
        result = analyze_duplicates(
            current_fingerprint=current,
            known_reports=(("RPT-001", known),),
            threshold=70,
        )
        
        assert result.is_duplicate == False
        assert result.confidence == DuplicateConfidence.UNIQUE or result.duplicate_probability < 40
    
    def test_has_result_id(self):
        current = create_report_fingerprint("/api", "", tuple(), "")
        result = analyze_duplicates(current, tuple(), 70)
        assert result.result_id.startswith("DUP-")
    
    def test_has_determinism_hash(self):
        current = create_report_fingerprint("/api", "", tuple(), "")
        result = analyze_duplicates(current, tuple(), 70)
        assert len(result.determinism_hash) == 32
    
    def test_returns_recommendation(self):
        current = create_report_fingerprint("/api", "", tuple(), "")
        result = analyze_duplicates(current, tuple(), 70)
        assert len(result.recommendation) > 0


class TestQuickDuplicateCheck:
    """Tests for quick_duplicate_check function."""
    
    def test_exact_match(self):
        prob = quick_duplicate_check(
            endpoint="/api/users",
            known_endpoints=("/api/users",),
        )
        assert prob == 100
    
    def test_no_match(self):
        prob = quick_duplicate_check(
            endpoint="/api/orders",
            known_endpoints=("/api/users",),
        )
        assert prob < 100
    
    def test_empty_known(self):
        prob = quick_duplicate_check(
            endpoint="/api/users",
            known_endpoints=tuple(),
        )
        assert prob == 0


class TestDuplicateIntelligenceEngine:
    """Focused tests for Batch 4 Group A duplicate intelligence."""

    def test_exact_cve_match_returns_duplicate(self):
        engine = DuplicateIntelligenceEngine(
            stored_reports=[
                _build_report(
                    "RPT-001",
                    "Remote code execution in admin portal",
                    cve_ids=("CVE-2025-1111",),
                    affected_product=("admin-portal",),
                )
            ]
        )

        result = engine.evaluate(
            _build_report(
                "RPT-002",
                "Completely different wording",
                cve_ids=("CVE-2025-1111",),
                affected_product=("separate-service",),
            )
        )

        assert isinstance(result, DuplicateRecord)
        assert result.report_id == "RPT-001"
        assert result.decision == "DUPLICATE"
        assert result.similarity_score > 0.85
        assert result.matched_fields == ["cve_id"]

    def test_no_overlap_returns_unique(self):
        engine = DuplicateIntelligenceEngine(
            stored_reports=[
                _build_report(
                    "RPT-001",
                    "SQL injection in login endpoint",
                    cve_ids=("CVE-2025-2222",),
                    affected_product=("auth-gateway",),
                )
            ]
        )

        result = engine.evaluate(
            _build_report(
                "RPT-002",
                "Cross site scripting in feedback form",
                cve_ids=(),
                affected_product=("feedback-ui",),
            )
        )

        assert result.report_id == ""
        assert result.decision == "UNIQUE"
        assert result.similarity_score == 0.0
        assert result.matched_fields == []

    def test_thresholds_are_applied_correctly(self):
        engine = DuplicateIntelligenceEngine(
            stored_reports=[
                _build_report(
                    "RPT-BASE",
                    "SQL injection in login form",
                    affected_product=("customer-portal",),
                )
            ]
        )

        likely = engine.evaluate(
            _build_report(
                "RPT-LIKELY",
                "SQL injection in login form",
                affected_product=("customer-portal",),
            )
        )

        unique = engine.evaluate(
            _build_report(
                "RPT-UNIQUE",
                "Broken access control in admin export",
                affected_product=("backoffice",),
            )
        )

        assert likely.decision == "LIKELY_DUPLICATE"
        assert likely.similarity_score == pytest.approx(2 / 3)
        assert 0.6 < likely.similarity_score <= 0.85
        assert unique.decision == "UNIQUE"
        assert unique.similarity_score <= 0.6

    def test_audit_log_caps_at_5000_entries(self):
        audit_log = DuplicateAuditLog()

        for index in range(5002):
            audit_log.append(
                DuplicateRecord(
                    report_id=f"RPT-{index:04d}",
                    similarity_score=0.1,
                    matched_fields=[],
                    decision="UNIQUE",
                )
            )

        entries = audit_log.entries()
        assert len(entries) == 5000
        assert entries[0].report_id == "RPT-0002"
        assert entries[-1].report_id == "RPT-5001"

    def test_duplicate_stats_track_counts_and_mean_similarity(self):
        engine = DuplicateIntelligenceEngine(
            stored_reports=[
                _build_report(
                    "RPT-001",
                    "Server-side request forgery in image fetcher",
                    cve_ids=("CVE-2025-3333",),
                    affected_product=("media-processor",),
                )
            ]
        )

        duplicate = engine.evaluate(
            _build_report(
                "RPT-002",
                "Different title but same CVE",
                cve_ids=("CVE-2025-3333",),
                affected_product=("other-service",),
            )
        )
        unique = engine.evaluate(
            _build_report(
                "RPT-003",
                "Privilege escalation in billing role assignment",
                cve_ids=(),
                affected_product=("billing-console",),
            )
        )

        stats = engine.get_duplicate_stats()
        assert stats["total_evaluated"] == 2
        assert stats["duplicates_found"] == 1
        assert stats["unique_found"] == 1
        assert stats["mean_similarity"] == pytest.approx(
            (duplicate.similarity_score + unique.similarity_score) / 2
        )

    def test_module_level_duplicate_stats_start_empty(self):
        stats = get_duplicate_stats()
        assert set(stats) == {
            "total_evaluated",
            "duplicates_found",
            "unique_found",
            "mean_similarity",
        }


class TestCanIgnoreDuplicateScore:
    """Tests for can_ignore_duplicate_score guard."""
    
    def test_returns_false(self):
        can_ignore, reason = can_ignore_duplicate_score()
        assert can_ignore == False
    
    def test_has_reason(self):
        can_ignore, reason = can_ignore_duplicate_score()
        assert "duplicate" in reason.lower()


class TestCanSubmitDuplicate:
    """Tests for can_submit_duplicate guard."""
    
    def test_returns_false(self):
        can_submit, reason = can_submit_duplicate()
        assert can_submit == False
    
    def test_has_reason(self):
        can_submit, reason = can_submit_duplicate()
        assert len(reason) > 0


class TestCanBypassDuplicateCheck:
    """Tests for can_bypass_duplicate_check guard."""
    
    def test_returns_false(self):
        can_bypass, reason = can_bypass_duplicate_check()
        assert can_bypass == False
    
    def test_reason_mentions_mandatory(self):
        can_bypass, reason = can_bypass_duplicate_check()
        assert "mandatory" in reason.lower()


class TestCanLowerThreshold:
    """Tests for can_lower_threshold guard."""
    
    def test_returns_false(self):
        can_lower, reason = can_lower_threshold()
        assert can_lower == False
    
    def test_has_reason(self):
        can_lower, reason = can_lower_threshold()
        assert "threshold" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive test that ALL guards return False."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_ignore_duplicate_score,
            can_submit_duplicate,
            can_bypass_duplicate_check,
            can_lower_threshold,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result == False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0, f"Guard {guard.__name__} has empty reason!"


class TestFrozenDatastructures:
    """Tests that all datastructures are frozen."""
    
    def test_duplicate_analysis_result_is_frozen(self):
        current = create_report_fingerprint("/api", "", tuple(), "")
        result = analyze_duplicates(current, tuple(), 70)
        with pytest.raises(AttributeError):
            result.is_duplicate = True


class TestNoForbiddenImports:
    """Tests that G34 has no forbidden imports."""
    
    def test_no_forbidden_imports(self):
        import impl_v1.phase49.governors.g34_duplicate_intelligence as g34
        import inspect
        
        source = inspect.getsource(g34)
        
        forbidden = ["subprocess", "socket", "selenium", "playwright"]
        for name in forbidden:
            assert f"import {name}" not in source
