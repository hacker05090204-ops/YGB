# test_g14_target_discovery.py
"""Tests for G14: Target Discovery Assistant"""

import pytest
from unittest.mock import patch

import impl_v1.phase49.governors.g14_target_discovery as target_discovery

from impl_v1.phase49.governors.g14_target_discovery import (
    DiscoverySource,
    PayoutTier,
    ReportDensity,
    TargetCandidate,
    DiscoveryResult,
    TargetValidator,
    discover_targets,
    get_high_value_targets,
    get_discovery_stats,
    can_discovery_trigger_execution,
    clear_discovery_state,
    validate_candidate,
)


def _build_program(
    *,
    name="Example Program",
    scope="example.com",
    target_url="https://example.com",
    payout="HIGH",
    density="LOW",
    public=True,
    invite=False,
    source="HACKERONE_PUBLIC",
    discovery_method="SECURITY_TXT",
    confidence=0.92,
):
    return {
        "name": name,
        "source": source,
        "scope": scope,
        "target_url": target_url,
        "payout": payout,
        "density": density,
        "public": public,
        "invite": invite,
        "discovery_method": discovery_method,
        "confidence": confidence,
    }


@pytest.fixture(autouse=True)
def reset_discovery_state():
    clear_discovery_state()
    yield
    clear_discovery_state()


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

    def test_wildcard_scope_match_works(self):
        programs = [
            _build_program(
                name="Wildcard Program",
                scope="*.example.com",
                target_url="https://api.example.com",
                discovery_method="SECURITY_TXT",
                confidence=0.81,
            )
        ]

        with patch.object(target_discovery, "_load_programs", return_value=programs):
            with patch.object(
                target_discovery.AuthorityLock,
                "is_action_allowed",
                return_value={"allowed": True, "reason": "test override"},
            ):
                result = discover_targets(scope_rules=["*.example.com"])

        assert len(result.candidates) == 1
        assert result.target_url == "https://api.example.com"
        assert result.scope_matched is True
        assert result.discovery_method == "SECURITY_TXT"
        assert result.confidence == pytest.approx(0.81)
        assert result.discovered_at

        stats = get_discovery_stats()
        assert stats["sessions_run"] == 1
        assert stats["total_targets_evaluated"] == 1
        assert stats["in_scope"] == 1
        assert stats["out_of_scope"] == 0
        assert stats["recorded_targets"] == 1

    def test_out_of_scope_targets_are_blocked(self):
        programs = [
            _build_program(
                name="Outside Scope Program",
                scope="outside.example.net",
                target_url="https://outside.example.net",
            )
        ]

        with patch.object(target_discovery, "_load_programs", return_value=programs):
            with patch.object(
                target_discovery.AuthorityLock,
                "is_action_allowed",
                return_value={"allowed": True, "reason": "test override"},
            ):
                result = discover_targets(scope_rules=["*.example.com"])

        assert result.candidates == tuple()
        assert result.scope_matched is False
        assert result.target_url == ""

        stats = get_discovery_stats()
        assert stats["sessions_run"] == 1
        assert stats["total_targets_evaluated"] == 1
        assert stats["in_scope"] == 0
        assert stats["out_of_scope"] == 1
        assert stats["recorded_targets"] == 0

    def test_authority_lock_is_respected(self):
        programs = [
            _build_program(
                name="In Scope Program",
                scope="api.example.com",
                target_url="https://api.example.com",
            )
        ]

        with patch.object(target_discovery, "_load_programs", return_value=programs):
            with patch.object(
                target_discovery.AuthorityLock,
                "is_action_allowed",
                return_value={"allowed": False, "reason": "PERMANENTLY_BLOCKED: target_company"},
            ):
                result = discover_targets(scope_rules=["api.example.com"])

        assert result.candidates == tuple()

        stats = get_discovery_stats()
        assert stats["sessions_run"] == 1
        assert stats["total_targets_evaluated"] == 1
        assert stats["in_scope"] == 1
        assert stats["out_of_scope"] == 0
        assert stats["recorded_targets"] == 0
        assert stats["authority_blocked"] == 1


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


class TestTargetValidator:
    def test_validate_scope_supports_real_wildcards(self):
        assert TargetValidator.validate_scope("https://app.example.com", ["*.example.com"]) is True

    def test_validate_scope_does_not_match_apex_for_wildcard(self):
        assert TargetValidator.validate_scope("https://example.com", ["*.example.com"]) is False


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
