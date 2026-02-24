"""
Tests for Phase-12 Deny-By-Default.

Tests:
- Unknown → UNVERIFIED
- Default → LOW confidence
- No forbidden imports
- No phase13+ imports
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_evaluate_empty_bundle(self):
        """Empty bundle → LOW confidence."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel
        from python.phase12_evidence.evidence_context import EvidenceBundle
        from python.phase12_evidence.confidence_engine import evaluate_evidence

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=None
        )

        result = evaluate_evidence(bundle)
        assert result.level == ConfidenceLevel.LOW


class TestConsistencyResultFrozen:
    """Test ConsistencyResult immutability."""

    def test_consistency_result_is_frozen(self):
        """ConsistencyResult is frozen."""
        from python.phase12_evidence.evidence_types import EvidenceState
        from python.phase12_evidence.consistency_engine import ConsistencyResult

        result = ConsistencyResult(
            bundle_id="B-001",
            state=EvidenceState.UNVERIFIED,
            source_count=0,
            matching_count=0,
            conflict_detected=False,
            reason_code="CS-001",
            reason_description="No sources"
        )

        with pytest.raises(Exception):
            result.state = EvidenceState.CONSISTENT


class TestNoForbiddenImports:
    """Test no forbidden imports in any file."""

    def test_no_os_import(self):
        """No os import in any module."""
        import python.phase12_evidence.evidence_types as types_module
        import python.phase12_evidence.evidence_context as context_module
        import python.phase12_evidence.consistency_engine as engine_module
        import python.phase12_evidence.confidence_engine as conf_module
        import inspect

        for module in [types_module, context_module, engine_module, conf_module]:
            source = inspect.getsource(module)
            assert 'import os' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase12_evidence.consistency_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_socket_import(self):
        """No socket import."""
        import python.phase12_evidence.consistency_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import socket' not in source

    def test_no_asyncio_import(self):
        """No asyncio import."""
        import python.phase12_evidence.consistency_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import asyncio' not in source

    def test_no_threading_import(self):
        """No threading import."""
        import python.phase12_evidence.consistency_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import threading' not in source

    def test_no_exec_eval(self):
        """No exec or eval in any file."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'exec(' not in content, f"Found exec( in {filename}"
                    assert 'eval(' not in content, f"Found eval( in {filename}"

    def test_no_phase13_import(self):
        """No phase13+ imports in implementation files (test files excluded)."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '').replace('\\tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase13' not in content, f"Found phase13 in {filename}"


class TestDeterminism:
    """Test same input produces same output."""

    def test_same_bundle_same_result(self):
        """Same bundle produces same result."""
        from python.phase12_evidence.evidence_context import EvidenceBundle
        from python.phase12_evidence.confidence_engine import evaluate_evidence

        bundle = EvidenceBundle(
            bundle_id="B-001",
            target_id="T-001",
            sources=frozenset(),
            replay_steps=None
        )

        result1 = evaluate_evidence(bundle)
        result2 = evaluate_evidence(bundle)
        result3 = evaluate_evidence(bundle)

        assert result1.level == result2.level == result3.level
        assert result1.reason_code == result2.reason_code == result3.reason_code
