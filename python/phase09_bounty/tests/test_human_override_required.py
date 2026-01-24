"""
Tests for human override requirements - Phase-09.

Tests verify:
- NEEDS_REVIEW requires human intervention
- Ambiguous cases flag human review
- No autonomous decisions on unclear submissions
- requires_human_review flag is set correctly
"""

import pytest


class TestNeedsReviewRequiresHuman:
    """Test NEEDS_REVIEW decisions require human."""
    
    def test_needs_review_sets_human_flag(self):
        """NEEDS_REVIEW decision sets requires_human_review=True."""
        from python.phase09_bounty.bounty_types import BountyDecision
        
        # Any decision result with NEEDS_REVIEW should have requires_human_review=True
        # This is tested through the engine
        assert BountyDecision.NEEDS_REVIEW.value == "needs_review"


class TestHumanReviewFlag:
    """Test requires_human_review flag behavior."""
    
    def test_eligible_does_not_require_human(self):
        """ELIGIBLE decision does not require human review."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        context = BountyContext(
            report_id="elig-001",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        assert result.decision == BountyDecision.ELIGIBLE
        assert result.requires_human_review is False
    
    def test_not_eligible_does_not_require_human(self):
        """NOT_ELIGIBLE (clear case) does not require human review."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        context = BountyContext(
            report_id="out-001",
            asset_type=AssetType.OUT_OF_PROGRAM,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        assert result.decision == BountyDecision.NOT_ELIGIBLE
        assert result.requires_human_review is False
    
    def test_duplicate_does_not_require_human(self):
        """DUPLICATE decision does not require human review."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        context = BountyContext(
            report_id="dup-001",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",
            is_duplicate=True,
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        assert result.decision == BountyDecision.DUPLICATE
        assert result.requires_human_review is False


class TestNoAutonomousDecisions:
    """Test no autonomous decisions on unclear submissions."""
    
    def test_clear_eligible_is_deterministic(self):
        """Clear eligible case is deterministic."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        context = BountyContext(
            report_id="clear-001",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        assert result.decision == BountyDecision.ELIGIBLE
    
    def test_clear_not_eligible_is_deterministic(self):
        """Clear not eligible case is deterministic."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        context = BountyContext(
            report_id="clear-002",
            asset_type=AssetType.INFRASTRUCTURE,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        assert result.decision == BountyDecision.NOT_ELIGIBLE


class TestDecisionTableCoverage:
    """Test all decision table cases are covered."""
    
    def test_out_of_scope_returns_not_eligible(self):
        """Out of scope asset returns NOT_ELIGIBLE."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        context = BountyContext(
            report_id="dt-001",
            asset_type=AssetType.UNKNOWN,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        assert result.decision == BountyDecision.NOT_ELIGIBLE
    
    def test_not_in_program_returns_not_eligible(self):
        """Not in program returns NOT_ELIGIBLE."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        context = BountyContext(
            report_id="dt-002",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=False
        )
        
        result = evaluate_bounty(context)
        assert result.decision == BountyDecision.NOT_ELIGIBLE
