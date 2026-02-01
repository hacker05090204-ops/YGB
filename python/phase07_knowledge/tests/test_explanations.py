"""
Tests for BugExplanation dataclass - Phase-07.

Tests verify:
- BugExplanation exists and is frozen
- Contains all required fields
- Hindi and English fields exist
"""

import pytest
from dataclasses import FrozenInstanceError


class TestBugExplanationExists:
    """Test BugExplanation dataclass existence."""
    
    def test_bug_explanation_exists(self):
        """BugExplanation must exist."""
        from python.phase07_knowledge.explanations import BugExplanation
        assert BugExplanation is not None
    
    def test_bug_explanation_is_dataclass(self):
        """BugExplanation must be a dataclass."""
        from python.phase07_knowledge.explanations import BugExplanation
        from dataclasses import is_dataclass
        assert is_dataclass(BugExplanation)


class TestBugExplanationFields:
    """Test BugExplanation has required fields."""
    
    def test_has_bug_type_field(self):
        """BugExplanation must have bug_type field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'bug_type' in fields
    
    def test_has_title_en_field(self):
        """BugExplanation must have title_en field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'title_en' in fields
    
    def test_has_title_hi_field(self):
        """BugExplanation must have title_hi field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'title_hi' in fields
    
    def test_has_description_en_field(self):
        """BugExplanation must have description_en field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'description_en' in fields
    
    def test_has_description_hi_field(self):
        """BugExplanation must have description_hi field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'description_hi' in fields
    
    def test_has_impact_en_field(self):
        """BugExplanation must have impact_en field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'impact_en' in fields
    
    def test_has_impact_hi_field(self):
        """BugExplanation must have impact_hi field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'impact_hi' in fields
    
    def test_has_steps_en_field(self):
        """BugExplanation must have steps_en field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'steps_en' in fields
    
    def test_has_steps_hi_field(self):
        """BugExplanation must have steps_hi field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'steps_hi' in fields
    
    def test_has_cwe_id_field(self):
        """BugExplanation must have cwe_id field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'cwe_id' in fields
    
    def test_has_source_field(self):
        """BugExplanation must have source field."""
        from python.phase07_knowledge.explanations import BugExplanation
        import dataclasses
        fields = {f.name for f in dataclasses.fields(BugExplanation)}
        assert 'source' in fields


class TestBugExplanationImmutability:
    """Test BugExplanation is frozen (immutable)."""
    
    def test_bug_explanation_is_frozen(self):
        """BugExplanation must be frozen."""
        from python.phase07_knowledge.explanations import BugExplanation
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        
        explanation = BugExplanation(
            bug_type=BugType.XSS,
            title_en="Test",
            title_hi="टेस्ट",
            description_en="Test description",
            description_hi="टेस्ट विवरण",
            impact_en="Test impact",
            impact_hi="टेस्ट प्रभाव",
            steps_en=("Step 1",),
            steps_hi=("चरण 1",),
            cwe_id="CWE-79",
            source=KnowledgeSource.CWE
        )
        
        with pytest.raises(FrozenInstanceError):
            explanation.title_en = "Modified"


class TestKnowledgeRegistry:
    """Test knowledge registry exists."""
    
    def test_get_known_explanations_exists(self):
        """get_known_explanations function must exist."""
        from python.phase07_knowledge.explanations import get_known_explanations
        assert get_known_explanations is not None
        assert callable(get_known_explanations)
    
    def test_xss_explanation_exists(self):
        """XSS explanation must be in registry."""
        from python.phase07_knowledge.explanations import get_known_explanations
        from python.phase07_knowledge.bug_types import BugType
        registry = get_known_explanations()
        assert BugType.XSS in registry
    
    def test_sqli_explanation_exists(self):
        """SQLI explanation must be in registry."""
        from python.phase07_knowledge.explanations import get_known_explanations
        from python.phase07_knowledge.bug_types import BugType
        registry = get_known_explanations()
        assert BugType.SQLI in registry
