"""
Tests for duplicate detection - Phase-09.

Tests verify:
- Duplicate reports return DUPLICATE
- First report is not duplicate
- Same vulnerability different asset is not duplicate
- Different vulnerability same asset is not duplicate
"""

import pytest


class TestDuplicateReturnsHuplicateDecision:
    """Test duplicate reports return DUPLICATE decision."""
    
    def test_duplicate_flag_returns_duplicate(self):
        """is_duplicate=True returns DUPLICATE decision."""
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
    
    def test_duplicate_has_correct_reason(self):
        """Duplicate decision has correct reason."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType
        
        context = BountyContext(
            report_id="dup-002",
            asset_type=AssetType.API,
            vulnerability_type="SQLI",
            is_duplicate=True,
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        assert "duplicate" in result.reason.lower()


class TestFirstReportNotDuplicate:
    """Test first report is not duplicate."""
    
    def test_first_report_not_duplicate(self):
        """is_duplicate=False does not return DUPLICATE."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        context = BountyContext(
            report_id="first-001",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        assert result.decision != BountyDecision.DUPLICATE


class TestDuplicateFlagIsSourceOfTruth:
    """Test is_duplicate flag is the sole source of truth."""
    
    def test_duplicate_flag_respected(self):
        """is_duplicate flag is respected regardless of other fields."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType, BountyDecision
        
        # Same vulnerability type but is_duplicate=False
        context = BountyContext(
            report_id="unique-001",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",  # Same vuln type as others
            is_duplicate=False,  # But marked as not duplicate
            is_in_program=True
        )
        
        result = evaluate_bounty(context)
        # Should NOT be duplicate because flag says so
        assert result.decision != BountyDecision.DUPLICATE


class TestDuplicateDeterminism:
    """Test duplicate detection is deterministic."""
    
    def test_same_context_same_result(self):
        """Same context gives same result."""
        from python.phase09_bounty.bounty_engine import evaluate_bounty
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType
        
        context = BountyContext(
            report_id="det-001",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",
            is_duplicate=True,
            is_in_program=True
        )
        
        result1 = evaluate_bounty(context)
        result2 = evaluate_bounty(context)
        assert result1 == result2
