"""
Tests for Phase-09 Bounty Decision Logic.

Tests:
- All decision table combinations
- Eligibility precondition tests
- Reason code verification
- NOT_ELIGIBLE conditions
- ELIGIBLE conditions
- Determinism tests
"""
import pytest


class TestBountyDecisionEnum:
    """Test BountyDecision enum definition."""

    def test_has_eligible(self):
        """BountyDecision must have ELIGIBLE member."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert hasattr(BountyDecision, 'ELIGIBLE')

    def test_has_not_eligible(self):
        """BountyDecision must have NOT_ELIGIBLE member."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert hasattr(BountyDecision, 'NOT_ELIGIBLE')

    def test_has_duplicate(self):
        """BountyDecision must have DUPLICATE member."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert hasattr(BountyDecision, 'DUPLICATE')

    def test_has_needs_review(self):
        """BountyDecision must have NEEDS_REVIEW member."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert hasattr(BountyDecision, 'NEEDS_REVIEW')

    def test_exactly_four_members(self):
        """BountyDecision must have exactly 4 members (closed enum)."""
        from python.phase09_bounty.bounty_types import BountyDecision
        assert len(BountyDecision) == 4


class TestBountyDecisionResult:
    """Test BountyDecisionResult dataclass."""

    def test_result_is_frozen(self):
        """BountyDecisionResult must be frozen (immutable)."""
        from python.phase09_bounty.bounty_types import ScopeResult, BountyDecision
        from python.phase09_bounty.bounty_engine import BountyDecisionResult

        result = BountyDecisionResult(
            submission_id="SUB-001",
            scope_result=ScopeResult.IN_SCOPE,
            is_duplicate=False,
            decision=BountyDecision.ELIGIBLE,
            reason_code="EL-001",
            reason_description="All conditions met",
            requires_human_review=False,
            review_reason=None
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            result.decision = BountyDecision.NOT_ELIGIBLE


class TestDecisionTableInScopeNotDuplicate:
    """Test decision: IN_SCOPE + NOT_DUPLICATE = ELIGIBLE."""

    def test_in_scope_not_duplicate_no_poc_required(self):
        """IN_SCOPE + NOT_DUPLICATE + POC not required = ELIGIBLE."""
        from python.phase09_bounty.bounty_types import ScopeResult, BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-001",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter="q",
            root_cause_hash="abc123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=False,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        assert result.decision == BountyDecision.ELIGIBLE
        assert result.scope_result == ScopeResult.IN_SCOPE
        assert result.is_duplicate is False

    def test_in_scope_not_duplicate_poc_required_has_poc(self):
        """IN_SCOPE + NOT_DUPLICATE + POC required + has POC = ELIGIBLE."""
        from python.phase09_bounty.bounty_types import ScopeResult, BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=True  # REQUIRED
        )
        context = BountyContext(
            submission_id="SUB-002",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter="q",
            root_cause_hash="def456",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,  # HAS POC
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        assert result.decision == BountyDecision.ELIGIBLE


class TestDecisionTablePOCRequired:
    """Test decision: POC required but missing = NOT_ELIGIBLE."""

    def test_poc_required_no_poc_not_eligible(self):
        """IN_SCOPE + NOT_DUPLICATE + POC required + no POC = NOT_ELIGIBLE."""
        from python.phase09_bounty.bounty_types import ScopeResult, BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=True  # REQUIRED
        )
        context = BountyContext(
            submission_id="SUB-003",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter="q",
            root_cause_hash="ghi789",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=False,  # NO POC
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        assert result.decision == BountyDecision.NOT_ELIGIBLE
        assert "NE-004" in result.reason_code  # Missing POC


class TestDecisionTableOutOfScope:
    """Test decision: OUT_OF_SCOPE = NOT_ELIGIBLE."""

    def test_out_of_scope_not_eligible(self):
        """OUT_OF_SCOPE always → NOT_ELIGIBLE."""
        from python.phase09_bounty.bounty_types import ScopeResult, BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-004",
            target_asset="notinscope.com",  # OUT OF SCOPE
            vulnerability_type="XSS",
            affected_parameter="q",
            root_cause_hash="jkl012",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        assert result.decision == BountyDecision.NOT_ELIGIBLE
        assert result.scope_result == ScopeResult.OUT_OF_SCOPE


class TestDecisionTableDuplicate:
    """Test decision: DUPLICATE scenarios."""

    def test_in_scope_duplicate_returns_duplicate(self):
        """IN_SCOPE + DUPLICATE → DUPLICATE."""
        from python.phase09_bounty.bounty_types import ScopeResult, BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-005",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter="q",
            root_cause_hash="abc123",  # Same hash as prior
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"abc123"})  # PRIOR EXISTS
        )

        result = make_decision(context)
        assert result.decision == BountyDecision.DUPLICATE
        assert result.is_duplicate is True


class TestReasonCodes:
    """Test reason codes are correctly assigned."""

    def test_eligible_reason_code(self):
        """ELIGIBLE decision has EL-001 reason code."""
        from python.phase09_bounty.bounty_types import BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-006",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="unique123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        assert result.reason_code == "EL-001"

    def test_not_eligible_scope_reason_code(self):
        """NOT_ELIGIBLE due to scope has NE-001 reason code."""
        from python.phase09_bounty.bounty_types import BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-007",
            target_asset="outofscope.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="abc789",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        assert "NE-001" in result.reason_code

    def test_duplicate_reason_code(self):
        """DUPLICATE decision has DU-001 reason code."""
        from python.phase09_bounty.bounty_types import BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-008",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="dup456",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"dup456"})
        )

        result = make_decision(context)
        assert "DU-001" in result.reason_code


class TestDeterminism:
    """Test same input → same output."""

    def test_same_context_same_decision(self):
        """Same context always produces same decision."""
        from python.phase09_bounty.bounty_types import BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-009",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="xyz999",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result1 = make_decision(context)
        result2 = make_decision(context)
        result3 = make_decision(context)

        assert result1.decision == result2.decision == result3.decision
        assert result1.reason_code == result2.reason_code == result3.reason_code


class TestNoForbiddenImports:
    """Test no forbidden imports in bounty_engine module."""

    def test_no_os_import(self):
        """No os import in bounty_engine."""
        import python.phase09_bounty.bounty_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_subprocess_import(self):
        """No subprocess import in bounty_engine."""
        import python.phase09_bounty.bounty_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_socket_import(self):
        """No socket import in bounty_engine."""
        import python.phase09_bounty.bounty_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import socket' not in source

    def test_no_phase10_import(self):
        """No phase10+ imports in bounty_engine."""
        import python.phase09_bounty.bounty_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'phase10' not in source
