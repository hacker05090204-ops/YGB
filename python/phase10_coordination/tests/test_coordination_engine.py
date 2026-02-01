"""
Tests for Phase-10 Coordination Engine.

Tests:
- Claim operations
- Release operations
- Duplicate prevention
- Expiry logic
- Deny-by-default
- Human override path
- Determinism
"""
import pytest


class TestClaimTarget:
    """Test claim_target function."""

    def test_claim_unclaimed_target_granted(self):
        """Claiming unclaimed target is granted."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            TargetID, CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)
        context = WorkClaimContext(
            request_id="REQ-001",
            target=target,
            researcher_id="RES-001",
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset(),
            claim_owners={}
        )

        result = claim_target(context)
        assert result.granted is True
        assert result.status == WorkClaimStatus.CLAIMED
        assert result.reason_code == "CL-001"

    def test_claim_already_claimed_by_self_denied(self):
        """Claiming target already claimed by self is denied."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            TargetID, CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)
        context = WorkClaimContext(
            request_id="REQ-002",
            target=target,
            researcher_id="RES-001",
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset({target.target_hash}),
            claim_owners={target.target_hash: "RES-001"}
        )

        result = claim_target(context)
        assert result.granted is False
        assert result.status == WorkClaimStatus.DENIED
        assert "DN-001" in result.reason_code

    def test_claim_owned_by_another_denied(self):
        """Claiming target owned by another is denied."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            TargetID, CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)
        context = WorkClaimContext(
            request_id="REQ-003",
            target=target,
            researcher_id="RES-002",  # Different researcher
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset({target.target_hash}),
            claim_owners={target.target_hash: "RES-001"}  # Owned by RES-001
        )

        result = claim_target(context)
        assert result.granted is False
        assert result.status == WorkClaimStatus.DENIED
        assert "DN-002" in result.reason_code


class TestReleaseClaim:
    """Test release_claim function."""

    def test_release_own_claim_success(self):
        """Releasing own claim succeeds."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            TargetID, CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import release_claim

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)
        context = WorkClaimContext(
            request_id="REQ-004",
            target=target,
            researcher_id="RES-001",
            action=ClaimAction.RELEASE,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset({target.target_hash}),
            claim_owners={target.target_hash: "RES-001"}
        )

        result = release_claim(context)
        assert result.granted is True
        assert result.status == WorkClaimStatus.RELEASED
        assert result.reason_code == "RL-001"

    def test_release_nothing_to_release_denied(self):
        """Releasing non-existent claim denied."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            TargetID, CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import release_claim

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)
        context = WorkClaimContext(
            request_id="REQ-005",
            target=target,
            researcher_id="RES-001",
            action=ClaimAction.RELEASE,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset(),  # No claims
            claim_owners={}
        )

        result = release_claim(context)
        assert result.granted is False
        assert result.status == WorkClaimStatus.DENIED
        assert "DN-005" in result.reason_code

    def test_release_not_your_claim_denied(self):
        """Releasing another's claim denied."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            TargetID, CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import release_claim

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)
        context = WorkClaimContext(
            request_id="REQ-006",
            target=target,
            researcher_id="RES-002",  # Not the owner
            action=ClaimAction.RELEASE,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset({target.target_hash}),
            claim_owners={target.target_hash: "RES-001"}  # Owned by RES-001
        )

        result = release_claim(context)
        assert result.granted is False
        assert result.status == WorkClaimStatus.DENIED
        assert "DN-006" in result.reason_code


class TestDuplicatePrevention:
    """Test duplicate prevention across users."""

    def test_different_users_cannot_claim_same_target(self):
        """Different users cannot claim same target simultaneously."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)

        # Second user tries to claim
        context = WorkClaimContext(
            request_id="REQ-007",
            target=target,
            researcher_id="RES-002",
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset({target.target_hash}),
            claim_owners={target.target_hash: "RES-001"}
        )

        result = claim_target(context)
        assert result.granted is False

    def test_different_users_get_different_targets(self):
        """Different users can claim different targets."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target1 = create_target_id("PROG-001", "example.com", "XSS")
        target2 = create_target_id("PROG-001", "api.example.com", "SQLi")
        policy = CoordinationPolicy("POL-001", 86400, True, True)

        # User 2 claims different target
        context = WorkClaimContext(
            request_id="REQ-008",
            target=target2,
            researcher_id="RES-002",
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset({target1.target_hash}),
            claim_owners={target1.target_hash: "RES-001"}
        )

        result = claim_target(context)
        assert result.granted is True


