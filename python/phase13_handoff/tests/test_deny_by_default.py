"""
Tests for Phase-13 Deny-By-Default.

Tests:
- Unknown → REVIEW_REQUIRED or BLOCKING
- No forbidden imports
- No phase14+ imports
"""
import pytest


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_high_unverified_not_ready(self):
        """HIGH + UNVERIFIED → NOT_READY."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import ReadinessState, BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import check_readiness

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.UNVERIFIED,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        result = check_readiness(context)
        assert result == ReadinessState.NOT_READY


class TestDataclassFrozen:
    """Test dataclass immutability."""

    def test_handoff_context_is_frozen(self):
        """HandoffContext is frozen."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        with pytest.raises(Exception):
            context.bug_id = "MODIFIED"


class TestNoForbiddenImports:
    """Test no forbidden imports in any file."""

    def test_no_os_import(self):
        """No os import in any module."""
        import python.phase13_handoff.handoff_types as types_module
        import python.phase13_handoff.handoff_context as context_module
        import python.phase13_handoff.readiness_engine as engine_module
        import inspect

        for module in [types_module, context_module, engine_module]:
            source = inspect.getsource(module)
            assert 'import os' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase13_handoff.readiness_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_browser_imports(self):
        """No browser automation imports."""
        import python.phase13_handoff.readiness_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'playwright' not in source.lower()
        assert 'selenium' not in source.lower()

    def test_no_phase14_import(self):
        """No phase14+ imports in implementation files (test files excluded)."""
        import os
        module_dir = os.path.dirname(__file__).replace('/tests', '').replace('\\tests', '')
        for filename in os.listdir(module_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(module_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase14' not in content, f"Found phase14 in {filename}"


class TestDeterminism:
    """Test same input produces same output."""

    def test_same_context_same_decision(self):
        """Same context produces same decision."""
        from python.phase12_evidence.evidence_types import ConfidenceLevel, EvidenceState
        from python.phase13_handoff.handoff_types import BugSeverity, TargetType
        from python.phase13_handoff.handoff_context import HandoffContext
        from python.phase13_handoff.readiness_engine import make_handoff_decision

        context = HandoffContext(
            bug_id="BUG-001",
            confidence=ConfidenceLevel.HIGH,
            consistency_state=EvidenceState.CONSISTENT,
            human_review_completed=True,
            severity=BugSeverity.HIGH,
            target_type=TargetType.PRODUCTION,
            has_active_blockers=False,
            human_confirmed=True
        )

        decision1 = make_handoff_decision(context)
        decision2 = make_handoff_decision(context)
        decision3 = make_handoff_decision(context)

        assert decision1.can_proceed == decision2.can_proceed == decision3.can_proceed
        assert decision1.reason_code == decision2.reason_code == decision3.reason_code


class TestOtherEnums:
    """Test other enums."""

    def test_bug_severity_has_four_members(self):
        """BugSeverity has 4 members."""
        from python.phase13_handoff.handoff_types import BugSeverity
        assert len(BugSeverity) == 4

    def test_target_type_has_four_members(self):
        """TargetType has 4 members."""
        from python.phase13_handoff.handoff_types import TargetType
        assert len(TargetType) == 4
