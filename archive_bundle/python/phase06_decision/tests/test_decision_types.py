"""
Tests for FinalDecision enum - Phase-06.

Tests verify:
- Enum exists with ALLOW, DENY, ESCALATE
- Enum is closed (no dynamic members)
- Values are correct strings
"""

import pytest
from enum import Enum


class TestFinalDecisionEnum:
    """Test FinalDecision enum existence and values."""
    
    def test_final_decision_enum_exists(self):
        """FinalDecision enum must exist."""
        from python.phase06_decision.decision_types import FinalDecision
        assert FinalDecision is not None
    
    def test_final_decision_is_enum(self):
        """FinalDecision must be an Enum."""
        from python.phase06_decision.decision_types import FinalDecision
        assert issubclass(FinalDecision, Enum)
    
    def test_final_decision_has_allow(self):
        """FinalDecision must have ALLOW member."""
        from python.phase06_decision.decision_types import FinalDecision
        assert hasattr(FinalDecision, 'ALLOW')
        assert FinalDecision.ALLOW.value == "allow"
    
    def test_final_decision_has_deny(self):
        """FinalDecision must have DENY member."""
        from python.phase06_decision.decision_types import FinalDecision
        assert hasattr(FinalDecision, 'DENY')
        assert FinalDecision.DENY.value == "deny"
    
    def test_final_decision_has_escalate(self):
        """FinalDecision must have ESCALATE member."""
        from python.phase06_decision.decision_types import FinalDecision
        assert hasattr(FinalDecision, 'ESCALATE')
        assert FinalDecision.ESCALATE.value == "escalate"
    
    def test_final_decision_is_closed(self):
        """FinalDecision must have exactly 3 members."""
        from python.phase06_decision.decision_types import FinalDecision
        assert len(FinalDecision) == 3


class TestFinalDecisionImmutability:
    """Test FinalDecision cannot be modified."""
    
    def test_enum_members_are_final_decision_type(self):
        """All members are FinalDecision instances."""
        from python.phase06_decision.decision_types import FinalDecision
        for member in FinalDecision:
            assert isinstance(member, FinalDecision)
    
    def test_cannot_modify_decision_value(self):
        """Cannot modify existing decision values."""
        from python.phase06_decision.decision_types import FinalDecision
        with pytest.raises(AttributeError):
            FinalDecision.ALLOW.value = "modified"


class TestNoForbiddenDecisions:
    """Test that forbidden decision types do not exist."""
    
    def test_no_auto_decision(self):
        """No AUTO decision type."""
        from python.phase06_decision.decision_types import FinalDecision
        # Check actual enum members, not class attributes
        member_names = [m.name for m in FinalDecision]
        assert 'AUTO' not in member_names
    
    def test_no_bypass_decision(self):
        """No BYPASS decision type."""
        from python.phase06_decision.decision_types import FinalDecision
        member_names = [m.name for m in FinalDecision]
        assert 'BYPASS' not in member_names
    
    def test_no_skip_decision(self):
        """No SKIP decision type."""
        from python.phase06_decision.decision_types import FinalDecision
        member_names = [m.name for m in FinalDecision]
        assert 'SKIP' not in member_names
    
    def test_no_execute_decision(self):
        """No EXECUTE decision type."""
        from python.phase06_decision.decision_types import FinalDecision
        member_names = [m.name for m in FinalDecision]
        assert 'EXECUTE' not in member_names
    
    def test_only_three_members(self):
        """Enum has exactly ALLOW, DENY, ESCALATE."""
        from python.phase06_decision.decision_types import FinalDecision
        member_names = {m.name for m in FinalDecision}
        assert member_names == {'ALLOW', 'DENY', 'ESCALATE'}
