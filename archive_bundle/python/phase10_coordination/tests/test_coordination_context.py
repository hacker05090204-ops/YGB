"""
Tests for Phase-10 Coordination Context.

Tests:
- TargetID dataclass
- CoordinationPolicy dataclass
- WorkClaimContext dataclass
- Immutability verification
- Target ID creation
"""
import pytest


class TestTargetID:
    """Test TargetID dataclass."""

    def test_target_id_is_frozen(self):
        """TargetID must be frozen (immutable)."""
        from python.phase10_coordination.coordination_context import TargetID

        target = TargetID(
            program_id="PROG-001",
            asset_id="example.com",
            vulnerability_class="XSS",
            target_hash="abc123"
        )

        with pytest.raises(Exception):
            target.program_id = "MODIFIED"

    def test_target_id_has_all_fields(self):
        """TargetID has required fields."""
        from python.phase10_coordination.coordination_context import TargetID

        target = TargetID(
            program_id="PROG-001",
            asset_id="example.com",
            vulnerability_class="XSS",
            target_hash="abc123"
        )

        assert target.program_id == "PROG-001"
        assert target.asset_id == "example.com"
        assert target.vulnerability_class == "XSS"
        assert target.target_hash == "abc123"


class TestCoordinationPolicy:
    """Test CoordinationPolicy dataclass."""

    def test_policy_is_frozen(self):
        """CoordinationPolicy must be frozen."""
        from python.phase10_coordination.coordination_context import CoordinationPolicy

        policy = CoordinationPolicy(
            policy_id="POL-001",
            claim_duration_seconds=86400,
            allow_reclaim_after_expiry=True,
            active=True
        )

        with pytest.raises(Exception):
            policy.claim_duration_seconds = 0

    def test_policy_has_all_fields(self):
        """CoordinationPolicy has required fields."""
        from python.phase10_coordination.coordination_context import CoordinationPolicy

        policy = CoordinationPolicy(
            policy_id="POL-001",
            claim_duration_seconds=86400,
            allow_reclaim_after_expiry=True,
            active=True
        )

        assert policy.policy_id == "POL-001"
        assert policy.claim_duration_seconds == 86400
        assert policy.allow_reclaim_after_expiry is True
        assert policy.active is True


class TestWorkClaimContext:
    """Test WorkClaimContext dataclass."""

    def test_context_is_frozen(self):
        """WorkClaimContext must be frozen."""
        from python.phase10_coordination.coordination_types import ClaimAction
        from python.phase10_coordination.coordination_context import (
            TargetID, CoordinationPolicy, WorkClaimContext
        )

        target = TargetID("PROG-001", "example.com", "XSS", "hash123")
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

        with pytest.raises(Exception):
            context.researcher_id = "MODIFIED"


class TestCreateTargetID:
    """Test create_target_id function."""

    def test_creates_target_with_hash(self):
        """create_target_id produces TargetID with hash."""
        from python.phase10_coordination.coordination_context import create_target_id

        target = create_target_id("PROG-001", "example.com", "XSS")

        assert target.program_id == "PROG-001"
        assert target.asset_id == "example.com"
        assert target.vulnerability_class == "XSS"
        assert len(target.target_hash) > 0

    def test_same_inputs_same_hash(self):
        """Same inputs produce same hash (determinism)."""
        from python.phase10_coordination.coordination_context import create_target_id

        target1 = create_target_id("PROG-001", "example.com", "XSS")
        target2 = create_target_id("PROG-001", "example.com", "XSS")

        assert target1.target_hash == target2.target_hash

    def test_different_inputs_different_hash(self):
        """Different inputs produce different hash."""
        from python.phase10_coordination.coordination_context import create_target_id

        target1 = create_target_id("PROG-001", "example.com", "XSS")
        target2 = create_target_id("PROG-001", "example.com", "SQLi")

        assert target1.target_hash != target2.target_hash

    def test_empty_program_id(self):
        """Empty program_id still produces hash."""
        from python.phase10_coordination.coordination_context import create_target_id

        target = create_target_id("", "example.com", "XSS")
        assert len(target.target_hash) > 0


class TestNoForbiddenImports:
    """Test no forbidden imports in context module."""

    def test_no_os_import(self):
        """No os import in coordination_context."""
        import python.phase10_coordination.coordination_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import os' not in source

    def test_no_subprocess_import(self):
        """No subprocess import."""
        import python.phase10_coordination.coordination_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'import subprocess' not in source

    def test_no_phase11_import(self):
        """No phase11+ imports."""
        import python.phase10_coordination.coordination_context as module
        import inspect
        source = inspect.getsource(module)
        assert 'phase11' not in source
