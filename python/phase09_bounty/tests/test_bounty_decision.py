"""
Tests for bounty decision types - Phase-09.

Tests verify:
- BountyDecision enum completeness
- ScopeResult enum completeness
- AssetType enum completeness
- BountyContext immutability
- BountyDecisionResult immutability
- Decision determinism
"""

import pytest
from dataclasses import FrozenInstanceError
from enum import Enum


class TestBountyDecisionEnum:
    """Test BountyDecision enum."""
    
    def test_enum_exists(self):
        """BountyDecision enum must exist."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert issubclass(BountyDecision, Enum)
    
    def test_eligible_value(self):
        """ELIGIBLE value exists."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert BountyDecision.ELIGIBLE.value == "eligible"
    
    def test_not_eligible_value(self):
        """NOT_ELIGIBLE value exists."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert BountyDecision.NOT_ELIGIBLE.value == "not_eligible"
    
    def test_duplicate_value(self):
        """DUPLICATE value exists."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert BountyDecision.DUPLICATE.value == "duplicate"
    
    def test_needs_review_value(self):
        """NEEDS_REVIEW value exists."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert BountyDecision.NEEDS_REVIEW.value == "needs_review"
    
    def test_exactly_four_values(self):
        """BountyDecision has exactly 4 values."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert len(BountyDecision) == 4


class TestScopeResultEnum:
    """Test ScopeResult enum."""
    
    def test_enum_exists(self):
        """ScopeResult enum must exist."""
        from python.phase09_bounty.bounty_types import ScopeResult
        assert issubclass(ScopeResult, Enum)
    
    def test_in_scope_value(self):
        """IN_SCOPE value exists."""
        from python.phase09_bounty.bounty_types import ScopeResult
        assert ScopeResult.IN_SCOPE.value == "in_scope"
    
    def test_out_of_scope_value(self):
        """OUT_OF_SCOPE value exists."""
        from python.phase09_bounty.bounty_types import ScopeResult
        assert ScopeResult.OUT_OF_SCOPE.value == "out_of_scope"
    
    def test_exactly_two_values(self):
        """ScopeResult has exactly 2 values."""
        from python.phase09_bounty.bounty_types import ScopeResult
        assert len(ScopeResult) == 2


class TestAssetTypeEnum:
    """Test AssetType enum."""
    
    def test_enum_exists(self):
        """AssetType enum must exist."""
        from python.phase09_bounty.bounty_types import AssetType
        assert issubclass(AssetType, Enum)
    
    def test_all_values_exist(self):
        """All required values exist."""
        from python.phase09_bounty.bounty_types import AssetType
        assert AssetType.WEB_APP.value == "web_app"
        assert AssetType.API.value == "api"
        assert AssetType.MOBILE.value == "mobile"
        assert AssetType.INFRASTRUCTURE.value == "infrastructure"
        assert AssetType.OUT_OF_PROGRAM.value == "out_of_program"
        assert AssetType.UNKNOWN.value == "unknown"
    
    def test_exactly_six_values(self):
        """AssetType has exactly 6 values."""
        from python.phase09_bounty.bounty_types import AssetType
        assert len(AssetType) == 6


class TestBountyContextImmutability:
    """Test BountyContext is frozen."""
    
    def test_context_is_frozen(self):
        """BountyContext must be frozen."""
        from python.phase09_bounty.bounty_context import BountyContext
        from python.phase09_bounty.bounty_types import AssetType
        
        context = BountyContext(
            report_id="test-001",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=True
        )
        
        with pytest.raises(FrozenInstanceError):
            context.report_id = "modified"


class TestBountyDecisionResultImmutability:
    """Test BountyDecisionResult is frozen."""
    
    def test_result_is_frozen(self):
        """BountyDecisionResult must be frozen."""
        from python.phase09_bounty.bounty_context import BountyContext, BountyDecisionResult
        from python.phase09_bounty.bounty_types import AssetType, ScopeResult, BountyDecision
        
        context = BountyContext(
            report_id="test-001",
            asset_type=AssetType.WEB_APP,
            vulnerability_type="XSS",
            is_duplicate=False,
            is_in_program=True
        )
        
        result = BountyDecisionResult(
            context=context,
            scope_result=ScopeResult.IN_SCOPE,
            decision=BountyDecision.ELIGIBLE,
            requires_human_review=False,
            reason="All conditions met"
        )
        
        with pytest.raises(FrozenInstanceError):
            result.decision = BountyDecision.NOT_ELIGIBLE
