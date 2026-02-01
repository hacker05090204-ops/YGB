# test_g35_ai_accelerator.py
"""Tests for G35 AI Accelerator (Advisory Only)."""

import pytest

from impl_v1.phase49.governors.g35_ai_accelerator import (
    # Enums
    AdvisoryType,
    PriorityLevel,
    # Data structures
    AIAdvisory,
    PriorityRanking,
    NoiseReduction,
    MistakeDetection,
    AIAcceleratorResult,
    # Functions
    suggest_priority,
    rank_findings_batch,
    suggest_noise_reduction,
    detect_mistakes,
    accelerate_triage,
    # Guards
    can_ai_approve,
    can_ai_verify,
    can_ai_execute,
    can_ai_bypass_governance,
    can_ai_make_binding_decision,
    can_ai_override_human,
)


class TestAdvisoryTypeEnum:
    """Tests for AdvisoryType enum."""
    
    def test_has_4_types(self):
        assert len(AdvisoryType) == 4
    
    def test_has_priority_ranking(self):
        assert AdvisoryType.PRIORITY_RANKING.value == "PRIORITY_RANKING"


class TestPriorityLevelEnum:
    """Tests for PriorityLevel enum."""
    
    def test_has_5_levels(self):
        assert len(PriorityLevel) == 5
    
    def test_has_critical(self):
        assert PriorityLevel.CRITICAL.value == "CRITICAL"
    
    def test_has_noise(self):
        assert PriorityLevel.NOISE.value == "NOISE"


class TestSuggestPriority:
    """Tests for suggest_priority function."""
    
    def test_detects_critical_rce(self):
        ranking = suggest_priority("Remote code execution found", "F001")
        assert ranking.suggested_priority == PriorityLevel.CRITICAL
        assert ranking.is_binding == False
    
    def test_detects_high_sqli(self):
        ranking = suggest_priority("SQLI vulnerability in login form", "F002")
        assert ranking.suggested_priority == PriorityLevel.HIGH
        assert ranking.is_binding == False
    
    def test_detects_noise_missing_header(self):
        ranking = suggest_priority("Missing header X-Frame-Options", "F003")
        assert ranking.suggested_priority == PriorityLevel.NOISE
        assert ranking.is_binding == False
    
    def test_always_not_binding(self):
        ranking = suggest_priority("Critical account takeover", "F001")
        assert ranking.is_binding == False


class TestRankFindingsBatch:
    """Tests for rank_findings_batch function."""
    
    def test_ranks_multiple_findings(self):
        findings = (
            ("F001", "RCE vulnerability"),
            ("F002", "Missing header"),
            ("F003", "IDOR detected"),
        )
        rankings = rank_findings_batch(findings)
        
        assert len(rankings) == 3
        assert all(r.is_binding == False for r in rankings)


class TestNoiseReduction:
    """Tests for suggest_noise_reduction function."""
    
    def test_identifies_noise(self):
        findings = (
            ("F001", "Missing X-Frame-Options"),
            ("F002", "SQL injection"),
            ("F003", "Server header leaked"),
        )
        reduction = suggest_noise_reduction(findings)
        
        assert reduction.original_count == 3
        assert reduction.reduced_count < 3
        assert "F001" in reduction.removed_ids or "F003" in reduction.removed_ids
        assert reduction.is_binding == False
    
    def test_always_not_binding(self):
        reduction = suggest_noise_reduction((("F001", "test"),))
        assert reduction.is_binding == False


class TestMistakeDetection:
    """Tests for detect_mistakes function."""
    
    def test_detects_missing_poc(self):
        # Report without proof/poc keywords
        mistakes = detect_mistakes("Found vulnerability in login page")
        assert len(mistakes) >= 1
        assert all(m.is_binding == False for m in mistakes)
    
    def test_detects_theoretical_only(self):
        mistakes = detect_mistakes("This is theoretical only and may be exploitable")
        assert any("THEORETICAL" in m.mistake_type for m in mistakes)
    
    def test_always_not_binding(self):
        mistakes = detect_mistakes("test report")
        assert all(m.is_binding == False for m in mistakes)


class TestAccelerateTriage:
    """Tests for accelerate_triage function."""
    
    def test_returns_complete_result(self):
        findings = (
            ("F001", "RCE vulnerability"),
            ("F002", "Missing header"),
        )
        result = accelerate_triage(findings, "Report text")
        
        assert isinstance(result, AIAcceleratorResult)
        assert result.result_id.startswith("ACC-")
        assert result.binding_decisions == 0  # ALWAYS 0
    
    def test_always_zero_binding_decisions(self):
        findings = (("F001", "Critical account takeover RCE"),)
        result = accelerate_triage(findings, "Important report")
        
        assert result.binding_decisions == 0
    
    def test_has_determinism_hash(self):
        result = accelerate_triage(tuple(), "")
        assert len(result.determinism_hash) == 32


