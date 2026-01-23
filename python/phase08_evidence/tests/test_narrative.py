"""
Tests for EvidenceNarrative dataclass - Phase-08.

Tests verify:
- EvidenceNarrative exists and is frozen
- Contains all required fields
- Hindi and English fields exist
"""

import pytest
from dataclasses import FrozenInstanceError


class TestEvidenceNarrativeExists:
    """Test EvidenceNarrative dataclass existence."""
    
    def test_evidence_narrative_exists(self):
        """EvidenceNarrative must exist."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        assert EvidenceNarrative is not None
    
    def test_evidence_narrative_is_dataclass(self):
        """EvidenceNarrative must be a dataclass."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        from dataclasses import is_dataclass
        assert is_dataclass(EvidenceNarrative)


class TestEvidenceNarrativeFields:
    """Test EvidenceNarrative has required fields."""
    
    def test_has_step_field(self):
        """EvidenceNarrative must have step field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'step' in fields
    
    def test_has_decision_field(self):
        """EvidenceNarrative must have decision field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'decision' in fields
    
    def test_has_bug_type_field(self):
        """EvidenceNarrative must have bug_type field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'bug_type' in fields
    
    def test_has_title_en_field(self):
        """EvidenceNarrative must have title_en field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'title_en' in fields
    
    def test_has_title_hi_field(self):
        """EvidenceNarrative must have title_hi field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'title_hi' in fields
    
    def test_has_summary_en_field(self):
        """EvidenceNarrative must have summary_en field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'summary_en' in fields
    
    def test_has_summary_hi_field(self):
        """EvidenceNarrative must have summary_hi field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'summary_hi' in fields
    
    def test_has_recommendation_en_field(self):
        """EvidenceNarrative must have recommendation_en field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'recommendation_en' in fields
    
    def test_has_recommendation_hi_field(self):
        """EvidenceNarrative must have recommendation_hi field."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        import dataclasses
        fields = {f.name for f in dataclasses.fields(EvidenceNarrative)}
        assert 'recommendation_hi' in fields


class TestEvidenceNarrativeImmutability:
    """Test EvidenceNarrative is frozen."""
    
    def test_evidence_narrative_is_frozen(self):
        """EvidenceNarrative must be frozen."""
        from python.phase08_evidence.narrative import EvidenceNarrative
        from python.phase08_evidence.evidence_steps import EvidenceStep
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        
        narrative = EvidenceNarrative(
            step=EvidenceStep.DECISION,
            decision=FinalDecision.ALLOW,
            bug_type=BugType.XSS,
            title_en="Test",
            title_hi="टेस्ट",
            summary_en="Test summary",
            summary_hi="टेस्ट सारांश",
            recommendation_en="Test recommendation",
            recommendation_hi="टेस्ट सिफारिश"
        )
        
        with pytest.raises(FrozenInstanceError):
            narrative.title_en = "Modified"
