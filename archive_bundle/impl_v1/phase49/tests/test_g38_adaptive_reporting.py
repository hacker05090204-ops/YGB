# Test G38 Adaptive Reporting
"""
Tests for G38 Adaptive Report Pattern Engine.

100% coverage required.
"""

import pytest

from impl_v1.phase49.governors.g38_adaptive_reporting import (
    # Enums
    ToneProfile,
    SectionOrder,
    # Dataclasses
    ReportPattern,
    PatternUsage,
    PatternRegistry,
    REPORT_PATTERNS,
    # Functions
    create_pattern_registry,
    get_available_patterns,
    select_next_pattern,
    record_pattern_usage,
    format_intro,
    format_conclusion,
    order_sections,
    generate_adaptive_report,
    # Guards
    can_pattern_manipulate_content,
    can_pattern_deceive,
    can_pattern_bypass_proof,
    can_pattern_hide_duplicates,
)


class TestToneProfile:
    """Tests for ToneProfile enum."""
    
    def test_has_technical(self):
        assert ToneProfile.TECHNICAL.value == "TECHNICAL"
    
    def test_has_business(self):
        assert ToneProfile.BUSINESS.value == "BUSINESS"


class TestSectionOrder:
    """Tests for SectionOrder enum."""
    
    def test_has_impact_first(self):
        assert SectionOrder.IMPACT_FIRST.value == "IMPACT_FIRST"
    
    def test_has_evidence_first(self):
        assert SectionOrder.EVIDENCE_FIRST.value == "EVIDENCE_FIRST"


class TestReportPatterns:
    """Tests for pattern definitions."""
    
    def test_has_8_patterns(self):
        assert len(REPORT_PATTERNS) == 8
    
    def test_patterns_have_unique_ids(self):
        ids = [p.pattern_id for p in REPORT_PATTERNS]
        assert len(ids) == len(set(ids))


class TestPatternRegistry:
    """Tests for pattern registry."""
    
    def test_create_registry(self):
        registry = create_pattern_registry(cooldown_hours=12)
        
        assert registry.registry_id.startswith("REG-")
        assert len(registry.patterns) == 8
        assert registry.cooldown_hours == 12
    
    def test_get_available_patterns(self):
        registry = create_pattern_registry()
        current = "2026-02-01T12:00:00Z"
        
        available = get_available_patterns(registry, current)
        
        assert len(available) == 8  # All available initially


class TestPatternSelection:
    """Tests for pattern selection."""
    
    def test_select_next_pattern(self):
        registry = create_pattern_registry()
        current = "2026-02-01T12:00:00Z"
        
        pattern = select_next_pattern(registry, current)
        
        assert pattern.pattern_id.startswith("PAT-")
    
    def test_pattern_rotation(self):
        registry = create_pattern_registry()
        current = "2026-02-01T12:00:00Z"
        
        # Select first pattern
        p1 = select_next_pattern(registry, current)
        registry = record_pattern_usage(registry, p1, "RPT-001", current)
        
        # Select second pattern - should be different
        current2 = "2026-02-01T12:01:00Z"
        p2 = select_next_pattern(registry, current2)
        
        # Different pattern selected (rotation)
        # Note: may be same if cooldown not expired, but prefer unused
        assert p2.pattern_id != p1.pattern_id or len(get_available_patterns(registry, current2)) == 0


class TestFormatting:
    """Tests for formatting functions."""
    
    def test_format_intro_direct(self):
        intro = format_intro("direct", "SQLi", "HIGH")
        assert "SQLi" in intro
        assert "HIGH" in intro
    
    def test_format_intro_contextual(self):
        intro = format_intro("contextual", "XSS", "MEDIUM")
        assert "XSS" in intro
        assert "security testing" in intro.lower()
    
    def test_format_conclusion_recommendation(self):
        conclusion = format_conclusion("recommendation", "Fix immediately")
        assert "Recommendation" in conclusion
    
    def test_format_conclusion_next_steps(self):
        conclusion = format_conclusion("next_steps", "Patch the code")
        assert "Next Steps" in conclusion


class TestSectionOrdering:
    """Tests for section ordering."""
    
    def test_impact_first(self):
        sections = {
            "impact": "HIGH",
            "technical": "SQL injection",
            "steps": "Step 1",
            "evidence": "Screenshot",
        }
        
        ordered = order_sections(SectionOrder.IMPACT_FIRST, sections)
        
        assert ordered[0][0] == "impact"
    
    def test_technical_first(self):
        sections = {"impact": "H", "technical": "T"}
        
        ordered = order_sections(SectionOrder.TECHNICAL_FIRST, sections)
        
        assert ordered[0][0] == "technical"


class TestGenerateAdaptiveReport:
    """Tests for adaptive report generation."""
    
    def test_generates_report(self):
        registry = create_pattern_registry()
        current = "2026-02-01T12:00:00Z"
        
        report, updated = generate_adaptive_report(
            registry=registry,
            title="SQL Injection",
            technical_details="Parameter 'id' is vulnerable",
            impact="Database compromise",
            steps=("Navigate to /login", "Enter payload", "Observe"),
            evidence=("screenshot.png", "video.webm"),
            recommendation="Use parameterized queries",
            current_time=current,
        )
        
        assert "SQL Injection" in report
        assert "Database compromise" in report
        assert "parameterized queries" in report
        assert len(updated.usage_history) == 1
    
    def test_different_patterns_produce_different_structure(self):
        registry = create_pattern_registry()
        
        r1, reg1 = generate_adaptive_report(
            registry,
            "Bug1", "Tech1", "Impact1",
            ("Step1",), ("Ev1",), "Fix1",
            "2026-02-01T12:00:00Z",
        )
        
        r2, reg2 = generate_adaptive_report(
            reg1,
            "Bug2", "Tech2", "Impact2",
            ("Step2",), ("Ev2",), "Fix2",
            "2026-02-01T12:01:00Z",
        )
        
        # Different pattern IDs used
        assert reg1.usage_history[-1].pattern_id != reg2.usage_history[-1].pattern_id


class TestGuards:
    """Tests for all guards."""
    
    def test_can_pattern_manipulate_content_returns_false(self):
        can_manipulate, reason = can_pattern_manipulate_content()
        assert can_manipulate is False
        assert "style" in reason.lower()
    
    def test_can_pattern_deceive_returns_false(self):
        can_deceive, reason = can_pattern_deceive()
        assert can_deceive is False
        assert "deception" in reason.lower()
    
    def test_can_pattern_bypass_proof_returns_false(self):
        can_bypass, reason = can_pattern_bypass_proof()
        assert can_bypass is False
        assert "proof" in reason.lower()
    
    def test_can_pattern_hide_duplicates_returns_false(self):
        can_hide, reason = can_pattern_hide_duplicates()
        assert can_hide is False
        assert "duplicate" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive guard test."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_pattern_manipulate_content,
            can_pattern_deceive,
            can_pattern_bypass_proof,
            can_pattern_hide_duplicates,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result is False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0


class TestFrozenDataclasses:
    """Test dataclasses are frozen."""
    
    def test_report_pattern_frozen(self):
        pattern = REPORT_PATTERNS[0]
        with pytest.raises(AttributeError):
            pattern.tone = ToneProfile.BUSINESS
    
    def test_pattern_registry_frozen(self):
        registry = create_pattern_registry()
        with pytest.raises(AttributeError):
            registry.cooldown_hours = 0