class TestCanAiApprove:
    """Tests for can_ai_approve guard."""
    
    def test_returns_false(self):
        can_approve, reason = can_ai_approve()
        assert can_approve == False
    
    def test_reason_mentions_human(self):
        can_approve, reason = can_ai_approve()
        assert "human" in reason.lower()


class TestCanAiVerify:
    """Tests for can_ai_verify guard."""
    
    def test_returns_false(self):
        can_verify, reason = can_ai_verify()
        assert can_verify == False
    
    def test_reason_mentions_g33(self):
        can_verify, reason = can_ai_verify()
        assert "g33" in reason.lower() or "verification" in reason.lower()


class TestCanAiExecute:
    """Tests for can_ai_execute guard."""
    
    def test_returns_false(self):
        can_execute, reason = can_ai_execute()
        assert can_execute == False
    
    def test_reason_mentions_advisory(self):
        can_execute, reason = can_ai_execute()
        assert "advisory" in reason.lower()


class TestCanAiBypassGovernance:
    """Tests for can_ai_bypass_governance guard."""
    
    def test_returns_false(self):
        can_bypass, reason = can_ai_bypass_governance()
        assert can_bypass == False
    
    def test_reason_mentions_governance(self):
        can_bypass, reason = can_ai_bypass_governance()
        assert "governance" in reason.lower()


class TestCanAiMakeBindingDecision:
    """Tests for can_ai_make_binding_decision guard."""
    
    def test_returns_false(self):
        can_decide, reason = can_ai_make_binding_decision()
        assert can_decide == False
    
    def test_reason_mentions_advisory(self):
        can_decide, reason = can_ai_make_binding_decision()
        assert "advisory" in reason.lower()


class TestCanAiOverrideHuman:
    """Tests for can_ai_override_human guard."""
    
    def test_returns_false(self):
        can_override, reason = can_ai_override_human()
        assert can_override == False
    
    def test_reason_mentions_absolute(self):
        can_override, reason = can_ai_override_human()
        assert "absolute" in reason.lower()


class TestAllGuardsReturnFalse:
    """Comprehensive test that ALL guards return False."""
    
    def test_all_guards_return_false(self):
        guards = [
            can_ai_approve,
            can_ai_verify,
            can_ai_execute,
            can_ai_bypass_governance,
            can_ai_make_binding_decision,
            can_ai_override_human,
        ]
        
        for guard in guards:
            result, reason = guard()
            assert result == False, f"Guard {guard.__name__} returned True!"
            assert len(reason) > 0, f"Guard {guard.__name__} has empty reason!"


class TestAllOutputsNotBinding:
    """Tests that ALL AI outputs have is_binding=False."""
    
    def test_priority_ranking_not_binding(self):
        ranking = suggest_priority("RCE", "F001")
        assert ranking.is_binding == False
    
    def test_noise_reduction_not_binding(self):
        reduction = suggest_noise_reduction((("F001", "test"),))
        assert reduction.is_binding == False
    
    def test_mistake_detection_not_binding(self):
        mistakes = detect_mistakes("test")
        for m in mistakes:
            assert m.is_binding == False
    
    def test_advisories_not_binding(self):
        result = accelerate_triage((("F001", "test"),), "")
        for adv in result.advisories:
            assert adv.is_binding == False


class TestFrozenDatastructures:
    """Tests that all datastructures are frozen."""
    
    def test_ai_accelerator_result_is_frozen(self):
        result = accelerate_triage(tuple(), "")
        with pytest.raises(AttributeError):
            result.binding_decisions = 1


class TestNoForbiddenImports:
    """Tests that G35 has no forbidden imports."""
    
    def test_no_forbidden_imports(self):
        import impl_v1.phase49.governors.g35_ai_accelerator as g35
        import inspect
        
        source = inspect.getsource(g35)
        
        forbidden = ["subprocess", "socket", "selenium", "playwright"]
        for name in forbidden:
            assert f"import {name}" not in source


class TestAiCannotApproveOrVerify:
    """Critical test: AI CANNOT approve or verify bugs."""
    
    def test_ai_output_never_approves(self):
        # Even for critical findings, AI cannot approve
        result = accelerate_triage(
            (("F001", "Critical RCE with full exploit"),),
            "Perfect report with PoC",
        )
        
        # Check that no output indicates approval
        for adv in result.advisories:
            assert "approved" not in adv.suggestion.lower()
            assert "verified" not in adv.suggestion.lower()
        
        # Binding decisions MUST be 0
        assert result.binding_decisions == 0
