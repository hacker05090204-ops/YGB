"""
Tests for EvidenceStep enum - Phase-08.

Tests verify:
- Enum exists with required steps
- Enum is closed
"""

import pytest
from enum import Enum


class TestEvidenceStepEnum:
    """Test EvidenceStep enum existence and values."""
    
    def test_evidence_step_enum_exists(self):
        """EvidenceStep enum must exist."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        assert EvidenceStep is not None
    
    def test_evidence_step_is_enum(self):
        """EvidenceStep must be an Enum."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        assert issubclass(EvidenceStep, Enum)
    
    def test_has_discovery(self):
        """EvidenceStep must have DISCOVERY member."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        assert hasattr(EvidenceStep, 'DISCOVERY')
        assert EvidenceStep.DISCOVERY.value == "discovery"
    
    def test_has_validation(self):
        """EvidenceStep must have VALIDATION member."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        assert hasattr(EvidenceStep, 'VALIDATION')
        assert EvidenceStep.VALIDATION.value == "validation"
    
    def test_has_decision(self):
        """EvidenceStep must have DECISION member."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        assert hasattr(EvidenceStep, 'DECISION')
        assert EvidenceStep.DECISION.value == "decision"
    
    def test_has_explanation(self):
        """EvidenceStep must have EXPLANATION member."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        assert hasattr(EvidenceStep, 'EXPLANATION')
        assert EvidenceStep.EXPLANATION.value == "explanation"
    
    def test_has_recommendation(self):
        """EvidenceStep must have RECOMMENDATION member."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        assert hasattr(EvidenceStep, 'RECOMMENDATION')
        assert EvidenceStep.RECOMMENDATION.value == "recommendation"
    
    def test_evidence_step_is_closed(self):
        """EvidenceStep must have exactly 5 members."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        assert len(EvidenceStep) == 5
    
    def test_all_members_correct(self):
        """Verify all expected members exist."""
        from python.phase08_evidence.evidence_steps import EvidenceStep
        member_names = {m.name for m in EvidenceStep}
        expected = {'DISCOVERY', 'VALIDATION', 'DECISION', 'EXPLANATION', 'RECOMMENDATION'}
        assert member_names == expected