class TestExpiryLogic:
    """Test time-based lock expiry."""

    def test_is_claim_expired_false_when_active(self):
        """Claim within duration is not expired."""
        from python.phase10_coordination.coordination_engine import is_claim_expired

        # Claim 1 hour ago, duration 24 hours
        result = is_claim_expired(
            claim_timestamp="2026-01-24T09:00:00Z",
            current_time="2026-01-24T10:00:00Z",
            duration_seconds=86400
        )
        assert result is False

    def test_is_claim_expired_true_when_past_duration(self):
        """Claim past duration is expired."""
        from python.phase10_coordination.coordination_engine import is_claim_expired

        # Claim 25 hours ago, duration 24 hours
        result = is_claim_expired(
            claim_timestamp="2026-01-23T09:00:00Z",
            current_time="2026-01-24T10:00:00Z",
            duration_seconds=86400
        )
        assert result is True

    def test_expired_claim_reclaimable(self):
        """Expired claim can be reclaimed."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)

        # New user claims expired target
        context = WorkClaimContext(
            request_id="REQ-009",
            target=target,
            researcher_id="RES-002",
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-25T12:00:00Z",  # 25+ hours later
            policy=policy,
            existing_claims=frozenset({target.target_hash}),
            claim_owners={target.target_hash: "RES-001"},
            claim_timestamps={target.target_hash: "2026-01-24T10:00:00Z"}
        )

        result = claim_target(context)
        # Should be granted because prior claim expired
        assert result.granted is True
        assert result.reason_code == "CL-002"


class TestDenyByDefault:
    """Test deny-by-default behavior."""

    def test_inactive_policy_denied(self):
        """Inactive policy results in denial."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, False)  # INACTIVE

        context = WorkClaimContext(
            request_id="REQ-010",
            target=target,
            researcher_id="RES-001",
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset(),
            claim_owners={}
        )

        result = claim_target(context)
        assert result.granted is False
        assert "DN-004" in result.reason_code


class TestWorkClaimResult:
    """Test WorkClaimResult dataclass."""

    def test_result_is_frozen(self):
        """WorkClaimResult must be frozen."""
        from python.phase10_coordination.coordination_types import WorkClaimStatus
        from python.phase10_coordination.coordination_engine import WorkClaimResult

        result = WorkClaimResult(
            request_id="REQ-001",
            target_hash="hash123",
            status=WorkClaimStatus.CLAIMED,
            granted=True,
            reason_code="CL-001",
            reason_description="Claim granted",
            claim_expiry="2026-01-25T10:00:00Z",
            owner_id="RES-001"
        )

        with pytest.raises(Exception):
            result.granted = False


class TestDeterminism:
    """Test same input → same output."""

    def test_same_context_same_result(self):
        """Same context produces same result."""
        from python.phase10_coordination.coordination_types import ClaimAction
        from python.phase10_coordination.coordination_context import (
            CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)
        context = WorkClaimContext(
            request_id="REQ-011",
            target=target,
            researcher_id="RES-001",
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-24T10:00:00Z",
            policy=policy,
            existing_claims=frozenset(),
            claim_owners={}
        )

        result1 = claim_target(context)
        result2 = claim_target(context)
        result3 = claim_target(context)

        assert result1.granted == result2.granted == result3.granted
        assert result1.reason_code == result2.reason_code == result3.reason_code


class TestNoForbiddenImports:
    """Test no forbidden imports in engine module."""

    def test_no_os_import(self):
        """No os import in coordination_engine."""
        import python.phase10_coordination.coordination_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase10_coordination.coordination_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_asyncio_import(self):
        """No asyncio import."""
        import python.phase10_coordination.coordination_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import asyncio' not in source

    def test_no_threading_import(self):
        """No threading import."""
        import python.phase10_coordination.coordination_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'import threading' not in source

    def test_no_phase11_import(self):
        """No phase11+ imports."""
        import python.phase10_coordination.coordination_engine as module
        import inspect
        source = inspect.getsource(module)
        assert 'phase11' not in source


