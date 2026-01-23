"""
Tests for compose_narrative function - Phase-08.

Tests verify:
- Deterministic narratives
- No guessing
- Hindi + English support
- Phase-06 decision respected
- Phase-07 knowledge respected
- No forbidden imports
- No phase09+ imports
"""

import pytest
import os


class TestComposerExists:
    """Test composer function exists."""
    
    def test_compose_narrative_exists(self):
        """compose_narrative function must exist."""
        from python.phase08_evidence.composer import compose_narrative
        assert compose_narrative is not None
        assert callable(compose_narrative)
    
    def test_get_recommendation_exists(self):
        """get_recommendation function must exist."""
        from python.phase08_evidence.composer import get_recommendation
        assert get_recommendation is not None
        assert callable(get_recommendation)


class TestDecisionRespected:
    """Test Phase-06 decisions are respected in narratives."""
    
    def test_allow_decision_reflected(self):
        """ALLOW decision is reflected in narrative."""
        from python.phase08_evidence.composer import compose_narrative
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_explanation = resolve_bug_info(BugType.XSS)
        narrative = compose_narrative(FinalDecision.ALLOW, bug_explanation)
        
        assert narrative.decision == FinalDecision.ALLOW
        assert "allow" in narrative.title_en.lower() or "Allow" in narrative.title_en
    
    def test_deny_decision_reflected(self):
        """DENY decision is reflected in narrative."""
        from python.phase08_evidence.composer import compose_narrative
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_explanation = resolve_bug_info(BugType.SQLI)
        narrative = compose_narrative(FinalDecision.DENY, bug_explanation)
        
        assert narrative.decision == FinalDecision.DENY
        assert "deny" in narrative.title_en.lower() or "Deny" in narrative.title_en or "Denied" in narrative.title_en
    
    def test_escalate_decision_reflected(self):
        """ESCALATE decision is reflected in narrative."""
        from python.phase08_evidence.composer import compose_narrative
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_explanation = resolve_bug_info(BugType.SSRF)
        narrative = compose_narrative(FinalDecision.ESCALATE, bug_explanation)
        
        assert narrative.decision == FinalDecision.ESCALATE
        assert "escalate" in narrative.title_en.lower() or "Escalate" in narrative.title_en or "Review" in narrative.title_en


class TestKnowledgeIntegrated:
    """Test Phase-07 knowledge is integrated."""
    
    def test_bug_type_preserved(self):
        """Bug type from knowledge is preserved."""
        from python.phase08_evidence.composer import compose_narrative
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_explanation = resolve_bug_info(BugType.XSS)
        narrative = compose_narrative(FinalDecision.DENY, bug_explanation)
        
        assert narrative.bug_type == BugType.XSS
    
    def test_unknown_bug_handled(self):
        """UNKNOWN bug type produces valid narrative."""
        from python.phase08_evidence.composer import compose_narrative
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_explanation = resolve_bug_info(BugType.UNKNOWN)
        narrative = compose_narrative(FinalDecision.ESCALATE, bug_explanation)
        
        assert narrative.bug_type == BugType.UNKNOWN
        assert len(narrative.title_en) > 0


class TestBilingualSupport:
    """Test Hindi and English support."""
    
    def test_has_english_fields(self):
        """Narrative has English fields."""
        from python.phase08_evidence.composer import compose_narrative
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_explanation = resolve_bug_info(BugType.XSS)
        narrative = compose_narrative(FinalDecision.ALLOW, bug_explanation)
        
        assert len(narrative.title_en) > 0
        assert len(narrative.summary_en) > 0
        assert len(narrative.recommendation_en) > 0
    
    def test_has_hindi_fields(self):
        """Narrative has Hindi fields."""
        from python.phase08_evidence.composer import compose_narrative
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_explanation = resolve_bug_info(BugType.XSS)
        narrative = compose_narrative(FinalDecision.ALLOW, bug_explanation)
        
        assert len(narrative.title_hi) > 0
        assert len(narrative.summary_hi) > 0
        assert len(narrative.recommendation_hi) > 0


class TestDeterminism:
    """Test narratives are deterministic."""
    
    def test_same_input_same_output(self):
        """Same inputs produce same narrative."""
        from python.phase08_evidence.composer import compose_narrative
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        from python.phase07_knowledge.resolver import resolve_bug_info
        
        bug_explanation = resolve_bug_info(BugType.XSS)
        
        narrative1 = compose_narrative(FinalDecision.DENY, bug_explanation)
        narrative2 = compose_narrative(FinalDecision.DENY, bug_explanation)
        
        assert narrative1 == narrative2


class TestRecommendations:
    """Test get_recommendation function."""
    
    def test_allow_recommendation(self):
        """ALLOW produces appropriate recommendation."""
        from python.phase08_evidence.composer import get_recommendation
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        
        rec_en, rec_hi = get_recommendation(FinalDecision.ALLOW, BugType.XSS)
        
        assert len(rec_en) > 0
        assert len(rec_hi) > 0
    
    def test_deny_recommendation(self):
        """DENY produces appropriate recommendation."""
        from python.phase08_evidence.composer import get_recommendation
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        
        rec_en, rec_hi = get_recommendation(FinalDecision.DENY, BugType.XSS)
        
        assert len(rec_en) > 0
        assert len(rec_hi) > 0
    
    def test_escalate_recommendation(self):
        """ESCALATE produces appropriate recommendation."""
        from python.phase08_evidence.composer import get_recommendation
        from python.phase06_decision.decision_types import FinalDecision
        from python.phase07_knowledge.bug_types import BugType
        
        rec_en, rec_hi = get_recommendation(FinalDecision.ESCALATE, BugType.XSS)
        
        assert len(rec_en) > 0
        assert len(rec_hi) > 0


class TestNoForbiddenImports:
    """Test no forbidden imports."""
    
    def test_no_os_import(self):
        """No os import in composer.py."""
        composer_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'composer.py'
        )
        with open(composer_path, 'r') as f:
            content = f.read()
        assert 'import os' not in content
    
    def test_no_subprocess_import(self):
        """No subprocess import."""
        composer_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'composer.py'
        )
        with open(composer_path, 'r') as f:
            content = f.read()
        assert 'import subprocess' not in content
    
    def test_no_asyncio_import(self):
        """No asyncio import."""
        composer_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'composer.py'
        )
        with open(composer_path, 'r') as f:
            content = f.read()
        assert 'import asyncio' not in content


class TestNoFuturePhaseCoupling:
    """Test no phase09+ imports."""
    
    def test_no_phase09_import(self):
        """No phase09 imports in Phase-08 files."""
        phase08_dir = os.path.dirname(os.path.dirname(__file__))
        for filename in os.listdir(phase08_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(phase08_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read().lower()
                assert 'phase09' not in content, f"Found phase09 in {filename}"
                assert 'phase10' not in content, f"Found phase10 in {filename}"
