"""
Tests for Phase-23 No Browser Imports.

Tests:
- No browser imports (playwright, selenium)
- No OS imports (subprocess, os)
- No phase24+ imports
"""
import pytest


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import(self):
        """No playwright import."""
        import HUMANOID_HUNTER.evidence.evidence_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import(self):
        """No selenium import."""
        import HUMANOID_HUNTER.evidence.evidence_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import HUMANOID_HUNTER.evidence.evidence_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import(self):
        """No os import."""
        import HUMANOID_HUNTER.evidence.evidence_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase24_import(self):
        """No phase24+ imports."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase24' not in content


class TestEnumCounts:
    """Test enum member counts."""

    def test_evidence_format_has_three_members(self):
        """EvidenceFormat has exactly 3 members."""
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceFormat
        assert len(EvidenceFormat) == 3

    def test_evidence_integrity_status_has_four_members(self):
        """EvidenceIntegrityStatus has exactly 4 members."""
        from HUMANOID_HUNTER.evidence.evidence_types import EvidenceIntegrityStatus
        assert len(EvidenceIntegrityStatus) == 4

    def test_verification_decision_has_three_members(self):
        """VerificationDecision has exactly 3 members."""
        from HUMANOID_HUNTER.evidence.evidence_types import VerificationDecision
        assert len(VerificationDecision) == 3
