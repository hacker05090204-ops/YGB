"""
Tests for Phase-18 No Browser Imports.

Tests:
- No browser imports (playwright, selenium)
- No execution imports (subprocess, os)
- No phase19+ imports
"""
import pytest


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_playwright_import(self):
        """No playwright import."""
        import python.phase18_ledger.ledger_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source

    def test_no_selenium_import(self):
        """No selenium import."""
        import python.phase18_ledger.ledger_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'selenium' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase18_ledger.ledger_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_os_import(self):
        """No os import."""
        import python.phase18_ledger.ledger_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_phase19_import(self):
        """No phase19+ imports."""
        import os
        from pathlib import Path
        module_dir = str(Path(__file__).parent.parent)
        for filename in os.listdir(module_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase19' not in content, \
                        f"File {filename} contains forbidden 'phase19' import"


class TestEnumCounts:
    """Test enum member counts."""

    def test_execution_state_has_six_members(self):
        """ExecutionState has exactly 6 members."""
        from python.phase18_ledger.ledger_types import ExecutionState
        assert len(ExecutionState) == 6

    def test_evidence_status_has_four_members(self):
        """EvidenceStatus has exactly 4 members."""
        from python.phase18_ledger.ledger_types import EvidenceStatus
        assert len(EvidenceStatus) == 4

    def test_retry_decision_has_three_members(self):
        """RetryDecision has exactly 3 members."""
        from python.phase18_ledger.ledger_types import RetryDecision
        assert len(RetryDecision) == 3
