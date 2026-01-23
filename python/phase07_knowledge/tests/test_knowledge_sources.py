"""
Tests for KnowledgeSource enum - Phase-07.

Tests verify:
- Enum exists with CVE, CWE, MANUAL, UNKNOWN
- Enum is closed
"""

import pytest
from enum import Enum


class TestKnowledgeSourceEnum:
    """Test KnowledgeSource enum existence and values."""
    
    def test_knowledge_source_enum_exists(self):
        """KnowledgeSource enum must exist."""
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        assert KnowledgeSource is not None
    
    def test_knowledge_source_is_enum(self):
        """KnowledgeSource must be an Enum."""
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        assert issubclass(KnowledgeSource, Enum)
    
    def test_has_cve(self):
        """KnowledgeSource must have CVE member."""
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        assert hasattr(KnowledgeSource, 'CVE')
        assert KnowledgeSource.CVE.value == "cve"
    
    def test_has_cwe(self):
        """KnowledgeSource must have CWE member."""
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        assert hasattr(KnowledgeSource, 'CWE')
        assert KnowledgeSource.CWE.value == "cwe"
    
    def test_has_manual(self):
        """KnowledgeSource must have MANUAL member."""
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        assert hasattr(KnowledgeSource, 'MANUAL')
        assert KnowledgeSource.MANUAL.value == "manual"
    
    def test_has_unknown(self):
        """KnowledgeSource must have UNKNOWN member."""
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        assert hasattr(KnowledgeSource, 'UNKNOWN')
        assert KnowledgeSource.UNKNOWN.value == "unknown"
    
    def test_knowledge_source_is_closed(self):
        """KnowledgeSource must have exactly 4 members."""
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        assert len(KnowledgeSource) == 4
    
    def test_all_members_correct(self):
        """Verify all expected members exist."""
        from python.phase07_knowledge.knowledge_sources import KnowledgeSource
        member_names = {m.name for m in KnowledgeSource}
        assert member_names == {'CVE', 'CWE', 'MANUAL', 'UNKNOWN'}
