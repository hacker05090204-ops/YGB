# Phase-40 Additional Coverage Tests
"""Additional tests for full coverage."""

import pytest

from impl_v1.phase40.authority_types import (
    AuthorityLevel,
    ConflictType,
    ResolutionRule,
    AuthorityDecision,
    ArbitrationState,
    AuthoritySource,
    AuthorityConflict,
)

from impl_v1.phase40.authority_engine import (
    detect_conflict,
    detect_conflicts_in_sources,
    resolve_conflict,
    arbitrate_sources,
    create_authority_audit_entry,
)


def make_source(
    source_id: str = "SRC-001",
    level: AuthorityLevel = AuthorityLevel.GOVERNOR,
    claim_type: str = "ALLOW",
    scope: str = "test-scope",
    timestamp: str = "2026-01-27T00:00:00Z"
) -> AuthoritySource:
    """Create an authority source for testing."""
    return AuthoritySource(
        source_id=source_id,
        level=level,
        claim_type=claim_type,
        scope=scope,
        timestamp=timestamp,
        context_hash="a" * 64
    )


class TestAdditionalAuthorityCoverage:
    """Additional coverage tests."""
    
    def test_interface_level(self):
        """INTERFACE authority level works."""
        source = make_source(level=AuthorityLevel.INTERFACE)
        assert source.level == AuthorityLevel.INTERFACE
    
    def test_detect_conflicts_in_multiple_sources(self):
        """Detect conflicts among multiple sources."""
        sources = [
            make_source(source_id="A", claim_type="ALLOW", scope="s"),
            make_source(source_id="B", claim_type="DENY", scope="s"),
            make_source(source_id="C", claim_type="ALLOW", scope="s"),
        ]
        
        conflicts = detect_conflicts_in_sources(sources)
        assert len(conflicts) >= 1
    
    def test_no_conflicts_different_scopes(self):
        """No conflicts with different scopes."""
        sources = [
            make_source(source_id="A", scope="scope-1", claim_type="ALLOW"),
            make_source(source_id="B", scope="scope-2", claim_type="DENY"),
        ]
        
        conflicts = detect_conflicts_in_sources(sources)
        assert len(conflicts) == 0
    
    def test_first_registered_resolution(self):
        """First registered wins when both ALLOW at same level."""
        source_a = make_source(
            source_id="A",
            level=AuthorityLevel.GOVERNOR,
            claim_type="ALLOW",
            scope="s",
            timestamp="2026-01-27T00:00:00Z"
        )
        source_b = make_source(
            source_id="B",
            level=AuthorityLevel.GOVERNOR,
            claim_type="ALLOW",
            scope="s",
            timestamp="2026-01-27T01:00:00Z"
        )
        
        # Create conflict manually since same claim type
        conflict = AuthorityConflict(
            conflict_id="CONF-TEST",
            conflict_type=ConflictType.OVERLAPPING_SCOPE,
            source_a=source_a,
            source_b=source_b,
            detected_at="2026-01-27T02:00:00Z"
        )
        
        result = resolve_conflict(conflict)
        assert result.winning_source_id == "A"
        assert result.resolution_rule == ResolutionRule.FIRST_REGISTERED
    
    def test_arbitrate_no_conflict_with_deny(self):
        """Single DENY source causes overall DENY."""
        deny = make_source(source_id="D", claim_type="DENY")
        decision, winner, results = arbitrate_sources([deny])
        assert decision == AuthorityDecision.DENY
    
    def test_audit_entry_creation(self):
        """Audit entry is created correctly."""
        source_a = make_source(source_id="A", claim_type="ALLOW")
        source_b = make_source(source_id="B", claim_type="DENY")
        
        conflict = detect_conflict(source_a, source_b)
        result = resolve_conflict(conflict)
        
        audit = create_authority_audit_entry(conflict, result, human_involved=True)
        assert audit.audit_id.startswith("AAUD-")
        assert audit.human_involved is True
    
    def test_arbitration_state_enum(self):
        """ArbitrationState enum has all values."""
        states = [
            ArbitrationState.PENDING,
            ArbitrationState.ANALYZING,
            ArbitrationState.RESOLVED,
            ArbitrationState.ESCALATED,
            ArbitrationState.ABORTED,
            ArbitrationState.TIMEOUT,
        ]
        assert len(states) == 6
    
    def test_multiple_sources_highest_wins(self):
        """Multiple sources: highest authority wins."""
        sources = [
            make_source(source_id="E", level=AuthorityLevel.EXECUTOR, claim_type="ALLOW"),
            make_source(source_id="G", level=AuthorityLevel.GOVERNANCE, claim_type="ALLOW"),
        ]
        
        decision, winner, results = arbitrate_sources(sources)
        assert decision == AuthorityDecision.GRANT
        assert winner == "G"
