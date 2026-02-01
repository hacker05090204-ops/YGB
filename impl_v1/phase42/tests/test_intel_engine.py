# Phase-42 Tests
import pytest
from impl_v1.phase42.intel_types import *
from impl_v1.phase42.intel_engine import *


class TestEnumClosure:
    def test_target_priority_5(self): assert len(TargetPriority) == 5
    def test_tech_age_5(self): assert len(TechAge) == 5
    def test_bug_density_5(self): assert len(BugDensity) == 5
    def test_scope_status_5(self): assert len(ScopeStatus) == 5
    def test_intelligence_confidence_4(self): assert len(IntelligenceConfidence) == 4


class TestTechAge:
    def test_legacy(self): assert estimate_tech_age(15) == TechAge.LEGACY
    def test_mature(self): assert estimate_tech_age(7) == TechAge.MATURE
    def test_modern(self): assert estimate_tech_age(3) == TechAge.MODERN
    def test_recent(self): assert estimate_tech_age(1) == TechAge.RECENT
    def test_unknown(self): assert estimate_tech_age(-1) == TechAge.UNKNOWN


class TestBugDensity:
    def test_very_high(self): assert estimate_bug_density(15.0) == BugDensity.VERY_HIGH
    def test_high(self): assert estimate_bug_density(7.0) == BugDensity.HIGH
    def test_medium(self): assert estimate_bug_density(3.0) == BugDensity.MEDIUM
    def test_low(self): assert estimate_bug_density(1.0) == BugDensity.LOW
    def test_unknown(self): assert estimate_bug_density(-1.0) == BugDensity.UNKNOWN


class TestPriority:
    def test_out_of_scope_skip(self):
        assert calculate_priority(TechAge.LEGACY, BugDensity.HIGH, ScopeStatus.OUT_OF_SCOPE) == TargetPriority.SKIP
    
    def test_legacy_high_critical(self):
        assert calculate_priority(TechAge.LEGACY, BugDensity.HIGH, ScopeStatus.IN_SCOPE) == TargetPriority.CRITICAL
    
    def test_mature_high(self):
        assert calculate_priority(TechAge.MATURE, BugDensity.HIGH, ScopeStatus.IN_SCOPE) == TargetPriority.HIGH
    
    def test_modern_medium(self):
        assert calculate_priority(TechAge.MODERN, BugDensity.MEDIUM, ScopeStatus.IN_SCOPE) == TargetPriority.MEDIUM
    
    def test_recent_low(self):
        assert calculate_priority(TechAge.RECENT, BugDensity.LOW, ScopeStatus.IN_SCOPE) == TargetPriority.LOW


class TestProfile:
    def test_create_profile(self):
        p = create_target_profile("T-001", 12, 8.0, ScopeStatus.IN_SCOPE)
        assert p.target_id == "T-001"
        assert p.tech_age == TechAge.LEGACY
        assert p.priority == TargetPriority.CRITICAL


class TestScopeChange:
    def test_track_change(self):
        change = track_scope_change("T-001", ScopeStatus.IN_SCOPE, ScopeStatus.OUT_OF_SCOPE, "removed")
        assert change.change_id.startswith("SCH-")
        assert change.old_status == ScopeStatus.IN_SCOPE


class TestQuery:
    def test_query_no_profile(self):
        result = query_intelligence("T-001", {})
        assert result.confidence == IntelligenceConfidence.NONE
    
    def test_query_out_of_scope(self):
        profile = create_target_profile("T-001", 5, 3.0, ScopeStatus.OUT_OF_SCOPE)
        result = query_intelligence("T-001", {"T-001": profile})
        assert "OUT OF SCOPE" in result.recommendation
    
    def test_query_in_scope(self):
        profile = create_target_profile("T-001", 12, 8.0, ScopeStatus.IN_SCOPE)
        result = query_intelligence("T-001", {"T-001": profile})
        assert "Priority" in result.recommendation
