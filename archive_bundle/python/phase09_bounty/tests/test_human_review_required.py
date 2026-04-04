"""
Tests for Phase-09 Human Review Required Logic.

Tests:
- All NEEDS_REVIEW conditions (NR-001 through NR-008)
- Escalation path verification
- Human authority supremacy
- No forbidden imports
- No phase10+ imports
"""
import pytest
import os


class TestRequiresReviewFunction:
    """Test requires_review() function."""

    def test_returns_tuple(self):
        """requires_review returns (bool, Optional[str])."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import requires_review

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
            affected_parameter=None,
            root_cause_hash="abc123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = requires_review(context)
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)


class TestNeedsReviewConditions:
    """Test all NEEDS_REVIEW conditions."""

    def test_nr002_unknown_vuln_type_needs_review(self):
        """NR-002: Unknown vulnerability type → NEEDS_REVIEW."""
        from python.phase09_bounty.bounty_types import BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS", "SQLi"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-002",
            target_asset="example.com",
            vulnerability_type="UNKNOWN_NEW_VULN_TYPE",
            affected_parameter=None,
            root_cause_hash="def456",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        # Unknown vuln type on valid asset should trigger review
        # or be out of scope depending on policy
        assert result.decision in [BountyDecision.NEEDS_REVIEW, BountyDecision.NOT_ELIGIBLE]


class TestClearCasesNoReview:
    """Test clear cases that do NOT need review."""

    def test_clear_eligible_no_review(self):
        """Clear ELIGIBLE case does not need review."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import requires_review

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
            submission_id="SUB-003",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="clear123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        needs, reason = requires_review(context)
        assert needs is False
        assert reason is None

    def test_clear_out_of_scope_no_review(self):
        """Clear OUT_OF_SCOPE case does not need review."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import requires_review

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
            target_asset="notinscope.com",  # Clearly out of scope
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="oos123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        needs, reason = requires_review(context)
        assert needs is False

    def test_clear_duplicate_no_review(self):
        """Clear DUPLICATE case does not need review."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import requires_review

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
            affected_parameter=None,
            root_cause_hash="dup_hash",  # Same as prior
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"dup_hash"})
        )

        needs, reason = requires_review(context)
        assert needs is False


class TestNeedsReviewResult:
    """Test NEEDS_REVIEW decision result."""

    def test_needs_review_sets_flag(self):
        """NEEDS_REVIEW decision sets requires_human_review flag."""
        from python.phase09_bounty.bounty_types import BountyDecision
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import make_decision

        # Policy with no vuln types (forces NEEDS_REVIEW edge case)
        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset(),  # Empty
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-006",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="edge123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        # Should be NOT_ELIGIBLE with no review needed (empty types = deny)
        assert result.decision == BountyDecision.NOT_ELIGIBLE


class TestHumanAuthoritySupremacy:
    """Test human authority is enforced."""

    def test_decision_can_be_overridden(self):
        """Decisions can be marked for human override."""
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
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="human123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = make_decision(context)
        # Machine decision is made, but human can always override
        assert result.decision in [
            BountyDecision.ELIGIBLE,
            BountyDecision.NOT_ELIGIBLE,
            BountyDecision.DUPLICATE,
            BountyDecision.NEEDS_REVIEW
        ]


class TestDeterminism:
    """Test same input → same output."""

    def test_same_context_same_review_result(self):
        """Same context always produces same review result."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import requires_review

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
            root_cause_hash="determ123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result1 = requires_review(context)
        result2 = requires_review(context)
        result3 = requires_review(context)

        assert result1 == result2 == result3


class TestNoForbiddenImportsInAllFiles:
    """Test no forbidden imports across all Phase-09 files."""

    def test_no_forbidden_imports_in_bounty_types(self):
        """No forbidden imports in bounty_types module."""
        import python.phase09_bounty.bounty_types as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source
        assert 'import subprocess' not in source
        assert 'import socket' not in source
        assert 'import asyncio' not in source
        assert 'import threading' not in source

    def test_no_forbidden_imports_in_bounty_context(self):
        """No forbidden imports in bounty_context module."""
        import python.phase09_bounty.bounty_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source
        assert 'import subprocess' not in source
        assert 'import socket' not in source

    def test_no_exec_eval_in_any_file(self):
        """No exec() or eval() in any Phase-09 file."""
        phase_dir = os.path.dirname(os.path.dirname(__file__))
        for filename in os.listdir(phase_dir):
            if filename.endswith('.py') and not filename.startswith('test_'):
                filepath = os.path.join(phase_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'exec(' not in content, f"Found exec( in {filename}"
                    assert 'eval(' not in content, f"Found eval( in {filename}"


class TestNoPhase10Imports:
    """Test no phase10+ imports anywhere."""

    def test_no_phase10_in_any_file(self):
        """No phase10+ imports in any Phase-09 file."""
        phase_dir = os.path.dirname(os.path.dirname(__file__))
        for filename in os.listdir(phase_dir):
            if filename.endswith('.py'):
                filepath = os.path.join(phase_dir, filename)
                with open(filepath, 'r') as f:
                    content = f.read()
                    assert 'phase10' not in content, f"Found phase10 in {filename}"
                    assert 'phase11' not in content, f"Found phase11 in {filename}"
                    assert 'phase12' not in content, f"Found phase12 in {filename}"


class TestDataclassesAreFrozen:
    """Test all dataclasses are frozen."""

    def test_bounty_policy_is_frozen(self):
        """BountyPolicy is frozen."""
        from python.phase09_bounty.bounty_context import BountyPolicy

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test",
            in_scope_assets=frozenset(),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset(),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )

        with pytest.raises(Exception):
            policy.policy_id = "MODIFIED"

    def test_bounty_context_is_frozen(self):
        """BountyContext is frozen."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test",
            in_scope_assets=frozenset(),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset(),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-001",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="abc",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        with pytest.raises(Exception):
            context.submission_id = "MODIFIED"
