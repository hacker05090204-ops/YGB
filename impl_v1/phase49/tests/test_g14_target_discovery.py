# test_g14_target_discovery.py
"""Tests for G14: Target Discovery Assistant"""

import pytest
from impl_v1.phase49.governors.g14_target_discovery import (
    DiscoverySource,
    PayoutTier,
    ReportDensity,
    TargetCandidate,
    DiscoveryResult,
    discover_targets,
    get_high_value_targets,
    can_discovery_trigger_execution,
    validate_candidate,
)


class TestEnumClosure:
    def test_discovery_source_4_members(self):
        assert len(DiscoverySource) == 4
    
    def test_payout_tier_4_members(self):
        assert len(PayoutTier) == 4
    
    def test_report_density_3_members(self):
        assert len(ReportDensity) == 3


class TestDiscoverTargets:
    def test_returns_result(self):
        result = discover_targets()
        assert isinstance(result, DiscoveryResult)
    
    def test_result_has_id(self):
        result = discover_targets()
        assert result.result_id.startswith("DIS-")
    
    def test_filters_private(self):
        result = discover_targets(public_only=True)
        for candidate in result.candidates:
            assert candidate.is_public
    
    def test_filters_invite_required(self):
        result = discover_targets()
        for candidate in result.candidates:
            assert not candidate.requires_invite


class TestGetHighValueTargets:
    def test_high_payout_only(self):
        result = get_high_value_targets()
        for candidate in result.candidates:
            assert candidate.payout_tier == PayoutTier.HIGH
    
    def test_low_density_only(self):
        result = get_high_value_targets()
        for candidate in result.candidates:
            assert candidate.report_density == ReportDensity.LOW


class TestDiscoveryCannotExecute:
    def test_cannot_trigger_execution(self):
        can, reason = can_discovery_trigger_execution()
        assert not can
        assert "read-only" in reason


class TestValidateCandidate:
    def test_valid_public_target(self):
        candidate = TargetCandidate(
            candidate_id="TGT-TEST",
            program_name="Test Corp",
            source=DiscoverySource.HACKERONE_PUBLIC,
            scope_summary="*.test.com",
            payout_tier=PayoutTier.HIGH,
            report_density=ReportDensity.LOW,
            is_public=True,
            requires_invite=False,
            discovered_at="2026-01-28T00:00:00Z",
        )
        valid, reason = validate_candidate(candidate)
        assert valid
    
    def test_invalid_private_target(self):
        candidate = TargetCandidate(
            candidate_id="TGT-TEST",
            program_name="Private Corp",
            source=DiscoverySource.HACKERONE_PUBLIC,
            scope_summary="*.private.com",
            payout_tier=PayoutTier.HIGH,
            report_density=ReportDensity.LOW,
            is_public=False,
            requires_invite=False,
            discovered_at="2026-01-28T00:00:00Z",
        )
        valid, reason = validate_candidate(candidate)
        assert not valid
        assert "not public" in reason
    
    def test_invalid_invite_required(self):
        candidate = TargetCandidate(
            candidate_id="TGT-TEST",
            program_name="Invite Corp",
            source=DiscoverySource.HACKERONE_PUBLIC,
            scope_summary="*.invite.com",
            payout_tier=PayoutTier.HIGH,
            report_density=ReportDensity.LOW,
            is_public=True,
            requires_invite=True,
            discovered_at="2026-01-28T00:00:00Z",
        )
        valid, reason = validate_candidate(candidate)
        assert not valid
        assert "invite" in reason
    
    def test_forbidden_scope_login(self):
        candidate = TargetCandidate(
            candidate_id="TGT-TEST",
            program_name="Test",
            source=DiscoverySource.HACKERONE_PUBLIC,
            scope_summary="login.example.com",
            payout_tier=PayoutTier.HIGH,
            report_density=ReportDensity.LOW,
            is_public=True,
            requires_invite=False,
            discovered_at="2026-01-28T00:00:00Z",
        )
        valid, reason = validate_candidate(candidate)
        assert not valid
        assert "forbidden" in reason
    
    def test_forbidden_scope_admin(self):
        candidate = TargetCandidate(
            candidate_id="TGT-TEST",
            program_name="Test",
            source=DiscoverySource.HACKERONE_PUBLIC,
            scope_summary="admin.example.com",
            payout_tier=PayoutTier.HIGH,
            report_density=ReportDensity.LOW,
            is_public=True,
            requires_invite=False,
            discovered_at="2026-01-28T00:00:00Z",
        )
        valid, reason = validate_candidate(candidate)
        assert not valid


class TestDataclassFrozen:
    def test_candidate_frozen(self):
        result = discover_targets()
        if result.candidates:
            candidate = result.candidates[0]
            with pytest.raises(AttributeError):
                candidate.program_name = "Modified"
    
    def test_result_frozen(self):
        result = discover_targets()
        with pytest.raises(AttributeError):
            result.total_found = 999
