"""
Tests for Phase-11 Delegation Rules.

Tests:
- Delegation requires explicit consent
- Role-based delegation authority
- System cannot delegate
- Human override always allowed
"""
import pytest


class TestDelegationBasics:
    """Test basic delegation rules."""

    def test_human_can_delegate_without_consent(self):
        """Human can delegate without explicit consent."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        from python.phase11_scheduling.scheduling_context import DelegationContext
        from python.phase11_scheduling.scheduling_engine import delegate_work

        context = DelegationContext(
            request_id="REQ-001",
            delegator_role="HUMAN",
            target_owner_id="W-001",
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=False
        )

        result = delegate_work(context)
        assert result == DelegationDecision.ALLOWED

    def test_operator_own_target_can_delegate(self):
        """Operator can delegate their own target."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        from python.phase11_scheduling.scheduling_context import DelegationContext
        from python.phase11_scheduling.scheduling_engine import delegate_work

        context = DelegationContext(
            request_id="REQ-002",
            delegator_role="OPERATOR",
            target_owner_id="W-001",  # Delegator is owner
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=False  # Still works for own targets
        )

        # Delegator must match owner
        context_with_delegator = DelegationContext(
            request_id="REQ-002",
            delegator_role="OPERATOR",
            target_owner_id="OPERATOR",  # Match
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=False
        )

        result = delegate_work(context_with_delegator)
        assert result == DelegationDecision.ALLOWED


class TestDelegationConsentRequired:
    """Test delegation consent requirements."""

    def test_operator_other_target_needs_consent(self):
        """Operator delegating other's target needs consent."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        from python.phase11_scheduling.scheduling_context import DelegationContext
        from python.phase11_scheduling.scheduling_engine import delegate_work

        context = DelegationContext(
            request_id="REQ-003",
            delegator_role="OPERATOR",
            target_owner_id="W-001",  # Different from delegator
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=False  # No consent
        )

        result = delegate_work(context)
        assert result == DelegationDecision.DENIED_NO_CONSENT

    def test_operator_with_consent_allowed(self):
        """Operator with explicit consent can delegate."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        from python.phase11_scheduling.scheduling_context import DelegationContext
        from python.phase11_scheduling.scheduling_engine import delegate_work

        context = DelegationContext(
            request_id="REQ-004",
            delegator_role="OPERATOR",
            target_owner_id="W-001",
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=True  # Has consent
        )

        result = delegate_work(context)
        assert result == DelegationDecision.ALLOWED


class TestSystemCannotDelegate:
    """Test system cannot delegate."""

    def test_system_delegation_denied(self):
        """System cannot delegate, always denied."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        from python.phase11_scheduling.scheduling_context import DelegationContext
        from python.phase11_scheduling.scheduling_engine import delegate_work

        context = DelegationContext(
            request_id="REQ-005",
            delegator_role="SYSTEM",
            target_owner_id="W-001",
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=True  # Even with consent
        )

        result = delegate_work(context)
        assert result == DelegationDecision.DENIED_SYSTEM_DELEGATION


class TestAdministratorAuthority:
    """Test administrator delegation authority."""

    def test_administrator_can_delegate(self):
        """Administrator can always delegate."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        from python.phase11_scheduling.scheduling_context import DelegationContext
        from python.phase11_scheduling.scheduling_engine import delegate_work

        context = DelegationContext(
            request_id="REQ-006",
            delegator_role="ADMINISTRATOR",
            target_owner_id="W-001",
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=False
        )

        result = delegate_work(context)
        assert result == DelegationDecision.ALLOWED


class TestUnknownRoleDenied:
    """Test unknown role is denied by default."""

    def test_unknown_role_denied(self):
        """Unknown role results in denial."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        from python.phase11_scheduling.scheduling_context import DelegationContext
        from python.phase11_scheduling.scheduling_engine import delegate_work

        context = DelegationContext(
            request_id="REQ-007",
            delegator_role="UNKNOWN_ROLE",
            target_owner_id="W-001",
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=True
        )

        result = delegate_work(context)
        assert result == DelegationDecision.DENIED_NO_CONSENT


class TestMediumLoadHighDifficulty:
    """Test medium load + high difficulty queued."""

    def test_medium_load_high_difficulty_queued(self):
        """Medium load worker with high difficulty target gets queued."""
        from python.phase11_scheduling.scheduling_types import WorkSlotStatus
        from python.phase11_scheduling.scheduling_context import (
            WorkerProfile, WorkTarget, SchedulingPolicy, WorkAssignmentContext
        )
        from python.phase11_scheduling.scheduling_engine import assign_work

        worker = WorkerProfile(
            worker_id="W-001", worker_type="standard",
            max_parallel=10, has_gpu=False, gpu_memory_gb=0, active=True
        )
        target = WorkTarget(
            target_id="T-001", difficulty="high",
            requires_gpu=False, min_gpu_memory_gb=0
        )
        policy = SchedulingPolicy(
            policy_id="POL-001", light_load_threshold=2,
            medium_load_threshold=5, allow_gpu_override=False, active=True
        )
        # Worker has 4 assignments (medium load)
        context = WorkAssignmentContext(
            request_id="REQ-008", worker=worker, target=target,
            policy=policy, current_assignments=frozenset({"a", "b", "c", "d"}),
            team_assignments=frozenset()
        )

        result = assign_work(context)
        assert result.status == WorkSlotStatus.QUEUED
        assert "AS-002" in result.reason_code


class TestDelegationContextFrozen:
    """Test DelegationContext immutability."""

    def test_delegation_context_is_frozen(self):
        """DelegationContext is frozen."""
        from python.phase11_scheduling.scheduling_context import DelegationContext

        context = DelegationContext(
            request_id="REQ-001",
            delegator_role="HUMAN",
            target_owner_id="W-001",
            new_owner_id="W-002",
            target_id="T-001",
            explicit_consent=True
        )

        with pytest.raises(Exception):
            context.explicit_consent = False


class TestDelegationDecisionEnum:
    """Test DelegationDecision enum."""

    def test_has_allowed(self):
        """Has ALLOWED member."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        assert hasattr(DelegationDecision, 'ALLOWED')

    def test_has_denied_no_consent(self):
        """Has DENIED_NO_CONSENT member."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        assert hasattr(DelegationDecision, 'DENIED_NO_CONSENT')

    def test_has_denied_system(self):
        """Has DENIED_SYSTEM_DELEGATION member."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        assert hasattr(DelegationDecision, 'DENIED_SYSTEM_DELEGATION')

    def test_exactly_five_members(self):
        """DelegationDecision has exactly 5 members."""
        from python.phase11_scheduling.scheduling_types import DelegationDecision
        assert len(DelegationDecision) == 5
