"""
Tests for Phase-09 Scope Rules.

Tests:
- IN_SCOPE positive cases
- OUT_OF_SCOPE for all rule IDs (OOS-001 through OOS-006)
- Default deny behavior
- Edge cases
- No forbidden imports
"""
import pytest


class TestScopeResultEnum:
    """Test ScopeResult enum definition."""

    def test_scope_result_has_in_scope(self):
        """ScopeResult must have IN_SCOPE member."""
        from python.phase09_bounty.bounty_types import ScopeResult
        assert hasattr(ScopeResult, 'IN_SCOPE')

    def test_scope_result_has_out_of_scope(self):
        """ScopeResult must have OUT_OF_SCOPE member."""
        from python.phase09_bounty.bounty_types import ScopeResult
        assert hasattr(ScopeResult, 'OUT_OF_SCOPE')

    def test_scope_result_exactly_two_members(self):
        """ScopeResult must have exactly 2 members (closed enum)."""
        from python.phase09_bounty.bounty_types import ScopeResult
        assert len(ScopeResult) == 2


class TestInScopePositiveCases:
    """Test IN_SCOPE classification for valid submissions."""

    def test_valid_asset_valid_type_returns_in_scope(self):
        """Valid asset + valid vuln type = IN_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com", "api.example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS", "SQLi", "IDOR"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-001",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter="search",
            root_cause_hash="abc123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.IN_SCOPE

    def test_subdomain_in_scope(self):
        """Subdomain explicitly in scope returns IN_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"*.example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-002",
            target_asset="*.example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="def456",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=False,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.IN_SCOPE


class TestOutOfScopeRules:
    """Test OUT_OF_SCOPE for all rule IDs."""

    def test_oos_001_domain_not_in_asset_list(self):
        """OOS-001: Domain not in asset list → OUT_OF_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

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
            target_asset="notinscope.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="ghi789",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.OUT_OF_SCOPE

    def test_oos_002_vuln_type_excluded(self):
        """OOS-002: Vulnerability type explicitly excluded → OUT_OF_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS", "SQLi"}),
            excluded_vuln_types=frozenset({"Self-XSS"}),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-004",
            target_asset="example.com",
            vulnerability_type="Self-XSS",
            affected_parameter=None,
            root_cause_hash="jkl012",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.OUT_OF_SCOPE

    def test_oos_003_vuln_type_not_accepted(self):
        """OOS-003: Vulnerability type not in accepted list → OUT_OF_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

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
            submission_id="SUB-005",
            target_asset="example.com",
            vulnerability_type="DoS",
            affected_parameter=None,
            root_cause_hash="mno345",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.OUT_OF_SCOPE

    def test_oos_004_target_in_exclusion_list(self):
        """OOS-004: Target in exclusion list → OUT_OF_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"*.example.com"}),
            excluded_assets=frozenset({"staging.example.com"}),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-006",
            target_asset="staging.example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="pqr678",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.OUT_OF_SCOPE

    def test_oos_005_policy_inactive(self):
        """OOS-005: Policy inactive → OUT_OF_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=False,  # INACTIVE
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-007",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="stu901",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.OUT_OF_SCOPE

    def test_oos_006_empty_asset_is_out_of_scope(self):
        """OOS-006: Empty target asset → OUT_OF_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

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
            target_asset="",  # EMPTY
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="vwx234",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.OUT_OF_SCOPE


