"""
Tests for Phase-09 Duplicate Detection Logic.

Tests:
- Exact duplicate matching
- Non-duplicate conditions
- Precedence rules
- Self-duplicate detection
- Hash matching
"""
import pytest


class TestDuplicateCheckResult:
    """Test DuplicateCheckResult dataclass."""

    def test_result_is_frozen(self):
        """DuplicateCheckResult must be frozen (immutable)."""
        from python.phase09_bounty.bounty_engine import DuplicateCheckResult

        result = DuplicateCheckResult(
            is_duplicate=True,
            matching_submission_hash="abc123",
            match_reason="Exact hash match"
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            result.is_duplicate = False


class TestExactDuplicateMatching:
    """Test exact duplicate detection."""

    def test_exact_hash_match_is_duplicate(self):
        """Same root_cause_hash in prior submissions = duplicate."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            root_cause_hash="duplicate_hash_123",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"duplicate_hash_123"})
        )

        result = check_duplicate(context)
        assert result.is_duplicate is True
        assert result.matching_submission_hash == "duplicate_hash_123"

    def test_no_match_not_duplicate(self):
        """Different root_cause_hash = not duplicate."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            submission_id="SUB-002",
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter="q",
            root_cause_hash="new_unique_hash",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"other_hash_456"})
        )

        result = check_duplicate(context)
        assert result.is_duplicate is False
        assert result.matching_submission_hash is None


class TestNonDuplicateConditions:
    """Test non-duplicate conditions."""

    def test_empty_prior_hashes_not_duplicate(self):
        """Empty prior submissions = not duplicate (first submission)."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            affected_parameter="q",
            root_cause_hash="first_submission",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset()  # EMPTY
        )

        result = check_duplicate(context)
        assert result.is_duplicate is False

    def test_different_hash_not_duplicate(self):
        """Different root cause hash = not duplicate."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            target_asset="example.com",
            vulnerability_type="XSS",
            affected_parameter="q",
            root_cause_hash="hash_A",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"hash_B", "hash_C", "hash_D"})
        )

        result = check_duplicate(context)
        assert result.is_duplicate is False


class TestSelfDuplicate:
    """Test self-duplicate detection."""

    def test_same_researcher_same_hash(self):
        """Same researcher, same hash = duplicate (self-duplicate)."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            root_cause_hash="self_dup_hash",
            researcher_id="RES-001",  # Same researcher
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"self_dup_hash"})  # Same hash
        )

        result = check_duplicate(context)
        assert result.is_duplicate is True


class TestMultiplePriorSubmissions:
    """Test with multiple prior submissions."""

    def test_match_in_multiple_priors(self):
        """Hash matches one of multiple prior submissions."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            affected_parameter="q",
            root_cause_hash="hash_B",  # Matches one prior
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"hash_A", "hash_B", "hash_C"})
        )

        result = check_duplicate(context)
        assert result.is_duplicate is True
        assert result.matching_submission_hash == "hash_B"


class TestDuplicateMatchReason:
    """Test match reason is provided."""

    def test_match_reason_populated(self):
        """Match reason is populated for duplicates."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            affected_parameter="q",
            root_cause_hash="dup_reason_hash",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"dup_reason_hash"})
        )

        result = check_duplicate(context)
        assert result.is_duplicate is True
        assert result.match_reason is not None
        assert len(result.match_reason) > 0

    def test_no_match_reason_for_non_duplicate(self):
        """No match reason for non-duplicates."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            affected_parameter="q",
            root_cause_hash="unique_hash_999",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"other_hash"})
        )

        result = check_duplicate(context)
        assert result.is_duplicate is False
        assert result.match_reason is None


class TestDeterminism:
    """Test same input → same output."""

    def test_same_context_same_duplicate_result(self):
        """Same context always produces same duplicate result."""
        from python.phase09_bounty.bounty_context import BountyPolicy, BountyContext
        from python.phase09_bounty.bounty_engine import check_duplicate

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
            affected_parameter="q",
            root_cause_hash="determ_hash",
            researcher_id="RES-001",
            submission_timestamp="2026-01-24T10:00:00Z",
            has_proof_of_concept=True,
            policy=policy,
            prior_submission_hashes=frozenset({"determ_hash"})
        )

        result1 = check_duplicate(context)
        result2 = check_duplicate(context)
        result3 = check_duplicate(context)

        assert result1.is_duplicate == result2.is_duplicate == result3.is_duplicate
        assert result1.matching_submission_hash == result2.matching_submission_hash


class TestNoForbiddenImports:
    """Test no forbidden imports."""

    def test_no_asyncio_import(self):
        """No asyncio import in bounty_engine."""
        import python.phase09_bounty.bounty_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import asyncio' not in source

    def test_no_threading_import(self):
        """No threading import in bounty_engine."""
        import python.phase09_bounty.bounty_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import threading' not in source