class TestInvalidTimestampHandling:
    """Test invalid timestamp handling in expiry check."""

    def test_invalid_claim_timestamp_treated_as_expired(self):
        """Invalid claim timestamp is treated as expired."""
        from python.phase10_coordination.coordination_engine import is_claim_expired

        result = is_claim_expired(
            claim_timestamp="invalid-timestamp",
            current_time="2026-01-24T10:00:00Z",
            duration_seconds=86400
        )
        assert result is True

    def test_invalid_current_timestamp_treated_as_expired(self):
        """Invalid current timestamp is treated as expired."""
        from python.phase10_coordination.coordination_engine import is_claim_expired

        result = is_claim_expired(
            claim_timestamp="2026-01-24T10:00:00Z",
            current_time="not-a-timestamp",
            duration_seconds=86400
        )
        assert result is True


class TestSelfReclaimAfterExpiry:
    """Test self-reclaim after own claim expired."""

    def test_self_reclaim_after_own_expiry(self):
        """Same researcher can reclaim after their own claim expired."""
        from python.phase10_coordination.coordination_types import ClaimAction, WorkClaimStatus
        from python.phase10_coordination.coordination_context import (
            CoordinationPolicy, WorkClaimContext, create_target_id
        )
        from python.phase10_coordination.coordination_engine import claim_target

        target = create_target_id("PROG-001", "example.com", "XSS")
        policy = CoordinationPolicy("POL-001", 86400, True, True)

        # Same researcher reclaims after their own claim expired
        context = WorkClaimContext(
            request_id="REQ-012",
            target=target,
            researcher_id="RES-001",  # Same researcher
            action=ClaimAction.CLAIM,
            request_timestamp="2026-01-25T12:00:00Z",  # 26+ hours later
            policy=policy,
            existing_claims=frozenset({target.target_hash}),
            claim_owners={target.target_hash: "RES-001"},  # Owned by same researcher
            claim_timestamps={target.target_hash: "2026-01-24T10:00:00Z"}
        )

        result = claim_target(context)
        assert result.granted is True
        assert result.reason_code == "CL-002"


class TestCheckClaimStatus:
    """Test check_claim_status function."""

    def test_unclaimed_target(self):
        """Unclaimed target returns UNCLAIMED."""
        from python.phase10_coordination.coordination_types import WorkClaimStatus
        from python.phase10_coordination.coordination_engine import check_claim_status

        result = check_claim_status(
            target_hash="hash123",
            existing_claims=frozenset(),
            claim_timestamps={},
            current_time="2026-01-24T10:00:00Z",
            policy_duration=86400
        )
        assert result == WorkClaimStatus.UNCLAIMED

    def test_claimed_target_not_expired(self):
        """Claimed target that is not expired returns CLAIMED."""
        from python.phase10_coordination.coordination_types import WorkClaimStatus
        from python.phase10_coordination.coordination_engine import check_claim_status

        result = check_claim_status(
            target_hash="hash123",
            existing_claims=frozenset({"hash123"}),
            claim_timestamps={"hash123": "2026-01-24T09:00:00Z"},
            current_time="2026-01-24T10:00:00Z",
            policy_duration=86400
        )
        assert result == WorkClaimStatus.CLAIMED

    def test_claimed_target_expired(self):
        """Claimed target that is expired returns EXPIRED."""
        from python.phase10_coordination.coordination_types import WorkClaimStatus
        from python.phase10_coordination.coordination_engine import check_claim_status

        result = check_claim_status(
            target_hash="hash123",
            existing_claims=frozenset({"hash123"}),
            claim_timestamps={"hash123": "2026-01-23T09:00:00Z"},
            current_time="2026-01-24T10:00:00Z",
            policy_duration=86400
        )
        assert result == WorkClaimStatus.EXPIRED

    def test_claimed_target_no_timestamp(self):
        """Claimed target with no timestamp returns CLAIMED."""
        from python.phase10_coordination.coordination_types import WorkClaimStatus
        from python.phase10_coordination.coordination_engine import check_claim_status

        result = check_claim_status(
            target_hash="hash123",
            existing_claims=frozenset({"hash123"}),
            claim_timestamps={},  # No timestamp for this hash
            current_time="2026-01-24T10:00:00Z",
            policy_duration=86400
        )
        assert result == WorkClaimStatus.CLAIMED