class TestDefaultDenyBehavior:
    """Test deny-by-default behavior."""

    def test_unknown_asset_defaults_to_out_of_scope(self):
        """Unknown asset → OUT_OF_SCOPE (deny-by-default)."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset(),  # Empty - nothing in scope
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-009",
            target_asset="anything.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="yza567",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.OUT_OF_SCOPE

    def test_empty_vuln_types_defaults_to_out_of_scope(self):
        """Empty accepted vuln types → OUT_OF_SCOPE."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test Policy",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset(),  # Empty - no types accepted
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        context = BountyContext(
            submission_id="SUB-010",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="bcd890",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result = evaluate_scope(context)
        assert result == ScopeResult.OUT_OF_SCOPE


class TestHelperFunctions:
    """Test individual scope helper functions."""

    def test_is_asset_in_scope_true(self):
        """Asset in list returns True."""
        from python.phase09_bounty.bounty_context import BountyPolicy
        from python.phase09_bounty.scope_rules import is_asset_in_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset(),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        assert is_asset_in_scope("example.com", policy) is True

    def test_is_asset_in_scope_false(self):
        """Asset not in list returns False."""
        from python.phase09_bounty.bounty_context import BountyPolicy
        from python.phase09_bounty.scope_rules import is_asset_in_scope

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test",
            in_scope_assets=frozenset({"example.com"}),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset(),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        assert is_asset_in_scope("other.com", policy) is False

    def test_is_vuln_type_accepted_true(self):
        """Vuln type in list returns True."""
        from python.phase09_bounty.bounty_context import BountyPolicy
        from python.phase09_bounty.scope_rules import is_vuln_type_accepted

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test",
            in_scope_assets=frozenset(),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS", "SQLi"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        assert is_vuln_type_accepted("XSS", policy) is True

    def test_is_vuln_type_accepted_false(self):
        """Vuln type not in list returns False."""
        from python.phase09_bounty.bounty_context import BountyPolicy
        from python.phase09_bounty.scope_rules import is_vuln_type_accepted

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test",
            in_scope_assets=frozenset(),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS", "SQLi"}),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        assert is_vuln_type_accepted("DoS", policy) is False

    def test_is_vuln_type_excluded_true(self):
        """Excluded vuln type returns True."""
        from python.phase09_bounty.bounty_context import BountyPolicy
        from python.phase09_bounty.scope_rules import is_vuln_type_excluded

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test",
            in_scope_assets=frozenset(),
            excluded_assets=frozenset(),
            accepted_vuln_types=frozenset({"XSS"}),
            excluded_vuln_types=frozenset({"Self-XSS"}),
            active=True,
            require_proof_of_concept=False
        )
        assert is_vuln_type_excluded("Self-XSS", policy) is True

    def test_is_asset_excluded_true(self):
        """Excluded asset returns True."""
        from python.phase09_bounty.bounty_context import BountyPolicy
        from python.phase09_bounty.scope_rules import is_asset_excluded

        policy = BountyPolicy(
            policy_id="POL-001",
            policy_name="Test",
            in_scope_assets=frozenset({"*.example.com"}),
            excluded_assets=frozenset({"staging.example.com"}),
            accepted_vuln_types=frozenset(),
            excluded_vuln_types=frozenset(),
            active=True,
            require_proof_of_concept=False
        )
        assert is_asset_excluded("staging.example.com", policy) is True


class TestDeterminism:
    """Test same input → same output."""

    def test_same_context_same_result(self):
        """Same context always produces same result."""
        from python.phase09_bounty.bounty_types import ScopeResult
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.scope_rules import evaluate_scope

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
            submission_id="SUB-011",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter=None,
            root_cause_hash="efg123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()
        )

        result1 = evaluate_scope(context)
        result2 = evaluate_scope(context)
        result3 = evaluate_scope(context)

        assert result1 == result2 == result3 == ScopeResult.IN_SCOPE


class TestNoForbiddenImports:
    """Test no forbidden imports in scope_rules module."""

    def test_no_os_import(self):
        """No os import in scope_rules."""
        import python.phase09_bounty.scope_rules as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_subprocess_import(self):
        """No subprocess import in scope_rules."""
        import python.phase09_bounty.scope_rules as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_socket_import(self):
        """No socket import in scope_rules."""
        import python.phase09_bounty.scope_rules as module
        import inspect
        source = inspect.getsource(module)
        assert 'import socket' not in source

    def test_no_phase10_import(self):
        """No phase10+ imports in scope_rules."""
        import python.phase09_bounty.scope_rules as module
        import inspect
        source = inspect.getsource(module)
        assert 'phase10' not in source
        assert 'phase11' not in source
